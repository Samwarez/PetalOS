#!/usr/bin/python3 -B
"""Run actual installer operations on new virtual USB media, then firmware boot.

No physical target, existing image or host directory share is accepted.
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import select
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'local/installer'))
from petal_installer.bundles import create_bundle


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path);module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


vm = load('split_vm', ROOT / 'tests/run-split-storage-vm.py')
package = load('installer_package', ROOT / 'local/installer/build-package.py')


def gpt_range(image, number):
    with image.open('rb') as source:
        source.seek(512);header = source.read(512)
        table, count, size = struct.unpack_from('<QII', header, 72)
        assert 1 <= number <= count and size >= 128
        source.seek(table * 512 + (number - 1) * size);entry = source.read(size)
    start, end = struct.unpack_from('<QQ', entry, 32)
    return start * 512, (end - start + 1) * 512


def range_hash(image, number):
    start, remaining = gpt_range(image, number);digest = hashlib.sha256()
    with image.open('rb') as source:
        source.seek(start)
        while remaining:
            chunk = source.read(min(16 * 1024**2, remaining));assert chunk
            digest.update(chunk);remaining -= len(chunk)
    return digest.hexdigest()


def run_guest(work, data, release, stage, iso=None, firmware=False):
    target = work / 'disposable.img';wipe = work / 'wipe.img'
    assert target.parent == work and target.is_file() and not target.is_symlink()
    for image in (target, wipe):
        assert subprocess.run(['/usr/bin/fuser', str(image)], capture_output=True).returncode == 1
    acceleration = ['-accel', 'kvm', '-cpu', 'host'] if Path('/dev/kvm').exists() else ['-accel', 'tcg,thread=multi', '-cpu', 'max']
    args = ['/usr/bin/qemu-system-x86_64', *acceleration, '-machine', 'q35,smm=on', '-smp', '2', '-m', '3072',
            '-device', 'qemu-xhci', '-drive', f'file={target},format=raw,if=none,id=target',
            '-device', 'usb-storage,drive=target,removable=on,serial=PETAL-INSTALL-TEST',
            '-device', 'virtio-rng-pci', '-nic', 'none', '-display', 'none', '-serial', 'stdio', '-monitor', 'none', '-no-reboot']
    if firmware:
        args += ['-global', 'driver=cfi.pflash01,property=secure,value=on',
                 '-drive', 'if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.secboot.fd',
                 '-drive', 'if=pflash,format=raw,file=' + str(work / 'OVMF_VARS.fd')]
    else:
        args += ['-kernel', str(release / 'build/binary/live/vmlinuz'), '-initrd', str(work / 'fixture-initrd.img'),
                 '-append', 'console=ttyS0 panic=1 petalos.fixture.stage=' + stage,
                 '-drive', f'file={iso},format=raw,if=virtio,readonly=on',
                 '-drive', f'file={wipe},format=raw,if=none,id=wipe',
                 '-device', 'usb-storage,drive=wipe,removable=on,serial=PETAL-WIPE-TEST']
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    pending = bytearray();tail = bytearray();result = None;prompts = 0;start = time.monotonic()
    try:
        while process.poll() is None:
            if time.monotonic() - start > 1200:raise RuntimeError('Installer VM stage timed out.')
            if not select.select([process.stdout], [], [], 1)[0]:continue
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:break
            tail.extend(chunk);del tail[:-256 * 1024];pending.extend(chunk)
            while b'SYSTEM passphrase: ' in pending:
                before, _, after = pending.partition(b'SYSTEM passphrase: ');pending[:] = before + after
                prompts += 1;assert firmware and prompts == 1
                process.stdin.write(data['credentials']['system'].encode() + b'\n');process.stdin.flush()
            while b'\n' in pending:
                line, _, rest = pending.partition(b'\n');pending[:] = rest
                text = line.decode(errors='replace').strip()
                kind, value = vm.console_record(text)
                if kind == 'SPLIT_PASS ':print(kind + value, flush=True)
                elif kind == 'SPLIT_RESULT ':result = json.loads(value)
                elif text.startswith('ENGINE_STAGE '):print(text, flush=True)
        process.wait(timeout=10)
    finally:
        if process.poll() is None:process.kill();process.wait()
        output = bytes(tail)
        for value in data['credentials'].values():output = output.replace(value.encode(), b'<redacted disposable password>')
        (work / (stage + '-bounded.log')).write_bytes(output)
    assert result and result['passed'], 'Installer VM failed; inspect bounded local log.'
    if firmware:assert prompts == 1
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument('release', type=Path)
    parser.add_argument('--work-root', type=Path, default=Path('/tmp/petalos-installer-tests'), help='Disposable artifacts; defaults to RAM-backed /tmp')
    args = parser.parse_args()
    os.umask(0o077);release = args.release.resolve(strict=True)
    assert release.parent == ROOT.parent / 'releases'
    work, data = vm.prepare(release, base=args.work_root)
    assert (work / 'disposable.img').stat().st_blocks == 0
    os.truncate(work / 'disposable.img', 16 * 1024**3)
    with (work / 'wipe.img').open('xb') as output:output.truncate(128 * 1024**2)
    overlay = work / 'overlay';fixture = overlay / 'fixture'
    shutil.copy2(ROOT / 'tests/installer-engine-guest.py', fixture / 'test.py')
    staging = work / 'package-root';package.stage(staging)
    for folder in ('usr/lib/bloom-installer', 'usr/bin'):
        shutil.copytree(staging / folder, overlay / folder, dirs_exist_ok=True)
    for program in ('/usr/bin/fuser', '/usr/bin/sbverify', '/usr/bin/lsinitramfs', '/usr/bin/unmkinitramfs',
                    '/usr/bin/zstd', '/usr/bin/getopt', '/usr/bin/unsquashfs', '/usr/bin/cpio', '/usr/bin/gzip'):
        vm.copy_executable(program, overlay)
    init = overlay / 'init'
    init.write_text(init.read_text().replace('modprobe ext4', 'modprobe ext4\nmodprobe isofs\nmodprobe xhci_pci\nmodprobe usb_storage\nmodprobe sd_mod'))
    # A production-form unlock initrd: no fixture inputs or credentials.
    boot_delta = work / 'production-initrd-delta';boot_delta.mkdir()
    for name in ('portable-unlock', 'petalos-startup'):
        target = boot_delta / 'scripts/init-premount' / name;target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'config/includes.chroot/etc/initramfs-tools/scripts/init-premount' / name, target)
    target = boot_delta / 'usr/bin/portable-unlock-pair';target.parent.mkdir(parents=True)
    shutil.copy2(ROOT / 'config/includes.chroot/usr/local/share/portable/native-split-unlock/portable-unlock-pair', target)
    initrd = work / 'production-form-initrd.img'
    extracted = work / 'unpacked-base'
    subprocess.run(['/usr/bin/unmkinitramfs', str(release / 'build/binary/live/initrd.img'), str(extracted)], check=True, stdout=subprocess.DEVNULL)
    main = extracted / 'main'
    for source in boot_delta.rglob('*'):
        if not source.is_file():continue
        target = main / source.relative_to(boot_delta)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + '.new')
        shutil.copy2(source, temporary);temporary.replace(target)
    with initrd.open('xb') as output:
        for early in sorted(extracted.glob('early*')):
            output.write(vm.archive_tree(early, devices=False, preserve_hardlinks=True))
        output.write(gzip.compress(vm.archive_tree(main, preserve_hardlinks=True), compresslevel=1))
    inputs = work / 'public-bundles';inputs.mkdir()
    payloads = {'kernel': release / 'build/binary/live/vmlinuz', 'initrd': initrd,
                'shim': Path('/usr/lib/shim/shimx64.efi.signed'),
                'grub': Path('/usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed'),
                'mokmanager': Path('/usr/lib/shim/mmx64.efi.signed')}
    for letter in ('a', 'b'):
        tree = work / ('root-' + letter);tree.mkdir();(tree / 'public-canary').write_text(letter)
        rootfs = work / ('root-' + letter + '.squashfs')
        subprocess.run(['/usr/bin/mksquashfs', str(tree), str(rootfs), '-noappend', '-all-root', '-no-progress', '-processors', '2'], check=True, stdout=subprocess.DEVNULL)
        create_bundle(inputs / ('bundle-' + letter), 'test-' + letter, 'base', 'Disposable installer acceptance', dict(payloads, rootfs=rootfs))
    iso = work / 'public-bundles.iso'
    subprocess.run(['/usr/bin/xorriso', '-as', 'mkisofs', '-quiet', '-r', '-J', '-o', str(iso), str(inputs)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # VM-only post-install instrumentation; no secret, not included in bundles.
    orders = list(extracted.rglob('scripts/init-premount/ORDER'));assert len(orders) == 1
    probe = work / 'boot-probe';(probe / 'scripts/init-premount').mkdir(parents=True)
    (probe / 'scripts/init-premount/ORDER').write_text(orders[0].read_text() + '\n/scripts/init-premount/zz-installer-boot-check "$@"\n')
    script = probe / 'scripts/init-premount/zz-installer-boot-check'
    script.write_text('''#!/bin/sh
os=false;settings=false;private_closed=false;readonly=false;secure=false
[ ! -b /dev/mapper/portable_os ] || os=true
[ ! -b /dev/mapper/portable_system ] || settings=true
[ -b /dev/mapper/portable_data ] || private_closed=true
node=$(basename "$(readlink -f /dev/mapper/portable_os)")
[ "$(cat /sys/class/block/$node/ro)" != 1 ] || readonly=true
mkdir -p /sys/firmware/efi/efivars
modprobe efivarfs 2>/dev/null || true
mount -t efivarfs efivarfs /sys/firmware/efi/efivars 2>/dev/null || true
for value in /sys/firmware/efi/efivars/SecureBoot-*; do
 [ -f "$value" ] || continue
 [ "$(dd if="$value" bs=1 skip=4 count=1 2>/dev/null | od -An -tu1 | tr -d ' ')" != 1 ] || secure=true
done
# Some portable initramfs builds lack the efivarfs module. The signed kernel's
# own EFI lockdown report remains available before the root filesystem exists.
dmesg | grep -q 'Kernel is locked down from EFI Secure Boot' && secure=true
passed=false
if $os && $settings && $private_closed && $readonly && $secure; then passed=true; fi
echo "SPLIT_RESULT {\\"stage\\":\\"firmware\\",\\"passed\\":$passed,\\"checks\\":{\\"signed_uefi_boot\\":$secure,\\"os_unlocked\\":$os,\\"settings_unlocked\\":$settings,\\"private_closed\\":$private_closed,\\"os_readonly\\":$readonly}}" >/dev/console
poweroff -f
''');script.chmod(0o755)
    (fixture / 'boot-probe.cpio.gz').write_bytes(gzip.compress(vm.archive_tree(probe), compresslevel=1))
    with (work / 'fixture-initrd.img').open('wb') as output:
        with (release / 'build/binary/live/initrd.img').open('rb') as incoming:shutil.copyfileobj(incoming, output)
        output.write(gzip.compress(vm.archive_tree(overlay), compresslevel=1))
    shutil.copyfile('/usr/share/OVMF/OVMF_VARS_4M.ms.fd', work / 'OVMF_VARS.fd')
    print('Installer acceptance VM:', work, flush=True)
    fresh = run_guest(work, data, release, 'installer-fresh', iso)
    before = {str(n): range_hash(work / 'disposable.img', n) for n in (4, 5)}
    updated = run_guest(work, data, release, 'installer-update', iso)
    after = {str(n): range_hash(work / 'disposable.img', n) for n in (4, 5)}
    assert before == after, 'Persistent partition bytes changed during OS-only update.'
    print('SPLIT_PASS entire_settings_and_private_partitions_byte_identical', flush=True)
    firmware = run_guest(work, data, release, 'firmware', firmware=True)
    report = {'passed': True, 'fresh': fresh, 'update': updated, 'firmware': firmware,
              'persistent_partitions_byte_identical': True,
              'scope': 'Installed package core on virtual USB, real Argon2id, signed EFI chain and one-prompt unlock',
              'limits': ['Synthetic OS payloads, not desktop acceptance', 'Firmware probe appended only after installed artifact verification', 'No physical card or pre-existing images modified']}
    (work / 'installer-results.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Installer VM acceptance passed:', work / 'installer-results.json')


if __name__ == '__main__':
    try:main()
    except Exception as error:
        print('Installer VM stopped: ' + str(error), file=sys.stderr);raise SystemExit(1)
