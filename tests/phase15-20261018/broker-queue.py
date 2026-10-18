"""Bounded contention test on the actual production broker; no app is replaced."""
from pathlib import Path
import fcntl,json,os,subprocess,sys,time
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
assert c.worker_alive(c.read_record('offline-geany')) and c.worker_alive(c.read_record('offline-atril'))
children=[];out={};fd=os.open(c.BASE/'broker.lock',os.O_RDWR|os.O_NOFOLLOW|os.O_CREAT,0o600)
try:
 fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 for app in ('offline-geany','offline-atril'):
  children.append(subprocess.Popen(['setpriv','--reuid=1000','--regid=1000','--clear-groups','sudo','-n','--','/usr/local/sbin/portable-compartment','launch',app],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
 time.sleep(3);out['unrelated_app_launches_both_wait_on_global_lock']=all(p.poll() is None for p in children)
finally:fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
try:
 out['both_complete_after_lock_release']=all(p.wait(timeout=15)==0 for p in children)
finally:
 for p in children:
  if p.poll() is None:p.terminate();p.wait(timeout=5)
print(json.dumps(out))
