#!/usr/bin/python3 -B
"""Validate split storage in two networkless disposable VM boots, without sudo.

Uses a completed release kernel/initramfs with a focused test overlay. It never
mounts host storage, opens an existing image for writing or modifies the card.
"""
from pathlib import Path
import argparse
import datetime
import gzip
import hashlib
import json
import os
import re
import secrets
import select
import shutil
import stat
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def console_record(line):
    """Test stdout may be direct or prefixed by systemd/journald console output."""
    for marker in ('SPLIT_PASS ', 'SPLIT_RESULT '):
        position = line.find(marker)
        if position >= 0:
            return marker, line[position + len(marker):].strip()
    return None, None


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def copy_executable(path, overlay):
    source = Path(path)
    alias = overlay / str(source.parent.resolve() / source.name).lstrip('/')
    # The distro initrd hard-links BusyBox applets together. Replacing an applet
    # with another regular-file cpio member overwrites every hard link, including
    # /bin/sh. A new symlink breaks that alias without touching the BusyBox inode.
    destination = alias if source.suffix == '.so' else overlay / 'usr/lib/petalos-fixture-tools' / source.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    destination.chmod(source.stat().st_mode & 0o777)
    if destination != alias:
        alias.parent.mkdir(parents=True, exist_ok=True)
        if alias.exists() or alias.is_symlink():
            alias.unlink()
        alias.symlink_to('/usr/lib/petalos-fixture-tools/' + source.name)
    result = subprocess.run(['ldd', str(source)], capture_output=True, text=True)
    if result.returncode and 'not a dynamic executable' not in result.stdout + result.stderr:
        raise RuntimeError('Could not resolve a fixture executable.')
    for dependency in re.findall(r'(/[^\s()]+)', result.stdout):
        dependency = Path(dependency)
        if dependency.is_file():
            target = overlay / str(dependency.parent.resolve() / dependency.name).lstrip('/')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(dependency, target)
            target.chmod(dependency.stat().st_mode & 0o777)


def archive_tree(folder, *, devices=True, preserve_hardlinks=False):
    """Root-owned newc archive, including console nodes, with no host mknod."""
    output = bytearray()
    counter = 0
    def entry(name, mode, payload=b'', major=0, minor=0, inode=None, nlink=1):
        nonlocal counter
        counter += 1
        encoded = name.encode() + b'\0'
        fields = (counter if inode is None else inode, mode, 0, 0, nlink, 0, len(payload), 0, 0, major, minor, len(encoded), 0)
        header = b'070701' + b''.join(f'{value:08x}'.encode() for value in fields)
        output.extend(header + encoded)
        output.extend(b'\0' * (-len(output) % 4))
        output.extend(payload)
        output.extend(b'\0' * (-len(output) % 4))
    paths = sorted(folder.rglob('*'))
    hardlinks = {};counts = {}
    if preserve_hardlinks:
        for path in paths:
            if path.is_symlink() or not path.is_file():continue
            info = path.stat();key = (info.st_dev, info.st_ino)
            counts[key] = counts.get(key, 0) + 1
    for path in paths:
        name = str(path.relative_to(folder))
        if path.is_symlink():
            entry(name, stat.S_IFLNK | 0o777, str(path.readlink()).encode())
        elif path.is_dir():
            entry(name, stat.S_IFDIR | 0o755)
        elif path.is_file():
            info = path.stat();key = (info.st_dev, info.st_ino)
            if preserve_hardlinks and counts[key] > 1:
                if key in hardlinks:
                    entry(name, stat.S_IFREG | (info.st_mode & 0o777), inode=hardlinks[key], nlink=counts[key])
                else:
                    hardlinks[key] = counter + 1
                    entry(name, stat.S_IFREG | (info.st_mode & 0o777), path.read_bytes(), nlink=counts[key])
            else:entry(name, stat.S_IFREG | (info.st_mode & 0o777), path.read_bytes())
    if devices:
        entry('dev/console', stat.S_IFCHR | 0o600, major=5, minor=1)
        entry('dev/null', stat.S_IFCHR | 0o666, major=1, minor=3)
    entry('TRAILER!!!', 0)
    return bytes(output)


