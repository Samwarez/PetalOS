"""Harmless unsigned-initrd execution test on this disposable QEMU boot disk."""
from pathlib import Path
import hashlib,json,os,shutil,stat,subprocess,tempfile
assert os.geteuid()==0
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
dev=Path('/dev/disk/by-label/PORT_BOOT').resolve();assert dev==Path('/dev/vda2')
assert Path('/sys/class/block/vda2').resolve().parent.name=='vda'
assert int(Path('/sys/class/block/vda/size').read_text())*512==16*1024**3
work=Path(tempfile.mkdtemp(prefix='phase15-boot-',dir='/run'))
subprocess.run(['mount','-o','nodev,nosuid,noexec',str(dev),str(work)],check=True,capture_output=True)
def cpio(name,data,mode):
 raw=name.encode()+b'\0'
 fields=[1,mode,0,0,1,0,len(data),0,0,0,0,len(raw),0]
 h=b'070701'+b''.join(('%08x'%v).encode() for v in fields)
 p=h+raw;p+=bytes(-len(p)%4);p+=data;p+=bytes(-len(data)%4);return p
try:
 targets=set()
 configs={}
 for p in work.rglob('grub.cfg'):
  text=p.read_text();configs[str(p.relative_to(work))]=text
  if 'live-media=/dev/mapper/portable_system' not in text:continue
  for line in text.splitlines():
   a=line.split()
   if a and a[0] in ('initrd','initrdefi'):targets.add(work/a[1].lstrip('/'))
 assert len(targets)==1
 target=targets.pop();assert not target.is_symlink()
 original=target.with_name('phase15-original-initrd.img');assert not original.exists()
 shutil.copyfile(target,original)
 with original.open('rb') as f:before=hashlib.file_digest(f,'sha256').hexdigest()
 assert before=='2625d4f7a1c7ec10a0ec156e10c62df7874e595beacde15354dfc496cbd90247'
 body=b'#!/bin/sh\ncase "$1" in prereqs) exit 0;; esac\necho PETALOS_PHASE15_UNSIGNED_INITRD_EXECUTED > /dev/kmsg\nexit 0\n'
 archive=cpio('scripts/init-top/000-phase15-marker',body,stat.S_IFREG|0o755)+cpio('TRAILER!!!',b'',0)
 archive+=bytes(-len(archive)%512)
 with target.open('ab') as f:f.write(archive);f.flush();os.fsync(f.fileno())
 os.sync()
 print(json.dumps({'original_sha256':before,'appended_bytes':len(archive),'boot_configs':configs,'test_only_disposable_disk':True}))
finally:
 subprocess.run(['umount',str(work)],check=True,capture_output=True);work.rmdir()
