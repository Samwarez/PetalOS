"""Cold boot must restore only selected settings, with Private still closed."""
from pathlib import Path
import configparser
import json
import os
import subprocess
import sys
assert os.geteuid() == 0
sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
from app_preferences import endpoints
from desktop_session import environment
from system_state import STATE
assert not c.private_available()
checks = {'Private_still_closed_after_reboot': not Path('/dev/mapper/portable_data').exists(),
          'RAM_canary_gone': not Path('/home/Petal/combined-RAM-canary').exists(),
          'RAM_download_fixture_gone': not Path('/home/Petal/Downloads/petalos-audit-av.webm').exists(),
          'fresh_boot_trash_empty': not any(Path('/home/Petal/.local/share/Trash/files').glob('*')),
          'approved_SYSTEM_settings_retained': (STATE/'AppPreferences/transmission.json').is_file() and (STATE/'AppPreferences/amule.json').is_file()}
pre = ['setpriv', '--reuid=1000', '--regid=1000', '--clear-groups', '--']
r = subprocess.run(pre+['xfconf-query','-c','xsettings','-p','/Net/DoubleClickTime'], env=environment(), capture_output=True, text=True, timeout=5)
checks['immediate_desktop_save_restored'] = r.returncode == 0 and r.stdout.strip() == '333'
c.start('transmission');c.stop('transmission')
t = json.loads((c.PAYLOAD/'transmission/state/settings.json').read_text())
checks['actual_Transmission_applied_saved_preference'] = t['speed-limit-down'] == 12345 and t['speed-limit-down-enabled'] is True
checks['Transmission_history_path_not_restored'] = 'public-history-sentinel' not in t.get('download-dir','')
c.start('amule');c.stop('amule')
amule = c.PAYLOAD/'amule/state'
ini = configparser.ConfigParser(interpolation=None);ini.optionxform = str;ini.read(amule/'amule.conf')
checks['actual_aMule_applied_saved_preference'] = ini.getint('eMule','MaxConnections') == 37
checks['actual_aMule_restored_server_endpoint'] = endpoints((amule/'server.met').read_bytes()) == [['1.1.1.1',9]]
checks['aMule_history_canary_not_restored'] = 'public-history-sentinel' not in (amule/'amule.conf').read_text()
checks['Private_not_needed_for_restoration'] = not c.private_available()
print(json.dumps(checks))
assert all(checks.values())
