"""Exercise the real authenticated clock helper inside the disposable guest."""
from pathlib import Path
from datetime import datetime,timezone
import json,os,subprocess,sys,time
assert os.geteuid()==0
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
sys.path.insert(0,'/usr/local/lib/portable')
from vpn_profiles import select
name,_=select();helper='/usr/local/sbin/portable-set-clock'
def run(a,t=120):return subprocess.run(a,capture_output=True,timeout=t)
def utc(value):return datetime.fromtimestamp(value,timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
real=time.time();mono=time.monotonic();report={}
rtc=Path('/sys/class/rtc/rtc0/since_epoch');old_rtc=int(rtc.read_text())
try:
 r=run(['setpriv','--reuid=1000','--regid=1000','--clear-groups','--','sudo','-k','-n','--',helper,utc(real)])
 report['unauthenticated_correction_rejected']=r.returncode!=0 and b'password is required' in r.stderr
 assert Path('/sys/class/net/wg0').exists()
 report['correction_while_connected_rejected']=run([helper,utc(real)]).returncode!=0
 assert run(['/usr/local/sbin/portable-vpn','disconnect']).returncode==0
 time.clock_settime(time.CLOCK_REALTIME,1577836800.)
 for bad in ('2026-02-30 00:00:00','2026-01-01 25:00:00','2026-01-01 00:00:00;true'):
  assert run([helper,bad]).returncode!=0
 report['invalid_inputs_leave_clock_unchanged']=time.time()<1577836900
 r=run([helper,utc(real+time.monotonic()-mono)])
 report['manual_correction_succeeded']=r.returncode==0 and abs(time.time()-(real+time.monotonic()-mono))<2
 report['reconnect_and_active_checks_succeeded']=run(['/usr/local/sbin/portable-vpn','connect',name]).returncode==0
 report['hardware_clock_not_reset']=abs((int(rtc.read_text())-old_rtc)-(time.monotonic()-mono))<3
 assert all(report.values())
finally:
 if abs(time.time()-(real+time.monotonic()-mono))>2:
  time.clock_settime(time.CLOCK_REALTIME,real+time.monotonic()-mono)
 if not Path('/sys/class/net/wg0').exists():run(['/usr/local/sbin/portable-vpn','connect',name])
print(json.dumps(report))
