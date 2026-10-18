#!/usr/bin/env python3
"""Diskless, offline TCG regression tests with mocked network commands."""
from pathlib import Path
import os, re, shutil, subprocess, tempfile
project = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='petalos-qemu-', dir='/tmp') as tmp:
    root = Path(tmp)/'root'; root.mkdir()
    def copy(src, dest):
        target=root/dest.lstrip('/'); target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src,target)
    for exe in ('/bin/bash','/usr/bin/busybox','/usr/bin/flock'):
        copy(exe, '/bin/'+Path(exe).name)
        deps=subprocess.check_output(['ldd',exe],text=True)
        for lib in re.findall(r'(/[\w./+-]+)',deps):
            if Path(lib).is_file(): copy(lib,lib)
    for name in ('mount','mkdir','cat','rm','chmod','install','sed','grep','touch','poweroff','awk','stat','cp','mv'):
        (root/'bin'/name).symlink_to('busybox')
    copy(project/'tests/vpn-qemu-init','/init'); (root/'init').chmod(0o755)
    for name in ('systemctl','mountpoint','findmnt','nft','wg','ip','curl','wg-quick','chronyc'):
        copy(project/'tests/vpn-command-mock','/mock/'+name); (root/'mock'/name).chmod(0o755)
    for name in ('portable-vpn','portable-check-vpn'):
        copy(project/'config/includes.chroot/usr/local/sbin'/name,'/usr/local/sbin/'+name)
    # Parser/transaction behavior is exercised by separate Python/live tests.
    # This minimal initramfs continues to test shell rollback with a stub.
    copy(project/'tests/vpn-profile-mock','/usr/local/sbin/portable-vpn-profile')
    archive=Path(tmp)/'initramfs.cpio'
    with archive.open('wb') as out:
        subprocess.run(['bash','-c','find . -print0 | cpio --null -o -H newc --quiet'],cwd=root,stdout=out,check=True)
    result=subprocess.run(['qemu-system-x86_64','-accel','tcg','-m','256','-kernel',str(project/'binary/live/vmlinuz'),'-initrd',str(archive),'-append','console=ttyS0 panic=-1','-nographic','-no-reboot','-nic','none'],capture_output=True,text=True,timeout=120)
    lines=[s for s in result.stdout.splitlines() if s.startswith(('PASS:','FAIL:','QEMU_TEST_'))]
    print('\n'.join(lines))
    if 'QEMU_TEST_FAILURES=0' not in lines:
        print('Guest did not complete successfully. Last boot lines:')
        print('\n'.join(result.stdout.splitlines()[-15:]))
        raise SystemExit(1)
