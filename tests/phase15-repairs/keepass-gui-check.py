from pathlib import Path
import hashlib,json,os,subprocess,sys
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
assert os.geteuid()==0
folder=Path('/home/Petal/Documents/keepassxc')
assert os.path.ismount(folder)
os.chown(folder/'public-gui-fixture.fill',1000,1000)
p=folder/'public-gui-fixture.kdbx'
expected=json.loads(Path('/run/petalos-keepass-gui-test.json').read_text())['sha256']
code="""import json,subprocess
p='/mnt/ram/Documents/keepassxc/public-gui-fixture.kdbx'
r=subprocess.run(['/usr/bin/keepassxc-cli','db-info',p],input=b'public-disposable-fixture-only\\n',capture_output=True)
print(json.dumps({'original_database_readable':r.returncode==0}))
"""
r=subprocess.run(c.sandbox('offline-keepassxc',['aa-exec','-p','petalos_offline_keepassxc','--','python3','-I','-c',code]),capture_output=True,timeout=20)
assert r.returncode==0
result=json.loads(r.stdout)
result['original_database_unchanged']=hashlib.sha256(p.read_bytes()).hexdigest()==expected
assert all(result.values())
(folder/'public-gui-fixture.fill').unlink()
print(json.dumps({**result,'space_freed_for_gui_retry':True}))
