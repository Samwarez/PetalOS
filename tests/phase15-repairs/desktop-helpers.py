import json,os,subprocess,sys
sys.path.insert(0,'/usr/local/lib/portable')
from desktop_session import environment
assert os.geteuid()==0
r=subprocess.run(['setpriv','--reuid=1000','--regid=1000','--clear-groups','--','python3','-B',
 '/tmp/petalos-ui-repair/tests/check-desktop-helpers.py'],env=environment(),capture_output=True,text=True,timeout=60)
print(json.dumps({'exit':r.returncode,'checks':r.stdout.splitlines(),'error':r.stderr[-2000:]}))
assert r.returncode==0
