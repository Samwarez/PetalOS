"""0600 create/edit, desktop access and sibling isolation in real role profiles."""
from pathlib import Path
import json,os,secrets,subprocess,sys
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
assert os.geteuid()==0 and c.private_available()
out={}
for app in [*c.OFFLINE,'transmission','pan','amule','sabnzbd']:
    category='Documents' if app in c.OFFLINE else 'Downloads'
    name=c.OFFLINE[app][0] if app in c.OFFLINE else app
    c.home(app);c.storage_setup(app)
    filename='public-owner-fixture-'+secrets.token_hex(8)+'.txt'
    targets=[Path('/home/Petal')/category/name/filename,c.PRIVATE/category/name/filename]
    code='''from pathlib import Path
import json,os,sys
app,category,name,filename=sys.argv[1:]
result={}
for area in ('ram','private'):
 p=Path('/mnt')/area/category/name/filename
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 os.write(fd,b'public fixture');os.close(fd)
 result[area+'_owner_matches_process']=p.stat().st_uid==os.getuid()
 result[area+'_mode0600']=(p.stat().st_mode & 0o777)==0o600
 p.write_bytes(b'public edited fixture')
 result[area+'_edit_reopen']=p.read_bytes()==b'public edited fixture'
 result[area+'_siblings_hidden']=not any(x.name!=name for x in p.parent.parent.iterdir())
print(json.dumps(result))
'''
    try:
        r=subprocess.run(c.sandbox(app,['aa-exec','-p','petalos_'+app.replace('-','_'),'--',
             'python3','-I','-c',code,app,category,name,filename]),capture_output=True,text=True,timeout=20)
        assert r.returncode==0,app+' failed; output suppressed'
        result=json.loads(r.stdout)
        for area,p in zip(('ram','private'),targets):
            assert p.stat().st_uid==1000
            r=subprocess.run(['setpriv','--reuid=1000','--regid=1000','--clear-groups','--','python3','-I','-c',
                'from pathlib import Path;import sys;p=Path(sys.argv[1]);assert p.read_bytes()==b"public edited fixture";p.write_bytes(b"desktop edited fixture")',str(p)],
                capture_output=True,timeout=5)
            result[area+'_desktop_read_edit']=r.returncode==0
        assert all(result.values())
        out[app]=result
    finally:
        for p in targets:p.unlink(missing_ok=True)
print(json.dumps(out,sort_keys=True))
