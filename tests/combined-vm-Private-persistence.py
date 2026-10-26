"""Verify synthetic Private content after reboot, then close its mapping."""
from pathlib import Path
import json
import os
import subprocess
import sys
assert os.geteuid() == 0
sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
import private_storage as p
import system_state
values = json.load(sys.stdin)
assert not c.private_available()
checks = {}
try:
    assert p.unlock(values['private'].encode(), raise_errors=True)
    canary = Path('/mnt/private/combined-Private-canary')
    checks['Private_content_retained_after_reboot'] = canary.read_text() == 'public synthetic persistence canary'
    checks['Private_canary_owner_and_mode_retained'] = canary.stat().st_uid == 1000 and canary.stat().st_mode & 0o777 == 0o600
    c.home('offline-keepassxc');c.storage_setup('offline-keepassxc')
    target = '/mnt/private/Documents/keepassxc/combined-gui-fixture.kdbx'
    result = subprocess.run(c.sandbox('offline-keepassxc', ['aa-exec','-p','petalos_offline_keepassxc','--',
        '/usr/bin/keepassxc-cli','ls',target]), input=(values['private']+'\n').encode(), capture_output=True, timeout=25)
    checks['GUI_saved_database_survived_reboot'] = result.returncode == 0 and b'Combined GUI group' in result.stdout
    checks['fresh_install_has_no_legacy_PortableSettings_folder'] = not Path('/mnt/private/PortableSettings').exists()
finally:
    p.lock()
checks['Private_closed_after_check'] = not Path('/dev/mapper/portable_data').exists()
checks['SYSTEM_state_still_ready'] = system_state.ready()
print(json.dumps(checks))
assert all(checks.values())
