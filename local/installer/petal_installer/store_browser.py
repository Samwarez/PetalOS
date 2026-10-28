"""Descriptor-confined settings browser. No Private or administrator access."""
from pathlib import PurePosixPath
import json
import os
import stat

from . import InstallerError
from .releases import require
from .store import NAME, checked_payload, directory_fd, publish_file, read_import

FOLDERS = {
    'Network/Profiles': ('VPN profiles', 'vpn'),
    'Wallpapers': ('Wallpapers', 'wallpaper'),
    'Files': ('Other saved files', 'file'),
    'Desktop': ('Desktop settings (browse only)', None),
    'Applications': ('Application settings (browse only)', None),
    'Installer/PendingThemes': ('Pending themes', 'theme'),
    'Installer/PendingOverrides': ('Pending overrides', 'override'),
}
ACTIONS = {'browse', 'put', 'mkdir', 'rename', 'delete'}
MAX_FILE_BYTES = 32 * 1024**2


def filename(value):
    require(isinstance(value, str) and value not in ('', '.', '..') and len(value.encode('utf-8')) <= 255
            and '/' not in value and not value.startswith('.petalos-import-')
            and not any(ord(c) < 32 or ord(c) == 127 for c in value), 'Choose a simple file or folder name without path separators.')
    return value


def location(value):
    require(isinstance(value, str) and len(value) <= 1024, 'Invalid settings folder.')
    if value == '':return '', None
    parts = value.split('/')
    require(all(filename(p) == p for p in parts), 'Invalid settings folder.')
    root = next((p for p in FOLDERS if value == p or value.startswith(p + '/')), None)
    require(root is not None, 'This folder is outside the saved-settings browser.')
    return root, FOLDERS[root][1]


def validate(request):
    action = request.get('action')
    require(action in ACTIONS, 'Unsupported settings browser action.')
    common = {'mode', 'device', 'plan_sha256', 'action', 'path'}
    extra = {'browse': set(), 'put': {'source', 'name', 'replace'}, 'mkdir': {'name'},
             'rename': {'name', 'new_name'}, 'delete': {'name'}}[action]
    require(common <= request.keys() and request.keys() <= common | extra, 'Unexpected settings browser fields.')
    root, kind = location(request['path'])
    if action == 'browse':return
    require(kind is not None, 'This settings folder is managed by PetalOS and is browse only.')
    require(kind == 'file' or request['path'] == root, 'Create additional folders under Other saved files.')
    filename(request.get('name'))
    if action == 'rename':filename(request.get('new_name'))
    if action == 'mkdir':require(kind == 'file', 'New folders belong under Other saved files.')
    if action == 'put':
        require(isinstance(request.get('source'), str) and type(request.get('replace', False)) is bool,
                'Invalid settings file upload.')


def _typed_name(kind, name):
    if kind == 'file':return
    suffix = {'vpn': '.conf', 'wallpaper': '.png', 'theme': '.json', 'override': '.json'}[kind]
    require(name.endswith(suffix) and NAME.fullmatch(name[:-len(suffix)])
            and not (kind == 'vpn' and name == 'legacy.conf'), 'Use a valid settings name ending in ' + suffix + '.')


def prepare_upload(request):
    validate(request)
    _, kind = location(request['path'])
    _typed_name(kind, request['name'])
    if kind == 'file':return read_import(request['source'], MAX_FILE_BYTES)
    return checked_payload(kind, request['source'])[2]


def _folder(state, path, *, create=False):
    location(path)
    fd = directory_fd(state)
    try:
        for part in path.split('/') if path else ():
            try:following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if not create:raise
                os.mkdir(part, mode=0o700, dir_fd=fd)
                if os.geteuid() == 0:os.chown(part, 1000, 1000, dir_fd=fd, follow_symlinks=False)
                following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd);fd = following
        return fd
    except BaseException:
        os.close(fd);raise


def browse(state, path=''):
    root, kind = location(path)
    if not path:
        entries = [{'name': title, 'kind': 'folder', 'path': relative, 'bytes': 0}
                   for relative, (title, _) in FOLDERS.items()]
    else:
        entries = []
        try:fd = _folder(state, path)
        except FileNotFoundError:
            require(path == root, 'Settings folder is no longer available.')
        else:
            try:
                names = [n for n in os.listdir(fd) if not n.startswith('.petalos-import-')]
                require(len(names) <= 200, 'This folder has more than 200 entries; use smaller subfolders.')
                for name in sorted(names, key=str.casefold):
                    filename(name)
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    entry_kind = 'folder' if stat.S_ISDIR(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode) else 'blocked'
                    entries.append({'name': name, 'kind': entry_kind, 'bytes': info.st_size if entry_kind == 'file' else 0})
            finally:os.close(fd)
    parent = str(PurePosixPath(path).parent) if path and path != root else ''
    result = {'path': path, 'parent': parent, 'entries': entries, 'can_add': kind is not None and (kind == 'file' or path == root),
              'can_mkdir': kind == 'file', 'private_opened': False}
    require(len(json.dumps(result).encode()) < 48000, 'Folder listing exceeds the browser limit.')
    return result


def change(state, request, payload=None):
    validate(request)
    action, path, name = request['action'], request['path'], request['name']
    _, kind = location(path)
    _typed_name(kind, name)
    if action == 'put':
        require(isinstance(payload, bytes) and len(payload) <= MAX_FILE_BYTES, 'Invalid settings upload payload.')
        publish_file(state, path, name, payload, replace=request.get('replace', False))
    else:
        fd = _folder(state, path, create=action == 'mkdir')
        try:
            if action == 'mkdir':
                os.mkdir(name, mode=0o700, dir_fd=fd)
                if os.geteuid() == 0:os.chown(name, 1000, 1000, dir_fd=fd, follow_symlinks=False)
            else:
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                require(stat.S_ISREG(info.st_mode) or (kind == 'file' and stat.S_ISDIR(info.st_mode)),
                        'Only regular settings files and saved-file folders can be managed.')
                if kind == 'vpn':
                    base = directory_fd(state)
                    try:
                        network = os.open('Network', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=base)
                        try:
                            try:marker = os.open('selected-profile', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=network)
                            except FileNotFoundError:marker = None
                            if marker is not None:
                                with os.fdopen(marker, 'rb') as source:
                                    require(stat.S_ISREG(os.fstat(source.fileno()).st_mode), 'Unsafe VPN selection marker.')
                                    selected = source.read(256).strip()
                                    require(selected != name[:-5].encode(), 'Select another VPN profile before renaming or deleting the active profile.')
                        finally:os.close(network)
                    finally:os.close(base)
                if action == 'delete':
                    if stat.S_ISDIR(info.st_mode):os.rmdir(name, dir_fd=fd)
                    else:os.unlink(name, dir_fd=fd)
                elif action == 'rename':
                    new = request['new_name'];_typed_name(kind, new)
                    # link/unlink gives atomic no-overwrite for files. Directory
                    # renaming is refused, avoiding an overwrite race in rename().
                    require(stat.S_ISREG(info.st_mode), 'Folder renaming is unavailable; create a new folder and move files separately.')
                    os.link(name, new, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
                    os.unlink(name, dir_fd=fd)
            os.fsync(fd)
        finally:os.close(fd)
    result = browse(state, path)
    result['status'] = {'put': 'File saved.', 'mkdir': 'Folder created.', 'rename': 'File renamed.', 'delete': 'Removed.'}[action]
    return result
