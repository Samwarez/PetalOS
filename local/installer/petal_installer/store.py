"""Selected offline SYSTEM access and constrained, explicit asset imports."""
from pathlib import Path
import contextlib
import getpass
import importlib.util
import json
import os
import re
import secrets
import stat
import tempfile

from . import InstallerError
from .linux import choose, command
from .plans import existing_layout
from .releases import plain_file, require

ROOT = Path(__file__).resolve().parents[3]
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z')
KINDS = ('vpn', 'wallpaper', 'theme', 'override')


def safe_directory(path):
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Store directory contains a symbolic link.')
    require(path.is_dir(), 'Selected SYSTEM settings directory is unavailable.')


def directory_fd(path):
    """Pin each directory component; later renames cannot redirect an import."""
    parts = Path(path).absolute().parts
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[1:]:
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = following
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_import(path, limit):
    path = Path(path).absolute()
    parent = directory_fd(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_size <= limit, 'Import must be a size-bounded regular file.')
        data = source.read(limit + 1)
        require(len(data) <= limit, 'Selected import grew beyond its size limit.')
        return data


def inventory(state):
    """Deliberately list user-selected settings names, never file contents."""
    state = Path(state)
    safe_directory(state)
    result = {}
    for relative in ('Network/Profiles', 'Wallpapers', 'Desktop', 'Installer/PendingThemes', 'Installer/PendingOverrides'):
        folder = state / relative
        if not folder.exists() and not folder.is_symlink():
            result[relative] = []
            continue
        safe_directory(folder)
        # Bounded, nonrecursive browsing; never traverse links.
        names = sorted(entry.name for entry in folder.iterdir() if entry.is_file() and not entry.is_symlink())
        require(len(names) <= 1000, 'Selected settings folder has too many entries to list.')
        result[relative] = names
    return result


def checked_payload(kind, source):
    require(kind in KINDS, 'Unsupported settings import kind.')
    source = plain_file(Path(source).absolute())
    limit = 32 * 1024**2 if kind == 'wallpaper' else 16384
    data = read_import(source, limit)
    if kind == 'vpn':
        candidate = ROOT / 'config/includes.chroot/usr/local/lib/portable/vpn_profiles.py'
        if not candidate.exists():candidate = Path(__file__).with_name('shared') / 'vpn_profiles.py'
        spec = importlib.util.spec_from_file_location('petalos_import_vpn', candidate)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        try:
            data = module.serialize(module.parse(data.decode('utf-8'))).encode()
        except (module.ProfileError, UnicodeError):
            raise InstallerError('Invalid VPN profile; executable hooks, hostname bootstrap and incomplete tunnel routes are refused. Contents suppressed.') from None
        return 'Network/Profiles', '.conf', data, True
    if kind == 'wallpaper':
        require(len(data) >= 33 and data[:8] == b'\x89PNG\r\n\x1a\n' and data[12:16] == b'IHDR',
                'Wallpaper import requires a PNG image.')
        width, height = int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')
        require(0 < width <= 16384 and 0 < height <= 16384 and width * height <= 64_000_000,
                'Wallpaper dimensions exceed the supported limit.')
        return 'Wallpapers', '.png', data, True
    try:
        value = json.loads(data)
    except (ValueError, UnicodeError):
        raise InstallerError('Theme/override imports must be JSON descriptions, not executable scripts.') from None
    require(type(value) is dict and value.get('format') == 1, 'Unsupported theme/override format.')
    if kind == 'theme':
        require(set(value) <= {'format', 'name', 'colors'} and isinstance(value.get('name'), str)
                and len(value['name']) <= 100 and type(value.get('colors')) is dict,
                'A theme contains format, name and colors.')
        require(value['colors'] and value['colors'].keys() <= {'background', 'surface', 'text', 'accent', 'border'},
                'Unknown theme color.')
        require(all(isinstance(v, str) and re.fullmatch(r'#[0-9A-Fa-f]{6}', v) for v in value['colors'].values()),
                'Theme colors must be six-digit hex colors.')
        return 'Installer/PendingThemes', '.json', json.dumps(value, indent=2).encode() + b'\n', False
    require(set(value) <= {'format', 'wallpaper', 'double_click_ms', 'double_click_distance'},
            'Overrides are limited to wallpaper and desktop double-click preferences.')
    require(len(value) > 1, 'Override contains no preferences.')
    if 'wallpaper' in value:
        require(isinstance(value['wallpaper'], str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.png', value['wallpaper']),
                'Override wallpaper must name an existing wallpaper PNG, without paths.')
    for key, low, high in [('double_click_ms', 100, 1500), ('double_click_distance', 1, 64)]:
        if key in value:
            require(type(value[key]) is int and low <= value[key] <= high, 'Desktop preference is outside its supported range.')
    return 'Installer/PendingOverrides', '.json', json.dumps(value, indent=2).encode() + b'\n', False


def import_file(state, kind, source, name, *, replace=False):
    state = Path(state)
    safe_directory(state)
    require(isinstance(name, str) and NAME.fullmatch(name), 'Import name must use letters, numbers, underscores or hyphens.')
    folder, suffix, data, active = checked_payload(kind, source)
    parentfd = directory_fd(state)
    staging = '.petalos-import-' + secrets.token_hex(12)
    fd = None
    try:
        for part in folder.split('/'):
            created = False
            try:
                following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parentfd)
            except FileNotFoundError:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=parentfd)
                    created = True
                except FileExistsError:
                    pass
                following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parentfd)
            os.close(parentfd)
            parentfd = following
            if created and os.geteuid() == 0:
                os.fchown(parentfd, 1000, 1000)
        fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parentfd)
        with os.fdopen(fd, 'wb') as output:
            if os.geteuid() == 0:
                os.fchown(output.fileno(), 1000, 1000)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        # Same-filesystem no-overwrite publication, even if the destination appears late.
        if replace:
            try:
                existing = os.stat(name + suffix, dir_fd=parentfd, follow_symlinks=False)
                require(stat.S_ISREG(existing.st_mode), 'Existing settings destination is not a regular file.')
            except FileNotFoundError:pass
            os.replace(staging, name + suffix, src_dir_fd=parentfd, dst_dir_fd=parentfd)
        else:
            os.link(staging, name + suffix, src_dir_fd=parentfd, dst_dir_fd=parentfd, follow_symlinks=False)
        os.fsync(parentfd)
    except OSError as error:
        if not isinstance(error, FileExistsError):
            raise InstallerError('Import path could not be accessed safely; existing files were preserved.') from None
        raise InstallerError('That settings file appeared during import; it was preserved.') from None
    finally:
        if fd is not None:
            try:os.unlink(staging, dir_fd=parentfd)
            except FileNotFoundError:pass
        os.close(parentfd)
    return {'imported': True, 'kind': kind, 'name': name, 'available_to_current_os': active,
            'status': 'Imported; VPN selection is unchanged.' if kind == 'vpn' else
                      'Imported; choose it in Desktop Settings.' if kind == 'wallpaper' else
                      'Staged inactive; current OS has no theme/override pack loader.'}


