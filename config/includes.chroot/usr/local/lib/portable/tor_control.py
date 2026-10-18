"""Bounded SAFECOOKIE front end; browser cannot reconfigure Tor transport."""
import hashlib
import hmac
import os
from pathlib import Path
import select
import shlex
import socket
import socketserver
import struct
import threading

SERVER_KEY = b'Tor safe cookie authentication server-to-controller hash'
CLIENT_KEY = b'Tor safe cookie authentication controller-to-server hash'
EVENTS = {'CIRC', 'CIRC_MINOR', 'STREAM', 'ORCONN', 'BW', 'NOTICE', 'WARN', 'ERR',
          'STATUS_GENERAL', 'STATUS_CLIENT', 'NETWORK_LIVENESS', 'NEWCONSENSUS',
          'NEWDESC', 'CONF_CHANGED', 'SIGNAL', 'CLIENTS_SEEN', 'HS_DESC'}
INFO = {'version', 'status/bootstrap-phase', 'status/circuit-established',
        'status/enough-dir-info', 'network-liveness', 'circuit-status',
        'stream-status', 'net/listeners/socks', 'traffic/read', 'traffic/written'}
CONF = {'disablenetwork', 'socksport', 'usebridges', 'bridge',
        'clienttransportplugin', 'entrynodes', 'exitnodes', 'excludenodes',
        'excludeexitnodes', 'strictnodes', 'clientuseipv6', 'clientpreferipv6orport',
        'connectionpadding', 'reducedconnectionpadding'}


def allowed_command(line):
    if len(line) > 16384 or any(c in line for c in ('\r', '\n', '\x00')):
        return False
    try:
        words = shlex.split(line)
    except ValueError:
        return False
    if not words:
        return False
    command, arguments = words[0].upper(), words[1:]
    if command == 'GETINFO':
        # In particular, do not expose GETINFO address (the VPN identity).
        return bool(arguments) and all(x.lower() in INFO or x.lower().startswith(('ns/id/', 'ip-to-country/')) for x in arguments)
    if command == 'GETCONF':
        return bool(arguments) and all(x.lower() in CONF for x in arguments)
    if command == 'SETEVENTS':
        return all(x.upper() in EVENTS or x.upper() == 'EXTENDED' for x in arguments)
    if command == 'SIGNAL':
        return len(arguments) == 1 and arguments[0].upper() == 'NEWNYM'
    if command == 'SETCONF':
        return bool(arguments) and all(x.lower() in ('disablenetwork=0', 'disablenetwork=1') for x in arguments)
    return command == 'QUIT' and not arguments


def backend_connection(path, cookie):
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(5)
    connection.connect(str(path))
    connection.sendall(b'AUTHENTICATE ' + cookie.hex().encode() + b'\r\n')
    response = b''
    while not response.endswith(b'\r\n') and len(response) < 4096:
        data = connection.recv(4096)
        if not data:
            break
        response += data
    if response != b'250 OK\r\n':
        connection.close()
        raise RuntimeError('Tor control authentication failed.')
    return connection


def query(path, cookie, command):
    with backend_connection(path, cookie) as connection:
        connection.sendall(command.encode('ascii') + b'\r\n')
        data = b''
        while len(data) < 65536:
            chunk = connection.recv(8192)
            if not chunk:
                break
            data += chunk
            if data.endswith(b'250 OK\r\n') or data.startswith(b'5'):
                break
        return data


class ControlServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    request_queue_size = 8


def serve(front, backend, front_cookie, backend_cookie, uid, version):
    budget = threading.BoundedSemaphore(8)

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            pid, peer, group = struct.unpack('3i', self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if peer not in (0, uid) or not budget.acquire(blocking=False):
                return
            authenticated = False
            expected = None
            remote = None
            pending = b''
            self.request.settimeout(60)
            try:
                while True:
                    sockets = [self.request] + ([remote] if remote else [])
                    ready, _, _ = select.select(sockets, [], [], 60)
                    if not ready:
                        continue
                    if remote in ready:
                        data = remote.recv(16384)
                        if not data:
                            break
                        self.request.sendall(data)
                    if self.request not in ready:
                        continue
                    data = self.request.recv(16384)
                    if not data:
                        break
                    pending += data
                    if len(pending) > 65536:
                        break
                    while b'\r\n' in pending:
                        raw, pending = pending.split(b'\r\n', 1)
                        try:
                            line = raw.decode('ascii')
                            words = shlex.split(line)
                        except (UnicodeError, ValueError):
                            self.request.sendall(b'500 Invalid control request\r\n')
                            continue
                        if words and words[0].upper() == 'PROTOCOLINFO':
                            self.request.sendall(('250-PROTOCOLINFO 1\r\n250-AUTH METHODS=SAFECOOKIE COOKIEFILE="/run/portable-tor/control_auth_cookie"\r\n250-VERSION Tor="' + version + '"\r\n250 OK\r\n').encode())
                        elif len(words) == 3 and words[:2] == ['AUTHCHALLENGE', 'SAFECOOKIE']:
                            try:
                                nonce = bytes.fromhex(words[2])
                                assert len(nonce) == 32
                                server_nonce = os.urandom(32)
                                message = front_cookie + nonce + server_nonce
                                expected = hmac.new(CLIENT_KEY, message, hashlib.sha256).digest()
                                answer = hmac.new(SERVER_KEY, message, hashlib.sha256).hexdigest()
                                self.request.sendall(('250 AUTHCHALLENGE SERVERHASH=' + answer + ' SERVERNONCE=' + server_nonce.hex() + '\r\n').encode())
                            except (ValueError, AssertionError):
                                self.request.sendall(b'513 Invalid challenge\r\n')
                        elif len(words) == 2 and words[0].upper() == 'AUTHENTICATE' and expected:
                            try:
                                valid = hmac.compare_digest(bytes.fromhex(words[1]), expected)
                            except ValueError:
                                valid = False
                            expected = None
                            if not valid:
                                self.request.sendall(b'515 Authentication failed\r\n')
                                return
                            if remote:
                                remote.close()
                            remote = backend_connection(backend, backend_cookie)
                            remote.settimeout(5)
                            authenticated = True
                            self.request.sendall(b'250 OK\r\n')
                        elif not authenticated:
                            self.request.sendall(b'514 Authentication required\r\n')
                        elif allowed_command(line):
                            remote.sendall(raw + b'\r\n')
                        else:
                            self.request.sendall(b'552 Command denied by PetalOS control policy\r\n')
            except (OSError, ValueError):
                pass
            finally:
                if remote:
                    remote.close()
                budget.release()

    server = ControlServer(str(front), Handler)
    os.chown(front, 0, uid)
    os.chmod(front, 0o660)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
