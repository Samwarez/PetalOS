"""Read-only fresh inventory: output public metadata, never configuration payloads."""
from pathlib import Path
import hashlib,json,os,stat,subprocess,sys
assert os.geteuid()==0
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
def run(a):
 r=subprocess.run(a,capture_output=True,text=True,timeout=30);return r.returncode,r.stdout
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c,system_state as ss
out={'kernel':os.uname().release,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
 'cmdline':Path('/proc/cmdline').read_text().strip(),'swap_count':len(Path('/proc/swaps').read_text().splitlines())-1}
out['mounts']=json.loads(run(['findmnt','-J','-o','TARGET,SOURCE,FSTYPE,OPTIONS'])[1])
out['packages']=[line.split('\t') for line in run(['dpkg-query','-W','-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\n'])[1].splitlines()]
out['policies']=run(['cat','/sys/kernel/security/apparmor/profiles'])[1].splitlines()
out['failed_services']=run(['systemctl','--failed','--no-legend','--plain'])[1].splitlines()
out['listeners']=run(['ss','-H','-lntup'])[1].splitlines()
out['sysctl']={k:run(['sysctl','-n',k])[1].strip() for k in ('kernel.unprivileged_userns_clone','kernel.yama.ptrace_scope','kernel.kptr_restrict','kernel.dmesg_restrict','fs.protected_hardlinks','fs.protected_symlinks')}
out['accounts']={u:run(['passwd','-S',u])[1].split()[1] for u in ('root','Petal')}
out['firewall']=json.loads(run(['nft','-j','list','ruleset'])[1])
# Remove endpoint addresses from public record, keeping counts.
for entry in out['firewall']['nftables']:
 if 'set' in entry and 'elem' in entry['set']:entry['set']['elem_count']=len(entry['set'].pop('elem'))
out['luks']={}
for name in ('PORTABLE_SYSTEM','PORTABLE_DATA'):
 data=json.loads(run(['cryptsetup','luksDump','--dump-json-metadata','/dev/disk/by-label/'+name])[1])
 out['luks'][name]={'slots':{k:{'type':v['type'],'key_size':v['key_size'],'kdf':{a:b for a,b in v['kdf'].items() if a!='salt'}} for k,v in data['keyslots'].items()},'segments':{k:{a:b for a,b in v.items() if a in ('type','encryption','sector_size','offset')} for k,v in data['segments'].items()},'token_count':len(data['tokens'])}
out['private_open']=Path('/dev/mapper/portable_data').exists()
out['system_state_ready']=ss.ready()
out['legacy_key_exists']=(ss.FULL/'.portable-keys/data.key').exists()
out['boot_modules']=(Path('/run/live/medium/live/filesystem.module').read_text().splitlines() if Path('/run/live/medium/live/filesystem.module').exists() else [])
out['hashes']={}
for base in ('/usr/local/bin','/usr/local/sbin','/usr/local/lib/portable','/usr/local/libexec','/etc/apparmor.d','/usr/lib/live/config'):
 for p in Path(base).iterdir():
  if p.is_file() and not p.is_symlink() and (p.name.startswith(('portable-','petalos.')) or base.endswith('portable') or 'petal-' in p.name):out['hashes'][str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
out['secureboot']=any(p.read_bytes()[-1:]==b'\x01' for p in Path('/sys/firmware/efi/efivars').glob('SecureBoot-*'))
out['lockdown']=Path('/sys/kernel/security/lockdown').read_text().strip()
out['hostname']=run(['hostname'])[1].strip()
import base64,zlib
print(json.dumps({'compressed_public_metadata':base64.b64encode(zlib.compress(json.dumps(out,sort_keys=True).encode())).decode()}))
