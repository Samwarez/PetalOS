"""Preserve disposable guest RAM content before testing the new boot service."""
from pathlib import Path
import hashlib,json,os,stat,subprocess,sys
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
assert os.geteuid()==0
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
for app in c.ROLES:
    c.stop(app)
    c.reset_ram(app)
home=Path('/home/Petal');backup=home/'.petalos-content-before-repair'
assert not backup.exists()
backup.mkdir(mode=0o700)
categories=('Documents','Downloads')
for name in categories:
    folder=home/name
    assert not folder.is_symlink() and not os.path.ismount(folder)
    assert not any(os.path.ismount(p) for p in folder.rglob('*') if p.is_dir() and not p.is_symlink())
for name in categories:
    (home/name).rename(backup/name)
    (home/name).mkdir(mode=0o700);os.chown(home/name,1000,1000)
subprocess.run(['/usr/local/sbin/portable-ram-content-setup'],check=True,capture_output=True)
count=0
for name in categories:
    subprocess.run(['cp','-a','--',str(backup/name)+'/.',str(home/name)+'/'],check=True,capture_output=True)
    for old in (backup/name).rglob('*'):
        new=home/name/old.relative_to(backup/name)
        assert stat.S_IFMT(old.lstat().st_mode)==stat.S_IFMT(new.lstat().st_mode)
        if old.is_symlink():assert os.readlink(old)==os.readlink(new)
        elif old.is_file():
            with old.open('rb') as a,new.open('rb') as b:
                assert hashlib.file_digest(a,'sha256').digest()==hashlib.file_digest(b,'sha256').digest()
            count+=1
subprocess.run(['systemctl','daemon-reload'],check=True,capture_output=True)
subprocess.run(['systemctl','start','portable-ram-content'],check=True,capture_output=True)
print(json.dumps({'guest_ram_files_verified':count,'original_guest_ram_folders_preserved':True,
                  'new_content_service_active':True}))
