#!/usr/bin/python3 -B
"""Boot the real completed OS with reviewed layout-2 code on fresh virtual media.

Produces a disposable test image, never a publishable release: its test initrd
contains fresh test-only credentials. No existing image or physical disk is used.
"""
from pathlib import Path
import argparse
import gzip
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('split_vm', ROOT / 'tests/run-split-storage-vm.py')
vm = importlib.util.module_from_spec(spec);spec.loader.exec_module(vm)


def check_clean_release(release, manifest):
    """Refuse source overlays or stale production startup in clean-build tests."""
    for relative in ('binary/live/vmlinuz', 'binary/live/initrd.img',
                     'binary/live/filesystem.squashfs', 'live-image-amd64.hybrid.iso'):
        path = release / 'build' / relative
        record = manifest[relative]
        if path.stat().st_size != record['bytes'] or vm.digest(path) != record['sha256']:
            raise RuntimeError('Completed release payload failed verification: ' + relative)
    public = ROOT / 'config/includes.chroot'
    previous = release / 'build/config/includes.chroot'
    for source in public.rglob('*'):
        if not source.is_file() or '__pycache__' in source.parts or source.suffix == '.pyc':
            continue
        relative = source.relative_to(public)
        staged = previous / relative
        if not staged.is_file() or vm.digest(source) != vm.digest(staged):
            raise RuntimeError('Clean release does not contain the current build input: ' + str(relative))
    rootfs = release / 'build/binary/live/filesystem.squashfs'
    for name in ('private_storage.py', 'storage_layout.py', 'system_state.py', 'account_auth.py'):
        relative = 'usr/local/lib/portable/' + name
        actual = subprocess.check_output(['/usr/bin/unsquashfs', '-cat', str(rootfs), relative])
        if actual != (public / relative).read_bytes():
            raise RuntimeError('Clean rootfs has different storage code: ' + name)
    native = public / 'usr/local/share/portable/native-split-unlock/portable-unlock-pair'
    actual = subprocess.check_output(['/usr/bin/unsquashfs', '-cat', str(rootfs),
                                      'usr/local/libexec/portable-unlock-pair'])
    if actual != native.read_bytes():
        raise RuntimeError('Clean rootfs has a different paired-unlock helper.')
    with tempfile.TemporaryDirectory(prefix='split-clean-initrd-') as temporary:
        extracted = Path(temporary)
        subprocess.run(['/usr/bin/unmkinitramfs', str(release / 'build/binary/live/initrd.img'),
                        str(extracted)], check=True, stdout=subprocess.DEVNULL)
        for name in ('portable-unlock', 'petalos-startup'):
            matches = list(extracted.rglob('scripts/init-premount/' + name))
            expected = (public / 'etc/initramfs-tools/scripts/init-premount' / name).read_bytes()
            if len(matches) != 1 or matches[0].read_bytes() != expected:
                raise RuntimeError('Clean initramfs has different startup code: ' + name)
        matches = [p for p in extracted.rglob('portable-unlock-pair') if p.is_file()]
        if not matches or any(p.read_bytes() != native.read_bytes() for p in matches):
            raise RuntimeError('Clean initramfs is missing the reviewed paired-unlock helper.')


