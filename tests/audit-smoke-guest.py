#!/usr/bin/python3 -I
"""Initial checks for a fresh disposable audit guest, with Private still closed."""
from pathlib import Path
import json
import os
import subprocess
import sys

assert os.geteuid() == 0
assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
sys.path.insert(0, '/usr/local/lib/portable')
import system_state


def result(args):
    return subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=35).returncode


packages = subprocess.check_output(['dpkg-query', '-W', '-f=${Package}\t${db:Status-Status}\n'], text=True)
installed = {line.split('\t')[0] for line in packages.splitlines() if line.endswith('\tinstalled')}
checks = {
    'selective_SYSTEM_ready': system_state.ready(),
    'Private_closed_at_boot': not Path('/dev/mapper/portable_data').exists(),
    'no_legacy_automatic_Private_key': not (system_state.FULL / '.portable-keys/data.key').exists(),
    'administrator_hash_in_encrypted_SYSTEM': (system_state.FULL / '.petalos-auth/root-admin.hash').is_file(),
    'synaptic_absent': 'synaptic' not in installed,
    'VLC_absent': not any(p.startswith(('vlc', 'libvlc')) for p in installed),
    'sudo_configuration_valid': result(['/usr/sbin/visudo', '-c']) == 0,
    'Petal_password_disabled': subprocess.check_output(['passwd', '-S', 'Petal'], text=True).split()[1] == 'L',
    'no_swap': len(Path('/proc/swaps').read_text().splitlines()) == 1,
    'freed_memory_zeroing': {'init_on_alloc=1', 'init_on_free=1'} <= set(Path('/proc/cmdline').read_text().split()),
}
checks['printing_off_at_boot'] = all(result(['systemctl', 'is-active', '--quiet', unit]) != 0
    for unit in ('cups.service', 'cups.socket', 'cups.path', 'cups-browsed.service'))
try:
    checks['explicit_print_start'] = result(['/usr/local/sbin/portable-printing', 'start']) == 0
    sockets = subprocess.check_output(['ss', '-H', '-ltn'], text=True)
    checks['no_TCP_print_listener'] = not any(line.split()[3].rsplit(':', 1)[-1] == '631' for line in sockets.splitlines())
    checks['local_print_socket'] = Path('/run/cups/cups.sock').is_socket()
finally:
    checks['explicit_print_stop'] = result(['/usr/local/sbin/portable-printing', 'stop']) == 0
checks['printing_reactivation_masked'] = all(subprocess.run(['systemctl', 'is-enabled', unit],
    capture_output=True, text=True).stdout.strip() == 'masked' for unit in ('cups.service', 'cups.socket'))
table = json.loads(subprocess.check_output(['nft', '-j', 'list', 'table', 'inet', 'portable_vpn'], text=True))
chains = {item['chain']['name']: item['chain'].get('policy') for item in table['nftables'] if 'chain' in item}
checks['firewall_default_drop'] = all(chains.get(name) == 'drop' for name in ('input', 'output', 'forward'))
print(json.dumps(checks, sort_keys=True))
assert all(checks.values())
