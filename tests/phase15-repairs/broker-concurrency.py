"""Block only Tor egress; test independent launch, contention and cancellation."""
from pathlib import Path
import json,os,subprocess,sys,time
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
assert os.geteuid()==0
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
pre=['setpriv','--reuid=1000','--regid=1000','--clear-groups','--']
command=['sudo','-n','--','/usr/local/sbin/portable-compartment','launch']
controller=r'''import json,subprocess,sys,time
p=subprocess.Popen(['sudo','-n','--','/usr/local/sbin/portable-compartment','launch','tor'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
sys.stdin.buffer.read(1)
t=time.monotonic();p.terminate();code=p.wait(timeout=35)
print(json.dumps({'cancel_exit':code,'cancel_seconds':round(time.monotonic()-t,2),'ordinary_user_cancel_succeeded':True}))
'''
c.stop('browser');c.stop('tor');c.stop('offline-geany')
assert subprocess.run(['nft','list','table','inet','petalos_repair_tor_block'],capture_output=True).returncode!=0
rules='''table inet petalos_repair_tor_block {
 chain output {
  type filter hook output priority -1; policy accept;
  meta skuid 940 drop
 }
}
'''
subprocess.run(['nft','-f','-'],input=rules.encode(),check=True,capture_output=True)
child=None;report={}
try:
 child=subprocess.Popen(pre+['python3','-I','-c',controller],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 deadline=time.monotonic()+20
 while time.monotonic()<deadline:
  record=c.read_record('tor')
  if c.worker_alive(record) and record.get('phase')=='starting':break
  time.sleep(.1)
 else:raise AssertionError('Tor did not enter controlled startup')
 t=time.monotonic();r=subprocess.run(pre+command+['offline-geany'],capture_output=True,timeout=20)
 report['unrelated_app_launch_exit']=r.returncode;report['unrelated_app_seconds']=round(time.monotonic()-t,2)
 assert r.returncode==0
 t=time.monotonic();r=subprocess.run(pre+command+['tor'],capture_output=True,timeout=8)
 report['duplicate_launch_rejected']=r.returncode!=0;report['duplicate_launch_seconds']=round(time.monotonic()-t,2)
 assert r.returncode!=0
 out,err=child.communicate(input=b'C',timeout=40)
 assert child.returncode==0,'Ordinary-user cancellation failed; output suppressed.'
 report.update(json.loads(out))
 report['cancelled_tor_worker_gone']=not c.worker_alive(c.read_record('tor'))
 report['unrelated_app_remains_ready']=c.worker_alive(c.read_record('offline-geany'))
 assert report['cancelled_tor_worker_gone'] and report['unrelated_app_remains_ready']
finally:
 if child is not None and child.poll() is None:
  try:child.communicate(input=b'C',timeout=40)
  except Exception:child.kill();child.wait()
 subprocess.run(['nft','delete','table','inet','petalos_repair_tor_block'],check=True,capture_output=True)
 c.stop('browser');c.stop('tor');c.stop('offline-geany')
report['live_vpn_check_after_test']=subprocess.run(['/usr/local/sbin/portable-check-vpn'],capture_output=True,timeout=20).returncode==0
print(json.dumps(report))
