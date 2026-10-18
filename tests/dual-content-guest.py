#!/usr/bin/python3 -I
"""QEMU public canaries: delegated Private and RAM folders stay separate."""
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
c.private_ready(); c.ram_ready(); c.roles()
canaries = []
for app in ('transmission', 'pan', 'amule', 'sabnzbd', 'browser', *c.OFFLINE):
    c.stop(app); c.reset_ram(app); c.home(app); c.storage_setup(app)
    if app == 'browser':
        c.prepare_tor_home(app)
    category = 'Documents' if app in c.OFFLINE else 'Downloads'
    name = c.OFFLINE[app][0] if app in c.OFFLINE else ('TorBrowser' if app == 'browser' else app)
    token = '.public-dual-probe-' + secrets.token_hex(12)
    own = category + '/' + name
    code = '''import json,os
from pathlib import Path
ram=Path('/mnt/ram')/OWN_PATH/TOKEN_NAME
private=Path('/mnt/private')/OWN_PATH/TOKEN_NAME
try:
 ram.write_text('public RAM retention fixture')
 private.write_text('public Private access fixture')
 bookmarks=(Path.home()/'.config/gtk-3.0/bookmarks').read_text()
 checks={'RAM_writable':ram.read_text()=='public RAM retention fixture',
 'Private_writable':private.read_text()=='public Private access fixture',
 'distinct_storage':ram.stat().st_dev!=private.stat().st_dev,
 'both_bookmarks':str(ram.parent) in bookmarks and str(private.parent) in bookmarks,
 'SYSTEM_hidden':not Path('/mnt/system-state').exists(),
 'desktop_home_hidden':not Path('/home/Petal').exists()}
 print(json.dumps(checks));assert all(checks.values())
finally:private.unlink(missing_ok=True)
'''.replace('OWN_PATH', repr(own)).replace('TOKEN_NAME', repr(token))
    program = ['/usr/bin/python3', '-I', '-c', code]
    if app != 'browser':
        program = ['/usr/bin/aa-exec', '-p', 'petalos_' + app.replace('-', '_'), '--', *program]
    result = subprocess.run(c.sandbox(app, program), capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, 'Dual folder probe failed; raw output suppressed.'
    print(json.dumps({'app': app, 'checks': json.loads(result.stdout)}))
    canaries.append(str(c.ram_folder(app, category) / token))
marker = Path('/run/petalos-dual-ram-canaries.json')
fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
with os.fdopen(fd, 'w') as output:
    json.dump(canaries, output)
