"""Fixed application compartments. Root sets mounts, then drops real UID/caps."""
from pathlib import Path
import base64
import fcntl
import json
import os
import pwd
import grp
import hashlib
import re
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import tarfile
import time
import traceback
from urllib.parse import urlsplit, unquote

BASE = Path('/run/portable-compartments')
PAYLOAD = Path('/var/lib/portable-compartments')
ROLES = {'tor': 940, 'browser': 941, 'transmission': 942, 'pan': 943,
         'amule': 944, 'sabnzbd': 945, 'offline': 946, 'sab-viewer': 947}
PROGRAMS = {'transmission': '/usr/local/bin/portable-transmission',
            'pan': '/usr/local/bin/portable-pan', 'amule': '/usr/local/bin/portable-amule',
            'sabnzbd': '/usr/local/bin/portable-sabnzbd',
            'sab-viewer': '/usr/local/bin/portable-sab-view'}
LOCAL = {'geany', 'vim.basic', 'gthumb', 'lazpaint', 'keepassxc',
         'libreoffice', 'soffice', 'atril', 'parole', 'ristretto', 'mousepad', 'quodlibet'}
PRIVATE = Path('/mnt/private')
OFFLINE = {'offline-lazpaint': ('lazpaint', 948), 'offline-geany': ('geany', 949),
           'offline-gthumb': ('gthumb', 951),
           'offline-keepassxc': ('keepassxc', 952), 'offline-libreoffice': ('libreoffice', 953),
           'offline-atril': ('atril', 954), 'offline-parole': ('parole', 955),
           'offline-ristretto': ('ristretto', 956), 'offline-mousepad': ('mousepad', 957),
           'offline-quodlibet': ('quodlibet', 958),
           'offline-html': ('html', 959), 'offline-vim': ('vim', 960)}
ROLES.update({app: entry[1] for app, entry in OFFLINE.items()})


class CompartmentError(Exception):
    pass


def run(command, **kwargs):
    result = subprocess.run(command, stdin=subprocess.DEVNULL,
                            stdout=kwargs.pop('stdout', subprocess.DEVNULL), stderr=subprocess.DEVNULL,
                            timeout=kwargs.pop('timeout', 20), **kwargs)
    if result.returncode:
        raise CompartmentError('A required compartment operation failed.')


def protected(path, directory=True, uid=0, mode=0o700):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise CompartmentError('Unsafe compartment path.')
    if directory:
        created = not path.exists()
        path.mkdir(parents=True, exist_ok=True, mode=mode)
        if created:
            os.chown(path, uid, uid)
    info = path.lstat()
    if info.st_uid != uid or (directory and not stat.S_ISDIR(info.st_mode)):
        raise CompartmentError('Unexpected compartment owner.')
    path.chmod(mode)
    return path


def roles():
    assert os.geteuid() == 0
    for name, uid in ROLES.items():
        login = 'petal-' + name
        try:
            existing = pwd.getpwuid(uid)
            if existing.pw_name != login:
                raise CompartmentError('Application UID is already assigned.')
        except KeyError:
            try:
                existing = grp.getgrgid(uid)
                if existing.gr_name != login:
                    raise CompartmentError('Application GID is already assigned.')
            except KeyError:
                run(['/usr/sbin/groupadd', '--system', '--gid', str(uid), login])
            run(['/usr/sbin/useradd', '--system', '--uid', str(uid), '--gid', str(uid),
                 '--no-create-home', '--home-dir', '/nonexistent/' + login,
                 '--shell', '/usr/sbin/nologin', login])
        user = pwd.getpwnam(login)
        if user.pw_uid != uid or user.pw_gid != uid:
            raise CompartmentError('Application identity is inconsistent.')


