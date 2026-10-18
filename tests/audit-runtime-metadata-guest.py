#!/usr/bin/python3 -I
"""Bounded runtime readiness categories; no addresses, credentials or user files."""
from pathlib import Path
import json
import subprocess

record = Path('/run/portable-vpn-checks.json')
report = json.loads(record.read_text()) if record.exists() else {}
checks = {name: value.get('status') for name, value in report.get('checks', {}).items()}
desktop = {}
for name in ('labwc', 'xfce4-session', 'xfce4-panel', 'swaybg'):
    desktop[name] = subprocess.run(['pgrep', '-u', '1000', '-x', name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
print(json.dumps({'automatic_VPN_checks': checks, 'desktop_processes': desktop,
                  'Private_closed': not Path('/dev/mapper/portable_data').exists(),
                  'SecureBoot_enabled': any(p.read_bytes()[-1:] == b'\x01' for p in Path('/sys/firmware/efi/efivars').glob('SecureBoot-*')),
                  'kernel_lockdown_active': '[integrity]' in Path('/sys/kernel/security/lockdown').read_text()
                      or '[confidentiality]' in Path('/sys/kernel/security/lockdown').read_text()}, sort_keys=True))