@contextlib.contextmanager
def system_session(device, *, writable=False, passphrase=None):
    """One pinned SYSTEM mount session, with cleanup and no Private access.

    Must run as root from a reviewed installation. Never called by the planner.
    """
    require(os.geteuid() == 0, 'Opening SYSTEM requires administrator privileges; run the store command in an administrator terminal.')
    disk = choose(device)
    layout = existing_layout(disk)
    system = layout['system']
    partition = Path(system['path'])
    require(not partition.is_symlink() and stat.S_ISBLK(partition.stat().st_mode), 'SYSTEM must be a real block partition.')
    original = partition.stat().st_rdev
    require(command(['/usr/sbin/cryptsetup', 'luksUUID', str(partition)]).decode().strip() == system['uuid'],
            'SYSTEM encryption identity changed.')
    command(['/usr/sbin/cryptsetup', 'isLuks', '--type', 'luks2', str(partition)])
    mapper = 'petalos_installer_' + secrets.token_hex(6)
    work = Path(tempfile.mkdtemp(prefix='petalos-installer-store-', dir='/run'))
    full, selected = work / 'full', work / 'settings'
    full.mkdir(mode=0o700)
    selected.mkdir(mode=0o700)
    opened = False
    mounted = []

    def identity():
        require(partition.stat().st_rdev == original, 'SYSTEM device identity changed.')
        current = Path('/dev/mapper') / mapper
        info = current.stat()
        slaves = list(Path('/sys/dev/block', f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}', 'slaves').iterdir())
        require(len(slaves) == 1 and slaves[0].name == partition.name, 'SYSTEM mapping does not match the selected partition.')

    try:
        # Recheck the complete disk before accepting the passphrase or opening it.
        require(choose(device)['identity'] == disk['identity'], 'Drive identity changed before unlock.')
        if passphrase is None:
            passphrase = getpass.getpass('SYSTEM passphrase (Private will stay closed): ')
        require(passphrase and '\n' not in passphrase and '\0' not in passphrase, 'Invalid passphrase input.')
        arguments = ['/usr/sbin/cryptsetup', 'open', '--type', 'luks2', '--key-file', '-']
        if not writable:
            arguments.append('--readonly')
        command([*arguments, str(partition), mapper], payload=passphrase.encode(), timeout=180)
        passphrase = None
        opened = True
        identity()
        options = 'nodev,nosuid,noexec,noatime' if writable else 'ro,noload,nodev,nosuid,noexec,noatime'
        command(['/usr/bin/mount', '-t', 'ext4', '-o', options, '/dev/mapper/' + mapper, str(full)])
        mounted.append(full)
        state = full / '.petalos-state'
        safe_directory(state)
        command(['/usr/bin/mount', '--bind', str(state), str(selected)])
        mounted.append(selected)
        command(['/usr/bin/mount', '-o', 'remount,bind,' + ('rw' if writable else 'ro') + ',nodev,nosuid,noexec', str(selected)])
        command(['/usr/bin/mount', '-o', 'remount,bind,ro,nodev,nosuid,noexec', str(full)])
        identity()
        yield selected
        if writable:
            command(['/usr/bin/sync', '-f', str(selected)])
    finally:
        passphrase = None
        try:
            for mount in reversed(mounted):
                identity()
                actual = command(['/usr/bin/findmnt', '-n', '-o', 'MAJ:MIN', '--mountpoint', str(mount)]).decode().strip()
                mapperdev = (Path('/dev/mapper') / mapper).stat().st_rdev
                require(actual == f'{os.major(mapperdev)}:{os.minor(mapperdev)}', 'Refused cleanup of a changed mount.')
                command(['/usr/bin/umount', str(mount)])
            if opened:
                identity()
                command(['/usr/sbin/cryptsetup', 'close', mapper])
            full.rmdir()
            selected.rmdir()
            work.rmdir()
        except BaseException:
            raise InstallerError('SYSTEM cleanup could not complete. Keep the drive connected and inspect installer mounts/mapping before removal.') from None
