from pathlib import Path
import json,os,subprocess,sys,secrets
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
assert os.geteuid()==0
out={}
for app,(name,uid) in c.OFFLINE.items():
 c.home(app);c.storage_setup(app);paths=[];results={}
 try:
  for prefix,host in [('RAM',Path('/home/Petal/Documents')/name),('Private',Path('/mnt/private/Documents')/name)]:
   if prefix=='Private' and not c.private_available():continue
   p=host/('audit-petal-owned-'+secrets.token_hex(8)+'.txt');p.write_text('public fixture');os.chown(p,1000,1000);p.chmod(0o660);paths.append(p)
   c.grant(host,uid)
   visible='/mnt/'+('ram' if prefix=='RAM' else 'private')+'/Documents/'+name+'/'+p.name
   code='import os,json; p='+repr(visible)+'\nr={"read":False,"write":False}\ntry:\n fd=os.open(p,os.O_RDONLY);os.close(fd);r["read"]=True\nexcept OSError:pass\ntry:\n fd=os.open(p,os.O_WRONLY|os.O_APPEND);os.write(fd,b"x");os.close(fd);r["write"]=True\nexcept OSError:pass\nprint(json.dumps(r))'
   r=subprocess.run(c.sandbox(app,['aa-exec','-p','petalos_'+app.replace('-','_'),'--','python3','-I','-c',code]),capture_output=True,text=True,timeout=10)
   assert r.returncode==0
   results[prefix]=json.loads(r.stdout)
  out[name]=results
 finally:
  for p in paths:p.unlink(missing_ok=True)
print(json.dumps(out,sort_keys=True))
