#!/usr/bin/python3 -B
"""Synthetic sleep-hook checks, with no real storage or power operations."""
import os
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
from unittest.mock import patch

root = Path(__file__).resolve().parents[1] / 'config/includes.chroot'
script = root / 'usr/lib/systemd/system-sleep/portable-private-lock'


def scenario(phase, error=None):
    events = []
    def lock():
        events.append('lock')
        if error is not None:
            raise error
    def stop():
        events.append('power-off')
        raise SystemExit(91)
    with patch.dict(sys.modules, {'private_storage': SimpleNamespace(lock=lock, power_off=stop)}), \
         patch('os.geteuid', return_value=0), \
         patch.object(sys, 'argv', [str(script), phase, 'suspend']), \
         patch('time.monotonic', side_effect=[0, 16]), patch('time.sleep'):
        try:
            runpy.run_path(str(script))
        except SystemExit as result:
            assert result.code == (91 if error else 0)
    return events


assert scenario('pre') == ['lock']
assert scenario('post') == []
assert scenario('pre', RuntimeError('synthetic closure failure')) == ['lock', 'power-off']
assert scenario('pre', BlockingIOError()) == ['lock', 'power-off']
text = (root / 'etc/systemd/sleep.conf.d/20-petalos.conf').read_text()
for setting in ('AllowSuspend=yes', 'AllowHibernation=no', 'AllowHybridSleep=no', 'AllowSuspendThenHibernate=no'):
    assert setting in text.splitlines()
print('PASS: suspend pre-hook locks; closure failure/timeout fails closed; resume never unlocks Private; disk sleep disabled.')
