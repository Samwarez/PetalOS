"""Credential-safe Unix bridge to the fixed SABnzbd role's loopback server."""
import select
import socket
import socketserver
import struct
import threading
from pathlib import Path


def server_owner(connection, uid):
    """Check the established server socket, before forwarding request bytes."""
    local_port = connection.getsockname()[1]
    server_port = connection.getpeername()[1]
    expected_local = f'0100007F:{server_port:04X}'
    expected_remote = f'0100007F:{local_port:04X}'
    with Path('/proc/net/tcp').open() as entries:
        next(entries)
        for line in entries:
            fields = line.split()
            if fields[1:4] == [expected_local, expected_remote, '01']:
                return int(fields[7]) == uid
    return False


def connect_backend():
    connection = socket.create_connection(('127.0.0.1', 8080), timeout=3)
    try:
        if not server_owner(connection, 945):
            raise PermissionError('Unexpected management-server identity.')
        return connection
    except BaseException:
        connection.close()
        raise


class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        if not self.server.slots.acquire(blocking=False):
            return
        try:
            credentials = self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            if struct.unpack('3i', credentials)[1] != 947:
                return
            with connect_backend() as upstream:
                self.request.settimeout(3)
                peers = [self.request, upstream]
                while True:
                    readable, _, _ = select.select(peers, [], [], 60)
                    if not readable:
                        return
                    for source in readable:
                        data = source.recv(65536)
                        if not data:
                            return
                        destination = upstream if source is self.request else self.request
                        destination.sendall(data)
        except OSError:
            pass
        finally:
            self.server.slots.release()


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    slots = threading.BoundedSemaphore(8)


def main():
    import os
    path = '/run/portable-sab-admin/control.sock'
    assert os.geteuid() == 0
    with Server(path, Relay) as server:
        os.chown(path, 0, 947)
        os.chmod(path, 0o660)
        server.serve_forever(poll_interval=0.25)


if __name__ == '__main__':
    main()
