#!/usr/bin/python3 -I
"""Read only public boot layout for the identity-pinned RC1 card."""
from pathlib import Path
import importlib.util
import os
import subprocess
import tempfile
import builtins
import json

spec = importlib.util.spec_from_file_location('update', Path(__file__).with_name('update-card-release-root.py'))
u = importlib.util.module_from_spec(spec); spec.loader.exec_module(u)
u.require(os.geteuid() == 0 and os.environ.get('SUDO_UID') == '1000', 'Use sudo.')
fd, report = tempfile.mkstemp(prefix='petalos-card-inspection-', suffix='.txt', dir='/run/user/1000')
os.fchown(fd,1000,int(os.environ['SUDO_GID']))
report_file=os.fdopen(fd,'w',buffering=1)
def print(*args,**kwargs):
    builtins.print(*args,**kwargs)
    builtins.print(*args,file=report_file,flush=True)

device, number = u.load_helper().check_card(require_original_uuids=False)
part = Path(str(u.CARD) + '-part3')
u.require(u.run('/usr/sbin/blkid', '-s', 'UUID', '-o', 'value', str(part)) == u.IDENTITIES[3][0], 'Wrong SYSTEM UUID.')
u.require(not u.MAPPER.exists(), 'Mapping exists.')
print('Enter card SYSTEM passphrase for read-only inspection.', flush=True)
subprocess.run(['/usr/sbin/cryptsetup','open','--readonly',str(part),u.MAPPER.name],check=True)
work=Path(tempfile.mkdtemp(prefix='petalos-card-inspect-',dir='/run')); mounted=[]
try:
    md=u.MAPPER.stat().st_rdev
    slaves=Path(f'/sys/dev/block/{os.major(md)}:{os.minor(md)}/slaves')
    u.require([p.name for p in slaves.iterdir()]==[part.resolve().name], 'Wrong mapping backing device.')
    print('Checking unmounted SYSTEM filesystem without repairs.',flush=True)
    check=subprocess.run(['/usr/sbin/e2fsck','-fn',str(u.MAPPER)],capture_output=True,timeout=300)
    print('Read-only SYSTEM filesystem check exit code: '+str(check.returncode),flush=True)
    print('Checking boot filesystem without repairs.',flush=True)
    check=subprocess.run(['/usr/sbin/fsck.fat','-n',str(u.CARD)+'-part2'],capture_output=True,timeout=120)
    print('Read-only boot filesystem check exit code: '+str(check.returncode),flush=True)
    print('SYSTEM filesystem label: '+u.run('/usr/sbin/blkid','-s','LABEL','-o','value',str(u.MAPPER)),flush=True)
    for name,source,kind,options in [('system',u.MAPPER,'ext4','ro,noload'),('boot',Path(str(u.CARD)+'-part2'),'vfat','ro')]:
        target=work/name;target.mkdir()
        u.run('/usr/bin/mount','-t',kind,'-o',options+',nodev,nosuid,noexec',str(source),str(target));mounted.append(target)
    system=work/'system';boot=work/'boot'
    print('Legacy automatic Private key present: '+str((system/'.portable-keys/data.key').exists()),flush=True)
    selection=(system/'live/filesystem.module').read_text().split()
    allowed={'filesystem.squashfs','petalos-hardware-ssh.squashfs','petalos-config.squashfs'}
    print('Module selection matches expected: '+str(selection==['filesystem.squashfs','petalos-hardware-ssh.squashfs']),flush=True)
    print('Only known public modules selected: '+str(set(selection)<=allowed),flush=True)
    print('EFI executable count: '+str(sum(p.is_file() and p.suffix.lower()=='.efi' for p in boot.rglob('*'))),flush=True)
    for name in ('system','boot'):
        v=os.statvfs(work/name);print(name+' available bytes: '+str(v.f_bavail*v.f_frsize),flush=True)
    release=Path('/home/sam/portable-live/releases/20261016-220759-383148')
    manifest=json.loads((release/'manifest.json').read_text())
    print('Reading RC1 OS payloads from card.',flush=True)
    for name in ('filesystem.squashfs','vmlinuz','initrd.img'):
        candidates=[system/'live'/name] if name=='filesystem.squashfs' else [boot/name,boot/'live'/name]
        targets=[p for p in candidates if p.is_file()]
        print(name+' destination count: '+str(len(targets)),flush=True)
        for target in targets:
            try: matched=u.digest(target)==manifest['binary/live/'+name]['sha256']
            except OSError:
                print(name+' READ ERROR',flush=True);continue
            print(name+' RC1 checksum matches: '+str(matched),flush=True)
    extras=sorted(p for p in (system/'live').glob('*.squashfs') if p.name not in selection)
    print('Unselected squashfs count: '+str(len(extras)),flush=True)
    for target in extras:
        if not __import__('re').fullmatch(r'petalos-(?:config|qemu-ssh|wayland-test(?:-[uv]?[2-5])?)\.squashfs',target.name):
            print('Unrecognized leftover module; name suppressed.',flush=True);continue
        try:
            u.digest(target)
            print('Leftover '+target.name+' readable.',flush=True)
        except OSError:print('Leftover '+target.name+' READ ERROR',flush=True)
    log=subprocess.run(['/usr/bin/journalctl','-k','-n','250','--no-pager','-o','cat'],capture_output=True,text=True)
    lines=log.stdout.splitlines()
    print('Recent kernel USB disconnect count: '+str(sum('USB disconnect' in x for x in lines)),flush=True)
    print('Recent kernel storage error count: '+str(sum(any(t in x.lower() for t in ('i/o error','buffer i/o','reset high-speed','device descriptor read')) for x in lines)),flush=True)
    for config in boot.rglob('grub.cfg'):
        content=config.read_text()
        if 'live-media=/dev/mapper/portable_system' not in content:continue
        for line in content.splitlines():
            words=line.split()
            if words and words[0] in ('linux','linuxefi'):
                required={'toram','swap=false','init_on_alloc=1','init_on_free=1','petalos_hardware_ssh=1','live-media=/dev/mapper/portable_system'}
                print('Missing required boot flags: '+','.join(sorted(required-set(words))),flush=True)
finally:
    for target in reversed(mounted):u.run('/usr/bin/umount',str(target))
    u.run('/usr/sbin/cryptsetup','close',u.MAPPER.name)
    for child in work.iterdir():child.rmdir()
    work.rmdir()
print('Read-only inspection complete; mappings closed.',flush=True)
