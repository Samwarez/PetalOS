"""Inspect actual broker-created torrent import under the built RAM sandbox."""
from pathlib import Path
import json,os,sys,subprocess,secrets
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
assert not c.private_available()
app='transmission';c.home(app);c.storage_setup(app)
p=Path('/home/Petal')/('audit-'+secrets.token_hex(8)+'.torrent')
p.write_bytes(b'd4:infod6:lengthi1e4:name4:test12:piece lengthi16384e6:pieces20:00000000000000000000ee');os.chown(p,1000,1000)
try:
 args=c.import_items(app,[str(p)])
 code='import pathlib,json; print(json.dumps({"delegated_import_exists":pathlib.Path('+repr(args[0])+').is_file()}))'
 r=subprocess.run(c.sandbox(app,['aa-exec','-p','petalos_transmission','--','python3','-I','-c',code]),capture_output=True,text=True,timeout=15)
 assert r.returncode==0
 print(r.stdout.strip())
finally:
 p.unlink()
 if 'args' in locals():
  for v in args:(c.BASE/app/'imports'/Path(v).name).unlink(missing_ok=True)
