#!/usr/bin/python3 -I
"""Anonymous temporary-file commits in every offline app, with denials intact."""
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c

probe = '''import ctypes,json,os,secrets,socket
from pathlib import Path
checks={}
for root,key in ((Path.home()/'Documents','RAM'),(Path(PRIVATE_FOLDER),'Private')):
 p=root/('petalos-atomic-save-'+secrets.token_hex(12))
 temporary=p.with_suffix('.new')
 fd=None
 try:
  p.write_text('old public fixture')
  fd=os.open(root,os.O_TMPFILE|os.O_RDWR,0o600)
  os.write(fd,b'new public fixture');os.fsync(fd)
  library=ctypes.CDLL(None,use_errno=True)
  linked=library.linkat(-100,('/proc/self/fd/'+str(fd)).encode(),-100,str(temporary).encode(),0x400)
  if linked:raise OSError(ctypes.get_errno(),'temporary commit rejected')
  os.replace(temporary,p)
  checks[key+'_atomic_replace']=p.read_text()=='new public fixture'
 finally:
  if fd is not None:os.close(fd)
  temporary.unlink(missing_ok=True);p.unlink(missing_ok=True)
checks['no_groups']=not os.getgroups()
checks['no_caps']=next(x for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('CapEff:')).split()[1]=='0000000000000000'
checks['SYSTEM_hidden']=not Path('/mnt/system-state').exists()
checks['desktop_home_hidden']=not Path('/home/Petal').exists()
checks['VPN_profiles_hidden']=not Path('/mnt/private/Network').exists()
for family,key in ((socket.AF_INET,'ipv4_denied'),(socket.AF_INET6,'ipv6_denied')):
 try:s=socket.socket(family);s.close();checks[key]=False
 except PermissionError:checks[key]=True
print(json.dumps(checks));assert all(checks.values())
'''
c.private_ready()
for app, (name, uid) in c.OFFLINE.items():
    c.home(app); c.storage_setup(app)
    code = probe.replace('PRIVATE_FOLDER', repr('/mnt/private/Documents/' + name))
    result = subprocess.run(c.sandbox(app, ['/usr/bin/aa-exec', '-p',
        'petalos_' + app.replace('-', '_'), '--', '/usr/bin/python3', '-I', '-c', code]),
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, 'Atomic save fixture failed; raw output suppressed.'
    checks = json.loads(result.stdout)
    print(json.dumps({'app': name, 'checks': checks}, sort_keys=True))
    assert all(checks.values())
