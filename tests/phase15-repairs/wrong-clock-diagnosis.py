"""Inspect only handshake counters during a past-clock connection attempt."""
from pathlib import Path
import json, os, subprocess, sys, time
assert os.geteuid()==0
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
sys.path.insert(0,'/usr/local/lib/portable')
from vpn_profiles import select
name,_=select()
def run(a,t=110):return subprocess.run(a,capture_output=True,timeout=t)
real=time.time();mono=time.monotonic();report={};process=None
try:
 assert run(['/usr/local/sbin/portable-vpn','disconnect']).returncode==0
 time.clock_settime(time.CLOCK_REALTIME,1577836800.)
 process=subprocess.Popen(['/usr/local/sbin/portable-vpn','connect',name],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 deadline=time.monotonic()+45
 observations=[]
 while time.monotonic()<deadline and process.poll() is None:
  time.sleep(3)
  if not Path('/sys/class/net/wg0').exists():continue
  handshake=run(['wg','show','wg0','latest-handshakes'],5).stdout.splitlines()
  transfer=run(['wg','show','wg0','transfer'],5).stdout.splitlines()
  observations.append({'handshake_seen':any(int(line.split()[-1])>0 for line in handshake),
   'received_bytes':sum(int(line.split()[-2]) for line in transfer),
   'sent_bytes':sum(int(line.split()[-1]) for line in transfer)})
 stdout,stderr=process.communicate(timeout=50)
 report={'connection_returncode':process.returncode,'observations':observations,
         'time_sync_failure_reported':b'Clock synchronization and tunnel verification failed' in stdout+stderr,
         'tunnel_removed_after_failure':not Path('/sys/class/net/wg0').exists()}
finally:
 if process is not None and process.poll() is None:
  process.terminate();process.communicate(timeout=30)
 time.clock_settime(time.CLOCK_REALTIME,real+time.monotonic()-mono)
 run(['/usr/local/sbin/portable-vpn','disconnect'])
 report['restored_clock_reconnect']=run(['/usr/local/sbin/portable-vpn','connect',name]).returncode==0
print(json.dumps(report))
