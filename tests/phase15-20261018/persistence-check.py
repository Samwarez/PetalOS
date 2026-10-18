from pathlib import Path
import json,os,subprocess,sys
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c,private_storage as p
from desktop_session import environment
assert os.geteuid()==0
values=json.load(sys.stdin)
out={'Private_closed_after_boot':not Path('/dev/mapper/portable_data').exists(),'RAM_canary_gone':not Path('/home/Petal/petalos-phase15-ram-canary').exists()}
saved=json.loads(Path('/mnt/system-state/AppPreferences/transmission.json').read_text());out['SYSTEM_numeric_preference_retained']=saved['preferences']['speed-limit-down']==12345
env=environment();r=subprocess.run(['setpriv','--reuid=1000','--regid=1000','--clear-groups','xfconf-query','-c','xsettings','-p','/Net/DoubleClickTime'],env=env,capture_output=True,text=True)
out['desktop_setting_restored']=r.returncode==0 and r.stdout.strip()=='321'
assert p.unlock(values['private'].encode(),raise_errors=True)
f=Path('/mnt/private/petalos-phase15-private-canary');out['Private_canary_retained']=f.read_text()=='public synthetic persistence fixture';f.unlink()
print(json.dumps(out,sort_keys=True))
