"""Offline verification of the paired SYSTEM passphrase, without opening DATA."""
import getpass
import os

from .linux import choose, command
from .plans import existing_layout
from .releases import require


def verify_pair(device, passphrase=None):
    require(os.geteuid() == 0, 'Recovery passphrase verification requires an administrator terminal.')
    disk = choose(device)
    layout = existing_layout(disk)
    require(layout['layout'] == 2, 'Paired recovery requires the five-partition split-storage layout.')
    if passphrase is None:
        passphrase = getpass.getpass('SYSTEM passphrase (verifies OS and settings; Private stays closed): ')
    require(passphrase and not any(c in passphrase for c in ('\0', '\n', '\r')), 'Invalid passphrase input.')
    try:
        for role in ('os', 'system'):
            require(choose(device)['identity'] == disk['identity'], 'Drive identity changed during recovery.')
            volume = layout[role]
            require(command(['/usr/sbin/cryptsetup', 'luksUUID', volume['path']]).decode().strip() == volume['uuid'],
                    'Recovery volume identity changed.')
            command(['/usr/sbin/cryptsetup', 'open', '--type', 'luks2', '--test-passphrase',
                     '--key-file', '-', volume['path']], payload=passphrase.encode(), timeout=180)
        return {'verified': True, 'os_and_system_same_passphrase': True,
                'volumes_opened': False, 'private_opened': False,
                'note': 'Independent OS and SYSTEM headers require separate recovery backups. Restoring an old header can restore retired password slots.'}
    finally:
        passphrase = None
