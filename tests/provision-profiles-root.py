#!/usr/bin/python3
"""Seed only Sam's two selected WireGuard profiles into a detached test clone.

No payloads are copied into build inputs, printed, or written outside DATA.
"""
from pathlib import Path
import importlib.util
import os
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'config/includes.chroot/usr/local/lib/portable'))
from vpn_profiles import atomic_write, read_profile, safe_directory, serialize


def validated_assets():
    return {
        name: read_profile(path, protected=False)
        for name, path in (
            ('zrh43', Path('/home/sam/Desktop/zrh43-adb.conf')),
            ('got82', Path('/home/sam/Downloads/got82-adb.conf')),
        )
    }


def main():
    if os.geteuid() != 0 or len(sys.argv) != 2:
        raise RuntimeError('Use the preserved-clone coordinator through sudo.')
    assets = validated_assets()
    spec = importlib.util.spec_from_file_location('storage', PROJECT / 'tests/provision-vpn-root.py')
    storage = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(storage)

    def install(target, owner, guard):
        directory = target / 'Network/Profiles'
        safe_directory(directory)
        directory.parent.mkdir(mode=0o700, exist_ok=True)
        os.chown(directory.parent, owner.st_uid, owner.st_gid)
        directory.mkdir(mode=0o700, exist_ok=True)
        os.chown(directory, owner.st_uid, owner.st_gid)
        os.chmod(directory, 0o700)
        for name, profile in assets.items():
            guard()
            destination = directory / f'{name}.conf'
            if destination.exists() or destination.is_symlink():
                raise RuntimeError('A selected profile already exists; it was not overwritten.')
            atomic_write(destination, serialize(profile), owner.st_uid)
            installed = read_profile(destination)
            if serialize(installed) != serialize(profile):
                raise RuntimeError('Installed profile verification failed; contents suppressed.')
        guard()
        marker = directory.parent / 'selected-profile'
        if not marker.exists() and not marker.is_symlink():
            atomic_write(marker, 'zrh43\n', owner.st_uid)
        print('Two validated encrypted profiles installed with mode 600.', flush=True)

    storage.with_private(Path(sys.argv[1]), int(os.environ['SUDO_UID']), install)


if __name__ == '__main__':
    os.umask(0o077)
    try:
        main()
    except Exception:
        print('Profile provisioning failed. No configuration contents were logged.', file=sys.stderr)
        sys.exit(1)
