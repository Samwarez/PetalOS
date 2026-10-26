"""Install only trixie build dependencies in the disposable guest's RAM root."""
from pathlib import Path
import json,os,subprocess
assert os.geteuid()==0 and subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
assert Path('/sys/block/vda/size').read_text().strip()==str(16*1024**3//512)
subprocess.run(['/usr/local/sbin/portable-check-network-ready'],check=True,capture_output=True,timeout=30)
job=r'''from pathlib import Path
import json,os,subprocess,time
root=Path('/run/petalos-backport-deps');root.mkdir(mode=0o755,exist_ok=True)
environment={**os.environ,'DEBIAN_FRONTEND':'noninteractive'}
packages=['amule=1:2.3.3-3.2','libxml2=2.12.7+dfsg+really2.9.14-2.1+deb13u3','poppler=25.03.0-5+deb13u4','policykit-1=126-2']
status=root/'status.json'
try:
 for command in (['apt-get','build-dep','-y','--no-install-recommends',*packages],
                 ['apt-get','install','-y','--no-install-recommends','build-essential','fakeroot','qpdf','python3-debian']):
  status.write_text(json.dumps({'phase':command[1],'started':int(time.time())}))
  p=subprocess.Popen(command,env=environment,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  tail=b''
  while chunk:=p.stdout.read(65536):
   tail=(tail+chunk)[-2*1024**2:];(root/'public-apt-tail.txt').write_bytes(tail)
  assert p.wait()==0,'APT step failed'
 status.write_text(json.dumps({'phase':'complete','installed_only_in_disposable_RAM_root':True}))
except BaseException:
 status.write_text(json.dumps({'phase':'failed','inspect_bounded_public_APT_tail':True}));raise
'''
subprocess.run(['systemd-run','--unit=petalos-backport-build-deps','--property=RuntimeMaxSec=20min',
 '--property=StandardOutput=null','--property=StandardError=null','--','python3','-I','-c',job],
 check=True,capture_output=True)
print(json.dumps({'dependency_job_started':True,'bounded_status':'/run/petalos-backport-deps/status.json',
 'installed_only_in_disposable_RAM_root':True}))
