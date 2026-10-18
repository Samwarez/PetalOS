from pathlib import Path
import json,os,subprocess,sys
sys.path.insert(0,'/usr/local/lib/portable')
import private_storage as p
from desktop_session import environment
v=json.load(sys.stdin);assert p.unlock(v['private'].encode(),raise_errors=True)
e=environment();prefix=['setpriv','--reuid=1000','--regid=1000','--clear-groups','--']
s=subprocess.run(prefix+['sudo','-n','--','/usr/local/sbin/portable-storage','status'],env=e,capture_output=True,text=True,check=True)
if not json.loads(s.stdout)['download_mode']:subprocess.run(prefix+['sudo','-n','--','/usr/local/sbin/portable-storage','download-toggle'],env=e,capture_output=True,check=True)
r=subprocess.run(prefix+['/usr/local/bin/portable-lock'],env=e,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=35)
print(json.dumps({'manual_lock_succeeded':r.returncode==0,'manual_lock_overrides_download_mode':not Path('/dev/mapper/portable_data').exists(),'graphical_locker_running':subprocess.run(['pgrep','-u','1000','-x','gtklock'],stdout=subprocess.DEVNULL).returncode==0}))
