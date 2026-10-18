#!/usr/bin/env python3
"""Boot the verified release kernel without disks/network to check zeroing flags."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

PROJECT=Path(__file__).resolve().parents[1]
RELEASE=PROJECT.parent/'releases/20261012-205248-827255'


def cpio(files):
    """Create newc metadata in RAM; no host device node or privileged writer."""
    output=bytearray();inode=1
    def add(name,data=b'',mode=0o100644,major=0,minor=0):
        nonlocal inode
        encoded=name.encode()+b'\0'
        fields=[inode,mode,0,0,1,0,len(data),0,0,major,minor,len(encoded),0];inode+=1
        output.extend(b'070701'+''.join(f'{v:08x}' for v in fields).encode())
        output.extend(encoded);output.extend(b'\0'*((-len(output))%4))
        output.extend(data);output.extend(b'\0'*((-len(output))%4))
    directories={'dev','proc','sys','bin'}
    for name in files:
        directories.update(str(p) for p in Path(name).parents if str(p)!='.')
    for name in sorted(directories,key=lambda v:(v.count('/'),v)):add(name,mode=0o40755)
    add('dev/console',mode=0o20600,major=5,minor=1)
    for name,data in files.items():add(name,data,mode=0o100755)
    add('TRAILER!!!');return output


def main():
    assert os.geteuid()!=0
    kernel=RELEASE/'build/binary/live/vmlinuz'
    manifest=json.loads((RELEASE/'manifest.json').read_text())
    assert hashlib.sha256(kernel.read_bytes()).hexdigest()==manifest['binary/live/vmlinuz']['sha256']
    busybox=Path('/usr/bin/busybox')
    result=subprocess.run(['/usr/bin/ldd',str(busybox)],capture_output=True,text=True,check=True)
    libraries=set(re.findall(r'(/(?:lib|usr/lib)[^\s()]+)',result.stdout))
    assert libraries and all(p.startswith(('/lib/','/lib64/','/usr/lib/')) for p in libraries)
    files={'bin/busybox':busybox.read_bytes()}
    for library in libraries:files[library.lstrip('/')]=Path(library).read_bytes()
    files['init']=b'''#!/bin/busybox sh
/bin/busybox mount -t proc proc /proc
/bin/busybox mount -t sysfs sysfs /sys
/bin/busybox echo PETAL_MEMORY_TEST_START
/bin/busybox dmesg | /bin/busybox grep 'mem auto-init:'
/bin/busybox echo PETAL_MEMORY_TEST_DONE
/bin/busybox poweroff -f
'''
    with tempfile.TemporaryDirectory(prefix='petalos-memory-boot-',dir=f'/run/user/{os.getuid()}') as work:
        initrd=Path(work)/'public-initrd.cpio';initrd.write_bytes(cpio(files))
        result=subprocess.run(['qemu-system-x86_64','-enable-kvm','-machine','q35','-cpu','host',
            '-m','512','-smp','2','-nodefaults','-display','none','-serial','stdio','-monitor','none',
            '-no-reboot','-kernel',str(kernel),'-initrd',str(initrd),'-append',
            'console=ttyS0 rdinit=/init panic=-1 init_on_alloc=1 init_on_free=1'],
            stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=45)
    lines=[line for line in result.stdout.splitlines() if 'mem auto-init:' in line]
    if result.returncode!=0 or 'PETAL_MEMORY_TEST_DONE' not in result.stdout:
        print('Public diskless boot tail:',result.stdout[-3000:]);print('Public QEMU stderr:',result.stderr[-1000:])
    assert result.returncode==0 and 'PETAL_MEMORY_TEST_DONE' in result.stdout
    assert any('heap alloc:on' in line and 'heap free:on' in line for line in lines)
    print(json.dumps({'verified_release_kernel':True,'diskless_no_network_boot':True,
        'heap_allocation_zeroing_enabled':True,'freed_memory_zeroing_enabled':True,
        'kernel_report':next(line for line in lines if 'heap alloc:on' in line and 'heap free:on' in line)},sort_keys=True))

if __name__=='__main__':
    try:main()
    except Exception as error:
        print('Memory-zeroing boot verification failed: '+type(error).__name__,file=sys.stderr)
        raise SystemExit(1)
