from pathlib import Path
import hashlib,json,os,re,subprocess,sys,tempfile
assert os.geteuid()==0 and subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('kvm','qemu')
assert Path('/sys/block/vda/size').read_text().strip()==str(16*1024**3//512)
assert not Path('/dev/mapper/portable_data').exists()
control=json.load(sys.stdin);direction=control['direction'];assert direction in ('baseline','candidate')
generation=control['generation'];assert re.fullmatch('[a-f0-9]{24}',generation)
selected_path=b'live-media-path=/petalos/releases/'+generation.encode()+b'/live'
root=Path('/run/petalos-rollback-boot');root.mkdir(mode=0o700,exist_ok=False)
assert subprocess.check_output(['blkid','-s','LABEL','-o','value','/dev/vda2'],text=True).strip()=='PORT_BOOT'
subprocess.run(['mount','-o','nodev,nosuid,noexec','/dev/vda2',str(root)],check=True,capture_output=True)
def digest(data):return hashlib.sha256(data).hexdigest()
def durable(path,data):
 fd,tmp=tempfile.mkstemp(prefix='.audit-config-',dir=path.parent)
 try:
  with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
  os.replace(tmp,path)
  fd=os.open(path.parent,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
 finally:Path(tmp).unlink(missing_ok=True)
try:
 configs=[root/p for p in ('EFI/BOOT/grub.cfg','EFI/debian/grub.cfg','boot/grub/grub.cfg')]
 saved=root/'petalos/audit-rollback-test'
 if direction=='baseline':saved.mkdir(mode=0o700,exist_ok=False)
 metadata={};plans=[]
 for i,target in enumerate(configs):
  data=target.read_bytes();p=saved/(str(i)+'.cfg')
  if direction=='baseline':
   assert selected_path in data
   match=re.search(rb'^\s*configfile (/petalos/rollback/([a-f0-9]{64})\.cfg)$',data,re.M);assert match
   replacement=(root/match[1].decode().lstrip('/')).read_bytes();assert digest(replacement)==match[2].decode()
   assert b'linux /live/vmlinuz ' in replacement and b'initrd /live/initrd.img' in replacement
   durable(p,data);metadata[str(i)]=digest(data)
  else:
   expected=json.loads((saved/'sha256.json').read_text())[str(i)]
   replacement=p.read_bytes();assert digest(replacement)==expected
   assert selected_path in replacement
  plans.append((target,replacement))
 if direction=='baseline':durable(saved/'sha256.json',json.dumps(metadata).encode())
 for target,data in plans:durable(target,data);assert target.read_bytes()==data
 print(json.dumps({'selected':direction,'config_readbacks':len(plans),'original_and_repaired_payloads_retained':True,'Private_closed':True}))
finally:
 subprocess.run(['umount',str(root)],check=True,capture_output=True);root.rmdir()
