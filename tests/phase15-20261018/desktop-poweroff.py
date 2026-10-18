from pathlib import Path
import json,os,subprocess,sys
sys.path.insert(0,'/usr/local/lib/portable')
from desktop_session import environment
assert os.geteuid()==0 and subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
assert not Path('/dev/mapper/portable_data').exists()
assert subprocess.run(['pgrep','-u','1000','-x','gtklock'],stdout=subprocess.DEVNULL).returncode!=0
p=subprocess.Popen(['setpriv','--reuid=1000','--regid=1000','--clear-groups','--','xfce4-session-logout','--halt','--fast'],env=environment(),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
print(json.dumps({'normal_XFCE_session_poweroff_requested':True,'Private_was_closed':True}))
