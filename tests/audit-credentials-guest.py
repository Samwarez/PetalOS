#!/usr/bin/python3 -I
"""Synthetic credential boundaries; input is test-only JSON on stdin."""
from pathlib import Path
import json
import os
import re
import secrets
import sys

assert os.geteuid() == 0
values = json.load(sys.stdin)
assert set(values) == {'system', 'administrator', 'private'}
assert all(re.fullmatch(r'Audit-[0-9a-f]{24}', v) for v in values.values())
assert len(set(values.values())) == 3
sys.path.insert(0, '/usr/local/lib/portable')
import private_storage as p
assert not Path('/dev/mapper/portable_data').exists()
checks = {'SYSTEM_accepted_for_screen_auth': p.authenticate_system(values['system'].encode()),
          'Private_rejected_for_screen_auth': not p.authenticate_system(values['private'].encode()),
          'SYSTEM_rejected_for_Private': not p.unlock(values['system'].encode()),
          'administrator_rejected_for_Private': not p.unlock(values['administrator'].encode()),
          'wrong_credentials_leave_Private_closed': not Path('/dev/mapper/portable_data').exists()}
fixture = Path('/mnt/private') / ('petalos-disposable-audit-' + secrets.token_hex(12) + '.txt')
created = False
try:
    checks['Private_accepted_for_Private'] = p.unlock(values['private'].encode(), raise_errors=True)
    with fixture.open('x') as output:
        created = True;output.write('synthetic audit fixture only\n')
    checks['Private_content_writable'] = fixture.read_text() == 'synthetic audit fixture only\n'
finally:
    if created:fixture.unlink(missing_ok=True)
    if Path('/dev/mapper/portable_data').exists():p.lock()
checks['manual_lock_closes_Private_mapping'] = not Path('/dev/mapper/portable_data').exists()
checks['SYSTEM_auth_still_works_after_Private_lock'] = p.authenticate_system(values['system'].encode())
checks['SYSTEM_auth_does_not_reopen_Private'] = not Path('/dev/mapper/portable_data').exists()
print(json.dumps(checks, sort_keys=True))
assert all(checks.values())