def repack_provision(work, release):
    with (work / 'fixture-initrd.img').open('wb') as output:
        with (release / 'build/binary/live/initrd.img').open('rb') as original:
            shutil.copyfileobj(original, output)
        output.write(gzip.compress(vm.archive_tree(work / 'overlay'), compresslevel=1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release', type=Path)
    parser.add_argument('--work-root', type=Path, help='Directory for newly allocated disposable artifacts')
    parser.add_argument('--clean-release', action='store_true',
                        help='Require the current clean build and boot its unmodified production storage code')
    args = parser.parse_args()
    os.umask(0o077)
    release = args.release.resolve(strict=True)
    assert release.parent == ROOT.parent / 'releases'
    manifest = json.loads((release / 'manifest.json').read_text())
    if args.clean_release:
        check_clean_release(release, manifest)
    iso = release / 'build/live-image-amd64.hybrid.iso'
    assert vm.digest(iso) == manifest['live-image-amd64.hybrid.iso']['sha256']
    work, data = vm.prepare(release, base=args.work_root) if args.work_root else vm.prepare(release)
    image = work / 'disposable.img'
    assert image.stat().st_blocks == 0
    os.truncate(image, 6 * 1024**3)
    overlay = work / 'overlay'
    fixture = overlay / 'fixture'
    shutil.copy2(ROOT / 'tests/split-fullboot-provision.py', fixture / 'test.py')
    init = overlay / 'init'
    init.write_text(init.read_text().replace('modprobe ext4', 'modprobe ext4\nmodprobe isofs'))
    delta = work / 'runtime-delta';delta.mkdir()
    public = ROOT / 'config/includes.chroot'
    previous = release / 'build/config/includes.chroot'
    for source in (() if args.clean_release else public.rglob('*')):
        if not source.is_file() or '__pycache__' in source.parts or source.suffix == '.pyc':
            continue
        relative = source.relative_to(public)
        old = previous / relative
        if not old.is_file() or vm.digest(old) != vm.digest(source):
            target = delta / relative;target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    native = public / 'usr/local/share/portable/native-split-unlock/portable-unlock-pair'
    data['runtime_delta_sha256'] = None
    if not args.clean_release:
        target = delta / 'usr/local/libexec/portable-unlock-pair';target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(native, target)
        module = fixture / 'layout2-runtime.squashfs'
        subprocess.run(['/usr/bin/mksquashfs', str(delta), str(module), '-noappend', '-all-root',
                        '-no-xattrs', '-processors', '2', '-no-progress'], check=True, stdout=subprocess.DEVNULL)
        data['runtime_delta_sha256'] = vm.digest(module)
    data['base_rootfs_sha256'] = manifest['binary/live/filesystem.squashfs']['sha256']
    runtime = ['usr/local/lib/portable/private_storage.py', 'usr/local/lib/portable/storage_layout.py']
    data['runtime_files'] = {name: vm.digest(public / name) for name in runtime}
    (fixture / 'test-input.json').write_text(json.dumps(data))
    repack_provision(work, release)
    # Production initramfs plus the reviewed unlock scripts and static helper.
    boot_overlay = work / 'boot-overlay';boot_overlay.mkdir()
    for name in (() if args.clean_release else ('portable-unlock', 'petalos-startup')):
        target = boot_overlay / 'scripts/init-premount' / name;target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'config/includes.chroot/etc/initramfs-tools/scripts/init-premount' / name, target)
    if not args.clean_release:
        target = boot_overlay / 'usr/bin/portable-unlock-pair';target.parent.mkdir(parents=True)
        shutil.copy2(native, target)
    extracted = work / 'base-initramfs'
    subprocess.run(['/usr/bin/unmkinitramfs', str(release / 'build/binary/live/initrd.img'), str(extracted)],
                   check=True, stdout=subprocess.DEVNULL)
    orders = list(extracted.rglob('scripts/init-bottom/ORDER'));assert len(orders) == 1
    bottom = boot_overlay / 'scripts/init-bottom';bottom.mkdir(parents=True)
    (bottom / 'ORDER').write_text(orders[0].read_text() + '\n/scripts/init-bottom/petalos-split-test "$@"\n')
    hook = bottom / 'petalos-split-test'
    hook.write_text('''#!/bin/sh
set -eu
mkdir -p "$rootmnt/usr/local/lib/petalos-split-test" "$rootmnt/etc/systemd/system/multi-user.target.wants"
cp /fixture/fullboot-guest.py "$rootmnt/usr/local/lib/petalos-split-test/verify"
cp /fixture/test-input.json "$rootmnt/root/.petalos-split-test-input.json"
chmod 600 "$rootmnt/root/.petalos-split-test-input.json"
cp /fixture/petalos-split-test.service "$rootmnt/etc/systemd/system/petalos-split-test.service"
ln -s ../petalos-split-test.service "$rootmnt/etc/systemd/system/multi-user.target.wants/petalos-split-test.service"
''');hook.chmod(0o755)
    payload = boot_overlay / 'fixture';payload.mkdir()
    shutil.copy2(ROOT / 'tests/split-fullboot-guest.py', payload / 'fullboot-guest.py')
    (payload / 'test-input.json').write_text(json.dumps(data))
    (payload / 'test-input.json').chmod(0o600)
    (payload / 'petalos-split-test.service').write_text('''[Unit]
Description=PetalOS disposable split-storage full-boot verification
After=live-config.service
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -u /usr/local/lib/petalos-split-test/verify
TimeoutStartSec=180
StandardOutput=journal+console
StandardError=journal+console
''')
    full_initrd = work / 'fullboot-test-initrd.img'
    with full_initrd.open('xb') as output:
        with (release / 'build/binary/live/initrd.img').open('rb') as original:
            shutil.copyfileobj(original, output)
        output.write(gzip.compress(vm.archive_tree(boot_overlay), compresslevel=1))
    print('Fresh full-OS split-storage VM:', work, flush=True)
    provision = vm.boot(work, data, release, 'full-provision', 900, expected_prompts=0, iso=iso, work_root=args.work_root)
    print('Booting actual live OS with ' + ('clean production storage code' if args.clean_release else 'reviewed storage delta')
          + ', encrypted OS and separate settings.', flush=True)
    accepted = vm.boot(work, data, release, 'full-boot', 900, initrd=full_initrd, memory=8192, full_os=True, work_root=args.work_root)
    report = {'passed': True, 'base_release': release.name,
              'scope': ('Clean live-build OS/RAM boot with unmodified production storage code' if args.clean_release
                        else 'Actual full live OS/RAM boot with reviewed layout-2 delta'),
              'clean_release': args.clean_release,
              'provision': provision, 'boot': accepted, 'runtime_delta_sha256': data['runtime_delta_sha256'],
              'runtime_files': data['runtime_files'],
              'limits': ['Direct kernel boot, not firmware/Secure Boot or graphical acceptance',
                         'Fast test-only PBKDF2, not production KDF validation',
                         ('Test-only service/credentials appended to the verified clean production initrd' if args.clean_release
                          else 'Not a clean full live-build release; test initrd includes disposable credentials'),
                         'No physical media or pre-existing VM image modified']}
    (work / 'fullboot-results.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Full encrypted live boot passed:', work / 'fullboot-results.json')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Full-boot VM stopped: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
