"""Host controller for public audit fixtures; records bounded redacted evidence."""
from pathlib import Path
import importlib.util,json,subprocess,sys,time
PROJECT=Path(__file__).resolve().parents[2]
OUT=PROJECT/'docs/phase15-repairs'
STATE=PROJECT.parent/'testing/audit/20261017-221958-817753/state.json'
def main():
 name=sys.argv[1]; action=sys.argv[2] if len(sys.argv)>2 else 'root-script'
 fixture=Path(name)
 if not fixture.exists():fixture=Path(__file__).parent/(name+'.py')
 fixture=fixture.resolve()
 started=time.monotonic()
 r=subprocess.run([sys.executable,'-B',str(PROJECT/'tests/audit-vm.py'),str(STATE),action,str(fixture)],capture_output=True,timeout=620)
 record={'fixture':str(fixture.relative_to(PROJECT)),'exit':r.returncode,'elapsed_seconds':round(time.monotonic()-started,2),'stdout':r.stdout.decode(errors='replace')[-65536:],'stderr':r.stderr.decode(errors='replace')[-10000:]}
 try:
  record['result']=json.loads(record.pop('stdout'))
  if 'compressed_public_metadata' in record['result']:
   import base64,zlib
   record['result']=json.loads(zlib.decompress(base64.b64decode(record['result']['compressed_public_metadata'])))
 except (ValueError,KeyError):record['stdout']=r.stdout.decode(errors='replace')[-65536:]
 target=OUT/(fixture.stem+'-result.json');target.write_text(json.dumps(record,indent=2))
 print(json.dumps({'fixture':fixture.name,'exit':r.returncode,'seconds':record['elapsed_seconds'],'evidence':str(target)}))
 if 'result' in record and fixture.stem!='baseline':print(json.dumps(record['result']))
 if r.returncode:print(record['stderr'][-2500:])
 return r.returncode
if __name__=='__main__':sys.exit(main())
