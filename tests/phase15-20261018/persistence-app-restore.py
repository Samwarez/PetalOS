from pathlib import Path
import json,sys
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
assert not Path('/dev/mapper/portable_data').exists()
r=c.start('transmission');c.stop('transmission')
f=c.PAYLOAD/'transmission/state/settings.json';v=json.loads(f.read_text())
print(json.dumps({'actual_Transmission_RAM_launch_ready':r['phase']=='ready','selected_preference_applied_after_reboot':v['speed-limit-down']==12345 and v['speed-limit-down-enabled'] is True,'Private_remained_closed':not Path('/dev/mapper/portable_data').exists()}))
