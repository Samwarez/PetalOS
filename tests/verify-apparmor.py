#!/usr/bin/env python3
"""Acceptance checks over pinned SSH; no secret files or raw app logs printed."""
from pathlib import Path
import json
import shlex
import sys
from importlib.util import spec_from_file_location, module_from_spec

directory = Path(__file__).resolve().parent
spec = spec_from_file_location('guest_ssh',directory/'guest-ssh.py')
guest = module_from_spec(spec)
spec.loader.exec_module(guest)

def verify(command,timeout=60):
    response = guest.execute(command,timeout=timeout)
    if response.returncode:
        raise RuntimeError('AppArmor verification failed; raw output suppressed.')
    result = json.loads(response.stdout)
    if not all(result.values()):
        raise RuntimeError('AppArmor verification reported a failed check.')
    print(json.dumps(result,sort_keys=True))

try:
    verify('sudo -n python3 -c '+shlex.quote((directory/'apparmor-guest.py').read_text()))
    # Start the normal backend only if needed; do not stop an existing session.
    active = guest.execute('systemctl --user is-active --quiet portable-sabnzbd.service').returncode == 0
    try:
        response = guest.execute('/usr/local/bin/portable-sab-manager prepare',timeout=60)
        if response.returncode:
            raise RuntimeError('SAB bridge preparation failed; output suppressed.')
        verify('env DISPLAY=:0 PORTABLE_SAB_ADMIN=1 /usr/local/bin/portable-offline /usr/bin/python3 -c '+
               shlex.quote((directory/'apparmor-sab-probe.py').read_text()),timeout=30)
    finally:
        if not active:
            guest.execute('/usr/local/bin/portable-sab-manager stop')
except Exception as error:
    print(str(error),file=sys.stderr)
    sys.exit(1)
