"""One authorized SYSTEM editing session with a bounded RAM working copy."""
from pathlib import Path, PurePosixPath
import ctypes
import hashlib
import json
import os
import stat

from . import InstallerError
from . import store, store_browser
from .releases import require

SCOPES = {path: kind for path, (_, kind) in store_browser.FOLDERS.items() if kind is not None}
MAX_TOTAL = 128 * 1024**2
MAX_ENTRIES = 1000
IGNORED = {'.directory', '.DS_Store', 'Thumbs.db'}
README = ('Bloom SYSTEM editing session\n\n'
          'Drag files into Files for general saved files, Network/Profiles for\n'
          'WireGuard profiles, or Wallpapers for PNG wallpapers. Pending themes\n'
          'and overrides accept their supported JSON descriptions.\n\n'
          'This is a temporary RAM working copy. Return to Bloom and choose\n'
          'Save changes and lock to validate and save changes to the card.\n'
          'Discard and lock leaves unsaved changes off the card.\n'
          'Private, administrator credentials and managed OS files are excluded.\n')


def workspace_fd(path, uid):
    path = Path(path)
    require(uid > 0 and path.parent == Path('/run/user') / str(uid)
            and path.name.startswith('bloom-settings-'), 'Invalid desktop editing workspace.')
    fd = store.directory_fd(path)
    try:
        info = os.fstat(fd)
        require(info.st_uid == uid and stat.S_IMODE(info.st_mode) == 0o700, 'Editing workspace must be private to the desktop user.')
        data = ctypes.create_string_buffer(256)
        library = ctypes.CDLL('libc.so.6', use_errno=True)
        require(library.fstatfs(fd, ctypes.byref(data)) == 0 and ctypes.c_long.from_buffer(data).value == 0x01021994,
                'The editing workspace must be on a RAM filesystem.')
        return fd
    except BaseException:
        os.close(fd);raise


def directory(base, path, *, create=False, owner=None):
    fd = os.dup(base)
    try:
        for part in path.split('/') if path else ():
            store_browser.filename(part)
            try:following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if not create:raise
                os.mkdir(part, mode=0o700, dir_fd=fd)
                following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                if owner is not None:os.fchown(following, owner, -1)
            os.close(fd);fd = following
        return fd
    except BaseException:
        os.close(fd);raise


def scope(path):
    return next((p for p in SCOPES if path == p or path.startswith(p + '/')), None)


