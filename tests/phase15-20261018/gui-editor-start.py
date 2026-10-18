from pathlib import Path
import json,os,sys
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
assert os.geteuid()==0
c.home('offline-mousepad');c.storage_setup('offline-mousepad')
p=Path('/home/Petal/Documents/mousepad/petalos-audit-editor.txt')
assert not p.exists();p.write_text('before audit edit\n');os.chown(p,1000,1000);p.chmod(0o660)
r=c.start('offline-mousepad',[str(p)])
print(json.dumps({'native_editor_ready':r['phase']=='ready'}))
