"""Export approved numeric settings; leave activity canaries out of SYSTEM."""
from pathlib import Path
import configparser
import io
import json
import os
import subprocess
import sys
assert os.geteuid() == 0
sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
from system_state import STATE
from desktop_session import environment
assert c.private_available()
for app in c.ROLES:c.stop(app)
settings = c.PAYLOAD/'transmission/state/settings.json'
data = json.loads(settings.read_text())
data.update({'speed-limit-down': 12345, 'speed-limit-down-enabled': True,
             'download-dir': '/mnt/ram/Downloads/transmission/public-history-sentinel'})
settings.write_text(json.dumps(data));os.chown(settings, c.ROLES['transmission'], c.ROLES['transmission'])
amule = Path('/mnt/private/AppState/amule')
ini = configparser.ConfigParser(interpolation=None);ini.optionxform = str
ini.read(amule/'amule.conf')
assert ini.has_section('eMule')
ini.set('eMule', 'MaxConnections', '37');ini.set('eMule', 'Autoconnect', '0')
ini.set('eMule', 'Nick', 'public-history-sentinel')
ini.set('eMule', 'ConnectToKad', '0');ini.set('eMule', 'ConnectToED2K', '0')
buffer = io.StringIO();ini.write(buffer, space_around_delimiters=False)
(amule/'amule.conf').write_text(buffer.getvalue())
(amule/'server.met').write_bytes(b'\xe0'+(1).to_bytes(4,'little')+(0x01010101).to_bytes(4,'little')+(9).to_bytes(2,'little')+bytes(4))
for p in (amule/'amule.conf', amule/'server.met'):
    os.chown(p, c.ROLES['amule'], c.ROLES['amule']);p.chmod(0o600)
pre = ['setpriv', '--reuid=1000', '--regid=1000', '--clear-groups', '--']
subprocess.run(pre+['sudo', '-n', '--', '/usr/local/sbin/portable-save-app-preferences'], env=environment(), check=True, capture_output=True, timeout=25)
t = json.loads((STATE/'AppPreferences/transmission.json').read_text())
a = json.loads((STATE/'AppPreferences/amule.json').read_text())
checks = {'Transmission_numeric_preference_exported': t['preferences']['speed-limit-down'] == 12345,
          'aMule_numeric_preference_exported': a['preferences']['eMule/MaxConnections'] == 37,
          'aMule_numeric_server_endpoint_exported': a['servers'] == [['1.1.1.1',9]],
          'history_canaries_excluded': all(b'public-history-sentinel' not in p.read_bytes() for p in (STATE/'AppPreferences').glob('*.json'))}
for path in (Path('/home/Petal/combined-RAM-canary'), Path('/mnt/private/combined-Private-canary')):
    if path.exists():assert path.read_text() == 'public synthetic persistence canary'
    else:path.write_text('public synthetic persistence canary');os.chown(path,1000,1000);path.chmod(0o600)
print(json.dumps(checks))
assert all(checks.values())
