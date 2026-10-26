"""Shared split-storage provisioning contract; commands never run on import.

The caller must pin/authorize a fresh disposable target before issuing commands.
There is deliberately no migration from a populated legacy card in this module.
"""
from pathlib import Path
import json
import re
import uuid

from .releases import require
from .plans import ENCRYPTION
from .encryption import validate_calibration

VOLUMES = {
    'os': {'partition': 3, 'label': 'PORTABLE_OS', 'filesystem': 'LIVE_OS'},
    'system': {'partition': 4, 'label': 'PORTABLE_SYSTEM', 'filesystem': 'LIVE_SYSTEM'},
    'private': {'partition': 5, 'label': 'PORTABLE_DATA', 'filesystem': 'LIVE_DATA'},
}


def identities(values):
    require(set(values) == set(VOLUMES), 'OS, SYSTEM settings and Private identities are required.')
    require(all(str(uuid.UUID(value)) == value for value in values.values()) and len(set(values.values())) == 3,
            'Each encrypted volume needs a distinct canonical UUID.')
    return dict(values)


def partition_arguments(device, *, boot_mib, os_mib, system_mib):
    require(all(type(n) is int and n >= 32 for n in (boot_mib, os_mib, system_mib)), 'Invalid partition allocation.')
    return ['/usr/sbin/sgdisk', '--clear', '--new=1:2048:+2M', '--typecode=1:EF02', '--change-name=1:PETAL_BIOS',
            '--new=2:0:+' + str(boot_mib) + 'M', '--typecode=2:EF00', '--change-name=2:PETAL_BOOT',
            '--new=3:0:+' + str(os_mib) + 'M', '--typecode=3:8309', '--change-name=3:PETAL_OS',
            '--new=4:0:+' + str(system_mib) + 'M', '--typecode=4:8309', '--change-name=4:PETAL_SYSTEM',
            '--new=5:0:0', '--typecode=5:8309', '--change-name=5:PETAL_PRIVATE', str(device)]


def encryption_arguments(device, role, ident, *, profile='balanced', fixture_kdf=False, calibration=None):
    require(role in VOLUMES and profile in ENCRYPTION, 'Unknown encryption role/profile.')
    require(str(uuid.UUID(ident)) == ident, 'Invalid encryption identity.')
    policy = ENCRYPTION[profile]
    args = ['/usr/sbin/cryptsetup', 'luksFormat', '--batch-mode', '--type', 'luks2',
            '--label', VOLUMES[role]['label'], '--uuid', ident,
            '--cipher', policy['cipher'], '--key-size', str(policy['key_bits'])]
    if fixture_kdf:
        args += ['--pbkdf', 'pbkdf2', '--pbkdf-force-iterations', '1000']
    elif calibration is not None:
        calibrated = validate_calibration(profile, calibration)
        args += ['--pbkdf', 'argon2id', '--pbkdf-memory', str(calibrated['memory_kib']),
                 '--pbkdf-force-iterations', str(calibrated['iterations']), '--pbkdf-parallel', str(calibrated['parallel'])]
    else:
        args += ['--pbkdf', policy['pbkdf'], '--pbkdf-memory', str(policy['memory_kib']),
                 '--iter-time', str(policy['target_unlock_ms']), '--pbkdf-parallel', str(policy['parallel'])]
    # No supplied volume key and no copying LUKS headers: each invocation obtains
    # a fresh random volume key from cryptsetup, even when the passphrase matches.
    return [*args, '--key-file', '-', str(device)]


def boot_arguments(values, *, live_path='/live'):
    values = identities(values)
    require(live_path == '/live' or re.fullmatch(r'/petalos/releases/[a-f0-9]{24}/live', live_path),
            'Unexpected OS generation path.')
    return ['boot=live', 'components', 'username=Petal', 'hostname=PetalOS', 'toram', 'swap=false',
            'init_on_alloc=1', 'init_on_free=1', 'live-media=/dev/mapper/portable_os',
            'live-media-path=' + live_path, 'petalos.layout=2', 'petalos.os=' + values['os'],
            'petalos.system=' + values['system'], 'petalos.private=' + values['private']]


def grub_config(values):
    return ("set timeout=5\nset default=0\nsearch --no-floppy --label PORT_BOOT --set=root\n"
            "menuentry 'PetalOS' {\n linux /live/vmlinuz " + ' '.join(boot_arguments(values)) +
            " quiet splash\n initrd /live/initrd.img\n}\n")


def initialize_settings(root):
    """Create only the settings-side structure; administrator hash is separate."""
    import os
    root = Path(root)
    require(not any(p.is_symlink() for p in (root, *root.parents)), 'Unsafe settings mount path.')
    state = root / '.petalos-state'
    state.mkdir(mode=0o750)
    os.chown(state, 0, 1000)
    state.chmod(0o750)
    for relative in ('Network', 'Network/Profiles', 'Desktop', 'Applications', 'Applications/TorBrowser', 'Wallpapers'):
        path = state / relative
        path.mkdir(mode=0o700)
        os.chown(path, 1000, 1000)
    (root / '.petalos-auth').mkdir(mode=0o700)
    return state


def layout_record(values):
    return json.dumps({'format': 2, 'volumes': identities(values),
                       'system_passphrase_roles': ['os', 'system'],
                       'separate_credentials': ['private', 'administrator']}, sort_keys=True, indent=2) + '\n'
