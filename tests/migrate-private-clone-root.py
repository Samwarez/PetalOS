#!/usr/bin/python3 -I
"""Fresh DATA encryption on a registered disposable clone; no physical devices."""
import ctypes
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import stat
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
SESSIONS = PROJECT.parent/'testing/sessions'
NAMES = ('petal_migrate_source_system', 'petal_migrate_clone_system',
         'petal_migrate_source_data', 'petal_migrate_clone_data', 'petal_migrate_old_header')

def run(command, *, password=None, timeout=30):
    return subprocess.run(command, input=password, capture_output=True, timeout=timeout, check=True)

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        while block := source.read(4*1024*1024): h.update(block)
    return h.digest()

def validate_image(path, uid):
    path = Path(path)
    assert not path.is_symlink() and path.resolve()==path and path.resolve().is_relative_to(SESSIONS.resolve())
    info = path.stat()
    assert stat.S_ISREG(info.st_mode) and info.st_uid == uid and info.st_size == 16*1024**3
    assert re.fullmatch(r'encrypted-boot-\d{8}-\d{6}-\d+\.img', path.name)
    return path

class Disk:
    def __init__(self, path, readonly):
        self.path = path; self.identity = (path.stat().st_dev, path.stat().st_ino, path.stat().st_size)
        self.loop = None; self.readonly = readonly
    def verify(self):
        info = self.path.stat()
        assert (info.st_dev, info.st_ino, info.st_size) == self.identity
        if self.loop:
            backing = Path('/sys/class/block')/Path(self.loop).name/'loop/backing_file'
            assert Path(backing.read_text().strip()).resolve() == self.path.resolve()
    def attach(self):
        flags = ['--read-only'] if self.readonly else []
        self.loop = run(['/usr/sbin/losetup','--find','--show','--partscan',*flags,str(self.path)]).stdout.decode().strip()
        self.verify(); run(['/usr/bin/udevadm','settle','--timeout=10'])
        table = json.loads(run(['/usr/sbin/sfdisk','--json',self.loop]).stdout)['partitiontable']
        parts = table['partitions']
        assert table['label']=='gpt' and len(parts)==4
        assert parts[1]['size']==2097152 and parts[2]['size']==8388608
        self.layout = [(p['start'],p['size'],p['type']) for p in parts]
        for number,label in ((3,'PORTABLE_SYSTEM'),(4,'PORTABLE_DATA')):
            assert self.tag(self.partition(number),'LABEL') == label
            assert self.tag(self.partition(number),'TYPE') == 'crypto_LUKS'
    def partition(self, number):
        self.verify(); p = Path(f'{self.loop}p{number}')
        assert (Path('/sys/class/block')/p.name).resolve().parent.name == Path(self.loop).name
        return p
    def tag(self, device, field):
        return run(['/usr/sbin/blkid','-p','-s',field,'-o','value',str(device)]).stdout.decode().strip()
    def mapper(self, name, number, uuid=None):
        self.verify(); p = Path('/dev/mapper')/name; info = p.stat()
        assert stat.S_ISBLK(info.st_mode)
        directory = Path(f'/sys/dev/block/{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}')
        assert [x.name for x in (directory/'slaves').iterdir()] == [self.partition(number).name]
        expected = uuid or self.tag(self.partition(number),'UUID')
        assert (directory/'dm/uuid').read_text().strip().startswith('CRYPT-LUKS2-'+expected.replace('-','')+'-')
        return p
    def detach(self):
        if self.loop: self.verify();run(['/usr/sbin/losetup','--detach',self.loop]);self.loop=None

def accepts(device, *, password=None, key=None):
    r = subprocess.run(['/usr/sbin/cryptsetup','open','--test-passphrase','--key-file',
                        str(key) if key else '-',str(device)], input=password,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60)
    assert r.returncode in (0,2)
    return r.returncode==0

