#!/usr/bin/python3 -B
"""Lock callers return at compositor readiness, with recovery delegated to unlock."""
import os
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

script = Path(__file__).resolve().parents[1] / 'config/includes.chroot/usr/local/bin/portable-lock'
for storage_code, auth_code in ((0, 0), (0, 1), (1, 0)):
    calls = []
    fd, temporary = tempfile.mkstemp()
    def run(args, **kwargs):
        calls.append(args)
        if args[0] == '/usr/bin/sudo':
            return SimpleNamespace(returncode=storage_code)
        if args[0] == '/usr/bin/gtklock':
            return SimpleNamespace(returncode=auth_code)
        return SimpleNamespace(returncode=0)
    try:
        with patch.dict(sys.modules, {'desktop_session': SimpleNamespace(environment=lambda: {})}), \
             patch.object(sys, 'argv', ['portable-lock']), \
             patch('os.getuid', return_value=1000), patch('os.open', return_value=fd), \
             patch('os.fstat', return_value=SimpleNamespace(st_uid=1000, st_mode=0o100600)), \
             patch('subprocess.run', side_effect=run):
            try:
                runpy.run_path(str(script))
            except SystemExit as error:
                assert error.code == 1 and (storage_code or auth_code)
        assert all(args[0] != '/usr/local/libexec/portable-display-wake' for args in calls)
        lockers = [args for args in calls if args[0] == '/usr/bin/gtklock']
        if storage_code:
            assert not lockers
        else:
            assert len(lockers) == 1
            assert '--daemonize' in lockers[0]
            index = lockers[0].index('--unlock-command')
            assert lockers[0][index + 1] == '/usr/local/libexec/portable-display-wake'
            assert calls[0][0] == '/usr/bin/sudo'
    finally:
        os.close(fd)
        Path(temporary).unlink()
print('PASS: storage closes before lock-ready handshake; display wake is delegated exclusively to the locker unlock hook.')
