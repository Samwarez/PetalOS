"""QMP controls for the exact disposable audit VM; never type credentials here."""
from pathlib import Path
import json,socket,sys,struct,zlib
R=Path('/run/user/1000/petalos-audit-20261017-221958-817753')
assert json.loads((R/'running.json').read_text())['image']=='/home/sam/portable-live/testing/audit/20261017-221958-817753/audit.img'
def request(command,args=None):
 with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
  s.settimeout(8);s.connect(str(R/'qmp.sock'));f=s.makefile('rwb',buffering=0);json.loads(f.readline())
  result=None
  for msg in ({'execute':'qmp_capabilities'},{'execute':command,**({'arguments':args} if args is not None else {})}):
   f.write(json.dumps(msg).encode()+b'\n')
   while True:
    r=json.loads(f.readline())
    assert 'error' not in r,r
    if 'return' in r:result=r['return'];break
  return result
if sys.argv[1]=='capture':
 name=sys.argv[2];assert name.replace('-','').isalnum()
 ppm=R/(name+'.ppm');request('screendump',{'filename':str(ppm)})
 with ppm.open('rb') as f:
  assert f.readline().strip()==b'P6';w,h=map(int,f.readline().split());assert f.readline().strip()==b'255';pixels=f.read()
 def chunk(t,d):return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d))
 raw=b''.join(b'\0'+pixels[y*w*3:(y+1)*w*3] for y in range(h));png=ppm.with_suffix('.png')
 png.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''));print(png)
elif sys.argv[1]=='key':
 print(request('send-key',{'keys':[{'type':'qcode','data':x} for x in sys.argv[2:]],'hold-time':50}))
elif sys.argv[1]=='link':print(request('set_link',{'name':'virtio-net-pci.0','up':sys.argv[2]=='up'}))
else:print(json.dumps(request(sys.argv[1])))
