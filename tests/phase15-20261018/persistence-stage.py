"""Write explicitly public persistence canaries, through production exporters."""
from pathlib import Path
import json,os,subprocess,sys
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c,app_preferences as a,desktop_settings as d
from desktop_session import environment
assert os.geteuid()==0;c.private_ready()
for app in c.ROLES:c.stop(app)
# A normal application's selected numeric preference; no profile/history export.
state=Path('/mnt/private/AppState/transmission/settings.json');cfg=json.loads(state.read_text());cfg['speed-limit-down']=12345;cfg['speed-limit-down-enabled']=True
state.write_text(json.dumps(cfg));os.chown(state,942,942)
count=a.save_all()
saved=json.loads(Path('/mnt/system-state/AppPreferences/transmission.json').read_text())
assert saved['preferences']['speed-limit-down']==12345
env=environment()
args=['setpriv','--reuid=1000','--regid=1000','--clear-groups','xfconf-query','-c','xsettings','-p','/Net/DoubleClickTime','-s','321']
subprocess.run(args,check=True,capture_output=True,env=env)
subprocess.run(['setpriv','--reuid=1000','--regid=1000','--clear-groups','/usr/local/bin/portable-save-settings'],env=env,check=True,capture_output=True,timeout=20)
for f in (Path('/home/Petal/petalos-phase15-ram-canary'),Path('/mnt/private/petalos-phase15-private-canary')):
 assert not f.exists();f.write_text('public synthetic persistence fixture');os.chown(f,1000,1000)
print(json.dumps({'app_preference_records_saved':count,'transmission_numeric_preference_saved':True,'desktop_setting_set_and_exported':True,'RAM_and_Private_canaries_written':True}))
