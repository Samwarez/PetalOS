from pathlib import Path
import json,os,subprocess,sys
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
assert os.geteuid()==0
app='offline-keepassxc';folder=c.ram_folder(app,'Documents')
code="""import json,subprocess
p='/mnt/ram/Documents/keepassxc/public-gui-fixture.kdbx'
r=subprocess.run(['/usr/bin/keepassxc-cli','ls',p],input=b'public-disposable-fixture-only\\n',capture_output=True)
print(json.dumps({'gui_saved_entry_reopened':r.returncode==0 and b'public-gui-entry' in r.stdout}))
"""
r=subprocess.run(c.sandbox(app,['aa-exec','-p','petalos_offline_keepassxc','--','python3','-I','-c',code]),capture_output=True,timeout=20)
assert r.returncode==0
result=json.loads(r.stdout);assert result['gui_saved_entry_reopened']
c.stop(app)
subprocess.run(['umount',str(folder)],check=True,capture_output=True)
Path('/run/petalos-keepass-gui-test.json').unlink()
print(json.dumps({**result,'synthetic_volume_unmounted':True}))