def snapshot(base, *, workspace=False, uid=None):
    files = {};folders = set();total = 0;entries = 0
    def walk(fd, prefix):
        nonlocal total, entries
        for name in sorted(os.listdir(fd)):
            if name in IGNORED or name.startswith('.petalos-import-'):continue
            if workspace and not prefix and name == 'README.txt':continue
            store_browser.filename(name)
            relative = '/'.join(filter(None, (prefix, name)))
            require(len(relative.split('/')) <= 12, 'Saved folders are nested too deeply.')
            entries += 1;require(entries <= MAX_ENTRIES, 'This editing session exceeds 1000 entries.')
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if workspace:require(info.st_dev == os.fstat(base).st_dev, 'Mounted filesystems are not accepted inside the editing copy.')
            root = scope(relative)
            if stat.S_ISDIR(info.st_mode):
                require(any(p == relative or p.startswith(relative + '/') for p in SCOPES)
                        or relative.startswith('Files/'), 'Place additional folders inside Files.')
                folders.add(relative)
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:walk(child, relative)
                finally:os.close(child)
                continue
            require(root is not None and (root == 'Files' or str(PurePosixPath(relative).parent) == root),
                    'Place files inside the supported saved-settings folders.')
            incoming = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(incoming, 'rb') as source:
                before = os.fstat(source.fileno())
                require(stat.S_ISREG(before.st_mode) and before.st_size <= store_browser.MAX_FILE_BYTES,
                        'Editing supports regular files up to 32 MiB; links and special files are refused.')
                if workspace:require(before.st_uid == uid and before.st_nlink == 1, 'Editing files must belong to the desktop user and have no hard links.')
                total += before.st_size;require(total <= MAX_TOTAL, 'The RAM editing copy exceeds 128 MiB.')
                data = source.read(store_browser.MAX_FILE_BYTES + 1);after = os.fstat(source.fileno())
                require(len(data) == before.st_size and (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                        == (after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'A file is still changing. Finish copying it before saving.')
                files[relative] = data
    if workspace:walk(base, '')
    else:
        for path in SCOPES:
            try:fd = directory(base, path)
            except FileNotFoundError:continue
            try:folders.add(path);walk(fd, path)
            finally:os.close(fd)
    return files, folders


def fingerprints(files):return {path: hashlib.sha256(data).hexdigest() for path, data in files.items()}


class EditingCopy:
    def __init__(self, state, workspace, uid):
        self.state = Path(state);self.workspace = workspace;self.uid = uid
        self.baseline = {};self.folders = set()

    def export(self):
        require(not os.listdir(self.workspace), 'Choose a new empty editing workspace.')
        base = store.directory_fd(self.state)
        try:files, folders = snapshot(base)
        finally:os.close(base)
        self.baseline = fingerprints(files);self.folders = folders
        for path in set(SCOPES) | folders:
            fd = directory(self.workspace, path, create=True, owner=self.uid);os.close(fd)
        for path, data in [*files.items(), ('README.txt', README.encode())]:
            parent = str(PurePosixPath(path).parent)
            fd = directory(self.workspace, '' if parent == '.' else parent)
            try:
                target = os.open(PurePosixPath(path).name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
                with os.fdopen(target, 'wb') as output:
                    output.write(data);os.fchown(output.fileno(), self.uid, -1)
            finally:os.close(fd)
        return {'files': len(files), 'bytes': sum(map(len, files.values()))}

    def save(self):
        desired, folders = snapshot(self.workspace, workspace=True, uid=self.uid)
        base = store.directory_fd(self.state)
        try:current, _ = snapshot(base)
        finally:os.close(base)
        require(fingerprints(current) == self.baseline, 'Saved settings changed outside this session. Discard and reopen before saving.')
        wanted = fingerprints(desired)
        changed = {p: data for p, data in desired.items() if wanted[p] != self.baseline.get(p)}
        removed = set(self.baseline) - set(desired)
        # Validate every changed file before making the first card mutation.
        validated = {}
        for path, data in changed.items():
            root = scope(path);kind = SCOPES[root];name = PurePosixPath(path).name
            store_browser._typed_name(kind, name)
            validated[path] = data if kind == 'file' else store.checked_data(kind, data)[2]
        marker = self.state / 'Network/selected-profile'
        if marker.exists():
            active = store.read_import(marker, 256).strip().decode('utf-8')
            require('Network/Profiles/' + active + '.conf' not in removed,
                    'Restore the active VPN profile before saving, or select another profile in PetalOS first.')
        for path in removed:
            root = scope(path);store_browser._typed_name(SCOPES[root], PurePosixPath(path).name)
        for path in sorted(folders, key=lambda p: (p.count('/'), p)):
            if path.startswith('Files/') and path not in self.folders:
                parent = str(PurePosixPath(path).parent)
                base = store.directory_fd(self.state)
                try:
                    fd = directory(base, parent, create=True, owner=1000 if os.geteuid() == 0 else None)
                    try:
                        os.mkdir(PurePosixPath(path).name, 0o700, dir_fd=fd)
                        if os.geteuid() == 0:os.chown(PurePosixPath(path).name, 1000, 1000, dir_fd=fd, follow_symlinks=False)
                    finally:os.close(fd)
                finally:os.close(base)
        for path, data in validated.items():
            store.publish_file(self.state, str(PurePosixPath(path).parent), PurePosixPath(path).name, data, replace=path in self.baseline)
        for path in sorted(removed):
            base = store.directory_fd(self.state)
            try:
                fd = directory(base, str(PurePosixPath(path).parent))
                try:os.unlink(PurePosixPath(path).name, dir_fd=fd);os.fsync(fd)
                finally:os.close(fd)
            finally:os.close(base)
        for path in sorted(self.folders - folders, key=lambda p: (-p.count('/'), p)):
            if not path.startswith('Files/'):continue
            base = store.directory_fd(self.state)
            try:
                fd = directory(base, str(PurePosixPath(path).parent))
                try:os.rmdir(PurePosixPath(path).name, dir_fd=fd);os.fsync(fd)
                finally:os.close(fd)
            finally:os.close(base)
        return {'saved': True, 'written_files': len(validated), 'removed_files': len(removed), 'private_opened': False}


def serve(request, credentials, uid, incoming, emit, read_packet):
    from . import linux
    from .engine import credentials_checked
    from .plans import make_plan
    require(set(request) == {'mode', 'device', 'plan_sha256', 'workspace'}, 'Invalid editing-session request.')
    require(request['mode'] == 'store-editor', 'Invalid editing-session mode.')
    encoded = credentials_checked(credentials, 'store')
    disk = linux.choose(request['device'])
    plan = make_plan('system-store', disk)
    require(plan['plan_sha256'] == request['plan_sha256'], 'Selected settings drive changed. Review it again.')
    fd = workspace_fd(request['workspace'], uid)
    try:
        emit('progress', {'stage': 'unlocking-system-settings'})
        with store.system_session(request['device'], writable=True, passphrase=credentials['system']) as state:
            credentials.clear();encoded.clear()
            editing = EditingCopy(state, fd, uid)
            summary = editing.export()
            emit('editor-ready', {'workspace': request['workspace'], **summary})
            while True:
                raw = read_packet(incoming)
                if not raw:result = {'saved': False, 'private_opened': False};break
                command = json.loads(raw)
                require(type(command) is dict and set(command) == {'action'} and command['action'] in ('save', 'discard'),
                        'Unsupported editing-session command.')
                if command['action'] == 'discard':result = {'saved': False, 'private_opened': False};break
                try:
                    require(linux.describe(linux.raw_disk(request['device']))['identity'] == disk['identity'],
                            'The selected card changed or was disconnected. Do not save this session to another card.')
                    result = editing.save();break
                except InstallerError as error:emit('editor-error', {'message': str(error)})
                except InterruptedError:raise
                except OSError:emit('editor-error', {'message': 'Saving stopped. Some files may have been saved; inspect the card before retrying.'})
        return result
    finally:credentials.clear();encoded.clear();os.close(fd)
