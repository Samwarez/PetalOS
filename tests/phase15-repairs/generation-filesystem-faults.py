"""Actual FAT/ext4 ENOSPC during staging, on new RAM-backed guest loop images."""
from pathlib import Path
import errno,hashlib,importlib.util,json,os,re,subprocess,tempfile
assert os.geteuid()==0
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
assert Path('/sys/block/vda/size').read_text().strip()==str(16*1024**3//512)
module=Path('/tmp/petalos-generation-fixture/release_generations.py')
manifest=json.loads((module.parent/'manifest.json').read_text())
assert hashlib.sha256(module.read_bytes()).hexdigest()==manifest['sha256']
spec=importlib.util.spec_from_file_location('g',module);g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
os.umask(0o077)
config="menuentry 'public fixture' {\n linux /live/vmlinuz boot=live toram live-media=/dev/mapper/portable_system\n initrd /live/initrd.img\n}\n"
out={}
def run(args):return subprocess.check_output(args,stderr=subprocess.PIPE,text=True).strip()
with tempfile.TemporaryDirectory(prefix='petalos-generation-fault-',dir='/run') as directory:
 base=Path(directory);loops={};mounts=[]
 try:
  for name,kind in [('boot','vfat'),('system','ext4')]:
   image=base/(name+'.disk')
   with image.open('xb') as stream:stream.truncate(64*1024**2)
   device=run(['losetup','--find','--show',str(image)])
   assert re.fullmatch('/dev/loop[0-9]+',device);loops[name]=(device,image)
   assert Path('/sys/block',Path(device).name,'loop/backing_file').read_text().strip()==str(image)
   assert subprocess.run(['findmnt','-rn','-S',device],capture_output=True).returncode==1
   run(['mkfs.vfat','-F','32',device] if kind=='vfat' else ['mkfs.ext4','-q','-F',device])
   target=base/name;target.mkdir()
   run(['mount','-t',kind,'-o','nosuid,nodev'+(',uid=0,gid=0,umask=022' if kind=='vfat' else ''),device,str(target)])
   mounts.append(target)
  boot,system=base/'boot',base/'system'
  for root in (boot,system):(root/'live').mkdir()
  sources={}
  for name in ('vmlinuz','initrd.img','filesystem.squashfs'):
   source=base/('source-'+name);source.write_bytes(b'new public fixture\n'*65536);sources[name]=source
   ((system if name=='filesystem.squashfs' else boot)/'live'/name).write_bytes(b'old public fixture')
  (system/'settings-canary').write_text('preserve selected settings')
  selector=boot/'grub.cfg';selector.write_text(config)
  hashes={n:g.digest(p) for n,p in sources.items()}
  def identity():
   for name,(device,image) in loops.items():
    assert Path('/sys/block',Path(device).name,'loop/backing_file').read_text().strip()==str(image)
    assert run(['findmnt','-rn','-M',str(base/name),'-o','SOURCE'])==device
  for name,point in [('boot','generation-directories'),('system','staged-initrd.img')]:
   filler=base/name/'public-space-fixture'
   def checkpoint(stage):
    if stage!=point:return
    try:
     with filler.open('xb',buffering=0) as stream:
      while True:stream.write(b'\0'*(1024**2))
    except OSError as error:assert error.errno==errno.ENOSPC
   try:
    g.stage_and_activate(boot,system,sources,hashes,[(selector,selector.read_text())],
      ['filesystem.squashfs'],identity=identity,checkpoint=checkpoint)
   except OSError as error:assert error.errno==errno.ENOSPC
   else:raise AssertionError('Actual full filesystem did not fail staging')
   assert selector.read_text()==config
   assert (system/'settings-canary').read_text()=='preserve selected settings'
   assert not list((base/name).rglob('.petalos-partial-*'))
   filler.unlink();g.sync_directory(base/name)
   out[name+'_actual_ENOSPC_kept_old_selection']=True
  generation,installed=g.stage_and_activate(boot,system,sources,hashes,[(selector,config)],
    ['filesystem.squashfs'],identity=identity)
  assert all(g.digest(p)==h for p,h in installed.items())
  assert 'live-media-path=/petalos/releases/'+generation+'/live' in selector.read_text()
  assert (boot/'live/vmlinuz').read_bytes()==b'old public fixture'
  assert any(p.read_text()==config for p in (boot/'petalos/rollback').glob('*.cfg'))
  out['retry_activated_complete_generation_and_retained_rollback']=True
 finally:
  for target in reversed(mounts):run(['umount',str(target)])
  for device,image in loops.values():
   assert Path('/sys/block',Path(device).name,'loop/backing_file').read_text().strip()==str(image)
   run(['losetup','-d',device])
out['all_RAM_image_mounts_and_loops_closed']=True
print(json.dumps(out))
