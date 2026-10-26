#!/usr/bin/python3 -B
"""Build, verify in disposable VMs, and export a fresh split-storage OS bundle.

Run from a normal terminal as the desktop user. Only live-build needs sudo.
This tool never installs onto a physical drive or publishes a release.
"""
from pathlib import Path
import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RELEASES = ROOT.parent / 'releases'


def run(*arguments):
    subprocess.run([sys.executable, '-B', *map(str, arguments)], cwd=ROOT, check=True)


def completed():
    return {p.parent.resolve() for p in RELEASES.glob('*/manifest.json')}


@contextmanager
def verification_work():
    work = Path(tempfile.mkdtemp(prefix='petalos-release-verification-'))
    try:
        yield work
    except BaseException:
        print('Failed test artifacts retained privately under:', work, file=sys.stderr)
        raise
    else:
        shutil.rmtree(work)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, help='Verify/export this already completed new build instead of rebuilding')
    parser.add_argument('--version', help='Catalog version; default rc1-layout2-BUILD_TIMESTAMP')
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise RuntimeError('Run as your normal desktop user, not root.')
    os.umask(0o077)
    run(ROOT / 'tests/check-split-build-hooks.py')
    if args.release is None:
        before = completed()
        run(ROOT / 'tests/rebuild-release.py')
        created = completed() - before
        if len(created) != 1:
            raise RuntimeError('Expected exactly one newly completed build; specify --release explicitly.')
        release = created.pop()
    else:
        release = args.release.resolve(strict=True)
    if release.parent != RELEASES.resolve() or not (release / 'manifest.json').is_file():
        raise RuntimeError('Choose a completed build directly under the project releases directory.')
    version = args.version or 'rc1-layout2-' + release.name
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+_-]{0,95}', version):
        raise RuntimeError('Invalid release catalog version.')
    destination = ROOT.parent / 'release-dist' / version
    if destination.exists() or destination.is_symlink():
        raise RuntimeError('Release export already exists; choose a new --version. Existing export preserved.')
    spec = importlib.util.spec_from_file_location('split_fullboot', ROOT / 'tests/run-split-fullboot-vm.py')
    checker = importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    manifest = json.loads((release / 'manifest.json').read_text())
    # Refuse an older or changed build before creating any VM or export.
    checker.check_clean_release(release, manifest)
    with verification_work() as work:
        # Each runner allocates new images under its own directory. These test
        # initrds contain disposable credentials and never enter the export.
        run(ROOT / 'tests/run-split-storage-vm.py', release, '--work-root', work / 'focused')
        run(ROOT / 'tests/run-split-fullboot-vm.py', release, '--clean-release', '--work-root', work / 'fullboot')
        reports = sorted(work.rglob('*results.json'))
        if len(reports) != 2:
            raise RuntimeError('Expected both split-storage VM result reports.')
        checks = []
        for report in reports:
            record = json.loads(report.read_text())
            if record.get('passed') is not True:
                raise RuntimeError('A release VM check did not pass.')
            if report.name == 'fullboot-results.json' and (record.get('clean_release') is not True
                    or record.get('runtime_delta_sha256') is not None
                    or record.get('base_release') != release.name):
                raise RuntimeError('Full-boot results do not attest to this clean release without a runtime overlay.')
            checks.append({'suite': report.name, 'passed': True,
                           'sha256': hashlib.sha256(report.read_bytes()).hexdigest()})
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.mkdir()
        run(ROOT / 'scripts/bloom', 'bundle-from-build', release, '--version', version,
            '--variant', 'base', '--name', 'PetalOS RC 1 — split storage',
            '--destination', destination / 'base')
        bundle = destination / 'base'
        sums = []
        for path in sorted(bundle.iterdir()):
            if not path.is_file():
                raise RuntimeError('Unexpected directory in the exported release bundle.')
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            sums.append(digest + '  ' + path.name)
        (bundle / 'SHA256SUMS').write_text('\n'.join(sums) + '\n')
        evidence = {'format': 1, 'build': release.name, 'version': version, 'layout': 2,
                    'clean_release': True, 'runtime_overlay': False, 'vm_checks': checks,
                    'limits': ['Direct-kernel VM boot; firmware, graphical startup and hardware acceptance remain separate',
                               'Focused VM provisioning uses test-only PBKDF2; production Bloom KDF tests are separate',
                               'No physical drive modified and no release published by this command']}
        (destination / 'verification.json').write_text(json.dumps(evidence, indent=2) + '\n')
        for report in reports:
            # Result reports contain booleans/metadata; never copy test-input,
            # initramfs, disk images or the temporary fixture directory.
            (destination / report.name).write_bytes(report.read_bytes())
    print('Verified split-storage OS bundle:', destination / 'base')
    print('Release verification:', destination / 'verification.json')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print('Split release stopped: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
