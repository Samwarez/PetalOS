"""Network namespace and real Unix SOCKS route; no policy override."""
from pathlib import Path
import json,os,subprocess,sys
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
assert c.worker_alive(c.read_record('browser'))
pid=None;profile=None
for p in Path('/proc').iterdir():
 if not p.name.isdecimal():continue
 try:
  if p.stat().st_uid==941 and 'firefox' in (p/'comm').read_text():
   pid=int(p.name);profile=(p/'attr/current').read_text().strip();break
 except OSError:pass
assert pid
code='''import json,socket,ssl,struct
r={}
for family,key,target in ((socket.AF_INET,'ipv4_unreachable',('1.1.1.1',443)),(socket.AF_INET6,'ipv6_unreachable',('2606:4700:4700::1111',443))):
 s=socket.socket(family);s.settimeout(1)
 try:s.connect(target);r[key]=False
 except OSError:r[key]=True
 s.close()
s=socket.socket(socket.AF_UNIX);s.settimeout(25)
def exact(n):
 b=b''
 while len(b)<n:
  t=s.recv(n-len(b));assert t;b+=t
 return b
try:
 s.connect('/run/portable-tor/socks.sock');s.sendall(b'\\x05\\x01\\x00');assert exact(2)==b'\\x05\\x00'
 host=b'check.torproject.org';s.sendall(b'\\x05\\x01\\x00\\x03'+bytes([len(host)])+host+struct.pack('!H',443))
 reply=exact(4);assert reply[:2]==b'\\x05\\x00'
 exact({1:4,4:16}.get(reply[3],0));exact(2)
 tls=ssl.create_default_context().wrap_socket(s,server_hostname=host.decode());r['TLS_verified']=True
 tls.sendall(b'GET /api/ip HTTP/1.1\\r\\nHost: check.torproject.org\\r\\nConnection: close\\r\\n\\r\\n')
 data=b''
 while len(data)<65536:
  b=tls.recv(4096)
  if not b:break
  data+=b
 r['Tor_service_confirms_exit']=bool(__import__('re').search(rb'"IsTor"\\s*:\\s*true',data))
except Exception as e:r['error']=type(e).__name__
finally:s.close()
print(json.dumps(r))
'''
result=subprocess.run(['nsenter','-t',str(pid),'-n','--','setpriv','--reuid=941','--regid=941','--clear-groups','--bounding-set=-all','--no-new-privs','python3','-I','-c',code],capture_output=True,text=True,timeout=90)
assert result.returncode==0
out=json.loads(result.stdout);out['actual_browser_enforcing']=profile=='petalos_browser (enforce)';out['browser_network_namespace_distinct']=os.readlink('/proc/'+str(pid)+'/ns/net')!=os.readlink('/proc/1/ns/net')
out['scope']='Probe entered actual browser network namespace and UID; production browser AppArmor unchanged.'
print(json.dumps(out))
