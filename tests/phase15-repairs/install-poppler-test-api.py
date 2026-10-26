"""Install the public Poppler test API only in the disposable VM RAM root."""
from pathlib import Path
import json,os,subprocess
assert os.geteuid()==0
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
assert Path('/sys/block/vda/size').read_text().strip()==str(16*1024**3//512)
subprocess.run(['/usr/local/sbin/portable-check-network-ready'],check=True,capture_output=True,timeout=30)
r=subprocess.run(['apt-get','install','-y','--no-install-recommends',
 'gir1.2-poppler-0.18=25.03.0-5+deb13u4'],env={**os.environ,'DEBIAN_FRONTEND':'noninteractive'},
 stdin=subprocess.DEVNULL,capture_output=True,timeout=180)
print(json.dumps({'test_API_install_exit':r.returncode,'disposable_RAM_only':True}))
assert r.returncode==0,'Public test API install failed; output suppressed'
