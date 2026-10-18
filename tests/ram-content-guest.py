#!/usr/bin/python3 -I
"""Public QEMU canaries: useful RAM folders with Private genuinely closed."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c

assert os.geteuid() == 0
assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
assert not Path('/dev/mapper/portable_data').exists()
assert not c.private_available()
c.ram_ready(); c.roles()
for app in ('transmission', 'pan', 'amule', 'sabnzbd', 'browser', *c.OFFLINE):
    c.home(app); c.storage_setup(app)
    if app == 'browser':
        c.prepare_tor_home(app)
    name = c.OFFLINE[app][0] if app in c.OFFLINE else ('TorBrowser' if app == 'browser' else app)
    category = 'Documents' if app in c.OFFLINE else 'Downloads'
    profile = 'petalos_' + app.replace('-', '_')
    # The browser's execution profile is attached to Firefox, not Python.
    program = ['/usr/bin/python3', '-I', '-c']
    if app != 'browser':
        program = ['/usr/bin/aa-exec', '-p', profile, '--', *program]
    token = '.public-ram-probe-' + secrets.token_hex(12)
    code = '''import json,os
from pathlib import Path
p=Path(CONTENT_PATH)/CANARY_NAME
try:
 p.write_text('public RAM fixture')
 r={'content_writable':p.read_text()=='public RAM fixture',
    'Private_absent':not Path('/mnt/private').exists(),
    'SYSTEM_hidden':not Path('/mnt/system-state').exists(),
    'desktop_home_hidden':not Path('/home/Petal').exists(),
    'state_is_RAM':os.environ.get('PORTABLE_STATE_ROOT','/mnt/ram')=='/mnt/ram'}
 print(json.dumps(r));assert all(r.values())
finally:p.unlink(missing_ok=True)
'''.replace('CONTENT_PATH', repr('/mnt/ram/' + category + '/' + name)).replace('CANARY_NAME', repr(token))
    result = subprocess.run(c.sandbox(app, [*program, code]), capture_output=True,
                            text=True, timeout=20)
    assert result.returncode == 0, 'RAM role probe failed; raw output suppressed.'
    print(json.dumps({'app': app, 'checks': json.loads(result.stdout)}))
assert not Path('/mnt/private').exists() or not any(Path('/mnt/private').iterdir())
assert not Path('/dev/mapper/portable_data').exists()
