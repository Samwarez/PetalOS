"""Fetch exact trixie source packages through signed APT metadata in guest RAM."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
assert os.geteuid()==0 and subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
assert Path('/sys/block/vda/size').read_text().strip()==str(16*1024**3//512)
subprocess.run(['/usr/local/sbin/portable-check-network-ready'],check=True,capture_output=True,timeout=30)
sources=Path('/etc/apt/sources.list.d/petalos-repair-sources.sources')
assert not sources.exists()
sources.write_text('Types: deb-src\nURIs: https://deb.debian.org/debian\nSuites: trixie\nComponents: main\nSigned-By: /usr/share/keyrings/debian-archive-keyring.gpg\n\nTypes: deb-src\nURIs: https://security.debian.org/debian-security\nSuites: trixie-security\nComponents: main\nSigned-By: /usr/share/keyrings/debian-archive-keyring.gpg\n')
subprocess.run(['apt-get','update'],check=True,capture_output=True,timeout=120)
packages={'amule':'1:2.3.3-3.2','libxml2':'2.12.7+dfsg+really2.9.14-2.1+deb13u3',
 'poppler':'25.03.0-5+deb13u4','policykit-1':'126-2'}
root=Path('/tmp/petalos-security-backports');root.mkdir(mode=0o755,exist_ok=False)
report={}
for name,version in packages.items():
 folder=root/name;folder.mkdir(mode=0o700);os.chown(folder,1000,1000)
 r=subprocess.run(['setpriv','--reuid=1000','--regid=1000','--clear-groups','--','apt-get','source',
  '--download-only','--only-source',name+'='+version],cwd=folder,capture_output=True,timeout=120)
 assert r.returncode==0,'Signed source fetch failed for '+name+'; output suppressed'
 assert len(list(folder.glob('*.dsc')))==1
 report[name]={'version':version,'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()}}
print(json.dumps(report,sort_keys=True))
