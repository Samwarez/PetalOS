"""Exercise the production backport hook only against the disposable RAM root."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys
assert os.geteuid()==0
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
assert Path('/sys/block/vda/size').read_text().strip()==str(16*1024**3//512)
assert 'overlay'==subprocess.check_output(['findmnt','-rn','-M','/','-o','FSTYPE'],text=True).strip()
sys.path.insert(0,'/usr/local/lib/portable');import compartments as c
fixture=Path('/tmp/petalos-security-installer')
meta=json.loads((fixture/'manifest.json').read_text())
pins=json.loads((fixture/'inputs.json').read_text())
assert hashlib.sha256((fixture/'hook.py').read_bytes()).hexdigest()==pins['hook_sha256']
assert hashlib.sha256((fixture/'manifest.json').read_bytes()).hexdigest()==pins['manifest_sha256']
before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [
 Path('/etc/polkit-1/rules.d/00-petal-admin.rules'),Path('/etc/nftables.conf'),Path('/etc/sudoers')]}
for app in ('amule','offline-atril','offline-libreoffice','offline-gthumb'):
 c.stop(app)
target=Path('/usr/local/share/portable/security-backports');target.mkdir(mode=0o755,exist_ok=False)
shutil.copyfile(fixture/'manifest.json',target/'manifest.json')
for entry in meta['packages']:
 root=Path('/tmp/petalos-security-outputs'+('' if entry['source'] in ('amule','libxml2') else '-third'))
 source=root/entry['source']/entry['file']
 assert source.is_file() and not source.is_symlink()
 with source.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==entry['sha256']
 shutil.copyfile(source,target/entry['file'])
r=subprocess.run(['python3','-I',str(fixture/'hook.py')],capture_output=True,timeout=180)
if r.returncode:
 Path('/run/petalos-security-install-public-tail.txt').write_bytes((r.stdout+r.stderr)[-20000:])
 assert False,'Backport hook failed; bounded public package output retained in guest RAM'
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==sha for p,sha in before.items())
assert Path('/usr/bin/amule').read_text().startswith('#!/bin/sh\nexec /usr/local/bin/portable-amule')
subprocess.run(['systemctl','restart','polkit.service'],check=True,capture_output=True,timeout=20)
record=json.loads(Path('/usr/share/doc/petalos/security-backports.json').read_text())
print(json.dumps({'hook_exit':r.returncode,'installed_packages':record['installed'],
 'production_policies_unchanged':True,'amule_wrapper_preserved':True,
 'no_duplicate_debs_in_OS':not list(target.glob('*.deb')),'RAM_overlay_only':True}))
