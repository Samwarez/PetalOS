from pathlib import Path
import json,os,subprocess,hashlib
assert os.geteuid()==0
def cmd(a,t=40):return subprocess.run(a,capture_output=True,text=True,timeout=t)
assert cmd(['/usr/local/sbin/portable-check-network-ready']).returncode==0
r=cmd(['apt-get','update'],180)
assert r.returncode==0,'APT update failed; output suppressed'
sim=cmd(['apt-get','-s','upgrade'],90)
changed=[l.split()[1:3] for l in sim.stdout.splitlines() if l.startswith('Inst ')]
kernel=cmd(['dpkg-query','-W','-f=${Built-Using}','linux-image-'+os.uname().release]).stdout
out={'signed_apt_refresh':True,'available_package_upgrades':changed,'kernel_built_using':kernel,'installed_count':sum(1 for l in cmd(['dpkg-query','-W','-f=${db:Status-Status}\n']).stdout.splitlines() if l=='installed'),'sources':cmd(['apt-cache','policy']).stdout[:10000]}
for app in ('parole','conky'):
 meta=json.loads((Path('/usr/local/share/portable')/('native-'+app)/'provenance.json').read_text())
 f=Path('/usr/bin')/(app+'.portable-real' if app=='parole' else app)
 out[app]={'binary_matches_provenance':hashlib.sha256(f.read_bytes()).hexdigest()==meta['binary_sha256'],'binary_sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
out['amule_sha256']=hashlib.sha256(Path('/usr/bin/amule.portable-real').read_bytes()).hexdigest()
out['amule_matches_debian_md5']=False
for l in Path('/var/lib/dpkg/info/amule.md5sums').read_text().splitlines():
 h,path=l.split()
 if path=='usr/bin/amule':out['amule_matches_debian_md5']=hashlib.md5(Path('/usr/bin/amule.portable-real').read_bytes()).hexdigest()==h
print(json.dumps(out))
