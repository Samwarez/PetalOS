from pathlib import Path
import hashlib,json,os,subprocess,sys
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
assert not c.private_available()
p=Path('/home/Petal/Downloads/transmission/README')
expected=json.loads(Path('/tmp/petalos-public-download-expected.json').read_text())
assert p.stat().st_size==expected['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==expected['sha256']
r=subprocess.run(['setpriv','--reuid=1000','--regid=1000','--clear-groups','--','python3','-I','-c',
 'import hashlib,json,sys;from pathlib import Path;p=Path(sys.argv[1]);assert hashlib.sha256(p.read_bytes()).hexdigest()==sys.argv[2]',str(p),expected['sha256']],capture_output=True,timeout=5)
assert r.returncode==0
c.stop('transmission')
print(json.dumps({'actual_webseed_download_complete':True,'download_matches_source_hash':True,
 'Private_stayed_locked':not c.private_available(),'desktop_can_read_download':True,'download_owner_is_Petal':p.stat().st_uid==1000}))
