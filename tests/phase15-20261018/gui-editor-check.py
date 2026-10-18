from pathlib import Path
import json,os,sys
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
p=Path('/home/Petal/Documents/mousepad/petalos-audit-editor.txt')
assert os.geteuid()==0
print(json.dumps({'actual_GUI_save_persisted':p.read_text().strip()=='audit saved'}))
c.stop('offline-mousepad');p.unlink()
