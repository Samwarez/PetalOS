#!/usr/bin/env python3
"""Build the trixie KeePassXC sources with the reviewed atomic-save repair."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile

SOURCE_SHA256 = 'c0a14b1e1c897f5664f74284db8b339e686411cbcd300d39be8eabd424f7a325'
DEBIAN_SHA256 = '23df11fc5be1febe04607286785ebeb14f8df817604bbddadfb7c5e91eb5be4f'
OPTIONS = ['-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_INSTALL_PREFIX=/usr',
           '-DCMAKE_SKIP_RPATH=ON', '-DWITH_TESTS=ON', '-DWITH_GUI_TESTS=OFF',
           '-DWITH_XC_ALL=ON', '-DWITH_XC_UPDATECHECK=OFF', '-DWITH_XC_DOCS=OFF']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_archive', type=Path)
    parser.add_argument('debian_archive', type=Path)
    parser.add_argument('--verify-regression', action='store_true',
                        help='also prove the legacy-reader test fails without its security fix')
    args = parser.parse_args()
    assert os.geteuid() != 0, 'Compile as an ordinary user.'
    for path, expected in ((args.source_archive, SOURCE_SHA256), (args.debian_archive, DEBIAN_SHA256)):
        assert hashlib.file_digest(path.open('rb'), 'sha256').hexdigest() == expected
    project = Path(__file__).resolve().parents[2]
    patches = [Path(__file__).with_name(name) for name in
               ('atomic-flush.patch', 'legacy-reader-uaf.patch', 'legacy-reader-regression.patch')]
    destination = project/'config/includes.chroot/usr/local/share/portable/native-keepassxc'
    env = {**os.environ, 'LC_ALL': 'C.UTF-8'}
    env.setdefault('CFLAGS', '-O2 -fstack-protector-strong -D_FORTIFY_SOURCE=2')
    env.setdefault('CXXFLAGS', '-O2 -fstack-protector-strong -D_FORTIFY_SOURCE=2')
    env.setdefault('LDFLAGS', '-Wl,-z,relro,-z,now')
    with tempfile.TemporaryDirectory(prefix='petalos-keepass-build-') as directory:
        work = Path(directory)
        with tarfile.open(args.source_archive) as archive:
            archive.extractall(work, filter='data')
        source = work/'keepassxc-2.7.10'
        with tarfile.open(args.debian_archive) as archive:
            archive.extractall(source, filter='data')
        for line in (source/'debian/patches/series').read_text().splitlines():
            name = line.split('#', 1)[0].strip()
            if not name:
                continue
            assert ' ' not in name and '..' not in Path(name).parts and not Path(name).is_absolute()
            subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(source/'debian/patches'/name)],
                           cwd=source, check=True)
        for patch in patches:
            subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)], cwd=source, check=True)
        subprocess.run(['cmake', '-S', str(source), '-B', str(work/'out'), *OPTIONS], env=env, check=True)
        subprocess.run(['cmake', '--build', str(work/'out'), '--parallel', '4',
                        '--target', 'keepassxc', 'keepassxc-cli', 'testkeepass1reader'], env=env, check=True)
        subprocess.run([str(work/'out/tests/testkeepass1reader')],
                       env={**env, 'QT_QPA_PLATFORM': 'offscreen'}, check=True)
        if args.verify_regression:
            security_patch = patches[1]
            subprocess.run(['patch', '--batch', '--fuzz=0', '-R', '-p1', '-i', str(security_patch)],
                           cwd=source, check=True)
            subprocess.run(['cmake', '--build', str(work/'out'), '--parallel', '4',
                            '--target', 'testkeepass1reader'], env=env, check=True)
            negative = subprocess.run([str(work/'out/tests/testkeepass1reader'), 'testNoDeletedMetastreamReferences'],
                                      env={**env, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True)
            assert negative.returncode != 0 and b'FAIL!' in negative.stdout and b'testNoDeletedMetastreamReferences' in negative.stdout
            subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(security_patch)], cwd=source, check=True)
            subprocess.run(['cmake', '--build', str(work/'out'), '--parallel', '4', '--target',
                            'keepassxc', 'keepassxc-cli', 'testkeepass1reader'], env=env, check=True)
            subprocess.run([str(work/'out/tests/testkeepass1reader')],
                           env={**env, 'QT_QPA_PLATFORM': 'offscreen'}, check=True)
        destination.mkdir(parents=True, exist_ok=True)
        hashes = {}
        for name, relative in [('keepassxc', 'src/keepassxc'), ('keepassxc-cli', 'src/cli/keepassxc-cli')]:
            shutil.copyfile(work/'out'/relative, destination/name)
            subprocess.run(['strip', str(destination/name)], check=True)
            (destination/name).chmod(0o755)
            hashes[name] = hashlib.file_digest((destination/name).open('rb'), 'sha256').hexdigest()
        (destination/'binaries.sha256').write_text(''.join(h+'  '+n+'\n' for n,h in hashes.items()))
        (destination/'provenance.json').write_text(json.dumps({
            'debian_package_version': '2.7.10+dfsg1-1', 'source_sha256': SOURCE_SHA256,
            'debian_archive_sha256': DEBIAN_SHA256,
            'patch_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in patches},
            'binary_sha256': hashes, 'cmake_options': OPTIONS,
            'scope': 'atomic-save buffered-flush failure and CVE-2026-69150 legacy import',
            'legacy_reader_tests': 'passed',
            'legacy_reader_negative_control': args.verify_regression,
        }, indent=2)+'\n')


if __name__ == '__main__':
    main()
