"""Root-only, identity-pinned removable-media transaction and bounded copies."""
from pathlib import Path
import fcntl
import hashlib
import os
import secrets
import stat
import struct
import tempfile

from . import InstallerError
from . import linux
from .releases import require, file_digest

RUNTIME = Path('/run/petalos-installer')


def root_directory(path):
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Unsafe installer runtime directory.')
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.stat()
    require(info.st_uid == 0 and stat.S_ISDIR(info.st_mode) and not info.st_mode & 0o077,
            'Installer runtime must be a private root directory.')


def raw_hash(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


class Target:
    def __init__(self, device, expected_identity, progress=lambda event: None):
        self.device = str(device);self.expected = expected_identity;self.progress = progress
        self.maps = [];self.mounts = [];self.lock = None;self.work = None
        self.original = None;self.sys_inode = None;self.disk = None

    def __enter__(self):
        require(os.geteuid() == 0, 'Use an administrator terminal or the GUI to execute this operation.')
        self.disk = linux.choose(self.device)
        require(self.disk['identity'] == self.expected, 'Drive identity changed since review; refresh the plan.')
        original = Path(self.device).lstat()
        require(stat.S_ISBLK(original.st_mode), 'Target is not a real whole block device.')
        self.original = original.st_rdev
        node = Path('/sys/dev/block', f'{os.major(self.original)}:{os.minor(self.original)}')
        self.sys_inode = node.stat().st_ino;self.sys_path = node.resolve(strict=True)
        words = Path('/proc/cmdline').read_text().split()
        current = {w.split('=', 1)[1] for w in words if w.startswith(('petalos.os=', 'petalos.system='))}
        # Legacy RAM boots did not carry UUID flags. Their root-owned pinned
        # storage identity still identifies the running installation after its
        # mappings have been closed; it may only add a refusal, never authorize.
        legacy = Path('/run/portable-storage/identity.json')
        if legacy.exists():
            from .store import read_import
            import json
            require(legacy.stat().st_uid == 0, 'Running-storage identity has an unexpected owner.')
            values = json.loads(read_import(legacy, 4096))
            current.update(item['uuid'] for item in values.get('devices', {}).values())
        require(not current & {p.get('uuid') for p in self.disk['partitions']},
                'This is the running PetalOS installation. Boot another Linux system to modify it.')
        for record in linux.walk(linux.raw_disk(self.device)):
            require(linux.command(['/usr/bin/fuser', str(record['path'])], allowed=(1,)) == b'',
                    'A process is using this drive.')
        root_directory(RUNTIME)
        fd = os.open(RUNTIME / (self.expected + '.lock'), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        self.lock = os.fdopen(fd, 'r+b')
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1, 'Unsafe installer lock.')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.work = Path(tempfile.mkdtemp(prefix='operation-', dir=RUNTIME))
            self.check();return self
        except BaseException:
            self.lock.close();self.lock = None
            if self.work:self.work.rmdir()
            raise

    def check(self):
        info = Path(self.device).lstat()
        require(stat.S_ISBLK(info.st_mode) and info.st_rdev == self.original,
                'Selected device disappeared or changed; operation stopped.')
        sysnode = Path('/sys/dev/block', f'{os.major(self.original)}:{os.minor(self.original)}')
        require(sysnode.stat().st_ino == self.sys_inode and sysnode.resolve() == self.sys_path,
                'Drive was disconnected/replaced; operation stopped.')
        raw = linux.raw_disk(self.device)
        require(linux.describe(raw)['identity'] == self.expected, 'Drive identity changed during the operation.')
        owned = set()
        for name in self.maps:
            mapper = Path('/dev/mapper') / name
            if mapper.exists():
                dev = mapper.stat().st_rdev
                owned.add(Path('/sys/dev/block', f'{os.major(dev)}:{os.minor(dev)}').resolve().name)
        mounted = {str(item[1]) for item in self.mounts}
        for record in linux.walk(raw):
            require(all(not value or value in mounted for value in record.get('mountpoints') or []),
                    'An unexpected mount appeared on the selected drive.')
            device = Path(record['path']).stat().st_rdev
            node = Path('/sys/dev/block', f'{os.major(device)}:{os.minor(device)}')
            require(all(holder.name in owned for holder in (node / 'holders').iterdir()),
                    'Another process created a mapping on the selected drive.')
            if record['type'] not in ('disk', 'part'):
                require(node.resolve().name in owned, 'An unowned mapping appeared on the selected drive.')
        return raw

    def run(self, args, *, payload=None, timeout=180):
        self.check();result = linux.command(args, payload=payload, timeout=timeout);self.check();return result

    def partition(self, number):
        found = []
        for item in linux.walk(self.check()):
            if item['type'] != 'part':continue
            info = Path(item['path']).stat()
            node = Path('/sys/dev/block', f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}').resolve(strict=True)
            require(node.parent == self.sys_path, 'Partition does not belong to the selected drive.')
            if int((node / 'partition').read_text()) == number:found.append(Path(item['path']))
        require(len(found) == 1, 'Expected partition was not found on the selected drive.')
        return found[0]

    def open_volume(self, partition, password, *, readonly=False):
        self.check();name = 'petal_inst_' + secrets.token_hex(8)
        require(not Path('/dev/mapper', name).exists(), 'Installer mapping already exists.')
        self.maps.append(name)
        arguments = ['/usr/sbin/cryptsetup', 'open', '--type', 'luks2', '--key-file', '-']
        if readonly:arguments.append('--readonly')
        self.run([*arguments, str(partition), name], payload=password)
        mapper = Path('/dev/mapper', name);device = mapper.stat().st_rdev
        slaves = list(Path('/sys/dev/block', f'{os.major(device)}:{os.minor(device)}', 'slaves').iterdir())
        require(len(slaves) == 1 and (Path('/dev') / slaves[0].name).stat().st_rdev == Path(partition).stat().st_rdev,
                'Encryption mapping does not match the selected partition.')
        return mapper

    def mount(self, device, label, *, fstype='ext4', readonly=False):
        target = self.work / label
        require(not target.exists(), 'Installer mount directory already exists.')
        target.mkdir(mode=0o700)
        options = ('ro,noload,' if readonly and fstype == 'ext4' else 'ro,' if readonly else '') + 'nodev,nosuid,noexec,noatime'
        if fstype == 'vfat':options += ',uid=0,gid=0,fmask=0133,dmask=0022'
        dev = Path(device).stat().st_rdev
        self.mounts.append((Path(device), target, dev))
        self.run(['/usr/bin/mount', '-t', fstype, '-o', options, str(device), str(target)])
        actual = linux.command(['/usr/bin/findmnt', '-n', '-o', 'MAJ:MIN', '--mountpoint', str(target)]).decode().strip()
        require(actual == f'{os.major(dev)}:{os.minor(dev)}', 'Mounted device identity mismatch.')
        return target

    def close(self):
        errors = []
        for device, target, expected in reversed(self.mounts):
            try:
                result = linux.command(['/usr/bin/findmnt', '-n', '-o', 'MAJ:MIN', '--mountpoint', str(target)], allowed=(0, 1)).decode().strip()
                if result:
                    require(result == f'{os.major(expected)}:{os.minor(expected)}', 'Cleanup mount identity changed.')
                    linux.command(['/usr/bin/sync', '-f', str(target)], timeout=120)
                    linux.command(['/usr/bin/umount', str(target)], timeout=60)
                target.rmdir()
            except BaseException:errors.append('mount')
        for name in reversed(self.maps):
            try:
                if Path('/dev/mapper', name).exists():linux.command(['/usr/sbin/cryptsetup', 'close', name], timeout=60)
            except BaseException:errors.append('mapping')
        if not errors and self.work:self.work.rmdir()
        if self.lock:self.lock.close()
        if errors:
            self.progress({'stage': 'cleanup-required'})
            raise InstallerError('Installer cleanup could not finish. Keep the drive connected; its installer mounts/mappings need recovery before removal.')

    def __exit__(self, *args):self.close()


def atomic_copy(source, target, expected, *, check=lambda: None, progress=lambda event: None):
    check();target = Path(target)
    require(not target.is_symlink(), 'Refused a symlink destination.')
    fd, name = tempfile.mkstemp(prefix='.petalos-write-', dir=target.parent);temporary = Path(name)
    count = 0;checksum = hashlib.sha256();total = Path(source).stat().st_size
    try:
        with os.fdopen(fd, 'wb') as output, Path(source).open('rb') as incoming:
            while chunk := incoming.read(4 * 1024**2):
                output.write(chunk);checksum.update(chunk);count += len(chunk)
                if count % (32 * 1024**2) == 0:
                    output.flush();os.fsync(output.fileno());check()
                    progress({'stage': 'writing', 'bytes': count, 'total': total})
            output.flush();os.fsync(output.fileno());os.fchmod(output.fileno(), 0o644)
        require(count == total and checksum.hexdigest() == expected and file_digest(temporary) == expected,
                'Written payload failed verification; it was not selected for boot.')
        check();os.replace(temporary, target)
        folder = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:os.fsync(folder)
        finally:os.close(folder)
        return expected
    finally:temporary.unlink(missing_ok=True)


def write_public(data, target, **kwargs):
    fd, name = tempfile.mkstemp(prefix='petalos-public-', dir=RUNTIME)
    try:
        with os.fdopen(fd, 'wb') as output:output.write(data)
        return atomic_copy(Path(name), target, hashlib.sha256(data).hexdigest(), **kwargs)
    finally:Path(name).unlink(missing_ok=True)


def random_fill(target, progress):
    """Exclusive whole-device logical overwrite, bounded flushes and readback."""
    target.check();fd = os.open(target.device, os.O_RDWR | os.O_EXCL | os.O_NOFOLLOW)
    try:
        require(os.fstat(fd).st_rdev == target.original, 'Wipe descriptor points to a different device.')
        size = struct.unpack('Q', fcntl.ioctl(fd, 0x80081272, bytes(8)))[0]
        require(size == target.disk['bytes'], 'Wipe device capacity changed.')
        expected = hashlib.sha256();done = 0
        while done < size:
            chunk = os.urandom(min(4 * 1024**2, size - done));expected.update(chunk);view = memoryview(chunk)
            while view:
                amount = os.write(fd, view);require(amount > 0, 'Device write stopped early.');view = view[amount:]
            done += len(chunk)
            if done % (32 * 1024**2) == 0 or done == size:
                os.fsync(fd);target.check();progress({'stage': 'random-fill', 'bytes': done, 'total': size})
        os.fsync(fd);fcntl.ioctl(fd, 0x1261);os.lseek(fd, 0, os.SEEK_SET)
        actual = hashlib.sha256();done = 0
        while done < size:
            chunk = os.read(fd, min(4 * 1024**2, size - done))
            require(chunk, 'Wipe readback stopped early.');actual.update(chunk);done += len(chunk)
            if done % (32 * 1024**2) == 0 or done == size:
                target.check();progress({'stage': 'verifying-random-fill', 'bytes': done, 'total': size})
        require(actual.digest() == expected.digest(), 'Random overwrite readback mismatch.')
    finally:os.close(fd)
