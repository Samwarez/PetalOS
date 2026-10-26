"""Portable runtime selection and bounded, pipe-only privileged staging.

The native bootstrap pins the complete stream digest at build time. It stages
only ordinary files beneath a new root-only /run directory, verifies the whole
stream, and starts the existing worker in a private mount namespace. No policy,
service, executable or Python module is installed on the host.
"""
from pathlib import Path
import hashlib
import json
import os
import stat
import struct

from .releases import require

_ROOT = None
MAX_PAYLOAD = 1024**3


def configure(root):
    global _ROOT
    _ROOT = Path(root).resolve(strict=True)


def root():
    return _ROOT


def host_environment():
    """Never load portable libraries into the host's authorization program."""
    allowed = {'DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'XDG_RUNTIME_DIR',
               'DBUS_SESSION_BUS_ADDRESS', 'LANG', 'LC_ALL', 'TERM'}
    result = {key: value for key, value in os.environ.items() if key in allowed}
    result['PATH'] = '/usr/sbin:/usr/bin:/sbin:/bin'
    return result


def manifest(directory):
    value = json.loads((directory / 'portable.json').read_text())
    require(value.get('format') == 1 and type(value.get('files')) is list
            and 0 < value.get('payload_bytes', 0) <= MAX_PAYLOAD, 'Invalid portable application manifest.')
    require(value.get('bootstrap', 'petal-admin') in ('bloom-admin', 'petal-admin'), 'Invalid administrator launcher name.')
    names = set()
    for item in value['files']:
        name = item.get('path', '')
        require(type(name) is str and name.startswith(('app/', 'runtime/'))
                and all(part not in ('', '.', '..') for part in name.split('/'))
                and '\0' not in name and len(name.encode()) < 4096 and name not in names,
                'Invalid portable application path.')
        require(item.get('mode') in (0o644, 0o755) and type(item.get('bytes')) is int
                and 0 <= item['bytes'] <= MAX_PAYLOAD and len(item.get('sha256', '')) == 64,
                'Invalid portable application file.')
        names.add(name)
    return value


def chunks(directory, value):
    """Open without symlinks; framed bytes are rechecked by the root bootstrap."""
    for item in value['files']:
        name = item['path'].encode()
        path = directory / item['path']
        require(not any(p.is_symlink() for p in (path, *path.parents)),
                'Portable application contains a redirected path.')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as source:
            info = os.fstat(source.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_size == item['bytes'],
                    'Portable application is incomplete or changed.')
            yield struct.pack('<IIQ', len(name), item['mode'], item['bytes']) + name
            remaining = item['bytes'];digest = hashlib.sha256()
            while remaining:
                data = source.read(min(1024**2, remaining))
                require(bool(data), 'Portable application file ended early.')
                remaining -= len(data);digest.update(data);yield data
            require(digest.hexdigest() == item['sha256'], 'Portable application file failed verification.')
    yield struct.pack('<IIQ', 0, 0, 0)


def verify(directory):
    value = manifest(directory);digest = hashlib.sha256();length = 0
    for data in chunks(directory, value):digest.update(data);length += len(data)
    require(length == value['payload_bytes'] and digest.hexdigest() == value['payload_sha256'],
            'Portable application failed verification.')
    bootstrap = directory / value.get('bootstrap', 'petal-admin')
    require(bootstrap.is_file() and not bootstrap.is_symlink()
            and hashlib.sha256(bootstrap.read_bytes()).hexdigest() == value['bootstrap_sha256'],
            'Portable administrator launcher failed verification.')
    return value


def prepare():
    require(_ROOT is not None, 'Portable runtime is not configured.')
    require(os.geteuid() != 0, 'Start the portable app as your normal desktop user.')
    require(Path('/usr/bin/pkexec').is_file(),
            'This Linux desktop needs pkexec and a running administrator authorization agent.')
    value = verify(_ROOT)
    return ['/usr/bin/pkexec', str(_ROOT / value.get('bootstrap', 'petal-admin'))], value


def tool_command(arguments):
    if _ROOT is None:return arguments
    runtime = _ROOT / 'runtime'
    program = runtime / str(arguments[0]).lstrip('/')
    require(program.is_file(), 'A required tool is missing from the portable application.')
    loader = runtime / 'usr/lib64/ld-linux-x86-64.so.2'
    library = str(runtime / 'usr/lib/x86_64-linux-gnu') + ':' + str(runtime / 'usr/lib')
    with program.open('rb') as source:kind = source.read(4)
    if kind == b'\x7fELF':
        return [str(loader), '--library-path', library, str(program), *arguments[1:]]
    require(kind.startswith(b'#!/'), 'Unsupported portable tool type.')
    return [str(loader), '--library-path', library, str(runtime / 'usr/bin/dash'), str(program), *arguments[1:]]


def tool_environment():
    if _ROOT is None:return {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C.UTF-8', 'HOME': '/root'}
    result = dict(os.environ)
    result['PATH'] = str(_ROOT / 'tools')
    result['LC_ALL'] = 'C.UTF-8'
    for key in ('GH_TOKEN', 'GITHUB_TOKEN', 'PYTHONPATH', 'PYTHONSTARTUP'):result.pop(key, None)
    return result
