"""Reopen GUI-saved data through the installed CLI in the same production role."""
from pathlib import Path
import json
import os
import subprocess
import sys
assert os.geteuid() == 0
sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
values = json.load(sys.stdin)
target = Path('/mnt/private/Documents/keepassxc/combined-gui-fixture.kdbx')
command = c.sandbox('offline-keepassxc', ['aa-exec', '-p', 'petalos_offline_keepassxc', '--',
    '/usr/bin/keepassxc-cli', 'ls', str(target)])
result = subprocess.run(command, input=(values['private']+'\n').encode(), capture_output=True, timeout=25)
checks = {'GUI_saved_database_reopens': result.returncode == 0,
          'GUI_created_group_persisted': b'Combined GUI group' in result.stdout,
          'database_stays_desktop_owned': target.stat().st_uid == 1000}
print(json.dumps(checks))
assert all(checks.values())