def main():
    assert os.geteuid()==0 and (len(sys.argv)==4 or (len(sys.argv)==5 and sys.argv[4]=='--verify-existing-copy'))
    resume=len(sys.argv)==5
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    assert ctypes.CDLL('libc.so.6').prctl(4,0,0,0,0)==0
    uid=int(os.environ['SUDO_UID'])
    source=validate_image(sys.argv[1],uid);clone=validate_image(sys.argv[2],uid)
    assert source.resolve()!=clone.resolve() and not os.path.samefile(source,clone)
    state=json.loads(Path(f'/run/user/{uid}/petalos-encrypted-test.json').read_text())
    transfer=json.loads(Path(f'/run/user/{uid}/petalos-private-migration.json').read_text())
    assert state['image']==str(source) and transfer['source']==str(source) and transfer['clone']==str(clone)
    assert transfer['phase']=='awaiting-authentication'
    module=Path(sys.argv[3]);assert not module.is_symlink() and module.is_file()
    assert module.resolve().is_relative_to(SESSIONS.resolve()) and module.name=='petalos-wayland-test-v5.squashfs'
    manifest=json.loads((module.parent/'manifest.json').read_text())
    assert manifest['source_image']==str(source) and hashlib.sha256(module.read_bytes()).hexdigest()==manifest['module_sha256']
    assert not Path(f'/run/user/{uid}/petalos-qemu-monitor.sock').exists()
    assert not any(name.startswith(('qemu-system','qemu-nbd')) for name in run(['/usr/bin/ps','-eo','comm=']).stdout.decode().splitlines())
    for disk in (source,clone):
        assert subprocess.run(['/usr/bin/fuser',str(disk)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==1
        for backing in Path('/sys/block').glob('loop*/loop/backing_file'):
            assert Path(backing.read_text().strip()).resolve()!=disk.resolve()
    assert all(not (Path('/dev/mapper')/name).exists() for name in NAMES)
    print('Verifying the original and clone checksums (two 16 GiB reads); this can take a minute.',flush=True)
    before=digest(source)
    if not resume:assert before==digest(clone),'Clone is not an exact copy.'
    print('Source checksum captured; preparing existing-copy verification.' if resume else 'Original/clone checksums match; preparing encrypted mappings.',flush=True)
    src=Disk(source,True);dst=Disk(clone,False);mappings=[];mounts=[]
    work=Path(tempfile.mkdtemp(prefix='petalos-private-migration-',dir='/run'));work.chmod(0o700)
    def open_map(disk,number,name,*,password=None,key=None,header=None,readonly=False):
        disk.verify();args=['/usr/sbin/cryptsetup','open']
        if readonly:args+=['--readonly']
        if header:args+=['--header',str(header)]
        args+=['--key-file',str(key) if key else '-',str(disk.partition(number)),name]
        run(args,password=password,timeout=90)
        expected=src.tag(header,'UUID') if header else None
        mappings.append((disk,number,name,expected))
        p=disk.mapper(name,number,expected);os.chmod(p,0o600)
        if readonly:assert run(['/usr/sbin/blockdev','--getro',str(p)]).stdout.strip()==b'1'
        return p
    def mount_map(disk,p,name,directory,readonly):
        directory.mkdir(mode=0o700)
        disk.mapper(name,3)
        options=('ro,noload' if readonly else 'rw')+',nodev,nosuid,noexec,noatime'
        run(['/usr/bin/mount','-t','ext4','-o',options,str(p),str(directory)])
        mounts.append((disk,name,directory))
        assert disk.tag(p,'LABEL')=='LIVE_SYSTEM'
    try:
        src.attach();dst.attach();assert src.layout==dst.layout
        system_phrase=getpass.getpass('Existing SYSTEM passphrase: ').encode()
        old_sys=open_map(src,3,NAMES[0],password=system_phrase,readonly=True)
        new_sys=open_map(dst,3,NAMES[1],password=system_phrase)
        mount_map(src,old_sys,NAMES[0],work/'source-system',True)
        mount_map(dst,new_sys,NAMES[1],work/'clone-system',False)
        old_key=work/'source-system/.portable-keys/data.key'
        assert not any(p.is_symlink() for p in (old_key,*old_key.parents))
        info=old_key.stat();assert stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600
        old_data=open_map(src,4,NAMES[2],key=old_key,readonly=True)
        assert src.tag(old_data,'TYPE')=='ext4' and src.tag(old_data,'LABEL')=='PORTABLE_FILES'
        assert accepts(src.partition(4),password=system_phrase),'Reviewed shared-passphrase precondition changed.'
        new_text=getpass.getpass('Private passphrase chosen in the previous migration: ' if resume else 'NEW distinct Private passphrase (at least 12 characters): ')
        assert len(new_text)>=12
        new_phrase=new_text.encode();del new_text
        confirmation=getpass.getpass('Confirm that Private passphrase: ' if resume else 'Confirm NEW Private passphrase: ').encode()
        assert new_phrase==confirmation and 12<=len(new_phrase)<=512 and not any(x in new_phrase for x in (b'\n',b'\r',b'\0'))
        assert not accepts(src.partition(3),password=new_phrase),'New Private phrase also unlocks SYSTEM; refuse.'
        assert not accepts(src.partition(4),password=new_phrase),'New phrase must differ from old Private phrase.'
        admin_file=work/'source-system/.petalos-auth/root-admin.hash'
        assert not any(p.is_symlink() for p in (admin_file,*admin_file.parents))
        info=admin_file.stat()
        assert info.st_uid==0 and stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode)==0o600 and info.st_size<=256
        admin_hash=admin_file.read_bytes().rstrip(b'\n')
        assert re.fullmatch(rb'\$6\$rounds=100000\$[A-Za-z0-9]{16}\$[./A-Za-z0-9]{86}',admin_hash)
        crypt=ctypes.CDLL('libcrypt.so.1').crypt
        crypt.argtypes=(ctypes.c_char_p,ctypes.c_char_p);crypt.restype=ctypes.c_char_p
        candidate=crypt(new_phrase,admin_hash)
        assert candidate and candidate!=admin_hash,'New Private phrase must differ from administrator password.'
        del confirmation,admin_hash,candidate
        dst.verify();raw=dst.partition(4);old_uuid=src.tag(src.partition(4),'UUID')
        if not resume:
            print('Formatting only the disposable clone DATA partition with a fresh volume key.',flush=True)
            run(['/usr/sbin/cryptsetup','luksFormat','--batch-mode','--type','luks2','--label','PORTABLE_DATA',
                 '--cipher','aes-xts-plain64','--key-size','512','--sector-size','512',
                 '--offset','32768','--pbkdf','argon2id','--iter-time','2000','--key-file','-',str(raw)],password=new_phrase,timeout=180)
            assert dst.tag(raw,'UUID')!=old_uuid
        assert dst.tag(raw,'UUID')!=old_uuid
        new_data=open_map(dst,4,NAMES[3],password=new_phrase,readonly=resume)
        size=lambda p:int(run(['/usr/sbin/blockdev','--getsize64',str(p)]).stdout)
        assert size(old_data)==size(new_data),'Payload size differs; original untouched, do not boot clone.'
        total=size(old_data)
        src.mapper(NAMES[2],4);dst.mapper(NAMES[3],4)
        if resume:
            print('Verifying the existing copied filesystem; no formatting or data rewriting.',flush=True)
            assert digest(old_data)==digest(new_data),'Existing copy does not match original; stop.'
        else:
            checksum=hashlib.sha256();copied=0
            print('Copying plaintext only through root memory between encrypted device mappings.',flush=True)
            with old_data.open('rb',buffering=0) as reader,new_data.open('r+b',buffering=0) as writer:
                while block:=reader.read(4*1024*1024):
                    checksum.update(block);view=memoryview(block)
                    while view:
                        count=writer.write(view);assert count;view=view[count:]
                    copied+=len(block)
                    if copied % (1024**3)==0:print('Encrypted filesystem copy: '+str(copied//(1024**3))+' GiB of '+str(round(total/(1024**3),2))+' GiB.',flush=True)
                os.fsync(writer.fileno())
            assert copied==total
            print('Filesystem copied; reading the full new mapping for integrity verification.',flush=True)
            assert checksum.digest()==digest(new_data),'Encrypted migration verification failed.'
        print('Full copied filesystem integrity verified.',flush=True)
        assert dst.tag(new_data,'TYPE')=='ext4' and dst.tag(new_data,'LABEL')=='PORTABLE_FILES'
        assert accepts(raw,password=new_phrase) and not accepts(raw,key=old_key) and not accepts(raw,password=system_phrase)
        print('Current-header new/old passphrase checks passed.',flush=True)
        with new_data.open('rb') as correct:expected_block=correct.read(4096)
        # Free both data devices before the detached-header challenge.
        for name in (NAMES[3],NAMES[2]):
            record=next(record for record in mappings if record[2]==name)
            disk,number,_,uuid=record;disk.mapper(name,number,uuid)
            run(['/usr/sbin/cryptsetup','close',name]);mappings.remove(record)
        # Test the actual old header against NEW ciphertext, without copying a header.
        probe=open_map(dst,4,NAMES[4],key=old_key,header=src.partition(4),readonly=True)
        with probe.open('rb') as wrong:
            assert wrong.read(4096)!=expected_block,'Old header still decrypts new ciphertext.'
        metadata=json.loads(run(['/usr/sbin/cryptsetup','luksDump','--dump-json-metadata',str(raw)]).stdout)
        assert list(metadata['keyslots'])==['0'] and not metadata.get('tokens')
        assert metadata['keyslots']['0']['kdf']['type']=='argon2id'
        # Install the reviewed public source fix and unselect the previous test layer.
        live=work/'clone-system/live';selection=live/'filesystem.module'
        assert not selection.is_symlink() and selection.read_text().split()==['filesystem.squashfs','petalos-qemu-ssh.squashfs','petalos-wayland-test-v4.squashfs']
        target=live/module.name;assert not target.exists() and not target.is_symlink()
        with module.open('rb') as reader,target.open('xb') as writer:
            while block:=reader.read(4*1024*1024):writer.write(block)
            writer.flush();os.fsync(writer.fileno())
        assert digest(target)==digest(module);target.chmod(0o644)
        selection.write_text('filesystem.squashfs\npetalos-qemu-ssh.squashfs\n'+module.name+'\n')
        stale=work/'clone-system/.portable-keys/data.key'
        assert not stale.is_symlink() and stale.is_file() and stale.stat().st_uid==0 and stale.stat().st_nlink==1
        stale.unlink()  # logical retirement only; no forensic erasure claim
        run(['/usr/bin/sync','-f',str(work/'clone-system')])
        del new_phrase,system_phrase
        print('Verified: full filesystem copy matches; new Private phrase works; old automatic key and SYSTEM phrase fail.',flush=True)
        print('Verified: old header/key cannot read new ciphertext; clone has one Argon2id slot; original preserved.',flush=True)
    finally:
        for disk,name,directory in reversed(mounts):
            mapper=disk.mapper(name,3)
            actual=Path(run(['/usr/bin/findmnt','-n','-o','SOURCE','--mountpoint',str(directory)]).stdout.decode().strip())
            assert actual.stat().st_rdev==mapper.stat().st_rdev
            run(['/usr/bin/umount',str(directory)]);directory.rmdir()
        for disk,number,name,uuid in reversed(mappings):
            disk.mapper(name,number,uuid);run(['/usr/sbin/cryptsetup','close',name])
        dst.detach();src.detach();work.rmdir()
    print('Mappings closed; checking that the original image checksum is unchanged.',flush=True)
    assert digest(source)==before,'Original image changed.'
    print('Fresh encrypted clone migration complete; all mappings/mounts closed; source checksum unchanged.',flush=True)

if __name__=='__main__':
    try:main()
    except BaseException as error:
        print('Migration stopped ('+type(error).__name__+'); keep the original image and inspect cleanup before booting.',file=sys.stderr)
        if isinstance(error,subprocess.CalledProcessError):
            print('Failed tool: '+Path(error.cmd[0]).name+'; operation: '+str(error.cmd[1])+'; exit: '+str(error.returncode),file=sys.stderr)
            detail=(error.stderr or b'').decode(errors='replace').lower()
            flags=[word for word in ('busy','permission denied','not supported','offset','no key available','already','header') if word in detail]
            print('Public error categories: '+', '.join(flags),file=sys.stderr)
        raise SystemExit(1)
