#!/usr/bin/python3 -I
"""Gracefully stop only the disposable QEMU guest selected by the audit driver."""
import os
import subprocess

assert os.geteuid() == 0
assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
subprocess.run(['systemctl', '--no-block', 'poweroff'], check=True)
