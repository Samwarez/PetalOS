"""Change guest wall clock only; no RTC writes or credential changes."""
from pathlib import Path
import json,os,subprocess,sys,time
assert os.geteuid()==0
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
sys.path.insert(0,'/usr/local/lib/portable')
from vpn_profiles import select
name,_=select()
def run(a,t=110):return subprocess.run(a,capture_output=True,timeout=t)
real=time.time();mono=time.monotonic();report={}
try:
 assert run(['/usr/local/sbin/portable-vpn','disconnect']).returncode==0
 time.clock_settime(time.CLOCK_REALTIME,1577836800.)
 r=run(['/usr/local/sbin/portable-vpn','connect',name])
 report={'connection_succeeds_with_2020_clock':r.returncode==0,'clock_corrected':time.time()>1700000000,
 'failure_is_current_reachability':b'The VPN is not currently reachable.' in r.stdout+r.stderr,
 'tunnel_exists_after_attempt':Path('/sys/class/net/wg0').exists(),
 'chrony_active_after_attempt':run(['systemctl','is-active','--quiet','chrony']).returncode==0}
finally:
 time.clock_settime(time.CLOCK_REALTIME,real+time.monotonic()-mono)
 run(['/usr/local/sbin/portable-vpn','disconnect'])
 report['restored_clock_reconnect']=run(['/usr/local/sbin/portable-vpn','connect',name]).returncode==0
print(json.dumps(report,sort_keys=True))
