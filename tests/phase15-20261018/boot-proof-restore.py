from pathlib import Path
import hashlib,json,os,subprocess,tempfile
assert os.geteuid()==0
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
dev=Path('/dev/disk/by-label/PORT_BOOT').resolve();assert dev==Path('/dev/vda2')
log=subprocess.check_output(['dmesg'],text=True)
secure=any(p.read_bytes()[-1:]==b'\1' for p in Path('/sys/firmware/efi/efivars').glob('SecureBoot-*'))
work=Path(tempfile.mkdtemp(prefix='phase15-boot-restore-',dir='/run'))
subprocess.run(['mount','-o','nodev,nosuid,noexec',str(dev),str(work)],check=True,capture_output=True)
try:
 originals=list(work.rglob('phase15-original-initrd.img'));assert len(originals)==1
 source=originals[0]
 with source.open('rb') as f:d=hashlib.file_digest(f,'sha256').hexdigest()
 assert d=='2625d4f7a1c7ec10a0ec156e10c62df7874e595beacde15354dfc496cbd90247'
 os.replace(source,source.with_name('initrd.img'));os.sync()
 print(json.dumps({'unsigned_initrd_code_executed':'PETALOS_PHASE15_UNSIGNED_INITRD_EXECUTED' in log,'SecureBoot_enabled':secure,'original_initrd_restored':True}))
finally:
 subprocess.run(['umount',str(work)],check=True,capture_output=True);work.rmdir()
