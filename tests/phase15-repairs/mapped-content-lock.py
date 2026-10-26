"""Manual lock must evict live content views and close the Private encryption mapping."""
from pathlib import Path
import json,os,subprocess,sys
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
import private_storage as p
from desktop_session import environment
values=json.load(sys.stdin)
assert p.unlock(values['private'].encode(),raise_errors=True)
apps=('offline-geany','offline-keepassxc')
for app in apps:
 c.stop(app);c.start(app)
def has_view(uid,name):
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:
   if proc.stat().st_uid==uid and (' /mnt/private/Documents/'+name+' ') in (proc/'mountinfo').read_text():return True
  except (FileNotFoundError,ProcessLookupError,PermissionError):pass
 return False
assert all(has_view(c.ROLES[app],c.OFFLINE[app][0]) for app in apps)
e=environment();pre=['setpriv','--reuid=1000','--regid=1000','--clear-groups','--']
r=subprocess.run(pre+['/usr/local/bin/portable-lock'],env=e,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=35)
result={'manual_lock_succeeded':r.returncode==0,
 'Private_mapping_closed':not Path('/dev/mapper/portable_data').exists(),
 'SYSTEM_state_remains_ready':__import__('system_state').ready(),
 'application_workers_gone':all(not c.worker_alive(c.read_record(app)) for app in apps),
 'mapped_Private_views_gone':all(not has_view(c.ROLES[app],c.OFFLINE[app][0]) for app in apps)}
print(json.dumps(result))
assert all(result.values())
