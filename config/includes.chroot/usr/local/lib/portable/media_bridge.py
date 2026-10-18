"""Fixed aMule-to-offline-Parole request broker. Never reads media as root."""
import json
from pathlib import Path, PurePosixPath
import socket
import socketserver
import struct
import threading
import sys
from urllib.parse import quote

sys.path.insert(0, '/usr/local/lib/portable')


def relative_item(value, storage):
    assert isinstance(value, str) and len(value.encode()) <= 4096
    assert not any(x in value for x in ('\0', '\n', '\r'))
    assert storage in ('ram', 'private')
    path = PurePosixPath(value)
    assert '..' not in path.parts
    relative = path.relative_to('/mnt/' + storage + '/Downloads/amule')
    assert relative.parts and relative.name
    return str(relative)


class Request(socketserver.BaseRequestHandler):
    def handle(self):
        if not self.server.slot.acquire(blocking=False):
            return
        try:
            uid = struct.unpack('3i', self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
            assert uid == 944
            self.request.settimeout(5)
            data = bytearray()
            while not data.endswith(b'\n'):
                part = self.request.recv(8193 - len(data))
                assert part
                data += part
                assert len(data) <= 8192
            request = json.loads(data)
            assert isinstance(request, dict) and set(request) == {'path'}
            import compartments as c
            record = c.read_record('amule')
            assert c.worker_alive(record) and record.get('phase') == 'ready'
            storage = record['storage']
            relative = relative_item(request['path'], storage)
            import fcntl
            import os
            fd = os.open(c.BASE / 'broker.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'r+b') as lease:
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                c.start('offline-parole', ['petalos-amule-media:' + quote(relative, safe='')])
            self.request.sendall(b'OK\n')
        except Exception:
            try:
                self.request.sendall(b'ERROR\n')
            except OSError:
                pass
        finally:
            self.server.slot.release()


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    slot = threading.BoundedSemaphore(1)


def main():
    path = Path('/run/portable-compartments/amule/media/control.sock')
    assert not path.exists() and not path.is_symlink()
    import os
    os.umask(0o117)
    with Server(str(path), Request) as server:
        os.chown(path, 0, 944)
        path.chmod(0o660)
        server.serve_forever(poll_interval=.2)


if __name__ == '__main__':
    main()
