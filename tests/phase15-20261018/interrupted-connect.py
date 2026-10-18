from pathlib import Path
import json,os,subprocess,sys,time,signal
sys.path.insert(0,'/usr/local/lib/portable')
from vpn_profiles import select
assert os.geteuid()==0
name,_=select()
def run(args,t=110):return subprocess.run(args,capture_output=True,timeout=t)
assert run(['/usr/local/sbin/portable-vpn','disconnect']).returncode==0
p=subprocess.Popen(['/usr/local/sbin/portable-vpn','connect',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
report={}
try:
 deadline=time.monotonic()+15
 while time.monotonic()<deadline and p.poll() is None and not Path('/sys/class/net/wg0').exists():time.sleep(.02)
 report['tunnel_created_before_interruption']=Path('/sys/class/net/wg0').exists()
 p.terminate();p.wait(timeout=35)
 report['interrupted_operation_failed']=p.returncode!=0
 report['mapping_cleaned']=not Path('/sys/class/net/wg0').exists()
 report['runtime_key_file_cleaned']=not Path('/etc/wireguard/wg0.conf').exists()
 report['gate_denied']=run(['/usr/local/sbin/portable-check-network-ready'],25).returncode!=0
finally:
 if p.poll() is None:p.kill();p.wait()
 run(['/usr/local/sbin/portable-vpn','disconnect'])
 report['reconnect_without_reboot']=run(['/usr/local/sbin/portable-vpn','connect',name]).returncode==0
print(json.dumps(report))
