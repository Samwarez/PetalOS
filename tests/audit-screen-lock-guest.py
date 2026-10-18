#!/usr/bin/python3 -I
"""Establish the real graphical locker before host-side test credential input."""
from pathlib import Path
import os
import subprocess
import sys

assert os.geteuid() == 0
assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
assert not Path('/dev/mapper/portable_data').exists()
sys.path.insert(0, '/usr/local/lib/portable')
from desktop_session import environment
subprocess.run(['/usr/bin/setpriv', '--reuid=1000', '--regid=1000', '--clear-groups',
                '--', '/usr/local/bin/portable-lock'], env=environment(),
               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
               timeout=30, check=True)
print('Graphical locker established; Private remains closed.')
