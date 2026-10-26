"""CLI credential collection and pipe-only GUI/privileged-worker protocol."""
from pathlib import Path
import getpass
import json
import os
import subprocess
import threading

from . import InstallerError
from . import portable
from .releases import require

BACKEND = Path('/usr/lib/bloom-installer/backend.py')
MAX_REQUEST = 65536


def request_from_plan(plan, bundle=None):
    request = {'mode': plan['mode'], 'device': plan['target']['path'], 'plan_sha256': plan['plan_sha256']}
    if bundle:request['bundle'] = str(Path(bundle).absolute())
    if plan['mode'] == 'install':
        request.update(encryption=plan['encryption']['id'], os_gib=plan['allocation']['os_bytes'] // 1024**3,
                       system_gib=plan['allocation']['system_bytes'] // 1024**3, erase_mode=plan['erase_mode'])
    elif plan['mode'] == 'update':request['retention'] = plan['retention']
    elif plan['mode'] == 'wipe':request['wipe_method'] = plan['wipe_method']
    return request


def collect_credentials(mode, *, encryption='balanced'):
    from .engine import credentials_checked
    roles = ('system', 'private', 'administrator') if mode == 'install' else ('system',) if mode in ('update', 'store', 'recovery') else ()
    values = {}
    try:
        for role in roles:
            title = {'system': 'SYSTEM passphrase (OS and settings)', 'private': 'Private passphrase',
                     'administrator': 'PetalOS administrator password'}[role]
            values[role] = getpass.getpass(title + ': ')
            if mode == 'install':
                require(values[role] == getpass.getpass('Confirm ' + title + ': '), 'Password confirmation did not match; no drive changes made.')
        credentials_checked(values, mode, encryption=encryption)
        return values
    except BaseException:
        values.clear();raise


def validate_packet(packet):
    require(type(packet) is dict and set(packet) == {'request', 'credentials'}, 'Invalid backend packet.')
    require(type(packet['request']) is dict and type(packet['credentials']) is dict, 'Invalid backend request.')
    return packet['request'], packet['credentials']


def privileged(request, credentials, progress=lambda event: None, cancel=None):
    try:
        return _privileged(request, credentials, progress, cancel)
    finally:
        credentials.clear()


def _privileged(request, credentials, progress, cancel):
    value = None
    if portable.root() is not None:
        arguments, value = portable.prepare()
    else:
        require(BACKEND.exists() and BACKEND.stat().st_uid == 0 and not BACKEND.stat().st_mode & 0o022
                and not any(p.is_symlink() or p.stat().st_uid != 0 or (p.stat().st_mode & 0o022) for p in BACKEND.parents),
                'Install the package or use the complete portable app to enable administrator actions.')
        arguments = ['/usr/bin/pkexec', str(BACKEND)]
    packet = json.dumps({'request': request, 'credentials': credentials}).encode() + b'\n'
    require(len(packet) <= MAX_REQUEST, 'Administrator request is too large.')
    process = subprocess.Popen(arguments, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               env=portable.host_environment())
    done = threading.Event();sent = threading.Event();writer_errors = []
    def send_request():
        try:
            if value is not None:
                for data in portable.chunks(portable.root(), value):
                    if cancel is not None and cancel.is_set():raise InstallerError('Cancelled before starting the administrator operation.')
                    process.stdin.write(data)
            if cancel is not None and cancel.is_set():raise InstallerError('Cancelled before starting the administrator operation.')
            process.stdin.write(packet);process.stdin.flush();sent.set()
        except (OSError, ValueError, InstallerError) as error:
            writer_errors.append(error)
            try:process.stdin.close()
            except (OSError, ValueError):pass
    writer = threading.Thread(target=send_request, daemon=True)
    try:
        writer.start()
        def watch_cancel():
            if cancel is None:return
            while not done.wait(.1):
                if cancel.is_set() and sent.is_set():
                    try:process.stdin.write(b'{"cancel":true}\n');process.stdin.flush()
                    except (BrokenPipeError, OSError):pass
                    return
        threading.Thread(target=watch_cancel, daemon=True).start()
        result = None
        for raw in process.stdout:
            require(len(raw) <= MAX_REQUEST, 'Backend response exceeded its limit.')
            event = json.loads(raw)
            if event.get('type') == 'progress':progress(event['value'])
            elif event.get('type') == 'result':result = event['value']
            elif event.get('type') == 'error':raise InstallerError(event['message'])
        writer.join(timeout=5)
        if writer_errors:raise InstallerError('Portable application transfer was cancelled or failed verification.')
        require(process.wait() == 0 and result is not None,
                'Administrator authorization was cancelled or the operation could not complete.')
        return result
    finally:
        done.set()
        credentials.clear()
        if process.poll() is None:
            # EOF requests cancellation from the authenticated worker. Sending
            # a Unix signal to a root child is not permitted for this GUI user.
            try:process.stdin.close()
            except (OSError, ValueError):pass
            try:process.wait(timeout=180)
            except subprocess.TimeoutExpired:
                raise InstallerError('Installer cleanup is still running. Keep the drive connected.') from None
        if not process.stdin.closed:process.stdin.close()
        process.stdout.close()
