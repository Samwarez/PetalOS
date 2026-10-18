"""Real Transmission webseed download of Debian's small public README."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
assert os.geteuid()==0
c.private_ready();c.gate('transmission');c.stop('transmission')
fixture=Path('/home/Petal/phase15-public.torrent');target=Path('/mnt/private/Downloads/transmission/README')
assert not target.exists() and not fixture.exists()
ref=subprocess.run(['curl','--disable','--fail','--silent','--noproxy','*','--interface','wg0','--max-time','15','--max-filesize','65536','https://deb.debian.org/debian/README'],capture_output=True,timeout=20)
assert ref.returncode==0 and 0<len(ref.stdout)<65536
data=ref.stdout
def enc(v):
 if isinstance(v,int):return b'i'+str(v).encode()+b'e'
 if isinstance(v,bytes):return str(len(v)).encode()+b':'+v
 if isinstance(v,list):return b'l'+b''.join(map(enc,v))+b'e'
 return b'd'+b''.join(enc(k)+enc(v[k]) for k in sorted(v))+b'e'
info={b'name':b'README',b'length':len(data),b'piece length':65536,b'pieces':hashlib.sha1(data).digest(),b'private':1}
fixture.write_bytes(enc({b'info':info,b'url-list':[b'https://deb.debian.org/debian/README']}));os.chown(fixture,1000,1000);fixture.chmod(0o600)
settings=Path('/mnt/private/AppState/transmission/settings.json');saved=settings.read_bytes();cfg=json.loads(saved)
cfg.update({'show-options-window':False,'start-added-torrents':True,'user-has-given-informed-consent':True})
settings.write_text(json.dumps(cfg));os.chown(settings,942,942)
report={}
try:
 record=c.start('transmission',[str(fixture)]);report['started']=record['phase']=='ready'
 end=time.monotonic()+70
 while time.monotonic()<end:
  if target.is_file() and target.stat().st_size==len(data) and hashlib.sha256(target.read_bytes()).digest()==hashlib.sha256(data).digest():break
  time.sleep(.5)
 report.update(actual_download_complete=target.is_file() and target.read_bytes()==data,expected_bytes=len(data),expected_sha256=hashlib.sha256(data).hexdigest())
finally:
 c.stop('transmission');fixture.unlink(missing_ok=True)
 for f in (target,target.with_suffix('.part')):f.unlink(missing_ok=True)
 settings.write_bytes(saved);os.chown(settings,942,942)
 # Only newly generated public torrent state belongs to this clean audit VM.
 ih=hashlib.sha1(enc(info)).hexdigest()
 for folder in ('torrents','resume'):
  for p in (settings.parent/folder).glob(ih+'*'):p.unlink()
print(json.dumps(report,sort_keys=True))
