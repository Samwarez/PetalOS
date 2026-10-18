#!/usr/bin/env python3
"""Build the reviewed trixie Parole source into the live-build input tree."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile

SOURCE_SHA256 = '6625288b760d38a15c295051ecf66c556fcad21dd1516d6d661c2a582421ee0e'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_archive', type=Path)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[2]
    patch = Path(__file__).with_name('native-gtk.patch')
    assert hashlib.sha256(args.source_archive.read_bytes()).hexdigest() == SOURCE_SHA256
    destination = project / 'config/includes.chroot/usr/local/share/portable/native-parole'
    with tempfile.TemporaryDirectory(prefix='petalos-native-parole-') as temporary:
        with tarfile.open(args.source_archive) as archive:
            archive.extractall(temporary, filter='data')
        source = Path(temporary) / 'parole-4.18.2'
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)], cwd=source, check=True)
        subprocess.run(['./configure', '--prefix=/usr', '--disable-x11', '--enable-wayland',
                        '--disable-clutter', '--disable-notify-plugin', '--disable-tray-plugin',
                        '--disable-mpris2-plugin', '--disable-gtk-doc', '--disable-taglib'],
                       cwd=source, check=True)
        subprocess.run(['make', '-j4'], cwd=source, check=True)
        subprocess.run(['strip', source / 'src/parole'], check=True)
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / 'src/parole', destination / 'parole')
        os.chmod(destination / 'parole', 0o755)
    checksum = hashlib.sha256((destination / 'parole').read_bytes()).hexdigest()
    (destination / 'parole.sha256').write_text(checksum + '  parole\n')
    (destination / 'provenance.json').write_text(json.dumps({
        'debian_package_version': '4.18.2-1', 'source_sha256': SOURCE_SHA256,
        'patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
        'binary_sha256': checksum, 'x11': False, 'video_sink': 'gtksink'}, indent=2) + '\n')


if __name__ == '__main__':
    main()
