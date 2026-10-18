#!/usr/bin/python3 -I
"""QEMU-only boot diagnostic: publish booleans, never credential contents."""
import ctypes
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
assert os.geteuid() == 0
assert ctypes.CDLL('libc.so.6').prctl(4, 0, 0, 0, 0) == 0
assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('kvm', 'qemu')
sys.path.insert(0, '/usr/local/lib/portable')
from account_auth import load_hash
from system_state import ready
status = {'system_state_ready': ready()}
r = subprocess.run(['passwd', '-S', 'root'], capture_output=True, timeout=5)
fields = r.stdout.split()
status['root_password_configured'] = r.returncode == 0 and len(fields) > 1 and fields[1] == b'P'
try:
    stored = load_hash()
    status['stored_credential_valid'] = True
    # Compare only within the root process; neither value leaves guest memory.
    r = subprocess.run(['getent', 'shadow', 'root'], capture_output=True, timeout=5)
    fields = r.stdout.rstrip(b'\n').split(b':')
    status['active_matches_stored'] = r.returncode == 0 and len(fields) == 9 and fields[1] == stored
    del stored, fields, r
except Exception as error:
    status['stored_credential_valid'] = False
    status['load_error_type'] = type(error).__name__
target = Path('/run/petalos-admin-status.json')
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
with os.fdopen(fd, 'w') as stream:
    json.dump(status, stream)
