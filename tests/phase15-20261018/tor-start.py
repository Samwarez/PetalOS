import json,os,sys,time
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
assert os.geteuid()==0
r={}
for app in ('tor','browser'):
 t=time.monotonic()
 try:record=c.start(app,[] if app=='tor' else ['https://check.torproject.org/']);r[app]={'ready':record['phase']=='ready','seconds':round(time.monotonic()-t,2)}
 except Exception as e:r[app]={'ready':False,'error':type(e).__name__,'site':c.read_record(app).get('error_site'),'seconds':round(time.monotonic()-t,2)}
print(json.dumps(r))
