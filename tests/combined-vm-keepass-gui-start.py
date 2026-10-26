"""Open a new synthetic Private database in the actual KeePassXC GUI."""
from pathlib import Path
import json
import os
import subprocess
import sys
assert os.geteuid() == 0
sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
values = json.load(sys.stdin)
assert c.private_available()
c.stop('offline-keepassxc');c.home('offline-keepassxc');c.storage_setup('offline-keepassxc')
target = Path('/mnt/private/Documents/keepassxc/combined-gui-fixture.kdbx')
assert not target.exists()
command = c.sandbox('offline-keepassxc', ['aa-exec', '-p', 'petalos_offline_keepassxc', '--',
    '/usr/bin/keepassxc-cli', 'db-create', '-p', str(target)])
result = subprocess.run(command, input=(values['private']+'\n').encode()*2, capture_output=True, timeout=25)
assert result.returncode == 0 and target.is_file(), 'Synthetic database create failed; output suppressed.'
record = c.start('offline-keepassxc', [str(target)])
print(json.dumps({'new_synthetic_Private_database_created': True,
                  'actual_KeePassXC_window_ready': record['phase'] == 'ready',
                  'desktop_owns_new_database': target.stat().st_uid == 1000}))