def prepare(release, *, base=None):
    assert os.geteuid() != 0, 'Run QEMU as the normal user.'
    manifest = json.loads((release / 'manifest.json').read_text())
    for name in ('vmlinuz', 'initrd.img'):
        relative = 'binary/live/' + name
        assert digest(release / 'build' / relative) == manifest[relative]['sha256']
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    work = (Path(base) if base is not None else ROOT.parent / 'testing/split-storage') / stamp
    work.mkdir(parents=True, mode=0o700)
    credentials = {kind: secrets.token_urlsafe(32) for kind in ('system', 'private', 'administrator')}
    data = {'uuids': {role: str(uuid.uuid4()) for role in ('os', 'system', 'private')},
            'credentials': credentials}
    overlay = work / 'overlay';overlay.mkdir(mode=0o700)
    fixture = overlay / 'fixture';fixture.mkdir()
    (fixture / 'test-input.json').write_text(json.dumps(data))
    (fixture / 'test-input.json').chmod(0o600)
    # Only maintained source and stdlib are copied. No OS user data, VPN profile,
    # SSH access, release chroot, existing VM disk or personal secret is read.
    shutil.copytree(ROOT / 'local/installer/petal_installer', fixture / 'installer/petal_installer',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'assets'))
    shutil.copy2(ROOT / 'local/installer/backend.py', fixture / 'editing-backend.py')
    shutil.copy2(ROOT / 'tests/split-storage-guest.py', fixture / 'test.py')
    shutil.copy2(ROOT / 'tests/release_generations.py', fixture / 'release_generations.py')
    shutil.copy2(ROOT / 'local/installer/petal_installer/assets/petal-emblem.png', fixture / 'wallpaper.png')
    vpn_validator = fixture / 'source/config/includes.chroot/usr/local/lib/portable/vpn_profiles.py'
    vpn_validator.parent.mkdir(parents=True)
    shutil.copy2(ROOT / 'config/includes.chroot/usr/local/lib/portable/vpn_profiles.py', vpn_validator)
    portable = overlay / 'usr/local/lib/portable'
    shutil.copytree(ROOT / 'config/includes.chroot/usr/local/lib/portable', portable,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    boot = overlay / 'scripts/init-premount';boot.mkdir(parents=True)
    shutil.copy2(ROOT / 'config/includes.chroot/etc/initramfs-tools/scripts/init-premount/portable-unlock', boot / 'portable-unlock')
    programs = overlay / 'usr/bin';programs.mkdir(parents=True)
    shutil.copy2(ROOT / 'config/includes.chroot/usr/local/share/portable/native-split-unlock/portable-unlock-pair', programs / 'portable-unlock-pair')
    splash = programs / 'petalos-splash';splash.write_text('#!/bin/sh\nexit 0\n');splash.chmod(0o755)
    for program in ('/usr/bin/python3.13', '/usr/sbin/cryptsetup', '/usr/sbin/sgdisk', '/usr/sbin/partprobe',
                    '/usr/sbin/mkfs.ext4', '/usr/sbin/mkfs.vfat', '/usr/sbin/blockdev', '/usr/sbin/blkid',
                    '/usr/bin/mount', '/usr/bin/umount', '/usr/bin/findmnt', '/usr/bin/udevadm',
                    '/usr/bin/mountpoint', '/usr/bin/lsblk',
                    '/usr/bin/openssl', '/usr/bin/sync'):
        copy_executable(program, overlay)
    (programs / 'python3').symlink_to('python3.13')
    shutil.copytree('/usr/lib/python3.13', overlay / 'usr/lib/python3.13',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'test', 'tests', 'ensurepip', 'site-packages'))
    for extension in (overlay / 'usr/lib/python3.13/lib-dynload').glob('*.so'):
        # Resolve extension dependencies without copying any host site packages.
        actual = Path('/usr/lib/python3.13/lib-dynload') / extension.name
        copy_executable(actual, overlay)
    init = overlay / 'init'
    init.write_text('''#!/bin/sh
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export LC_ALL=C.UTF-8
umask 077
mkdir -p /proc /sys /dev /run /mnt
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mkdir -p /run /mnt /dev/pts
mount -t tmpfs -o mode=755,nosuid,nodev tmpfs /run
mount -t devpts devpts /dev/pts
mkdir -p /run/cryptsetup /run/udev
udevadm trigger --action=add >/dev/null 2>&1 || true
/usr/lib/systemd/systemd-udevd --daemon
modprobe virtio_pci
modprobe virtio_blk
modprobe dm_crypt
modprobe ext4
udevadm trigger --action=add >/dev/null 2>&1 || true
udevadm settle --timeout=15 || true
python3 -u /fixture/test.py
poweroff -f
''')
    init.chmod(0o755)
    initrd = work / 'fixture-initrd.img'
    with initrd.open('xb') as output:
        with (release / 'build/binary/live/initrd.img').open('rb') as original:
            shutil.copyfileobj(original, output)
        output.write(gzip.compress(archive_tree(overlay), compresslevel=1))
    initrd.chmod(0o600)
    image = work / 'disposable.img'
    with image.open('xb') as output:
        output.truncate(512 * 1024**2)
    image.chmod(0o600)
    return work, data


