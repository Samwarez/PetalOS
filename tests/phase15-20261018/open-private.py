import json,os,sys
from pathlib import Path
assert os.geteuid()==0
sys.path.insert(0,'/usr/local/lib/portable')
import private_storage as p
values=json.load(sys.stdin)
assert p.unlock(values['private'].encode(),raise_errors=True)
print(json.dumps({'private_open':Path('/dev/mapper/portable_data').exists()}))
