#!/usr/bin/python3 -I
"""Exercise the dedicated audit tunnel without logging profiles or addresses."""
import json
import os
import subprocess
import sys
import time

assert os.geteuid() == 0
sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c

result = subprocess.run(['/usr/local/sbin/portable-vpn', 'connect', 'audit'],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
checks = {'dedicated_VPN_connected': result.returncode == 0}
ready = False;deadline = time.monotonic() + 90
while checks['dedicated_VPN_connected'] and time.monotonic() < deadline:
    try:c.gate('transmission');ready = True;break
    except Exception:time.sleep(2)
checks['live_network_and_clock_gate_ready'] = ready
print(json.dumps(checks, sort_keys=True))
assert all(checks.values())
