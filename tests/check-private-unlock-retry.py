#!/usr/bin/python3 -B
"""Synthetic retry/cancel/storage-failure checks; never accesses a real volume."""
from contextlib import redirect_stderr
import importlib.machinery
import io
from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

root = Path(__file__).resolve().parents[1] / 'config/includes.chroot/usr/local'
s = importlib.machinery.SourceFileLoader('retry_storage', str(root / 'lib/portable/private_storage.py')).load_module()
helper = runpy.run_path(str(root / 'sbin/portable-unlock-data'), run_name='under_test')['main']
phrase = b'public-synthetic-passphrase-fixture'
for code, message, rejected in [
    (2, b'No key available with this passphrase.\n', True),
    (2, b'Permission denied.\n', False),
    (1, b'Invalid option.\n', False),
    (3, b'Out of memory.\n', False),
    (4, b'Wrong device.\n', False),
    (5, b'Device already exists or is busy.\n', False),
]:
    result = SimpleNamespace(returncode=code, stderr=message)
    with patch.object(s.subprocess, 'run', return_value=result):
        try:
            s.command(['/usr/sbin/cryptsetup', 'open', '--key-file', '-', '/synthetic/device'], password=phrase)
        except s.StorageOperationError as e:
            assert isinstance(e, s.PassphraseRejected) == rejected
            assert e.returncode == code and phrase.decode() not in str(e)
        else:
            raise AssertionError('Failure was accepted')
print('PASS: passphrase rejection distinguished from permission/device/memory/busy errors')


def scenario(events, responses, expected_modes, expected_exit):
    seen = []
    attempts = []
    prompt_objects = []
    repaired = []

    def prompt(args, **kwargs):
        seen.append(args[-1])
        code = next(responses)
        result = SimpleNamespace(returncode=code, stdout=phrase)
        prompt_objects.append(result)
        return result

    def unlock(secret, **kwargs):
        assert secret == phrase and kwargs == {'raise_errors': True}
        attempts.append(True)
        event = next(events)
        if isinstance(event, Exception):
            raise event
        return event

    fake = SimpleNamespace(unlock=unlock, boot_unlock=lambda: None, PassphraseRejected=s.PassphraseRejected)
    error = io.StringIO()
    with patch.dict(sys.modules, {'private_storage': fake, 'desktop_session': SimpleNamespace(environment=lambda: {}), 'compartments': SimpleNamespace(private_content_parent=repaired.append)}), \
         patch('os.geteuid', return_value=0), patch.dict('os.environ', {'SUDO_USER': 'Petal'}), \
         patch.object(sys, 'argv', ['portable-unlock-data', '--desktop']), \
         patch('subprocess.run', side_effect=prompt), redirect_stderr(error):
        assert helper() == expected_exit
    assert repaired == (['Documents', 'Downloads'] if expected_exit == 0 else [])
    assert seen == expected_modes
    assert all(p.stdout == b'' for p in prompt_objects), 'Prompt buffer reference was retained'
    assert phrase.decode() not in error.getvalue()
    return attempts


scenario(iter([s.PassphraseRejected(2), True]), iter([0, 0]),
         ['--data-password', '--data-password-retry'], 0)
scenario(iter([s.PassphraseRejected(2), s.PassphraseRejected(2), True]), iter([0, 0, 0]),
         ['--data-password', '--data-password-retry', '--data-password-retry'], 0)
scenario(iter([s.PassphraseRejected(2)]), iter([0, 1]),
         ['--data-password', '--data-password-retry'], 1)
assert not scenario(iter([]), iter([1]), ['--data-password'], 1)
scenario(iter([s.StorageOperationError(4)]), iter([0]), ['--data-password'], 1)
print('PASS: rejected entry retries, repeated rejection retries, cancel stops, storage errors do not retry')
