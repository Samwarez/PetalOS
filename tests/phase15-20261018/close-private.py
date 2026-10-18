from pathlib import Path
import json,sys
sys.path.insert(0,'/usr/local/lib/portable')
import private_storage as p
p.lock()
print(json.dumps({'Private_mapping_closed':not Path('/dev/mapper/portable_data').exists(),'runtime_VPN_key_removed':not Path('/etc/wireguard/wg0.conf').exists()}))
