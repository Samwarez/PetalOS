"""Real installed KeePassXC atomic-save failure/retry on a tiny isolated RAM disk."""
import json
import os
import subprocess
assert os.geteuid() == 0
code = r'''
from pathlib import Path
import json,os,subprocess,sys
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
app='offline-keepassxc';c.home(app);c.storage_setup(app)
folder=c.ram_folder(app,'Documents')
subprocess.run(['mount','-t','tmpfs','-o','size=2M,nodev,nosuid,noexec,mode=0700,uid=1000,gid=1000','tmpfs',str(folder)],check=True,capture_output=True)
probe=r"""from pathlib import Path
import errno,hashlib,json,subprocess
p=Path('/mnt/ram/Documents/keepassxc/public-combined-full.kdbx');fill=p.with_suffix('.fill')
password=b'public-disposable-fixture-only\n';out={}
def cli(args):return subprocess.run(['/usr/bin/keepassxc-cli',*args],input=password*2,capture_output=True,timeout=20)
assert cli(['db-create','-p',str(p)]).returncode==0
before=hashlib.sha256(p.read_bytes()).hexdigest()
with fill.open('wb',buffering=0) as f:
 try:
  while True:f.write(bytes(65536))
 except OSError as e:assert e.errno==errno.ENOSPC
out['full_store_update_reports_failure']=cli(['mkdir',str(p),'Public group']).returncode!=0
out['original_database_unchanged']=hashlib.sha256(p.read_bytes()).hexdigest()==before
out['original_database_readable']=cli(['db-info',str(p)]).returncode==0
fill.unlink()
out['retry_after_freeing_space_succeeds']=cli(['mkdir',str(p),'Public group']).returncode==0
out['retried_change_persisted']=b'Public group' in cli(['ls',str(p)]).stdout
print(json.dumps(out))
assert all(out.values())
"""
try:
 r=subprocess.run(c.sandbox(app,['aa-exec','-p','petalos_offline_keepassxc','--','python3','-I','-c',probe]),capture_output=True,text=True,timeout=110)
 assert r.returncode==0,'Isolated database fixture failed; raw output suppressed.'
 print(json.dumps(json.loads(r.stdout)))
finally:subprocess.run(['umount',str(folder)],check=True,capture_output=True)
'''
result = subprocess.run(['unshare', '--mount', '--propagation', 'private', 'python3', '-I', '-c', code], capture_output=True, text=True, timeout=120)
assert result.returncode == 0, 'Isolated database fixture failed; raw output suppressed.'
print(json.dumps(json.loads(result.stdout)))
