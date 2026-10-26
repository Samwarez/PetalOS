"""Exercise the actual SAB management relay and deny another desktop identity."""
from pathlib import Path
import json
import os
import subprocess
import sys
assert os.geteuid() == 0
sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
assert c.worker_alive(c.read_record('sabnzbd')) and c.worker_alive(c.read_record('sab-viewer'))
probe = '''import json,socket
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(5)
s.connect('/run/user/947/portable-sab-admin/control.sock')
s.sendall(b'GET / HTTP/1.1\\r\\nHost: 127.0.0.1:8080\\r\\nConnection: close\\r\\n\\r\\n')
data=b''
while len(data)<262144:
 part=s.recv(16384)
 if not part:break
 data+=part
s.close()
status=data.split(b'\\r\\n',1)[0]
print(json.dumps({'management_HTTP_response_received':any(b' '+v+b' ' in status for v in (b'200',b'302',b'303'))}))
'''
command = c.sandbox('sab-viewer', ['aa-exec', '-p', 'petalos_sab_viewer', '--', 'python3', '-I', '-c', probe],
    extra_binds=[(Path('/run/portable-sab-admin'), '/run/user/947/portable-sab-admin', False)])
result = subprocess.run(command, capture_output=True, text=True, timeout=15)
assert result.returncode == 0, 'SAB bridge probe failed; raw output suppressed.'
checks = json.loads(result.stdout)
negative = '''import socket
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
try:s.connect('/run/portable-sab-admin/control.sock')
except PermissionError:raise SystemExit(0)
raise SystemExit(1)
'''
checks['ordinary_desktop_identity_denied_management_socket'] = subprocess.run(
    ['setpriv', '--reuid=1000', '--regid=1000', '--clear-groups', '--', 'python3', '-I', '-c', negative],
    capture_output=True, timeout=5).returncode == 0
print(json.dumps(checks))
assert all(checks.values())
