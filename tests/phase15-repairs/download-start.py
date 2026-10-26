import json,os,sys
from pathlib import Path
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
assert os.geteuid()==0 and not c.private_available()
c.stop('transmission')
assert not Path('/home/Petal/Downloads/transmission/README').exists()
r=c.start('transmission',['/home/Petal/petalos-public-download.torrent'])
print(json.dumps({'locked_Private_real_torrent_import_ready':r['phase']=='ready'}))
