#!/usr/bin/python3 -I
"""Public fixture for native LazPaint's file and network boundary."""
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
assert os.geteuid() == 0
code = '''import json,os,socket,secrets
from pathlib import Path
r={'real_role_uid':os.getuid()==ROLE_UID,'no_groups':not os.getgroups()}
status=Path('/proc/self/status').read_text().splitlines()
r['no_caps']=next(x for x in status if x.startswith('CapEff:')).split()[1]=='0000000000000000'
r['no_new_privs']=next(x for x in status if x.startswith('NoNewPrivs:')).split()[1]=='1'
base=Path('/mnt/private/Documents/APP_NAME')
p=base/('petalos-public-probe-'+secrets.token_hex(8))
try:
 p.write_text('public fixture')
 r['own_private_folder_writable']=p.read_text()=='public fixture'
finally:p.unlink(missing_ok=True)
for path,key in [('/mnt/private/Network','vpn_profiles_hidden'),('/mnt/private/PortableSettings','private_settings_hidden'),('/mnt/private/Downloads','downloads_hidden'),('/home/Petal','parent_home_hidden'),('/run/user/1000','parent_runtime_hidden'),('/tmp/.X11-unix','x11_hidden')]:
 r[key]=not Path(path).exists()
for family,key in [(socket.AF_INET,'ipv4_denied'),(socket.AF_INET6,'ipv6_denied')]:
 try:s=socket.socket(family);s.close();r[key]=False
 except PermissionError:r[key]=True
print(json.dumps(r))
'''
c.roles()
for app, (name, uid) in c.OFFLINE.items():
    c.gate(app)
    c.home(app)
    c.grant(c.PRIVATE / 'Documents' / name, uid)
    fixture = code.replace('ROLE_UID', str(uid)).replace('APP_NAME', name)
    result = subprocess.run(c.sandbox(app, ['/usr/bin/aa-exec', '-p', 'petalos_' + app.replace('-', '_'), '--',
        '/usr/bin/python3', '-I', '-c', fixture]), capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, 'Offline fixture failed; raw output suppressed.'
    report = json.loads(result.stdout)
    print(json.dumps({'app': name, 'checks': report}, sort_keys=True))
    assert all(report.values())
