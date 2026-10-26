"""Verify the actual booted image and the specified initial uplink state."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time

assert os.geteuid() == 0
assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
import system_state

expected = json.loads(Path('/tmp/petalos-combined-expected.json').read_text())
bad_files = []
for name, digest in expected['public_files'].items():
    p = Path('/')/name
    if name == 'etc/hosts':
        # Debian live-config adds the configured hostname to localhost at boot.
        continue
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
        bad_files.append(name)
generation = expected['generation']
medium = Path('/run/live/medium')
command = Path('/proc/cmdline').read_text().split()
checks = {
    'public_files_match_built_image': not bad_files,
    'generation_boot_selected': 'live-media-path=/petalos/releases/'+generation+'/live' in command,
    'live_medium_is_RAM': subprocess.check_output(['findmnt', '-n', '-o', 'FSTYPE', '--mountpoint', str(medium)], text=True).strip() == 'tmpfs',
    'only_selected_generation_in_RAM': [p.name for p in (medium/'petalos/releases').iterdir()] == [generation],
    'SYSTEM_credentials_not_copied_into_live_RAM_medium': not (medium/'.petalos-auth').exists(),
    'SYSTEM_settings_not_copied_into_live_RAM_medium': not (medium/'.petalos-state').exists(),
    'SYSTEM_state_ready': system_state.ready(),
    'Private_closed_at_boot': not Path('/dev/mapper/portable_data').exists(),
    'no_swap': len(Path('/proc/swaps').read_text().splitlines()) == 1,
    'RAM_zeroing_options': {'init_on_alloc=1', 'init_on_free=1'} <= set(command),
    'Secure_Boot_enabled': any(p.read_bytes()[-1:] == b'\x01' for p in Path('/sys/firmware/efi/efivars').glob('SecureBoot-*')),
    'audit_initrd_marker_absent': b'PETALOS_REPAIR_UNSIGNED_INITRD_MARKER' not in subprocess.check_output(['dmesg']),
    'no_tunnel_at_desktop_boot': not Path('/sys/class/net/wg0').exists(),
}
checks['hosts_has_only_expected_live_config_change'] = [line.split() for line in Path('/etc/hosts').read_text().splitlines()] == [
    ['127.0.0.1', 'localhost', 'PetalOS'], ['127.0.1.1', 'PetalOS'],
    ['::1', 'localhost', 'ip6-localhost', 'ip6-loopback'],
    ['ff02::1', 'ip6-allnodes'], ['ff02::2', 'ip6-allrouters']]
uplinks = [p for p in Path('/sys/class/net').iterdir() if p.name != 'lo']
carrier = '0' if expected.get('offline', True) else '1'
checks['expected_uplink_carrier_state'] = bool(uplinks) and all((p/'carrier').read_text().strip() == carrier for p in uplinks)
checks['pre_VPN_network_gate_denied'] = subprocess.run(['/usr/local/sbin/portable-check-network-ready'], capture_output=True, timeout=25).returncode != 0
for name in ('Documents', 'Downloads'):
    checks[name+'_is_tmpfs'] = subprocess.check_output(['findmnt', '-n', '-o', 'FSTYPE', '--mountpoint', '/home/Petal/'+name], text=True).strip() == 'tmpfs'
def entered(unit):
    return int(subprocess.check_output(['systemctl', 'show', '-p', 'ActiveEnterTimestampMonotonic', '--value', unit], text=True))
checks['content_ready_before_desktop'] = 0 < entered('portable-ram-content.service') <= entered('display-manager.service')
checks['no_failed_system_units'] = not subprocess.check_output(['systemctl', '--failed', '--no-legend', '--plain'], text=True).strip()
deadline = time.monotonic()+30
while True:
    checks['Wayland_desktop_running'] = all(subprocess.run(['pgrep', '-u', '1000', '-x', name], capture_output=True).returncode == 0 for name in ('labwc', 'xfce4-panel', 'swaybg'))
    if checks['Wayland_desktop_running'] or time.monotonic() >= deadline:break
    time.sleep(.25)
print(json.dumps({'checks': checks, 'public_files_checked': len(expected['public_files']), 'mismatched_public_paths': bad_files}))
assert all(checks.values())