def boot(work, data, release, stage, timeout, *, expected_prompts=1, initrd=None, memory=1536, iso=None, full_os=False, work_root=None, usb_image=None):
    image = work / 'disposable.img'
    initial = image.stat()
    assert stat.S_ISREG(initial.st_mode) and initial.st_uid == os.getuid() and initial.st_nlink == 1
    expected_root = Path(work_root).resolve(strict=True) if work_root else ROOT.parent / 'testing/split-storage'
    assert not image.is_symlink() and work.parent == expected_root
    for backing in Path('/sys/block').glob('loop*/loop/backing_file'):
        assert Path(backing.read_text().strip()).resolve() != image.resolve()
    assert subprocess.run(['/usr/bin/fuser', str(image)], capture_output=True).returncode == 1
    sys.path.insert(0, str(ROOT / 'local/installer'))
    from petal_installer.layout2 import boot_arguments
    arguments = boot_arguments(data['uuids']) + ['console=ttyS0', 'nosplash', 'panic=1',
        'petalos.fixture.stage=' + stage]
    if full_os:
        arguments += ['systemd.unit=multi-user.target', 'systemd.mask=serial-getty@ttyS0.service']
    acceleration = ['-accel', 'kvm', '-cpu', 'host'] if Path('/dev/kvm').exists() else ['-accel', 'tcg,thread=multi', '-cpu', 'max']
    command = ['/usr/bin/qemu-system-x86_64', *acceleration, '-machine', 'q35', '-smp', '2', '-m', str(memory),
               '-kernel', str(release / 'build/binary/live/vmlinuz'), '-initrd', str(initrd or work / 'fixture-initrd.img'),
               '-append', ' '.join(arguments), '-drive', 'file=' + str(image) + ',format=raw,if=virtio',
               '-object', 'rng-random,filename=/dev/urandom,id=rng', '-device', 'virtio-rng-pci,rng=rng',
               '-nic', 'none', '-display', 'none', '-serial', 'stdio', '-monitor', 'none', '-no-reboot']
    if iso:
        command += ['-drive', 'file=' + str(iso) + ',format=raw,if=virtio,readonly=on']
    if usb_image is not None:
        usb_image = Path(usb_image)
        info = usb_image.stat()
        assert usb_image.parent == work and not usb_image.is_symlink()
        assert stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1
        assert subprocess.run(['/usr/bin/fuser', str(usb_image)], capture_output=True).returncode == 1
        command += ['-device', 'qemu-xhci,id=usbfixture', '-drive',
                    'file=' + str(usb_image) + ',format=raw,if=none,id=flashfixture',
                    '-device', 'usb-storage,drive=flashfixture,removable=on,serial=PETALOS_GUI_USB_TEST']
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    tail = bytearray()
    pending = bytearray()
    prompt_count = 0
    result = None
    start = time.monotonic()
    try:
        while process.poll() is None:
            if time.monotonic() - start > timeout:
                raise RuntimeError('Disposable VM stage timed out.')
            if not select.select([process.stdout], [], [], 1)[0]:
                continue
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                break
            tail.extend(chunk)
            if len(tail) > 256 * 1024:
                del tail[:-256 * 1024]
            pending.extend(chunk)
            # askpass disables terminal echo before writing this prompt.
            while b'SYSTEM passphrase: ' in pending:
                before, _, after = pending.partition(b'SYSTEM passphrase: ')
                pending[:] = before + after
                prompt_count += 1
                assert prompt_count <= expected_prompts, 'A successful boot must not prompt a second time.'
                process.stdin.write(data['credentials']['system'].encode() + b'\n')
                process.stdin.flush()
            while b'\n' in pending:
                line, _, rest = pending.partition(b'\n');pending[:] = rest
                line = line.decode(errors='replace').strip()
                kind, record = console_record(line)
                if kind == 'SPLIT_PASS ':
                    print(kind + record, flush=True)
                elif kind == 'SPLIT_RESULT ':
                    result = json.loads(record)
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill();process.wait()
        sanitized = bytes(tail)
        for value in data['credentials'].values():
            sanitized = sanitized.replace(value.encode(), b'<redacted disposable credential>')
        (work / (stage + '-bounded.log')).write_bytes(sanitized)
        (work / (stage + '-bounded.log')).chmod(0o600)
    assert image.stat().st_ino == initial.st_ino and image.stat().st_size == initial.st_size
    assert result and result['passed'], 'Disposable VM checks failed; inspect the bounded local guest log.'
    assert prompt_count == expected_prompts, 'The real boot script did not exercise the expected SYSTEM prompt count.'
    result['single_system_prompt'] = prompt_count == 1
    result['acceleration'] = 'kvm' if Path('/dev/kvm').exists() else 'tcg'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release', type=Path)
    parser.add_argument('--timeout', type=int, default=600, help='Seconds per boot')
    parser.add_argument('--work-root', type=Path, help='Directory for newly allocated disposable artifacts')
    args = parser.parse_args()
    os.umask(0o077)
    release = args.release.resolve(strict=True)
    assert release.parent == ROOT.parent / 'releases'
    work, data = prepare(release, base=args.work_root) if args.work_root else prepare(release)
    print('Disposable split-storage VM:', work, flush=True)
    results = []
    for stage in ('provision', 'verify'):
        print('Booting ' + stage + ' stage; no NIC or host share.', flush=True)
        results.append(boot(work, data, release, stage, args.timeout, work_root=args.work_root))
    report = {'passed': True, 'scope': 'Focused encrypted-storage VM, synthetic payloads, fast test-only PBKDF2',
              'release_kernel': release.name, 'results': results,
              'limits': ['Not a complete rebuilt OS', 'Not Secure Boot acceptance', 'Not production KDF performance',
                         'No physical media modified', 'RAM overlay environmental preconditions substituted as documented in guest test']}
    (work / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Split-storage VM acceptance passed. Results:', work / 'results.json')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Split-storage VM stopped: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
