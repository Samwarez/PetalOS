"""Fifteen-minute bounded guest load. Public counts only, all workers cleaned."""
from pathlib import Path
import json,os,subprocess,sys
assert os.geteuid()==0
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
root=Path('/run/petalos-phase15');root.mkdir(mode=0o700,exist_ok=True)
assert not (root/'soak.json').exists()
code=r'''
from pathlib import Path
import collections,hashlib,json,os,signal,subprocess,sys,time
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
root=Path('/run/petalos-phase15');report={'phase':'starting','apps':{},'samples':[]};workers=[];running=True
def signal_stop(*_):
 global running
 running=False
signal.signal(signal.SIGTERM,signal_stop)
def save():
 p=root/'soak.tmp';p.write_text(json.dumps(report));p.chmod(0o600);os.replace(p,root/'soak.json')
try:
 for app in c.OFFLINE:
  try:r=c.start(app);report['apps'][app]=r['phase']=='ready'
  except Exception as e:report['apps'][app]={'failed':type(e).__name__,'site':c.read_record(app).get('error_site')}
  save()
 c.start('transmission')
 worker="import hashlib,resource,time;resource.setrlimit(resource.RLIMIT_AS,(300*1024**2,300*1024**2));p=bytearray(128*1024**2);p[:]=b'x'*len(p);t=time.monotonic()+960\nwhile time.monotonic()<t:hashlib.sha256(p).digest()"
 for _ in range(4):workers.append(subprocess.Popen(['setpriv','--reuid=61001','--regid=61001','--clear-groups','--bounding-set=-all','--no-new-privs','nice','-n','10','python3','-I','-c',worker],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
 started=time.monotonic();report['phase']='soak';save()
 while running and time.monotonic()-started<900:
  mem={a:b.strip() for a,b in (x.split(':',1) for x in Path('/proc/meminfo').read_text().splitlines())}
  alive={app:c.worker_alive(c.read_record(app)) for app in c.ROLES if app not in ('offline',)}
  v=os.statvfs('/run');sample={'elapsed':round(time.monotonic()-started),'available_MiB':int(mem['MemAvailable'].split()[0])//1024,'run_used_MiB':(v.f_blocks-v.f_bfree)*v.f_frsize//1024**2,'apps_alive':alive,'workers_alive':sum(w.poll() is None for w in workers)}
  report['samples'].append(sample);save()
  if sample['available_MiB']<3072:report['abort']='low_memory';break
  time.sleep(15)
 report['phase']='completed' if running and 'abort' not in report else 'stopped';report['elapsed_seconds']=round(time.monotonic()-started)
finally:
 for w in workers:
  if w.poll() is None:w.terminate()
 for w in workers:
  try:w.wait(timeout=3)
  except subprocess.TimeoutExpired:w.kill();w.wait()
 report['stress_workers_reaped']=True;save()
'''
p=subprocess.Popen(['python3','-I','-c',code],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
(root/'soak.pid').write_text(str(p.pid))
print(json.dumps({'soak_started':True,'duration_seconds':900,'workers':4,'committed_worker_memory_MiB':512}))
