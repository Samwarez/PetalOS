from pathlib import Path
import json,os,subprocess,sys
sys.path.insert(0,'/usr/local/lib/portable')
from desktop_session import environment
assert os.geteuid()==0 and subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
subprocess.run(['/usr/local/sbin/portable-check-network-ready'],check=True,capture_output=True,timeout=25)
e=environment()
r=subprocess.run(['setpriv','--reuid=1000','--regid=1000','--clear-groups','--','gdbus','introspect','--session','--dest','org.xfce.Xfconf','--object-path','/org/xfce/Xfconf'],env=e,capture_output=True,text=True,timeout=15)
print(json.dumps({'xfconf_introspection':r.stdout[-12000:],'introspection_exit':r.returncode}),flush=True)
packages=['build-essential','cmake','pkg-config','qtbase5-dev','qtbase5-private-dev','qttools5-dev','qttools5-dev-tools','libqt5svg5-dev','libqt5x11extras5-dev','libbotan-2-dev','libargon2-dev','libcurl4-gnutls-dev','libminizip-dev','libpcsclite-dev','libqrencode-dev','libreadline-dev','libusb-1.0-0-dev','libxtst-dev','libzxcvbn-dev','zlib1g-dev','strace']
log=Path('/run/petalos-keepass-build-dependencies.log')
with log.open('wb') as f:
 r=subprocess.run(['apt-get','install','-y','--no-install-recommends',*packages],env={**os.environ,'DEBIAN_FRONTEND':'noninteractive'},stdout=f,stderr=subprocess.STDOUT,timeout=480)
print(json.dumps({'guest_build_dependencies_exit':r.returncode,'public_log_tail':log.read_text(errors='replace')[-1500:] if r.returncode else 'installed in disposable RAM root'}))
assert r.returncode==0
