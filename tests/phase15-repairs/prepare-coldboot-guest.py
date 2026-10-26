"""Disposable vda guest only: stage public repairs as a retained boot generation."""
from pathlib import Path
import hashlib, importlib.util, json, os, re, shutil, subprocess, sys, tarfile
assert os.geteuid()==0
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
assert Path('/sys/block/vda/size').read_text().strip()==str(16*1024**3//512)
assert 'toram' in Path('/proc/cmdline').read_text().split()
sys.path.insert(0,'/usr/local/lib/portable')
import private_storage as storage
import system_state
system_state.require();identity=storage.identity()
storage.backend().verify_mapping(identity,'system')
assert storage.backend().device(identity,'system').resolve()==Path('/dev/vda3')
assert not Path('/dev/mapper/portable_data').exists()
control=json.load(sys.stdin);values=control['credentials'];manifest=control['manifest']
source=Path('/tmp/petalos-public-repairs.tar')
assert not source.is_symlink() and source.stat().st_uid==1000
data=source.read_bytes();assert hashlib.sha256(data).hexdigest()==control['sha256']
base=Path('/run/petalos-coldboot-repair');base.mkdir(mode=0o700,exist_ok=True)
assert base.stat().st_uid==0 and not base.is_symlink()
inputs=base/control['sha256'][:24];inputs.mkdir(mode=0o700,exist_ok=False)
def run(args,**kwargs):
 r=subprocess.run(args,capture_output=True,timeout=240,**kwargs)
 if r.returncode:raise RuntimeError('Public test step failed: '+Path(args[0]).name+' exit '+str(r.returncode))
 return r
with tarfile.open(source) as archive:
 members=archive.getmembers();assert {m.name for m in members}==set(manifest)
 for member in members:
  p=Path(member.name);assert not p.is_absolute() and '..' not in p.parts and member.isfile()
  content=archive.extractfile(member).read();assert hashlib.sha256(content).hexdigest()==manifest[member.name]
  target=inputs/p;target.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
  target.write_bytes(content);target.chmod(member.mode)
print('Public inputs verified; preparing only the disposable guest.',flush=True)
run(['/usr/local/sbin/portable-check-network-ready'])
run(['apt-get','install','-y','--no-install-recommends','squashfs-tools'],env={**os.environ,'DEBIAN_FRONTEND':'noninteractive'})
toram=Path('/usr/lib/live/boot/9990-toram-todisk.sh')
original=toram.read_bytes();backup=base/'original-toram.sh'
if not backup.exists():backup.write_bytes(original)
else:assert backup.read_bytes()==original
hook=(inputs/'toram-hook').read_text();transform=hook.split("python3 - <<'PY'\n",1)[1].split('\nPY\n',1)[0]
assert subprocess.check_output(['dpkg-query','-W','-f=${Version}','live-boot'],text=True)=='1:20250815~deb13u1'
exec(compile(transform,'public-toram-hook','exec'),{})
run(['sh','-n',str(toram)])
layer=inputs/'root';target=layer/'usr/lib/live/boot/9990-toram-todisk.sh'
target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(toram,target)
link=layer/'etc/systemd/system/multi-user.target.wants/portable-ram-content.service'
link.parent.mkdir(parents=True,exist_ok=True);link.symlink_to('../portable-ram-content.service')
marker=Path('/etc/initramfs-tools/scripts/init-top/petalos-audit-marker')
assert not marker.exists()
marker.write_text('#!/bin/sh\ncase "$1" in prereqs) exit 0;; esac\necho PETALOS_REPAIR_UNSIGNED_INITRD_MARKER > /dev/kmsg\n')
marker.chmod(0o755)
initrd=inputs/'initrd.img'
try:run(['/usr/sbin/mkinitramfs','-o',str(initrd),os.uname().release])
finally:marker.unlink();toram.write_bytes(original)
unpacked=inputs/'initrd-unpacked';run(['unmkinitramfs',str(initrd),str(unpacked)])
assert len(list(unpacked.glob('*/scripts/init-top/petalos-audit-marker')))==1
# Check real disposable credentials only in RAM, without printing their values.
secrets=[v.encode() for v in values.values()]
for line in Path('/etc/shadow').read_text().splitlines():
 field=line.split(':')[1]
 if field.startswith('$'):secrets.append(field.encode())
for p in Path('/mnt/system-state/Network/Profiles').glob('*.conf'):
 secrets.extend(re.findall(rb'(?m)^\s*(?:PrivateKey|PresharedKey)\s*=\s*(\S+)',p.read_bytes()))
for p in (Path('/run/portable-storage/system-volume/.petalos-qemu-ssh')).glob('ssh_host_*_key'):
 secrets.append(p.read_bytes())
count=0
for p in unpacked.rglob('*'):
 if p.is_symlink() or not p.is_file():continue
 assert p.name not in ('shadow','gshadow','wg0.conf','data.key','root-admin.hash','credentials.json')
 content=p.read_bytes();assert not any(s in content for s in secrets);count+=1
module=inputs/'petalos-phase15-repair.squashfs'
run(['mksquashfs',str(layer),str(module),'-noappend','-comp','zstd','-processors','4','-no-progress'])
extract=inputs/'layer-readback';run(['unsquashfs','-d',str(extract),str(module)])
for name,expected in manifest.items():
 if name.startswith('root/'):
  p=extract/name[5:];assert hashlib.sha256(p.read_bytes()).hexdigest()==expected
print(json.dumps({'public_layer_readback':True,'initrd_files_checked_for_credentials':count,'benign_initrd_marker_present':True}),flush=True)
spec=importlib.util.spec_from_file_location('generation',inputs/'generation.py')
generation=importlib.util.module_from_spec(spec);spec.loader.exec_module(generation)
boot=base/'boot';system=base/'system'
for p in (boot,system):p.mkdir(mode=0o700,exist_ok=False)
mounted=[]
try:
 run(['mount','-o','nodev,nosuid,noexec','/dev/vda2',str(boot)]);mounted.append(boot)
 run(['mount','-o','nodev,nosuid,noexec','/dev/mapper/portable_system',str(system)]);mounted.append(system)
 assert subprocess.check_output(['blkid','-s','LABEL','-o','value','/dev/vda2'],text=True).strip()=='PORT_BOOT'
 sources={name:boot/'live'/name for name in ('vmlinuz','initrd.img')}
 sources['initrd.img']=initrd;sources['filesystem.squashfs']=system/'live/filesystem.squashfs'
 assert shutil.disk_usage(system).free > sources['filesystem.squashfs'].stat().st_size+module.stat().st_size+64*1024**2
 target=system/'live'/module.name;assert not target.exists();shutil.copyfile(module,target);target.chmod(0o644)
 configs=[(p,p.read_text()) for p in (boot/'EFI/BOOT/grub.cfg',boot/'EFI/debian/grub.cfg',boot/'boot/grub/grub.cfg')]
 modules=(system/'live/filesystem.module').read_text().splitlines()+[module.name]
 def pinned():
  storage.backend().verify_mapping(identity,'system')
  assert storage.backend().device(identity,'system').resolve()==Path('/dev/vda3')
  assert not Path('/dev/mapper/portable_data').exists()
 # Historical disposable audit fixture uses its existing legacy payload as input.
 # This is not an installation/update entry point for deployed PetalOS systems.
 gen,installed=generation.stage_and_activate(boot,system,sources,{k:generation.digest(v) for k,v in sources.items()},configs,modules,identity=pinned,retention='preserve')
 print(json.dumps({'generation':gen,'files_verified':len(installed),'old_payloads_retained':all((system/'live'/n).exists() for n in modules),'Private_stayed_closed':True}),flush=True)
finally:
 for p in reversed(mounted):run(['umount',str(p)])
assert system_state.ready()
print('Disposable generation ready; all preparation mounts closed.',flush=True)
