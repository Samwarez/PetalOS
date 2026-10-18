#!/usr/bin/python3 -I
"""Public results only; controller cookies remain entirely inside the guest."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

sys.path.insert(0, '/usr/local/lib/portable')
from tor_control import CLIENT_KEY, SERVER_KEY
assert os.geteuid() == 0
assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
cookie = Path('/run/portable-tor/control_auth_cookie').read_bytes()
results = {}
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
    connection.settimeout(5)
    connection.connect('/run/portable-tor/control.sock')
    stream = connection.makefile('rb')
    def command(line):
        connection.sendall(line.encode() + b'\r\n')
        return stream.readline(16384)
    results['unauthenticated_denied'] = command('GETINFO version').startswith(b'514 ')
    nonce = os.urandom(32)
    response = command('AUTHCHALLENGE SAFECOOKIE ' + nonce.hex())
    fields = dict(word.split(b'=', 1) for word in response.split() if b'=' in word)
    server_nonce = bytes.fromhex(fields[b'SERVERNONCE'].decode())
    message = cookie + nonce + server_nonce
    results['server_authenticated'] = hmac.compare_digest(
        hmac.new(SERVER_KEY, message, hashlib.sha256).hexdigest().encode(), fields[b'SERVERHASH'])
    response = command('AUTHENTICATE ' + hmac.new(CLIENT_KEY, message, hashlib.sha256).hexdigest())
    results['client_authenticated'] = response == b'250 OK\r\n'
    for line, name in [('GETINFO address', 'vpn_address_denied'),
                       ('SETCONF SocksPort=127.0.0.1:9050', 'socks_change_denied'),
                       ('SETCONF ClientTransportPlugin="exec /usr/bin/sh"', 'transport_exec_denied'),
                       ('SIGNAL SHUTDOWN', 'shutdown_denied'), ('LOADCONF', 'loadconf_denied')]:
        results[name] = command(line).startswith(b'552 ')
    response = command('GETINFO status/bootstrap-phase')
    results['bootstrap_complete'] = b'PROGRESS=100' in response
    assert stream.readline(16384) == b'250 OK\r\n'
print(json.dumps(results, sort_keys=True))
assert all(results.values())
