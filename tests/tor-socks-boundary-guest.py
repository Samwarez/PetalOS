#!/usr/bin/python3 -I
"""QEMU: HTTPS through the browser's Unix SOCKS path, with direct IP denied."""
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
assert os.geteuid() == 0
assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
c.gate('browser')
policy_file = c.BASE / 'tor-socks-audit.profile'
loaded = False
try:
    policy = Path('/etc/apparmor.d/petalos.browser').read_text().replace(
        'profile petalos_browser @{petalos_browser_executable} {', 'profile petalos_socks_audit {')
    position = policy.rfind('}')
    policy = policy[:position] + '\n /usr/bin/python3{,.13} ix,\n /usr/lib/python3.13/{,**} mr,\n #include <abstractions/ssl_certs>\n' + policy[position:]
    policy_file.write_text(policy)
    subprocess.run(['/usr/sbin/apparmor_parser', '-r', '-K', str(policy_file)], check=True, capture_output=True)
    loaded = True
    code = '''import json,os,socket,ssl,struct
r={'real_browser_uid':os.getuid()==941,'no_groups':not os.getgroups()}
for family,key in [(socket.AF_INET,'ipv4_direct_denied'),(socket.AF_INET6,'ipv6_direct_denied')]:
 try:s=socket.socket(family);s.close();r[key]=False
 except PermissionError:r[key]=True
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(12)
def exact(n):
 data=b''
 while len(data)<n:
  part=s.recv(n-len(data))
  if not part:raise RuntimeError('SOCKS connection closed')
  data+=part
 return data
try:
 s.connect('/run/portable-tor/socks.sock')
 s.sendall(b'\\x05\\x01\\x00');r['socks_greeting']=exact(2)==b'\\x05\\x00'
 assert r['socks_greeting']
 host=b'check.torproject.org'
 s.sendall(b'\\x05\\x01\\x00\\x03'+bytes([len(host)])+host+struct.pack('!H',443))
 reply=exact(4);r['socks_connect']=reply[0:2]==b'\\x05\\x00'
 assert r['socks_connect']
 if reply[3]==1:exact(4)
 elif reply[3]==4:exact(16)
 elif reply[3]==3:exact(exact(1)[0])
 else:raise RuntimeError('Invalid SOCKS address type')
 exact(2)
 tls=ssl.create_default_context().wrap_socket(s,server_hostname='check.torproject.org')
 r['tls_verified']=True
 tls.sendall(b'GET /api/ip HTTP/1.1\\r\\nHost: check.torproject.org\\r\\nConnection: close\\r\\n\\r\\n')
 data=b''
 while len(data)<65536:
  chunk=tls.recv(4096)
  if not chunk:break
  data+=chunk
 tls.close()
 header,body=data.split(b'\\r\\n\\r\\n',1)
 r['http_success']=b' 200 ' in header.split(b'\\r\\n')[0]
 # Do not log the returned exit IP or HTTP body.
 r['tor_confirmed']=bool(__import__('re').search(rb'"IsTor"\\s*:\\s*true',body))
except Exception as error:r['failure_type']=type(error).__name__
finally:s.close()
print(json.dumps(r),flush=True)
'''
    result = subprocess.run(c.sandbox('browser', ['/usr/bin/aa-exec', '-p', 'petalos_socks_audit',
                            '--', '/usr/bin/python3', '-I', '-c', code],
                            extra_binds=[(Path('/run/portable-tor'), '/run/portable-tor', False)]),
                            capture_output=True, text=True, timeout=45)
    if result.returncode:
        print(json.dumps({'probe_exit': result.returncode}))
        raise RuntimeError('SOCKS boundary fixture failed; raw output suppressed.')
    report = json.loads(result.stdout)
    print(json.dumps(report, sort_keys=True))
    assert 'failure_type' not in report and all(report.values())
finally:
    if loaded:
        subprocess.run(['/usr/sbin/apparmor_parser', '-R', str(policy_file)], check=True, capture_output=True)
    policy_file.unlink(missing_ok=True)
