#!/usr/bin/python3 -I
"""Secret-free read-only checks on the exact release-candidate guest."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

assert os.geteuid() == 0
assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
from app_preferences import SPECS, read_bounded, validate
from desktop_settings import validate_archive
from system_state import ready, STATE

packages = subprocess.check_output(['dpkg-query', '-W', '-f=${Package}\t${db:Status-Status}\n'], text=True)
checks = {
    'VLC_packages_absent': not any(line.split('\t')[0].startswith(('vlc', 'libvlc'))
                                 and line.endswith('\tinstalled') for line in packages.splitlines()),
    'VLC_command_absent': not Path('/usr/bin/vlc').exists() and not Path('/usr/bin/vlc.portable-real').exists(),
    'VLC_role_absent': 'offline-vlc' not in c.ROLES,
    'SYSTEM_ready': ready(),
    'Private_closed': not Path('/dev/mapper/portable_data').exists(),
    'profile_loader_active': subprocess.run(['systemctl', 'is-active', '--quiet', 'portable-apparmor']).returncode == 0,
}
loaded = Path('/sys/kernel/security/apparmor/profiles').read_text().splitlines()
checks['offline_profiles_enforcing'] = all('petalos_' + app.replace('-', '_') + ' (enforce)' in loaded for app in c.OFFLINE)
checks['network_profiles_enforcing'] = all('petalos_' + app + ' (enforce)' in loaded
    for app in ('transmission', 'pan', 'amule', 'sabnzbd', 'browser', 'isolated_tor'))
store = STATE / 'AppPreferences'
checks['preferences_root_only'] = store.is_dir() and store.stat().st_uid == 0 and stat.S_IMODE(store.stat().st_mode) == 0o700
valid = True
backups_safe = True
if store.is_dir():
    for p in store.iterdir():
        if p.name == 'Backups':
            info = p.lstat()
            backups_safe = stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700
            continue
        valid = valid and p.suffix == '.json' and p.stem in SPECS
        assert valid
        info = p.lstat()
        valid = valid and stat.S_ISREG(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600
        validate(p.stem, json.loads(read_bounded(store, p.name, {0})))
checks['preferences_whitelisted'] = valid
checks['preferences_backup_directory_safe'] = backups_safe
archive = STATE / 'Desktop/desktop-settings.tar'
if archive.exists():
    fd = os.open(archive, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        validate_archive(source)
checks['desktop_archive_strict'] = True
nft = json.loads(subprocess.check_output(['/usr/sbin/nft', '-j', 'list', 'table', 'inet', 'portable_vpn']))
chains = {item['chain']['name']: item['chain'].get('policy') for item in nft['nftables'] if 'chain' in item}
checks['firewall_all_drop'] = all(chains.get(name) == 'drop' for name in ('input', 'output', 'forward'))
print(json.dumps(checks, sort_keys=True))
assert all(checks.values())
