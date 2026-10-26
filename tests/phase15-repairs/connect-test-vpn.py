import json,subprocess,sys
from pathlib import Path
sys.path.insert(0,'/usr/local/lib/portable')
from vpn_profiles import select
from desktop_session import environment
pre=['setpriv','--reuid=1000','--regid=1000','--clear-groups','--']
if not Path('/sys/class/net/wg0').exists():
    name,_=select()
    r=subprocess.run(['/usr/local/sbin/portable-vpn','connect',name],capture_output=True,timeout=110)
    assert r.returncode==0,'Test profile reconnect failed; output suppressed'
r=subprocess.run(['/usr/local/sbin/portable-check-network-ready'],capture_output=True,timeout=25)
assert r.returncode==0
env=environment()
status=json.loads(subprocess.check_output(pre+['sudo','-n','--','/usr/local/sbin/portable-storage','status'],env=env))
if not status['download_mode']:
    subprocess.run(pre+['sudo','-n','--','/usr/local/sbin/portable-storage','download-toggle'],env=env,check=True,capture_output=True)
print(json.dumps({'live_vpn_check':True,'download_mode_for_tests':True}))
