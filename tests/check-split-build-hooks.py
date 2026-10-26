#!/usr/bin/python3 -B
"""Reproduce the missing-helper build failure and verify early initrd packaging.

Uses only private temporary directories and Debian's real initramfs-tools
copy functions. It does not run update-initramfs, sudo, or a disk operation.
Only the installation source/destination paths are relocated for this test.
"""
from pathlib import Path
import importlib.util
import os
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rebuild', ROOT / 'tests/rebuild-release.py')
build = importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
INSTALLER = 'hooks/live/0080-split-storage.hook.chroot'
INITRD = 'includes.chroot/etc/initramfs-tools/hooks/petalos-split-storage'
NATIVE = 'includes.chroot/usr/local/share/portable/native-split-unlock'


def check(name, condition):
    if not condition:
        raise RuntimeError('FAIL ' + name)
    print('PASS ' + name, flush=True)


def refused(config, expected):
    try:
        build.validate_split_storage(config)
    except RuntimeError as error:
        check(expected, expected in str(error))
    else:
        raise RuntimeError('Expected refusal: ' + expected)


def shell(source, environment):
    return subprocess.run(['/bin/sh'], input=source, env=environment,
                          text=True, capture_output=True, timeout=30)


def main():
    with tempfile.TemporaryDirectory(prefix='split-build-hook-check-') as temporary:
        work = Path(temporary)
        config = work / 'config'
        for name in (INSTALLER, INITRD, NATIVE + '/portable-unlock-pair', NATIVE + '/provenance.json',
                     'hooks/live/0912-generation-ram-copy.hook.chroot',
                     'hooks/live/0993-phase2-branding.hook.chroot'):
            target = config / name;target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / 'config' / name, target)
        build.validate_split_storage(config)
        check('production helper is installed before both initramfs refreshes', True)
        installer = config / INSTALLER
        late = installer.with_name('0992-split-storage.hook.chroot')
        installer.rename(late)
        refused(config, 'Missing executable early split-storage installation hook')
        late.rename(installer)
        premature = installer.with_name('0070-premature-initramfs.hook.chroot')
        premature.write_text('#!/bin/sh\nupdate-initramfs -u -k all\n')
        refused(config, 'Split-storage helper must be installed before initramfs refresh')
        premature.unlink()
        installer.chmod(0o644)
        refused(config, 'Missing executable early split-storage installation hook')
        installer.chmod(0o755)
        hook = config / INITRD
        hook.chmod(0o644)
        refused(config, 'Missing executable split-storage initramfs hook')
        hook.chmod(0o755)
        native = config / NATIVE / 'portable-unlock-pair'
        original = native.read_bytes()
        native.write_bytes(original + b'changed')
        refused(config, 'Rebuild the reviewed split-storage unlock helper')
        native.write_bytes(original)

        # Keep Debian's installed hook-functions untouched. Relocate only the
        # privileged install location into a new, user-owned fixture tree.
        installed = work / 'installed/usr/local/libexec/portable-unlock-pair'
        installed.parent.mkdir(parents=True)
        initrd = work / 'initrd';initrd.mkdir()
        environment = dict(os.environ, DESTDIR=str(initrd), verbose='n')
        initrd_source = hook.read_text().replace('/usr/local/libexec/portable-unlock-pair',
                                               shlex.quote(str(installed)))
        result = shell(initrd_source, environment)
        check('real initramfs hook reproduces the missing-helper failure', result.returncode != 0)
        install_source = installer.read_text().replace(
            "Path('/usr/local/share/portable/native-split-unlock')", 'Path(' + repr(str(config / NATIVE)) + ')').replace(
            "Path('/usr/local/libexec/portable-unlock-pair')", 'Path(' + repr(str(installed)) + ')')
        result = shell(install_source, environment)
        check('early installation copies the exact verified executable',
              result.returncode == 0 and installed.read_bytes() == original and os.access(installed, os.X_OK))
        result = shell(initrd_source, environment)
        check('real Debian initramfs hook succeeds after early installation', result.returncode == 0)
        check('initrd contains the exact production helper and askpass',
              (initrd / 'usr/bin/portable-unlock-pair').read_bytes() == original
              and (initrd / 'usr/lib/cryptsetup/askpass').read_bytes() == Path('/usr/lib/cryptsetup/askpass').read_bytes())
        result = shell(initrd_source, environment)
        check('repeated initramfs population remains successful', result.returncode == 0)
        archive = work / 'test-initrd.cpio'
        files = sorted(str(p.relative_to(initrd)) for p in initrd.rglob('*'))
        result = subprocess.run(['cpio', '--null', '-o', '-H', 'newc'],
                                input=('\0'.join(files) + '\0').encode(), cwd=initrd,
                                capture_output=True, timeout=30, check=True)
        archive.write_bytes(result.stdout)
        listing = subprocess.check_output(['lsinitramfs', str(archive)], text=True).splitlines()
        check('completed initrd archive lists paired helper and askpass',
              {'usr/bin/portable-unlock-pair', 'usr/lib/cryptsetup/askpass'} <= set(listing))


if __name__ == '__main__':
    main()
