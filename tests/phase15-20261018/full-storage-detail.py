"""ENOSPC against an isolated 2MiB tmpfs under the actual KeePassXC role."""
from pathlib import Path
import json,os,subprocess,sys
assert os.geteuid()==0
code=r'''
from pathlib import Path
import json,os,subprocess,sys
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
app='offline-keepassxc';folder=c.ram_folder(app,'Documents')
subprocess.run(['mount','-t','tmpfs','-o','size=2M,nodev,nosuid,noexec,mode=0700,uid=953,gid=953','tmpfs',str(folder)],check=True,capture_output=True)
os.chown(folder,c.ROLES[app],c.ROLES[app])
probe=r"""from pathlib import Path
import errno,hashlib,json,subprocess
p=Path('/mnt/ram/Documents/keepassxc/public-full-fixture.kdbx');fill=p.with_suffix('.fill');password=b'public-disposable-fixture-only\n';out={}
def cli(args):return subprocess.run(['/usr/bin/keepassxc-cli',*args],input=password*2,capture_output=True,timeout=20)
r=cli(['db-create','-p',str(p)]);assert r.returncode==0
out['initial_reopen_success']=cli(['db-info',str(p)]).returncode==0;out['initial_size']=p.stat().st_size;before=hashlib.sha256(p.read_bytes()).hexdigest()
with fill.open('wb',buffering=0) as f:
 try:
  while True:f.write(bytes(65536))
 except OSError as e:assert e.errno==errno.ENOSPC
r=cli(['mkdir',str(p),'Public group']);out['full_store_update_reports_failure']=r.returncode!=0;out['full_store_returncode']=r.returncode;out['full_store_public_stdout']=r.stdout.decode(errors='replace')[-1200:];out['full_store_public_stderr']=r.stderr.decode(errors='replace')[-1200:];out['post_update_size']=p.stat().st_size;out['public_fixture_names']=[f.name for f in p.parent.iterdir()]
out['original_database_unchanged']=hashlib.sha256(p.read_bytes()).hexdigest()==before
r=cli(['db-info',str(p)]);out['original_database_readable']=r.returncode==0;out['reopen_public_stderr']=r.stderr.decode(errors='replace')[-1200:]
fill.unlink();out['retry_after_freeing_space_succeeds']=cli(['mkdir',str(p),'Public group']).returncode==0
out['retried_change_persisted']=b'Public group' in cli(['ls',str(p)]).stdout
print(json.dumps(out))
"""
try:
 r=subprocess.run(c.sandbox(app,['aa-exec','-p','petalos_offline_keepassxc','--','python3','-I','-c',probe]),capture_output=True,text=True,timeout=110)
 assert r.returncode==0,'Isolated fixture failed; raw output suppressed.'
 print(json.dumps(json.loads(r.stdout)))
finally:subprocess.run(['umount',str(folder)],check=True,capture_output=True)
'''
r=subprocess.run(['unshare','--mount','--propagation','private','python3','-I','-c',code],capture_output=True,text=True,timeout=120)
assert r.returncode==0,'Isolated fixture failed; raw output suppressed.'
print(json.dumps(json.loads(r.stdout)))
