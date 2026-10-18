#!/usr/bin/env python3
"""Seed verified public Tor assets into encrypted test DATA; never a profile."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

PROJECT = Path(__file__).resolve().parents[1]
CACHE = PROJECT.parent / 'provisioning/TorBrowser'
KEYRING = PROJECT / 'config/includes.chroot/usr/local/share/portable/tor-browser-developers.keyring'
FINGERPRINT = 'EF6E286DDA85EA2A4BA7DE684E2C6E8793298290'


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''): result.update(block)
    return result.hexdigest()


def verified_assets():
    manifest = json.loads((CACHE / 'manifest.json').read_text())
    if manifest['signing_fingerprint'] != FINGERPRINT or len(manifest['assets']) != 2:
        raise RuntimeError('Unexpected public Tor asset manifest.')
    archives = [name for name in manifest['assets'] if re.fullmatch(r'tor-browser-linux-x86_64-\d+\.\d+\.\d+\.tar\.(?:xz|gz)', name)]
    if len(archives) != 1 or set(manifest['assets']) != {archives[0], archives[0] + '.asc'}:
        raise RuntimeError('Expected exactly one archive and matching signature.')
    for name, expected in manifest['assets'].items():
        path = CACHE / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size != expected['bytes'] or digest(path) != expected['sha256']:
            raise RuntimeError('Tor source asset identity or hash mismatch.')
    subprocess.run(['gpgv', '--keyring', str(KEYRING), str(CACHE / (archives[0] + '.asc')),
                    str(CACHE / archives[0])], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return manifest


def main():
    if os.geteuid() != 0 or len(sys.argv) != 2:
        raise RuntimeError('Use the prepared coordinator through sudo.')
    manifest = verified_assets()
    spec = importlib.util.spec_from_file_location('private_storage', PROJECT / 'tests/provision-vpn-root.py')
    storage = importlib.util.module_from_spec(spec); spec.loader.exec_module(storage)

    def install(target, owner, guard):
        def folder(parent, name):
            path = parent / name
            if path.is_symlink() or (path.exists() and not path.is_dir()):
                raise RuntimeError('Unexpected Tor destination directory.')
            if not path.exists():
                path.mkdir(mode=0o700); os.chown(path, owner.st_uid, owner.st_gid)
            return path

        directory = folder(folder(target, 'Applications'), 'TorBrowser')
        # Keep older public archives out of the launcher's top-level glob.
        previous = None
        for old in directory.iterdir():
            if re.fullmatch(r'tor-browser-linux-x86_64-.+\.tar\.(?:xz|gz)(?:\.asc)?', old.name):
                if old.is_symlink() or not old.is_file(): raise RuntimeError('Unexpected existing Tor asset.')
                if previous is None:
                    previous = folder(folder(directory, 'Previous'), str(time.time_ns()))
                old.rename(previous / old.name)
        for name, expected in manifest['assets'].items():
            guard()
            destination = directory / name
            fd, filename = tempfile.mkstemp(prefix='.tor-asset-', dir=directory)
            temporary = Path(filename)
            try:
                with os.fdopen(fd, 'wb') as output, (CACHE / name).open('rb') as source:
                    shutil.copyfileobj(source, output, 1024 * 1024); output.flush(); os.fsync(output.fileno())
                os.chown(temporary, owner.st_uid, owner.st_gid); temporary.chmod(0o600)
                if digest(temporary) != expected['sha256']: raise RuntimeError('Tor copied asset hash mismatch.')
                guard(); os.replace(temporary, destination)
            finally:
                if temporary.exists(): temporary.unlink()
        subprocess.run(['gpgv', '--keyring', str(KEYRING), str(directory / (next(name for name in manifest['assets'] if name.endswith('.asc')))),
                        str(directory / (next(name for name in manifest['assets'] if not name.endswith('.asc'))))],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print('Verified Tor archive and signature installed in encrypted Private/Applications/TorBrowser.', flush=True)

    storage.with_private(sys.argv[1], int(os.environ['SUDO_UID']), install)


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
