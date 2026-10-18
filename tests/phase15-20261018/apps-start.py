"""Start built applications, record actual confinement, keep them for workflows."""
from pathlib import Path
import json,os,subprocess,sys,time
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
assert os.geteuid()==0
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
report={}
for app in ('transmission','pan','amule','sabnzbd','sab-viewer','offline-keepassxc','offline-parole'):
 start=time.monotonic()
 try:
  r=c.start(app); row={'ready':r['phase']=='ready','seconds':round(time.monotonic()-start,2)}
 except Exception as e:
  r=c.read_record(app);row={'ready':False,'error':type(e).__name__,'site':r.get('error_site'),'seconds':round(time.monotonic()-start,2)}
 identities=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdecimal():continue
  try:
   if p.stat().st_uid!=c.ROLES[app]:continue
   status={k:v.strip() for k,v in (l.split(':',1) for l in (p/'status').read_text().splitlines() if ':' in l)}
   if status['State'].startswith('Z'):continue
   identities.append({'comm':(p/'comm').read_text().strip(),'profile':(p/'attr/current').read_text().strip(),'caps':status['CapEff'],'nnp':status['NoNewPrivs'],'cgroup':(p/'cgroup').read_text().strip()})
  except (OSError,KeyError):pass
 row['processes']=identities;report[app]=row
print(json.dumps(report,sort_keys=True))
