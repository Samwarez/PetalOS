#!/usr/bin/env python3
"""Reuse only verified public trixie archives from the managed guest's cache."""
from pathlib import Path
import datetime
import hashlib
import importlib.util
import json
import shlex
import subprocess

PROJECT = Path(__file__).resolve().parents[1]
PACKAGES = {
    'labwc': '0.8.3-1', 'wayland-utils': '1.2.0-2',
    'swaybg': '1.2.1-1', 'swayidle': '1.8.0-1', 'gtklock': '4.0.0-1',
    'libgtk-session-lock0': '0.2.0-2', 'libwlroots-0.18': '0.18.2-3',
    'libxcb-res0': '1.17.0-2+b1', 'libxcb-ewmh2': '0.4.2-1',
    'libxcb-errors0': '1.0.1-4', 'libseat1': '0.9.1-1',
    'libliftoff0': '0.5.0-1.1', 'libsfdo0': '0.1.3-1+b1',
}

def main():
    spec = importlib.util.spec_from_file_location('guest', PROJECT/'tests/guest-ssh.py')
    guest = importlib.util.module_from_spec(spec); spec.loader.exec_module(guest)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    output = PROJECT.parent/'testing/public-packages'/stamp
    output.mkdir(parents=True, mode=0o700)
    manifest = []
    for name, version in PACKAGES.items():
        metadata = guest.execute('apt-cache show '+shlex.quote(name+'='+version), 20)
        if metadata.returncode:
            raise RuntimeError('Approved package metadata unavailable.')
        records = [dict(line.split(': ', 1) for line in block.splitlines() if ': ' in line)
                   for block in metadata.stdout.decode().strip().split('\n\n')]
        matches = [r for r in records if r.get('Package') == name and r.get('Version') == version
                   and r.get('Architecture') == 'amd64' and 'SHA256' in r]
        hashes = {r['SHA256'] for r in matches}
        if len(hashes) != 1:
            raise RuntimeError('Package metadata is missing or ambiguous.')
        code = ('from pathlib import Path; import sys; '
                'matches=list(Path("/var/cache/apt/archives").glob('+repr(name+'_*.deb')+')); '
                'assert len(matches)==1 and not matches[0].is_symlink(); '
                'sys.stdout.buffer.write(matches[0].read_bytes())')
        archive = guest.execute('python3 -c '+shlex.quote(code), 30)
        checksum = hashlib.sha256(archive.stdout).hexdigest()
        if archive.returncode or checksum not in hashes:
            raise RuntimeError('Cached archive failed signed APT metadata digest validation.')
        target = output/(name+'.deb'); target.write_bytes(archive.stdout)
        identity = subprocess.check_output(['dpkg-deb', '-f', str(target),
                                            'Package', 'Version', 'Architecture'], text=True)
        if identity.splitlines() != ['Package: '+name, 'Version: '+version, 'Architecture: amd64']:
            raise RuntimeError('Archive identity differs from approved trixie package.')
        manifest.append({'file': target.name, 'package': name, 'version': version, 'sha256': checksum})
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('Verified public trixie package cache:', output)
    print('Archives:', len(manifest), '; no guest settings or credentials copied.')

if __name__ == '__main__':
    main()
