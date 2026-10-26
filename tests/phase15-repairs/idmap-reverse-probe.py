from pathlib import Path
import json,os,subprocess,sys,tempfile
assert os.geteuid()==0
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
code=r'''
from pathlib import Path
import json,os,subprocess,tempfile
out={}
for label,base in [('overlay','/home/Petal/Documents'),('tmpfs','/dev/shm'),('private','/mnt/private/Documents')]:
 with tempfile.TemporaryDirectory(prefix='public-idmap-test-',dir=base) as d, tempfile.TemporaryDirectory(prefix='idmap-mount-',dir='/run') as m:
  source=Path(d);target=Path(m);os.chown(source,1000,1000)
  r=subprocess.run(['mount','--bind','-o','X-mount.idmap=1000:949:1',str(source),str(target)],capture_output=True,text=True)
  result={'mount_exit':r.returncode,'error':r.stderr.strip()[:250]}
  if r.returncode==0:
   try:
    result['mapped_owner']=target.stat().st_uid
    p=target/'public-fixture';q=subprocess.run(['setpriv','--reuid=949','--regid=949','--clear-groups','--','python3','-I','-c','import os; fd=os.open('+repr(str(p))+',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.write(fd,b"public fixture");os.close(fd)'],capture_output=True)
    result['create_exit']=q.returncode
    if q.returncode==0:
     result['underlying_owner']=(source/p.name).stat().st_uid
     q=subprocess.run(['setpriv','--reuid=1000','--regid=1000','--clear-groups','--','python3','-I','-c','from pathlib import Path;assert Path('+repr(str(source/p.name))+').read_bytes()==b"public fixture"'],capture_output=True)
     result['desktop_read_exit']=q.returncode
   finally:subprocess.run(['umount',str(target)],check=True,capture_output=True)
  out[label]=result
print(json.dumps(out))
'''
r=subprocess.run(['unshare','--mount','--propagation','private','python3','-I','-c',code],capture_output=True,text=True,timeout=30)
assert r.returncode==0,r.stderr[-1000:]
print(r.stdout)
