#!/usr/bin/python3 -I
"""OS-only update of Sam's explicitly authorized, identity-pinned test card.

Raw boot and encrypted SYSTEM backups precede all card writes. Private is
never opened. Existing signed EFI executables and SYSTEM state are retained.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
CARD = Path('/dev/disk/by-id/usb-Mass_Storage_Device_121220160204-0:0')
MAPPER = Path('/dev/mapper/petal_rc1_card_system')
IDENTITIES = {
    2: ('D641-C591', 'PORT_BOOT', 'vfat', 1073741824),
    3: ('4fb8bb69-5c61-4466-affd-c1d9e258fe23', 'PORTABLE_SYSTEM', 'crypto_LUKS', 4294967296),
    4: ('cfad9f3d-d921-438b-9034-f245c745fb16', 'PORTABLE_DATA', 'crypto_LUKS', 250497449472),
}


def require(condition, message):
    if not condition:
        print('Check failed: ' + message, flush=True)
        raise RuntimeError(message)


def run(*args):
    result = subprocess.run(args, capture_output=True, text=True)
    require(result.returncode == 0, 'Command failed: ' + Path(args[0]).name)
    return result.stdout.strip()


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(4 * 1024**2):
            h.update(chunk)
    return h.hexdigest()


def load_helper():
    spec = importlib.util.spec_from_file_location('card_guard', HERE / 'install-hardware-card-root.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    require(os.geteuid() == 0 and os.environ.get('SUDO_UID') == '1000', 'Use the prepared sudo terminal.')
    require(len(sys.argv) == 2, 'One release directory required.')
    release = Path(sys.argv[1])
    require(release.parent == HERE.parent.parent / 'releases' and
            re.fullmatch(r'\d{8}-\d{6}-\d+', release.name) and
            release.resolve(strict=True) == release, 'Unexpected release path.')
    status = Path('/run/user/1000/petalos-rc1-card-update.json')
    record = {'release': str(release), 'target_by_id': str(CARD)}

    def stage(name, **extra):
        record.update(phase=name, **extra)
        fd, tmp = tempfile.mkstemp(dir=status.parent, prefix='.card-update-')
        with os.fdopen(fd, 'w') as output:
            os.fchown(output.fileno(), 1000, int(os.environ['SUDO_GID']))
            json.dump(record, output)
        os.replace(tmp, status)
        print(name, flush=True)

    guard = load_helper()
    stage('checking card and release')
    device, rdev = guard.check_card(require_original_uuids=False)
    sequence = (Path('/sys/class/block') / device.name / 'diskseq').read_text()

    def identity():
        require(CARD.resolve(strict=True) == device and CARD.stat().st_rdev == rdev and
                (Path('/sys/class/block') / device.name / 'diskseq').read_text() == sequence,
                'Card identity changed; stopped.')

    def part(number):
        identity()
        path = Path(str(CARD) + '-part' + str(number)).resolve(strict=True)
        require((Path('/sys/class/block') / path.name).resolve().parent.name == device.name,
                'Partition parent mismatch.')
        return path

    for number, (uuid, label, kind, size) in IDENTITIES.items():
        path = part(number)
        tags = dict(line.split('=', 1) for line in run('/usr/sbin/blkid', '-p', '-o', 'export', str(path)).splitlines() if '=' in line)
        require((tags.get('UUID'), tags.get('LABEL'), tags.get('TYPE')) == (uuid, label, kind),
                'Partition identity mismatch.')
        require(int(run('/usr/sbin/blockdev', '--getsize64', str(path))) == size, 'Partition size mismatch.')
    require(not MAPPER.exists(), 'Updater mapping already exists.')
    manifest = json.loads((release / 'manifest.json').read_text())
    sources = {}
    for name in ('vmlinuz', 'initrd.img', 'filesystem.squashfs'):
        relative = 'binary/live/' + name
        source = release / 'build' / relative
        require(not source.is_symlink() and source.is_file() and digest(source) == manifest[relative]['sha256'],
                'Release checksum mismatch.')
        sources[name] = source
    require('signature 1' in run('/usr/bin/sbverify', '--list', str(sources['vmlinuz'])), 'Unsigned kernel.')
    require('PRETTY_NAME="PetalOS RC 1"' in run('/usr/bin/unsquashfs', '-cat', str(sources['filesystem.squashfs']), 'etc/os-release'), 'Unexpected release identity.')
    backup = Path('/home/sam/petalos-backups') / ('rc1-card-update-' + time.strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid()))
    require(not backup.parent.is_symlink() and backup.parent.resolve() == backup.parent, 'Unsafe backup parent.')
    backup.mkdir(mode=0o700)
    record['backup'] = str(backup)
    require(os.statvfs(backup).f_bavail * os.statvfs(backup).f_frsize > 6 * 1024**3, 'Insufficient backup space.')
    hashes = {}
    for number in (2, 3):
        stage('backing up partition ' + str(number))
        identity()
        destination = backup / ('partition-' + str(number) + '.img')
        h = hashlib.sha256(); count = 0; last = time.monotonic()
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with part(number).open('rb') as source, os.fdopen(fd, 'wb') as output:
            while chunk := source.read(4 * 1024**2):
                output.write(chunk); h.update(chunk); count += len(chunk)
                if time.monotonic() - last > 15:
                    stage('backing up partition ' + str(number), bytes=count)
                    last = time.monotonic()
            output.flush(); os.fsync(output.fileno())
        require(count == IDENTITIES[number][3] and digest(destination) == h.hexdigest(), 'Backup verification failed.')
        hashes[destination.name] = h.hexdigest()
    (backup / 'checksums.json').write_text(json.dumps(hashes, indent=2) + '\n')
    identity(); guard.check_card(require_original_uuids=False)
    stage('backups verified; waiting for SYSTEM passphrase')
    print('Enter the card SYSTEM passphrase. Private will not be opened.', flush=True)
    result = subprocess.run(['/usr/sbin/cryptsetup', 'open', str(part(3)), MAPPER.name])
    require(result.returncode == 0, 'SYSTEM unlock failed; card payloads untouched.')
    work = Path(tempfile.mkdtemp(prefix='petalos-card-rc1-', dir='/run'))
    mounted = []

    def mapping():
        identity()
        md = MAPPER.stat().st_rdev
        slaves = Path(f'/sys/dev/block/{os.major(md)}:{os.minor(md)}/slaves')
        require([p.name for p in slaves.iterdir()] == [part(3).name], 'Mapper identity mismatch.')

    def safe(path, root):
        require(path.resolve(strict=True).is_relative_to(root) and not path.is_symlink() and path.is_file(), 'Unsafe destination path.')

    try:
        mapping()
        require(run('/usr/sbin/blkid', '-s', 'LABEL', '-o', 'value', str(MAPPER)) == 'LIVE_SYSTEM', 'Unexpected SYSTEM filesystem.')
        for name, source, kind in (('boot', part(2), 'vfat'), ('system', MAPPER, 'ext4')):
            target = work / name; target.mkdir()
            run('/usr/bin/mount', '-t', kind, '-o', 'nodev,nosuid,noexec,noatime', str(source), str(target))
            mounted.append((source, target))
        boot = work / 'boot'; system = work / 'system'
        require(not (system / '.portable-keys/data.key').exists(), 'Legacy automatic Private key needs separate review.')
        selection = system / 'live/filesystem.module'; safe(selection, system)
        require(selection.read_text().split() == ['filesystem.squashfs', 'petalos-hardware-ssh.squashfs'], 'Unexpected live module selection.')
        efi = {str(p.relative_to(boot)): digest(p) for p in boot.rglob('*') if p.is_file() and p.suffix.lower() == '.efi'}
        require(len(efi) >= 3, 'Signed EFI chain missing.')
        destinations = []; configs = []
        for config in boot.rglob('grub.cfg'):
            safe(config, boot); content = config.read_text()
            if 'live-media=/dev/mapper/portable_system' not in content: continue
            for line in content.splitlines():
                words = line.split()
                if words and words[0] in ('linux', 'linuxefi'):
                    require({'toram', 'swap=false', 'init_on_alloc=1', 'init_on_free=1', 'petalos_hardware_ssh=1', 'live-media=/dev/mapper/portable_system'} <= set(words), 'Unexpected boot security flags.')
                    require(re.fullmatch(r'/(?:live/|petalos/releases/[a-f0-9]{24}/)?vmlinuz', words[1]), 'Unexpected kernel path.')
                    destinations.append(('vmlinuz', boot / words[1].lstrip('/')))
                if words and words[0] in ('initrd', 'initrdefi'):
                    require(len(words) == 2 and re.fullmatch(r'/(?:live/|petalos/releases/[a-f0-9]{24}/)?initrd.img', words[1]), 'Unexpected initrd path.')
                    destinations.append(('initrd.img', boot / words[1].lstrip('/')))
            configs.append((config, content))
        require(configs and {name for name, _ in destinations} == {'vmlinuz', 'initrd.img'}, 'Missing boot payloads.')
        for _, target in destinations:safe(target, work)
        spec = importlib.util.spec_from_file_location('release_generations', HERE / 'release_generations.py')
        generations = importlib.util.module_from_spec(spec);spec.loader.exec_module(generations)
        stage('applying test retention; keeping active OS, then at most one previous release')
        generation, installed = generations.stage_and_activate(boot, system, sources,
            {name: manifest['binary/live/' + name]['sha256'] for name in sources}, configs,
            selection.read_text().split(), identity=mapping, checkpoint=stage, retention='test')
        record['generation'] = generation
        stage('flushing and reading back OS files')
        for source, target in reversed(mounted):
            run('/usr/bin/mount', '-o', 'remount,ro', str(target))
        for target, expected in installed.items():
            require(digest(target) == expected, 'Final generation readback failed.')
        require(all(digest(boot / path) == value for path, value in efi.items()), 'EFI executable changed unexpectedly.')
        require(selection.read_text().split() == ['filesystem.squashfs', 'petalos-hardware-ssh.squashfs'], 'Live module selection changed.')
    finally:
        for source, target in reversed(mounted):
            mapping()
            actual = Path(run('/usr/bin/findmnt', '-n', '-o', 'SOURCE', '--mountpoint', str(target)))
            require(actual.stat().st_rdev == source.stat().st_rdev, 'Cleanup mount identity mismatch.')
            run('/usr/bin/umount', str(target)); target.rmdir()
        mapping(); run('/usr/sbin/cryptsetup', 'close', MAPPER.name)
        work.rmdir()
    stage('complete')
    print('PetalOS RC 1 OS update and file readback complete. Private and SYSTEM settings preserved. All updater mounts/mappings closed. Card may now be removed.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        # Do not print subprocess output, command arguments or credential data.
        import traceback
        if type(error).__name__ == 'InsufficientGenerationSpace':
            print(str(error), flush=True)
        frame = traceback.extract_tb(error.__traceback__)[-1]
        print('Update stopped: ' + type(error).__name__ + '; line ' + str(frame.lineno) +
              '. Keep card connected; report this line before booting.', flush=True)
        sys.exit(1)
