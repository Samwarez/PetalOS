#!/usr/bin/env python3
"""Build trixie's Conky with a display-only Wayland input region."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile

SOURCE_SHA256 = '9959fde719d3d4340ab973aadbeb97a03e9f6bf4f928be0de69cfb02871d522e'
OPTIONS = ['-DCMAKE_INSTALL_PREFIX=/usr', '-DCMAKE_BUILD_TYPE=Release',
           '-DBUILD_WAYLAND=ON', '-DBUILD_X11=ON', '-DBUILD_WLAN=ON',
           '-DBUILD_JOURNAL=ON', '-DBUILD_DOCS=OFF', '-DBUILD_EXTRAS=OFF',
           '-DBUILD_TESTING=OFF', '-DUSE_CCACHE=OFF', '-DREPRODUCIBLE_BUILD=ON',
           '-DCMAKE_SKIP_RPATH=ON']


def stage(executable):
    destination = Path(__file__).resolve().parents[2] / 'config/includes.chroot/usr/local/share/portable/native-conky'
    patch = Path(__file__).with_name('click-through.patch')
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(executable, destination / 'conky')
    subprocess.run(['strip', str(destination / 'conky')], check=True)
    os.chmod(destination / 'conky', 0o755)
    checksum = hashlib.sha256((destination / 'conky').read_bytes()).hexdigest()
    (destination / 'conky.sha256').write_text(checksum + '  conky\n')
    (destination / 'provenance.json').write_text(json.dumps({
        'debian_package_version': '1.22.1-1', 'source_sha256': SOURCE_SHA256,
        'patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
        'binary_sha256': checksum, 'wayland_input': 'empty region',
        'cmake_options': OPTIONS}, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_archive', type=Path)
    args = parser.parse_args()
    assert hashlib.sha256(args.source_archive.read_bytes()).hexdigest() == SOURCE_SHA256
    patch = Path(__file__).with_name('click-through.patch')
    environment = os.environ.copy()
    for flag in ('CFLAGS', 'CXXFLAGS'):
        environment.setdefault(flag, '-O2 -g -fstack-protector-strong -D_FORTIFY_SOURCE=2')
    environment.setdefault('LDFLAGS', '-Wl,-z,relro,-z,now')
    with tempfile.TemporaryDirectory(prefix='petalos-native-conky-') as temporary:
        with tarfile.open(args.source_archive) as archive:
            archive.extractall(temporary, filter='data')
        source = Path(temporary) / 'conky-1.22.1'
        output = Path(temporary) / 'out'
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)], cwd=source, check=True)
        subprocess.run(['cmake', '-S', str(source), '-B', str(output), *OPTIONS], env=environment, check=True)
        subprocess.run(['cmake', '--build', str(output), '--parallel', '4'], env=environment, check=True)
        executable = output / 'src/conky'
        stage(executable)


if __name__ == '__main__':
    main()