def root_admin_configured():
    result = subprocess.run(['/usr/bin/passwd', '-S', 'root'], capture_output=True,
                            timeout=5, env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
    fields = result.stdout.split()
    return result.returncode == 0 and len(fields) > 1 and fields[1] == b'P'


def inside(app):
    """Recognize a sealed root delegation, never a cached VPN flag."""
    if app not in ROLES or os.getuid() != ROLES[app] or os.geteuid() != ROLES[app]:
        return False
    if Path('/proc/self/uid_map').read_text().split() != ['0', '0', '4294967295']:
        return False
    path = Path('/run/petalos-compartment.json')
    try:
        info = path.lstat()
        return (stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022
                and json.loads(path.read_text()) == {'app': app, 'uid': ROLES[app]}
                and os.environ.get('HOME') == virtual_home(app))
    except (OSError, ValueError):
        return False


def private_ready():
    if Path('/run/portable-storage/locking').exists():
        raise CompartmentError('Encrypted storage is locking or locked.')
    result = subprocess.run(['/usr/bin/findmnt', '-n', '-o', 'SOURCE', '--mountpoint', str(PRIVATE)], capture_output=True, timeout=5)
    if result.returncode or result.stdout.strip() != b'/dev/mapper/portable_data':
        raise CompartmentError('The encrypted Private volume is not mounted.')


def private_available():
    try:
        private_ready()
        return True
    except CompartmentError:
        return False


def ram_folder(app, category):
    ram_ready()
    assert category in ('Documents', 'Downloads')
    parent = Path('/home/Petal') / category
    name = OFFLINE[app][0] if app in OFFLINE else ('TorBrowser' if app == 'browser' else app)
    home_fd = os.open('/home/Petal', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    parent_fd = folder_fd = None
    try:
        if os.fstat(home_fd).st_uid != 1000:
            raise CompartmentError('Unexpected desktop home owner.')
        try:
            os.mkdir(category, mode=0o700, dir_fd=home_fd)
            created = True
        except FileExistsError:
            created = False
        parent_fd = os.open(category, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=home_fd)
        if created:
            os.fchown(parent_fd, 1000, 1000)
        if os.fstat(parent_fd).st_uid != 1000:
            raise CompartmentError('Unexpected RAM content folder owner.')
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
            created = True
        except FileExistsError:
            created = False
        folder_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        if created:
            os.fchown(folder_fd, 1000, 1000)
        grant(parent / name, ROLES[app], directory_fd=folder_fd)
        return parent / name
    finally:
        for fd in (folder_fd, parent_fd, home_fd):
            if fd is not None:
                os.close(fd)


def private_content_parent(category):
    """Keep user content browsable without delegating sibling app folders."""
    assert category in ('Documents', 'Downloads')
    private_ready()
    root_fd = os.open(PRIVATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    parent_fd = None
    try:
        try:
            os.mkdir(category, mode=0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        parent_fd = os.open(category, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        info = os.fstat(parent_fd)
        if info.st_dev != os.fstat(root_fd).st_dev or info.st_uid not in (0, 1000):
            raise CompartmentError('Unexpected Private content folder owner or filesystem.')
        # Earlier mkdir(parents=True) calls left new category parents root-only.
        # Repair only this pinned parent inode; child ownership/ACLs stay intact.
        os.fchown(parent_fd, 1000, 1000)
        os.fchmod(parent_fd, 0o700)
    finally:
        for fd in (parent_fd, root_fd):
            if fd is not None:
                os.close(fd)


def storage_setup(app):
    if app in OFFLINE:
        ram_folder(app, 'Documents')
    elif app in ('browser', 'transmission', 'pan', 'amule', 'sabnzbd'):
        ram_folder(app, 'Downloads')
    if app in ('transmission', 'pan', 'amule', 'sabnzbd'):
        protected(PAYLOAD); protected(PAYLOAD / app)
        protected(PAYLOAD / app / 'state', uid=ROLES[app])
    if not private_available():
        return
    if app in OFFLINE:
        private_content_parent('Documents')
    elif app in ('transmission', 'pan', 'amule', 'sabnzbd', 'browser'):
        private_content_parent('Downloads')
    if app in ('transmission', 'pan', 'amule', 'sabnzbd'):
        for base in ('AppState', 'Downloads'):
            grant(PRIVATE / base / app, ROLES[app])
    elif app == 'browser':
        grant(PRIVATE / 'Downloads/TorBrowser', ROLES[app])
    elif app in OFFLINE:
        grant(PRIVATE / 'Documents' / OFFLINE[app][0], ROLES[app])


def ram_ready():
    if 'toram' not in Path('/proc/cmdline').read_text().split():
        raise CompartmentError('Applications require the RAM live system.')
    result = subprocess.run(['/usr/bin/findmnt', '-n', '-o', 'FSTYPE,OPTIONS', '--mountpoint', '/'],
                            capture_output=True, text=True, timeout=5)
    fields = result.stdout.split()
    if result.returncode or len(fields) != 2:
        raise CompartmentError('Cannot verify the writable live filesystem.')
    if fields[0] == 'tmpfs':
        return
    upper = next((x.split('=', 1)[1] for x in fields[1].split(',') if x.startswith('upperdir=')), None)
    if fields[0] != 'overlay' or not upper or not upper.startswith('/'):
        raise CompartmentError('The writable live filesystem is not RAM.')
    result = subprocess.run(['/usr/bin/findmnt', '-n', '-o', 'FSTYPE', '--target', upper],
                            capture_output=True, text=True, timeout=5)
    if result.returncode or result.stdout.strip() != 'tmpfs':
        raise CompartmentError('The writable live filesystem is not RAM.')


def gate(app):
    ram_ready()
    if app != 'offline' and app not in OFFLINE:
        helper = 'portable-check-tor-ready' if app in ('tor', 'browser') else 'portable-check-network-ready'
        run(['/usr/local/sbin/' + helper], timeout=25)


def file_record(path, value):
    temporary = path.with_name('.' + path.name + '-' + secrets.token_hex(8))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as output:
        json.dump(value, output)
    os.replace(temporary, path)


def read_record(app):
    path = BASE / app / 'status.json'
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'r') as source:
            info = os.fstat(source.fileno())
            if info.st_uid or info.st_mode & 0o077 or not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
                raise CompartmentError('Invalid compartment status metadata.')
            return json.load(source)
    except FileNotFoundError:
        return {}


def worker_alive(record):
    try:
        process = Path('/proc') / str(record['pid'])
        fields = process.joinpath('stat').read_text().split(') ')[1].split()
        current = fields[19]
        command = process.joinpath('cmdline').read_bytes().split(b'\0')
        return (fields[0] != 'Z' and process.stat().st_uid == 0 and current == record['start'] and
                b'/usr/local/sbin/portable-compartment' in command and b'--worker' in command)
    except (FileNotFoundError, KeyError, ProcessLookupError):
        return False


def grant(directory, uid, *, directory_fd=None):
    # Only this application's directories are delegated, not Private's root.
    # Physical traversal skips symlinks; no file contents are inspected.
    if directory_fd is None:
        if any(p.is_symlink() for p in (directory, *directory.parents)):
            raise CompartmentError('Application storage cannot be a symlink.')
        created = not directory.exists()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if created:
            os.chown(directory, 1000, 1000)
    deadline = time.monotonic() + 60
    def visit(fd):
        info = os.fstat(fd)
        is_directory = stat.S_ISDIR(info.st_mode)
        if info.st_uid not in (1000, uid) or not (is_directory or stat.S_ISREG(info.st_mode)):
            raise CompartmentError('Unexpected application storage object.')
        if time.monotonic() > deadline:
            raise CompartmentError('Application storage permission update timed out.')
        acl = 'u:' + str(uid) + ':rwX,u:1000:rwX'
        if is_directory:
            acl += ',d:u:' + str(uid) + ':rwx,d:u:1000:rwx'
        # Pin each inode before delegating it. Concurrent rename/symlink
        # changes cannot redirect a privileged recursive path traversal.
        run(['/usr/bin/setfacl', '-m', acl, '/proc/self/fd/' + str(fd)], pass_fds=(fd,))
        if is_directory:
            for name in os.listdir(fd):
                try:
                    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                except (FileNotFoundError, PermissionError):
                    continue
                except OSError as error:
                    if error.errno == 40:  # symlinks are never delegated
                        continue
                    raise
                try:
                    visit(child)
                finally:
                    os.close(child)
    fd = os.dup(directory_fd) if directory_fd is not None else os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        visit(fd)
    finally:
        os.close(fd)


def home(app):
    protected(PAYLOAD)
    protected(PAYLOAD / app)
    location = PAYLOAD / app / 'home'
    if location.is_symlink():
        raise CompartmentError('Unsafe RAM home.')
    created = not location.exists()
    location.mkdir(mode=0o700, exist_ok=True)
    if created and (app in ('browser', 'transmission', 'pan', 'amule', 'sabnzbd') or app in OFFLINE):
        # Only a fresh, still root-owned home is seeded. Never write through
        # paths a running app can replace with symlinks.
        name = 'TorBrowser' if app == 'browser' else app
        download = ('/mnt/ram/Documents/' + OFFLINE[app][0]) if app in OFFLINE else '/mnt/ram/Downloads/' + name
        available = private_available()
        if available:
            (location / 'Private').symlink_to('/mnt/private')
        (location / 'Downloads').symlink_to(download)
        if app in OFFLINE:
            (location / 'Documents').symlink_to(download)
        configuration = location / '.config'
        configuration.mkdir(mode=0o700)
        if app in OFFLINE and OFFLINE[app][0] == 'keepassxc':
            name = OFFLINE[app][0]
            filename = 'keepassxc.ini'
            directory = configuration / name
            directory.mkdir(mode=0o700)
            shutil.copyfile(Path('/etc/skel/.config') / name / filename, directory / filename)
        (configuration / 'user-dirs.dirs').write_text('XDG_DOWNLOAD_DIR="' + download + '"\n')
        for toolkit in ('gtk-3.0', 'gtk-4.0'):
            directory = configuration / toolkit
            directory.mkdir(mode=0o700)
            private = download.replace('/mnt/ram/', '/mnt/private/')
            (directory / 'bookmarks').write_text('file://' + download + ' RAM files (temporary)\n' +
                ('file://' + private + ' Private files\n' if available else ''))
        for parent, directories, files in os.walk(configuration, followlinks=False):
            os.chown(parent, ROLES[app], ROLES[app])
            for item in files:
                os.chown(Path(parent) / item, ROLES[app], ROLES[app])
    os.chown(location, ROLES[app], ROLES[app])
    location.chmod(0o700)
    return location


def reset_ram(app):
    # This UID belongs solely to this app. Pin surviving processes before
    # signalling them; never infer identity from a recycled numeric PID.
    def survivors():
        entries = []
        for path in Path('/proc').iterdir():
            if not path.name.isdigit():
                continue
            try:
                if path.stat().st_uid != ROLES[app]:
                    continue
                if path.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[0] == 'Z':
                    continue
                fd = os.pidfd_open(int(path.name))
                if path.stat().st_uid == ROLES[app]:
                    entries.append(fd)
                else:
                    os.close(fd)
            except (FileNotFoundError, ProcessLookupError):
                pass
        return entries
    # A hostile survivor can fork while the first enumeration is in progress.
    # Verify quiescence before touching any role-owned home path as root.
    for attempt in range(27):
        active = survivors()
        if not active:
            break
        sent = signal.SIGTERM if attempt == 0 else signal.SIGKILL
        for fd in active:
            try:
                signal.pidfd_send_signal(fd, sent)
            except ProcessLookupError:
                pass
            finally:
                os.close(fd)
        time.sleep(0.2)
    else:
        raise CompartmentError('Application processes remain; RAM cleanup refused.')
    protected(PAYLOAD);protected(PAYLOAD / app)
    for path in (PAYLOAD / app / 'home', BASE / app / 'runtime', BASE / app / 'opened'):
        if path.is_symlink():
            raise CompartmentError('Unsafe application RAM directory.')
        if path.exists():
            # Python's fd-based rmtree does not follow child symlinks.
            if not shutil.rmtree.avoids_symlink_attacks:
                raise CompartmentError('Safe RAM cleanup is unavailable.')
            shutil.rmtree(path)


def virtual_home(app):
    return '/home/petal-' + app


def import_items(app, arguments):
    """Read selected files as Petal, then delegate a bounded RAM copy."""
    result = []
    for value in arguments:
        if app == 'transmission' and value.startswith('magnet:'):
            result.append(value)
            continue
        if app == 'amule' and value.startswith('ed2k://'):
            result.append('--link=' + value)
            continue
        parsed = urlsplit(value)
        if parsed.scheme == 'file':
            if parsed.netloc not in ('', 'localhost') or parsed.query or parsed.fragment:
                raise CompartmentError('Unsupported file URL.')
            value = unquote(parsed.path)
        elif parsed.scheme:
            raise CompartmentError('Unsupported application item.')
        suffix = {'transmission': '.torrent', 'pan': '.nzb'}.get(app)
        path = Path(value)
        if suffix is None or not path.is_absolute() or path.suffix.lower() != suffix:
            raise CompartmentError('Choose a supported local file.')
        folder = protected(BASE / app / 'imports', mode=0o755)
        target = folder / (secrets.token_hex(16) + suffix)
        reader = '''import os,stat,sys
fd=os.open(sys.argv[1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
with os.fdopen(fd,'rb') as source:
 info=os.fstat(source.fileno())
 assert stat.S_ISREG(info.st_mode) and 0<info.st_size<=64*1024**2
 data=source.read(64*1024**2+1)
 assert len(data)<=64*1024**2
 sys.stdout.buffer.write(data)
'''
        try:
            with target.open('xb') as output:
                run(['/usr/bin/setpriv', '--reuid', '1000', '--regid', '1000', '--clear-groups',
                     '--inh-caps=-all', '--bounding-set=-all', '--ambient-caps=-all', '--no-new-privs',
                     '--', '/usr/bin/python3', '-I', '-c', reader, str(path)],
                    stdout=output, timeout=15)
            target.chmod(0o644)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        result.append('/run/petalos-imports/' + target.name)
    return result


def distribution():
    from tor_archives import current, verify
    archive = current()
    protected(PAYLOAD)
    cache = protected(PAYLOAD / 'distribution')
    # First copy into a root-only RAM directory, then verify that exact copy.
    # Signed public payload only; never copy a browsing profile.
    copied = cache / archive.name
    signature = Path(str(copied) + '.asc')
    # Serialize copies/extraction across workers. Content-addressed generations
    # leave existing read-only mounts intact when the selected archive changes.
    lock = os.open(cache / 'extract.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock, 'r+b') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX)
        copied.unlink(missing_ok=True)
        signature.unlink(missing_ok=True)
        for source, destination in ((archive, copied), (Path(str(archive) + '.asc'), signature)):
            fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as input_file, destination.open('xb') as output:
                info = os.fstat(input_file.fileno())
                limit = 1024**2 if destination == signature else 512 * 1024**2
                if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
                    raise CompartmentError('Invalid public Tor archive.')
                copied_bytes = 0
                while data := input_file.read(1024 * 1024):
                    copied_bytes += len(data)
                    if copied_bytes > limit:
                        raise CompartmentError('Public Tor archive grew beyond its limit.')
                    output.write(data)
            destination.chmod(0o600)
        verify(copied, signature)
        with copied.open('rb') as contents:
            digest = hashlib.file_digest(contents, 'sha256').hexdigest()
        generation = protected(cache / digest)
        target = generation / 'tor-browser'
        if target.exists():
            copied.unlink();signature.unlink()
            return target
        temporary = cache / 'extracting'
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir(mode=0o700)
        try:
            with tarfile.open(copied) as package:
                package.extractall(temporary, filter='data')
            for root, directories, files in os.walk(temporary / 'tor-browser', followlinks=False):
                Path(root).chmod(0o755)
                for name in files:
                    public = Path(root) / name
                    if not public.is_symlink():
                        public.chmod(0o755 if public.stat().st_mode & 0o111 else 0o644)
            os.replace(temporary / 'tor-browser', target)
        finally:
            shutil.rmtree(temporary)
        copied.unlink();signature.unlink()
        return target


def prepare_tor_home(app):
    target = home(app) / '.local/share/portable-tor/tor-browser'
    public = distribution()
    data = target / 'Browser/TorBrowser/Data'
    if not data.exists():
        data.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(public / 'Browser/TorBrowser/Data', data, symlinks=True)
        for root, directories, files in os.walk(home(app), followlinks=False):
            os.chown(root, ROLES[app], ROLES[app])
            for name in [*directories, *files]:
                os.chown(Path(root) / name, ROLES[app], ROLES[app], follow_symlinks=False)
    if app == 'browser':
        profile = target / 'Browser/TorBrowser/Data/Browser/profile.default'
        policy = target / 'Browser/distribution/policies.json'
        policy.parent.mkdir(exist_ok=True)
        policy.write_text(json.dumps({'policies': {'DisableAppUpdate': True}}))
        (profile / 'user.js').write_text(
            'user_pref("torbrowser.settings.quickstart.enabled", true);\n'
            'user_pref("intl.language_notification.shown", true);\n'
            'user_pref("browser.download.folderList", 2);\n'
            'user_pref("browser.download.dir", "/mnt/ram/Downloads/TorBrowser");\n'
            'user_pref("network.proxy.type", 1);\n'
            'user_pref("network.proxy.socks", "file:///run/portable-tor/socks.sock");\n'
            'user_pref("network.proxy.socks_port", 0);\n'
            'user_pref("network.proxy.socks_version", 5);\n'
            'user_pref("network.proxy.socks_remote_dns", true);\n'
            'user_pref("extensions.torlauncher.start_tor", false);\n'
            'user_pref("extensions.torlauncher.socks_port_use_ipc", true);\n'
            'user_pref("extensions.torlauncher.socks_ipc_path", "/run/portable-tor/socks.sock");\n'
            'user_pref("extensions.torlauncher.control_port_use_ipc", true);\n'
            'user_pref("extensions.torlauncher.control_ipc_path", "/run/portable-tor/control.sock");\n')
        for path in (policy, profile / 'user.js'):
            os.chown(path, ROLES[app], ROLES[app])
    return target


def sandbox(app, command, *, extra_binds=(), wayland=None, environment=None, opened_media=()):
    assert os.geteuid() == 0
    uid = ROLES[app]
    target_home = virtual_home(app)
    runtime = protected(BASE / app / 'runtime', uid=uid)
    options = ['bwrap', '--die-with-parent', '--ro-bind', '/', '/', '--unshare-pid', '--unshare-ipc',
               '--proc', '/proc', '--dev', '/dev', '--chmod', '1777', '/dev/shm',
               '--perms', '1777', '--tmpfs', '/tmp', '--tmpfs', '/run',
               '--tmpfs', '/home', '--tmpfs', '/root', '--tmpfs', '/mnt', '--tmpfs', '/media',
               '--tmpfs', '/sys',
               '--ro-bind', '/sys/devices/system/cpu', '/sys/devices/system/cpu',
               '--ro-bind', '/sys/kernel/mm/transparent_hugepage', '/sys/kernel/mm/transparent_hugepage',
               '--chmod', '0755', '/sys/devices', '--chmod', '0755', '/sys/devices/system',
               '--chmod', '0755', '/sys/kernel', '--chmod', '0755', '/sys/kernel/mm',
               '--bind', str(home(app)), target_home,
               '--dir', '/run/user', '--chmod', '0755', '/run/user',
               '--bind', str(runtime), '/run/user/' + str(uid),
               '--chdir', target_home, '--clearenv',
               '--setenv', 'PATH', '/usr/local/bin:/usr/bin:/bin',
               '--setenv', 'HOME', target_home, '--setenv', 'USER', 'petal-' + app,
               '--setenv', 'LOGNAME', 'petal-' + app, '--setenv', 'LC_ALL', 'C.UTF-8',
               '--setenv', 'XDG_RUNTIME_DIR', '/run/user/' + str(uid),
               '--setenv', 'PORTABLE_COMPARTMENT', app,
               '--setenv', 'DBUS_SYSTEM_BUS_ADDRESS', 'unix:path=/run/no-system-bus',
               '--setenv', 'GSK_RENDERER', 'cairo', '--setenv', 'LIBGL_ALWAYS_SOFTWARE', '1',
               '--setenv', 'GTK_USE_PORTAL', '0']
    if app in ('browser', 'offline', 'sab-viewer') or app in OFFLINE:
        options += ['--unshare-net']
    if app in ('tor', 'browser'):
        installation = target_home + '/.local/share/portable-tor/tor-browser'
        local = home(app) / '.local/share/portable-tor/tor-browser'
        options += ['--ro-bind', str(distribution()), installation,
                    '--bind', str(local / 'Browser/TorBrowser/Data'), installation + '/Browser/TorBrowser/Data']
        if app == 'browser':
            options += ['--ro-bind', str(local / 'Browser/distribution'), installation + '/Browser/distribution']
    available = private_available()
    # GDBus can ask the bus itself to StartServiceByName before making a
    # destination call. Hide notification activation files as well as denying
    # calls, so no layer-shell daemon starts on this restricted connection.
    for service in ('org.xfce.xfce4-notifyd.Notifications.service',
                    'org.xfce.xfce4-notifyd.Notifyd.service'):
        target = Path('/usr/share/dbus-1/services') / service
        if target.is_file():
            options += ['--ro-bind', '/dev/null', str(target)]
    notifyd = Path('/usr/lib/x86_64-linux-gnu/xfce4/notifyd/xfce4-notifyd')
    if notifyd.is_file():
        options += ['--ro-bind', '/usr/bin/false', str(notifyd)]
    if app in ('browser', 'transmission', 'pan', 'amule', 'sabnzbd') or app in OFFLINE:
        category = 'Documents' if app in OFFLINE else 'Downloads'
        name = OFFLINE[app][0] if app in OFFLINE else ('TorBrowser' if app == 'browser' else app)
        target = '/mnt/ram/' + category + '/' + name
        options += ['--dir', '/mnt/ram/' + category, '--chmod', '0755', '/mnt/ram/' + category,
                    '--bind', str(ram_folder(app, category)), target]
    if app in ('transmission', 'pan', 'amule', 'sabnzbd'):
        state_root = '/mnt/private' if available else '/mnt/ram'
        if not available:
            options += ['--dir', '/mnt/ram/AppState', '--chmod', '0755', '/mnt/ram/AppState',
                        '--bind', str(protected(PAYLOAD / app / 'state', uid=ROLES[app])), '/mnt/ram/AppState/' + app]
        options += ['--setenv', 'PORTABLE_STATE_ROOT', state_root]
    if available:
        options += ['--dir', '/mnt/private', '--chmod', '0755', '/mnt/private']
    if available and app in ('transmission', 'pan', 'amule', 'sabnzbd'):
        for base in ('AppState', 'Downloads'):
            options += ['--dir', '/mnt/private/' + base, '--chmod', '0755', '/mnt/private/' + base]
            options += ['--bind', str(PRIVATE / base / app), '/mnt/private/' + base + '/' + app]
        imports = BASE / app / 'imports'
        if imports.exists():
            options += ['--ro-bind', str(imports), '/run/petalos-imports']
    elif available and app == 'browser':
        options += ['--dir', '/mnt/private/Downloads', '--chmod', '0755', '/mnt/private/Downloads']
        options += ['--bind', str(PRIVATE / 'Downloads/TorBrowser'), '/mnt/private/Downloads/TorBrowser']
    elif app in OFFLINE:
        name = OFFLINE[app][0]
        if available:
            options += ['--dir', '/mnt/private/Documents', '--chmod', '0755', '/mnt/private/Documents',
                        '--bind', str(PRIVATE / 'Documents' / name), '/mnt/private/Documents/' + name]
        options += ['--chdir', '/mnt/ram/Documents/' + name]
    elif app == 'offline':
        options += ['--bind', str(PRIVATE), '/mnt/private']
        for sensitive in ('Network', 'PortableSettings', 'AppState', 'Applications'):
            options += ['--tmpfs', '/mnt/private/' + sensitive]
    if wayland is not None:
        # Bind only the committed security-context listener, never the parent
        # runtime directory or the compositor's unrestricted display socket.
        options += ['--ro-bind', str(wayland['path']), '/run/user/' + str(uid) + '/wayland-0',
                    '--setenv', 'WAYLAND_DISPLAY', 'wayland-0',
                    '--setenv', 'XDG_SESSION_TYPE', 'wayland',
                    '--setenv', 'GDK_BACKEND', 'wayland', '--setenv', 'QT_QPA_PLATFORM', 'wayland',
                    '--setenv', 'MOZ_ENABLE_WAYLAND', '1', '--setenv', 'SDL_VIDEODRIVER', 'wayland']
    if app in OFFLINE:
        options += ['--dir', '/run/petalos-opened', '--chmod', '0755', '/run/petalos-opened']
    for source, destination, writable in extra_binds:
        options += ['--bind' if writable else '--ro-bind', str(source), destination]
    for name, value in (environment or {}).items():
        options += ['--setenv', name, value]
    # Root owns the mount/PID/net namespaces. setpriv then changes the actual
    # host UID, removes supplementary groups/caps and sets no_new_privs.
    # --uid on a root-created single-user namespace would map back to host UID0.
    inner = ['/usr/bin/setpriv', '--reuid', str(uid), '--regid', str(uid),
                      '--clear-groups', '--inh-caps=-all', '--bounding-set=-all',
                      '--ambient-caps=-all', '--no-new-privs', '--', *command]
    if opened_media:
        assert app == 'offline-parole'
        inner = ['/usr/bin/python3', '-I', '/usr/local/lib/portable/media_fd_exec.py',
                 *opened_media, '--', *inner]
    return options + ['--', *inner]


def start_process(command, *, environment=None, pass_fds=(), umask=0o077):
    return subprocess.Popen(command, env=environment, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True, close_fds=True, pass_fds=pass_fds, umask=umask)


def display_server(app):
    from desktop_session import environment
    from wayland_context import Connection
    values = environment()
    connection = Connection(Path(values['XDG_RUNTIME_DIR']) / values['WAYLAND_DISPLAY'])
    path = BASE / app / 'wayland.sock'
    path.unlink(missing_ok=True)
    lease = None
    try:
        connection.watch_windows()
        baseline = set(connection.windows)
        lease = connection.create_listener(path, app, secrets.token_hex(16))
        os.chown(path, ROLES[app], ROLES[app])
        return {'connection': connection, 'lease': lease, 'path': path, 'baseline': baseline}
    except BaseException:
        if lease is not None:
            os.close(lease)
        connection.close()
        path.unlink(missing_ok=True)
        raise


def desktop_audio(command):
    result = subprocess.run(['/usr/bin/setpriv', '--reuid', '1000', '--regid', '1000',
                             '--clear-groups', '--no-new-privs', '--', '/usr/bin/pactl', *command],
        env={'PATH': '/usr/bin:/bin', 'HOME': '/home/Petal', 'XDG_RUNTIME_DIR': '/run/user/1000',
             'PULSE_SERVER': 'unix:/run/user/1000/pulse/native'}, capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise CompartmentError('The desktop audio bridge is unavailable.')
    return result.stdout.strip()


def gui_ready(app, display, processes):
    expected = {'transmission': {'transmission', 'transmission-gtk', 'com.transmissionbt.transmission'},
                'pan': {'pan'}, 'amule': {'amule'},
                'browser': {'torbrowser', 'Tor Browser', 'org.torproject.torbrowser', 'Navigator', 'firefox'},
                'sab-viewer': {'petalos-sab-viewer', 'portable-sab-view', 'python3'}}.get(app)
    if app in OFFLINE:
        name = OFFLINE[app][0]
        expected = {name, name + '.portable-real', name.capitalize()}
        expected.update({'gthumb': {'org.gnome.gThumb'},
                         'keepassxc': {'org.keepassxc.KeePassXC'},
                         'libreoffice': {'libreoffice-startcenter', 'libreoffice-writer', 'libreoffice-calc', 'libreoffice-impress'},
                         'mousepad': {'org.xfce.mousepad'},
                         'ristretto': {'org.xfce.ristretto'},
                         'quodlibet': {'io.github.quodlibet.QuodLibet'},
                         'html': {'firefox', 'firefox-esr', 'Navigator'},
                         'vim': {'xfce4-terminal', 'org.xfce.Terminal'}}.get(name, set()))
    connection = display['connection']
    for _ in range(600):
        if any(process.poll() is not None for process in processes):
            raise CompartmentError('An application component exited during startup.')
        connection.roundtrip()
        # GTK4 appends its D-Bus instance/window numbers to the application ID.
        if any(handle not in display['baseline'] and re.sub(r'_[0-9]+_[0-9]+$', '', app_id) in expected
               for handle, app_id in connection.windows.items()):
            return
        time.sleep(0.1)
    raise CompartmentError('The application did not map a native Wayland window.')


def playback(app, processes, modules):
    # The app gets a private Pulse server with a playback sink, no microphone,
    # host audio socket, host cookie or sound device. PCM flows out via a FIFO.
    protected(BASE / app / 'runtime', uid=ROLES[app])
    root = protected(Path('/run/portable-audio'), mode=0o755)
    directory = protected(root / app, mode=0o755)
    fifo = directory / 'playback.fifo'
    if fifo.exists():
        if not stat.S_ISFIFO(fifo.lstat().st_mode):
            raise CompartmentError('Unsafe audio FIFO.')
        fifo.unlink()
    staging = protected(Path('/run/portable-audio-staging'), uid=1000)
    initial = staging / (app + '-' + secrets.token_hex(16) + '.fifo')
    source = 'petalos_' + app.replace('-', '_')
    modules.append(desktop_audio(['load-module', 'module-pipe-source', 'source_name=' + source,
        'file=' + str(initial), 'format=s16le', 'rate=48000', 'channels=2']))
    fd = os.open(initial, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISFIFO(info.st_mode) or info.st_uid != 1000:
            raise CompartmentError('Unsafe desktop audio FIFO.')
        os.rename(initial, fifo)
        sealed = fifo.lstat()
        if (sealed.st_dev, sealed.st_ino) != (info.st_dev, info.st_ino) or not stat.S_ISFIFO(sealed.st_mode):
            raise CompartmentError('Desktop audio FIFO changed during setup.')
        os.fchown(fd, ROLES[app], 1000);os.fchmod(fd, 0o660)
    finally:
        os.close(fd)
    modules.append(desktop_audio(['load-module', 'module-loopback', 'source=' + source,
                                 'sink=@DEFAULT_SINK@', 'latency_msec=50']))
    config = BASE / app / 'pulse.pa'
    runtime = '/run/user/' + str(ROLES[app])
    # The desktop pipe-source drains promptly; FIFO backpressure cannot clock
    # playback. Pace this sink against real time so GStreamer's audio clock
    # does not race ahead and discard the corresponding video frames.
    config.write_text('load-module module-native-protocol-unix socket=' + runtime + '/pulse/native\n'
        'load-module module-pipe-sink sink_name=playback file=/run/portable-playback.fifo format=s16le rate=48000 channels=2 use_system_clock_for_timing=yes\n'
        'set-default-sink playback\n')
    config.chmod(0o644)
    (BASE / app / 'runtime/pulse').mkdir(mode=0o700, exist_ok=True)
    os.chown(BASE / app / 'runtime/pulse', ROLES[app], ROLES[app])
    command = ['/usr/bin/aa-exec', '-p', 'petalos_playback', '--', '/usr/bin/pulseaudio',
               '-n', '--daemonize=no', '--exit-idle-time=-1', '--use-pid-file=no',
               '--disallow-exit', '--disallow-module-loading', '--file=/run/pulse.pa']
    process = start_process(sandbox(app, command, extra_binds=[(fifo, '/run/portable-playback.fifo', True),
                             (config, '/run/pulse.pa', False)]))
    processes.append(process)
    for _ in range(50):
        if process.poll() is not None:
            raise CompartmentError('Private playback stopped.')
        if (BASE / app / 'runtime/pulse/native').is_socket():
            return 'unix:' + runtime + '/pulse/native'
        time.sleep(0.1)
    raise CompartmentError('Private playback did not become ready.')


def stop(app):
    record = read_record(app)
    if worker_alive(record):
        os.kill(record['pid'], signal.SIGTERM)
        for _ in range(100):
            if not worker_alive(record):
                return
            time.sleep(0.1)
        raise CompartmentError('The compartment is still stopping.')


def prepare(app):
    if app not in ('transmission', 'pan', 'amule'):
        raise CompartmentError('Unsupported preparation action.')
    roles();gate(app);protected(BASE)
    directory = protected(BASE / app)
    if worker_alive(read_record(app)):
        return
    if 'petalos_' + app + ' (enforce)' not in Path('/sys/kernel/security/apparmor/profiles').read_text().splitlines():
        raise CompartmentError('Application confinement is unavailable.')
    home(app)
    storage_setup(app)
    marker = directory / 'identity.json'
    file_record(marker, {'app': app, 'uid': ROLES[app]});marker.chmod(0o644)
    run(sandbox(app, ['/usr/bin/aa-exec', '-p', 'petalos_' + app, '--', PROGRAMS[app], '--prepare'],
                extra_binds=[(marker, '/run/petalos-compartment.json', False)]), timeout=30)
    if private_available():
        for base in ('AppState', 'Downloads'):
            grant(PRIVATE / base / app, ROLES[app])


def start(app, arguments=()):
    roles()
    protected(BASE)
    directory = protected(BASE / app)
    record = read_record(app)
    if worker_alive(record):
        if record.get('phase') != 'ready':
            raise CompartmentError('The existing compartment is not ready.')
        if arguments:
            if app != 'offline-parole':
                raise CompartmentError('Close the existing compartment before opening another item.')
            # Each selection receives a fresh read-only file grant. Media has
            # no unsaved document edits; retire the old grant before replacing it.
            stop(app)
        else:
            return record
    reset_ram(app)
    if arguments and app in ('transmission', 'pan', 'amule'):
        arguments = import_items(app, arguments)
    token = secrets.token_hex(16)
    request = {'arguments': list(arguments), 'token': token}
    file_record(directory / 'request.json', request)
    child = start_process(['/usr/bin/python3', '-I', '/usr/local/sbin/portable-compartment', '--worker', app, token],
                          environment={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': '/root', 'LC_ALL': 'C.UTF-8'})
    for _ in range(1800):
        record = read_record(app)
        if record.get('token') == token and record.get('phase') == 'ready' and worker_alive(record):
            return record
        if child.poll() is not None or (record.get('token') == token and record.get('phase') == 'failed'):
            raise CompartmentError('The application compartment failed to start.')
        time.sleep(0.1)
    child.terminate()
    raise CompartmentError('The application compartment did not become ready.')


def supervise(app, token):
    assert os.geteuid() == 0 and app in ROLES
    directory = protected(BASE / app)
    request = json.loads((directory / 'request.json').read_text())
    if request['token'] != token:
        raise CompartmentError('Unexpected compartment request.')
    state = {'pid': os.getpid(), 'start': Path('/proc/self/stat').read_text().split(') ')[1].split()[19],
             'token': token, 'phase': 'starting', 'uid': ROLES[app]}
    def update(phase):
        state['phase'] = phase
        file_record(directory / 'status.json', state)
    processes = []
    audio_modules = []
    delegated_fds = []
    control = None
    display = None
    stopped = False
    def terminate(*_):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    update('starting')
    try:
        gate(app)
        profile = {'tor': 'petalos_isolated_tor', 'browser': 'petalos_browser',
                   'sab-viewer': 'petalos_sab_viewer'}.get(app, 'petalos_' + app)
        if app in OFFLINE:
            profile = 'petalos_' + app.replace('-', '_')
        loaded = Path('/sys/kernel/security/apparmor/profiles').read_text().splitlines()
        if profile + ' (enforce)' not in loaded:
            raise CompartmentError('Application confinement is unavailable.')
        home(app)
        if app in ('tor', 'browser'):
            prepare_tor_home(app)
        storage_setup(app)
        state['storage'] = 'private' if private_available() else 'ram'
        marker = directory / 'identity.json'
        file_record(marker, {'app': app, 'uid': ROLES[app]})
        marker.chmod(0o644)
        binds = [(marker, '/run/petalos-compartment.json', False)]
        from app_preferences import snapshot
        preferences = directory / 'preferences.json'
        have_preferences = snapshot(app, preferences)
        if have_preferences:
            binds.append((preferences, '/run/petalos-preferences.json', False))
        environment = {}
        arguments = request['arguments']
        if app == 'tor':
            backend = protected(Path('/run/portable-tor-backend'), uid=ROLES['tor'])
            config = directory / 'torrc'
            data = virtual_home('tor') + '/.local/share/portable-tor/tor-browser/Browser/TorBrowser/Data/Tor'
            config.write_text('DataDirectory ' + data + '\nClientOnly 1\nAvoidDiskWrites 1\nSocksPort unix:/run/portable-tor-backend/socks.sock IsolateSOCKSAuth\nControlSocket /run/portable-tor-backend/control.sock\nCookieAuthentication 1\nCookieAuthFile /run/portable-tor-backend/control_auth_cookie\nLog notice stdout\n')
            config.chmod(0o644)
            binds += [(backend, '/run/portable-tor-backend', True), (config, '/run/torrc', False)]
            executable = virtual_home('tor') + '/.local/share/portable-tor/tor-browser/Browser/TorBrowser/Tor/tor'
            command = ['/usr/bin/env', 'LD_LIBRARY_PATH=' + str(Path(executable).parent),
                       '/usr/bin/aa-exec', '-p', 'petalos_isolated_tor', '--', executable, '-f', '/run/torrc']
            process = start_process(sandbox(app, command, extra_binds=binds))
            processes.append(process)
            from tor_control import query, serve
            for _ in range(1500):
                if stopped or process.poll() is not None:
                    raise CompartmentError('Tor backend did not start.')
                try:
                    cookie = (backend / 'control_auth_cookie').read_bytes()
                    if len(cookie) == 32 and b'PROGRESS=100' in query(backend / 'control.sock', cookie, 'GETINFO status/bootstrap-phase'):
                        break
                except (OSError, RuntimeError):
                    pass
                time.sleep(0.1)
            else:
                raise CompartmentError('Tor bootstrap timed out.')
            front = protected(Path('/run/portable-tor'), mode=0o750)
            os.chown(front, 0, ROLES['browser'])
            frontend_cookie = secrets.token_bytes(32)
            target = front / 'control_auth_cookie'
            target.write_bytes(frontend_cookie)
            os.chown(target, 0, ROLES['browser']);target.chmod(0o640)
            for name in ('socks.sock', 'control.sock'):
                (front / name).unlink(missing_ok=True)
            processes.append(start_process(['/usr/bin/socat', 'UNIX-LISTEN:' + str(front / 'socks.sock') + ',fork,mode=0660,group=petal-browser', 'UNIX-CONNECT:' + str(backend / 'socks.sock')]))
            version_reply = query(backend / 'control.sock', cookie, 'GETINFO version').decode()
            version = next(x.split('=', 1)[1] for x in version_reply.splitlines() if x.startswith('250-version='))
            control = serve(front / 'control.sock', backend / 'control.sock', frontend_cookie, cookie, ROLES['browser'], version)
            for _ in range(50):
                if (front / 'socks.sock').is_socket():
                    break
                time.sleep(0.1)
            else:
                raise CompartmentError('Tor Unix bridge did not start.')
        else:
            display = display_server(app) if app != 'sabnzbd' else None
            if app == 'browser':
                binds += [(Path('/run/portable-tor'), '/run/portable-tor', False)]
                environment = {'TOR_SKIP_LAUNCH': '1', 'TOR_SOCKS_IPC_PATH': '/run/portable-tor/socks.sock',
                               'TOR_CONTROL_IPC_PATH': '/run/portable-tor/control.sock',
                               'TOR_CONTROL_COOKIE_AUTH_FILE': '/run/portable-tor/control_auth_cookie'}
                environment['PULSE_SERVER'] = playback(app, processes, audio_modules)
                program = virtual_home(app) + '/.local/share/portable-tor/tor-browser/Browser/start-tor-browser'
                # The signed starter runs inside the filesystem/net/display
                # boundary; firefox.real has an automatic named attachment.
                command = [program, *arguments]
            elif app == 'sab-viewer':
                bridge = protected(Path('/run/portable-sab-admin'), mode=0o750)
                os.chown(bridge, 0, ROLES[app])
                (bridge / 'control.sock').unlink(missing_ok=True)
                processes.append(start_process(['/usr/bin/python3', '-I', '/usr/local/lib/portable/sab_bridge.py']))
                for _ in range(50):
                    if (bridge / 'control.sock').is_socket():
                        break
                    if processes[-1].poll() is not None:
                        raise CompartmentError('Management bridge exited during startup.')
                    time.sleep(0.1)
                else:
                    raise CompartmentError('Management bridge did not start.')
                binds += [(bridge, '/run/user/' + str(ROLES[app]) + '/portable-sab-admin', False)]
                environment['PORTABLE_SAB_ADMIN'] = '1'
                command = ['/usr/bin/aa-exec', '-p', 'petalos_sab_viewer', '--', PROGRAMS[app]]
            elif app in OFFLINE:
                name = OFFLINE[app][0]
                from offline_files import delegate
                arguments, selected, delegated_fds = delegate(arguments, name)
                binds += selected
                flags = []
                if name in ('parole', 'quodlibet'):
                    environment['PULSE_SERVER'] = playback(app, processes, audio_modules)
                if name == 'libreoffice':
                    environment['SAL_USE_VCLPLUGIN'] = 'gtk3'
                program = ['/usr/bin/' + name + '.portable-real', *flags, *arguments]
                if name == 'html':
                    program = ['/usr/lib/firefox-esr/firefox-esr', '--no-remote', *arguments]
                elif name == 'vim':
                    # A native terminal belongs to the Vim role; it has no
                    # connection to the desktop user's terminal server or bus.
                    program = ['/usr/bin/xfce4-terminal', '--disable-server',
                               '--title=PetalOS Vim', '--execute',
                               '/usr/bin/vim.basic.portable-real', *arguments]
                elif name == 'parole':
                    program = ['/usr/bin/python3', '-I', '/usr/local/lib/portable/parole_runner.py', *program]
                command = ['/usr/bin/aa-exec', '-p', profile, '--', *program]
            elif app == 'offline':
                raise CompartmentError('Offline file delegation is not configured yet.')
            else:
                if app == 'amule':
                    bridge = protected(BASE / 'amule/media', mode=0o750)
                    os.chown(bridge, 0, ROLES[app])
                    (bridge / 'control.sock').unlink(missing_ok=True)
                    processes.append(start_process(['/usr/bin/python3', '-I', '/usr/local/lib/portable/media_bridge.py']))
                    for _ in range(50):
                        if (bridge / 'control.sock').is_socket():break
                        if processes[-1].poll() is not None:raise CompartmentError('Media bridge exited.')
                        time.sleep(.1)
                    else:raise CompartmentError('Media bridge did not start.')
                    binds += [(bridge, '/run/user/944/portable-media', False)]
                command = ['/usr/bin/aa-exec', '-p', 'petalos_' + app, '--', PROGRAMS[app], *arguments]
            if app != 'sabnzbd':
                command = ['/usr/bin/dbus-run-session',
                           '--config-file=/usr/local/share/portable/compartment-dbus.conf', '--', *command]
            if have_preferences:
                command = ['/usr/bin/python3', '-I', '/usr/local/lib/portable/preferences_runner.py', app, '--', *command]
            media = [destination for _, destination, _ in binds
                     if destination.startswith('/run/petalos-opened/')] if app == 'offline-parole' else []
            process = start_process(sandbox(app, command, extra_binds=binds, wayland=display,
                environment=environment, opened_media=media), pass_fds=tuple(delegated_fds), umask=0o007)
            for fd in delegated_fds:os.close(fd)
            delegated_fds.clear()
            processes.append(process)
            if display is not None:
                gui_ready(app, display, processes)
            else:
                for _ in range(50):
                    if process.poll() is not None:
                        raise CompartmentError('SABnzbd exited during startup.')
                    from sab_bridge import connect_backend
                    try:
                        with connect_backend() as probe:
                            probe.sendall(b'HEAD / HTTP/1.0\r\nHost: localhost\r\n\r\n')
                            if probe.recv(16).startswith(b'HTTP/'):
                                break
                    except OSError:
                        pass
                    time.sleep(0.1)
                else:
                    raise CompartmentError('SABnzbd did not answer its management request.')
        update('ready')
        while not stopped and all(process.poll() is None for process in processes):
            time.sleep(0.25)
        update('stopping')
    except BaseException as error:
        site = traceback.extract_tb(error.__traceback__)[-1]
        state['error_type'] = type(error).__name__
        state['error_site'] = site.name + ':' + str(site.lineno)
        if hasattr(error, 'gui_states'):
            state['gui_states'] = error.gui_states
        update('failed')
        raise
    finally:
        for fd in delegated_fds:os.close(fd)
        if display is not None:
            os.close(display['lease'])
            display['connection'].close()
            display['path'].unlink(missing_ok=True)
        if control:
            control.shutdown();control.server_close()
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill();process.wait()
        for module in reversed(audio_modules):
            try:
                if not module.isdigit():
                    raise CompartmentError('Invalid audio module identity.')
                desktop_audio(['unload-module', module])
            except CompartmentError:
                pass
        mounted = subprocess.run(['/usr/bin/findmnt', '-n', '-o', 'SOURCE', '--mountpoint', str(PRIVATE)],
                                 capture_output=True, timeout=5).stdout.strip() == b'/dev/mapper/portable_data'
        if mounted:
            if app in ('transmission', 'pan', 'amule', 'sabnzbd'):
                for base in ('AppState', 'Downloads'):
                    grant(PRIVATE / base / app, ROLES[app])
            elif app in OFFLINE:
                grant(PRIVATE / 'Documents' / OFFLINE[app][0], ROLES[app])
            elif app == 'browser':
                grant(PRIVATE / 'Downloads/TorBrowser', ROLES[app])
        if state['phase'] != 'failed':
            update('stopped')
