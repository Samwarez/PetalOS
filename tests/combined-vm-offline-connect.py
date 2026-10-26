"""A real selected-profile connection attempt must fail closed without uplink."""
from pathlib import Path
import json
import os
import subprocess
import time

assert os.geteuid() == 0
assert not Path('/sys/class/net/wg0').exists()
uplinks = [p for p in Path('/sys/class/net').iterdir() if p.name != 'lo']
assert uplinks and all((p/'carrier').read_text().strip() == '0' for p in uplinks)
started = time.monotonic()
result = subprocess.run(['/usr/local/sbin/portable-vpn', 'connect', 'audit'], capture_output=True, timeout=115)
checks = {'offline_connection_reports_failure': result.returncode != 0,
          'failed_connection_removed_tunnel': not Path('/sys/class/net/wg0').exists(),
          'readiness_denied_after_failure': subprocess.run(['/usr/local/sbin/portable-check-network-ready'], capture_output=True, timeout=25).returncode != 0}
table = json.loads(subprocess.check_output(['nft', '-j', 'list', 'table', 'inet', 'portable_vpn']))
chains = {e['chain']['name']: e['chain'].get('policy') for e in table['nftables'] if 'chain' in e}
checks['all_firewall_default_policies_still_drop'] = all(chains.get(n) == 'drop' for n in ('input', 'output', 'forward'))
print(json.dumps({'checks': checks, 'seconds': round(time.monotonic()-started, 2)}))
assert all(checks.values())
