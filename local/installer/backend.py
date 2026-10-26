#!/usr/bin/python3 -I
"""Root-owned installed worker: one bounded stdin packet, JSON event output."""
from pathlib import Path
import ctypes
import json
import os
import resource
import select
import signal
import sys
import threading

resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
ctypes.CDLL('libc.so.6').prctl(4, 0, 0, 0, 0)
os.umask(0o077)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from petal_installer import InstallerError
from petal_installer.bridge import MAX_REQUEST, validate_packet
from petal_installer.engine import perform
from petal_installer import linux


def emit(kind, value):
    print(json.dumps({'type': kind, 'value': value}), flush=True)


def read_packet(fd):
    """Do not prefetch cancellation bytes or acquire Python's buffered IO lock."""
    raw = bytearray()
    while len(raw) <= MAX_REQUEST:
        part = os.read(fd, 1)
        if not part:break
        raw.extend(part)
        if part == b'\n':break
    if len(raw) > MAX_REQUEST or not raw.endswith(b'\n'):
        raise InstallerError('Administrator packet is too large or incomplete.')
    return raw


def monitor_client(fd, finished, cancel):
    """A cancel byte or EOF cancels an active job; idle shutdown is bounded."""
    while not finished.is_set():
        ready, _, _ = select.select([fd], [], [], .1)
        if not ready:continue
        os.read(fd, 1)
        if not finished.is_set():cancel()
        return


def main():
    if os.geteuid() != 0 or sys.argv[1:]:raise InstallerError('Invalid administrator worker invocation.')
    for path in (Path(__file__), *Path(__file__).resolve().parents):
        if path.is_symlink() or path.stat().st_uid != 0 or path.stat().st_mode & 0o022:
            raise InstallerError('The installed backend must be owned by root and protected from modification.')
    supervisor = os.environ.get('PETALOS_SUPERVISOR_PID')
    if supervisor is not None:
        if not supervisor.isdecimal() or int(supervisor) != os.getppid():
            raise InstallerError('Could not establish the portable supervisor identity.')
        parent = Path('/proc') / supervisor
        if parent.stat().st_uid != 0:
            raise InstallerError('The portable supervisor is not protected by administrator ownership.')
        linux.HOST_MOUNTINFO = parent / 'mountinfo'
        linux.host_mounts()
    raw = read_packet(sys.stdin.fileno())
    request, credentials = validate_packet(json.loads(raw))
    raw = None
    finished = threading.Event()
    def interrupted(signum, frame):
        if not finished.is_set():raise InterruptedError('Client cancelled the installer.')
    signal.signal(signal.SIGTERM, interrupted)
    monitor = threading.Thread(target=monitor_client,
        args=(sys.stdin.fileno(), finished, lambda: os.kill(os.getpid(), signal.SIGTERM)), daemon=True)
    monitor.start()
    try:
        result = perform(request, credentials, lambda value: emit('progress', value))
        finished.set()
        emit('result', result)
    finally:
        finished.set();credentials.clear();monitor.join(timeout=1)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        message = str(error) if isinstance(error, InstallerError) else 'Installer stopped. Inspect its last stage; no raw diagnostic or credential data was emitted.'
        print(json.dumps({'type': 'error', 'message': message}), flush=True)
        raise SystemExit(1)
