"""Actual Wayland idle event and existing storage/locker paths, test credentials elsewhere."""
from pathlib import Path
import json,os,subprocess,sys,time
sys.path.insert(0,'/usr/local/lib/portable')
import private_storage as p
from desktop_session import environment
assert os.geteuid()==0 and Path('/dev/mapper/portable_data').exists()
e=environment();prefix=['setpriv','--reuid=1000','--regid=1000','--clear-groups','--']
def state():
 r=subprocess.run(prefix+['sudo','-n','--','/usr/local/sbin/portable-storage','status'],env=e,capture_output=True,text=True,check=True);return json.loads(r.stdout)
def toggle():subprocess.run(prefix+['sudo','-n','--','/usr/local/sbin/portable-storage','download-toggle'],env=e,capture_output=True,check=True)
def idle():
 child=subprocess.Popen(prefix+['swayidle','-w','timeout','3','/usr/local/bin/portable-lock --idle'],env=e,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:time.sleep(8)
 finally:child.terminate();child.wait(timeout=5)
out={}
if not state()['download_mode']:toggle()
idle();out['idle_inhibited_with_download_mode']=Path('/dev/mapper/portable_data').exists() and subprocess.run(['pgrep','-u','1000','-x','gtklock'],stdout=subprocess.DEVNULL).returncode!=0
# Direct idle call checks the inhibited return as well as the compositor event.
out['idle_controller_returns_inhibited']=p.lock(idle=True) is False
toggle();idle()
out['actual_idle_event_closes_Private']=not Path('/dev/mapper/portable_data').exists()
out['graphical_locker_running']=subprocess.run(['pgrep','-u','1000','-x','gtklock'],stdout=subprocess.DEVNULL).returncode==0
print(json.dumps(out))
