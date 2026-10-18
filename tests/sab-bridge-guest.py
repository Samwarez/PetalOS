#!/usr/bin/python3 -I
"""Public QEMU fixture: identify SAB and reject a substituted loopback server."""
import json
import os
import socket
import sys

sys.path.insert(0, '/usr/local/lib/portable')
from sab_bridge import connect_backend, server_owner

assert os.geteuid() == 0
report = {}
with connect_backend() as connection:
    report['actual_sab_role_accepted'] = server_owner(connection, 945)
    report['wrong_role_rejected'] = not server_owner(connection, 943)
    connection.sendall(b'HEAD / HTTP/1.0\r\nHost: localhost\r\n\r\n')
    report['actual_sab_http_response'] = connection.recv(16).startswith(b'HTTP/')
with socket.socket() as listener:
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    with socket.create_connection(listener.getsockname(), timeout=3) as client:
        with listener.accept()[0] as server:
            report['substituted_server_rejected'] = not server_owner(client, 945)
            report['fixture_owner_identified'] = server_owner(client, 0)
            server.settimeout(0.1)
            try:
                server.recv(1)
                report['no_request_bytes_before_identity_check'] = False
            except TimeoutError:
                report['no_request_bytes_before_identity_check'] = True
print(json.dumps(report, sort_keys=True))
assert all(report.values())
