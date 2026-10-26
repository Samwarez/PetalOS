"""Unprivileged, bounded Private-to-RAM Trash; never follows source symlinks."""
from contextlib import contextmanager
from datetime import datetime
import fcntl
import ctypes
import os
from pathlib import Path
import secrets
import re
import stat
import subprocess
from urllib.parse import quote_from_bytes

HOME=Path('/home/Petal')
PRIVATE=Path('/mnt/private')
BLOCKED=Path('/run/portable-trash-blocked')
DIR=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
LIMIT=2*1024**3
ENTRIES=10000


class TrashCapacityError(OSError):
    """A pre-deletion RAM/resource limit; the original has not been deleted."""


def block_private_trash():
    """Root transition barrier, published before draining Private readers."""
    assert os.geteuid()==0
    fd=os.open(BLOCKED,os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        info=os.fstat(fd)
        assert stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1 and not info.st_mode & 0o077
    finally:os.close(fd)


def allow_private_trash():
    """Root calls this only after successful, actively verified Private unlock."""
    assert os.geteuid()==0
    try:info=BLOCKED.lstat()
    except FileNotFoundError:return
    assert stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1 and not info.st_mode & 0o077
    BLOCKED.unlink()


def check_not_blocked():
    # This is a denial barrier, never proof that a volume is unlocked. The
    # caller must also hold/verify the actual Private mount's root descriptor.
    if BLOCKED.exists():raise OSError('Private is locking or locked.')


def token(info):
    return (info.st_dev,info.st_ino,info.st_mode,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


def rename_new(source,name,destination,target):
    libc=ctypes.CDLL(None,use_errno=True)
    rename=libc.renameat2
    rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    rename.restype=ctypes.c_int
    if rename(source,os.fsencode(name),destination,os.fsencode(target),1):
        error=ctypes.get_errno();raise OSError(error,os.strerror(error))


@contextmanager
def trash_directory(home=HOME, *, create=True, uid=1000, expected_device=None):
    """Pin each directory, reject links/foreign filesystems and unsafe owners."""
    handles=[]
    try:
        fd=os.open(home,DIR);handles.append(fd);device=os.fstat(fd).st_dev
        assert os.fstat(fd).st_uid==uid
        assert expected_device is None or device==expected_device
        for name in ('.local','share','Trash'):
            if create:
                try:os.mkdir(name,0o700,dir_fd=fd)
                except FileExistsError:pass
            fd=os.open(name,DIR,dir_fd=fd);handles.append(fd)
            info=os.fstat(fd)
            assert info.st_uid==uid and info.st_dev==device
            # GIO can create its parents using the session umask (e.g. 0002).
            # Pin and tighten only our owned RAM directories before copying.
            os.fchmod(fd,0o700 if name=='Trash' else stat.S_IMODE(info.st_mode)&~0o022)
            assert not os.fstat(fd).st_mode & 0o022
        assert not os.fstat(fd).st_mode & 0o077, 'Trash must be private to the desktop user.'
        yield fd
    finally:
        for fd in reversed(handles):os.close(fd)


def remove_at(parent,name):
    info=os.stat(name,dir_fd=parent,follow_symlinks=False)
    assert info.st_dev==os.fstat(parent).st_dev, 'Never clean across a filesystem boundary.'
    if stat.S_ISDIR(info.st_mode):
        fd=os.open(name,DIR,dir_fd=parent)
        try:
            assert os.fstat(fd).st_dev==info.st_dev and os.fstat(fd).st_ino==info.st_ino
            for child in os.listdir(fd):remove_at(fd,child)
        finally:os.close(fd)
        os.rmdir(name,dir_fd=parent)
    else:os.unlink(name,dir_fd=parent)


def clear():
    """Root lock path: clear only the desktop's RAM Trash, never Private's."""
    from compartments import ram_ready
    ram_ready()
    try:
        with trash_directory(create=False,expected_device=os.stat('/').st_dev) as root:
            assert os.fstat(root).st_dev==os.stat('/').st_dev
            try:
                lock=os.open('.petalos-copy.lock',os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=root)
                os.fchown(lock,1000,1000)
            except FileExistsError:
                lock=os.open('.petalos-copy.lock',os.O_RDWR|os.O_NOFOLLOW,dir_fd=root)
            try:
                info=os.fstat(lock)
                assert stat.S_ISREG(info.st_mode) and info.st_uid==1000 and info.st_nlink==1 and not info.st_mode & 0o077
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                for name in os.listdir(root):
                    if name=='.petalos-copy.lock':continue
                    if name in ('files','info'):
                        fd=os.open(name,DIR,dir_fd=root)
                        try:
                            assert os.fstat(fd).st_dev==os.fstat(root).st_dev and os.fstat(fd).st_uid==1000
                            os.fchmod(fd,0o700)
                            for child in os.listdir(fd):remove_at(fd,child)
                        finally:os.close(fd)
                    else:remove_at(root,name)
            finally:os.close(lock)
    except FileNotFoundError:pass


def memory_available():
    fields=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    return int(fields['MemAvailable'].split()[0])*1024


class Budget:
    def __init__(self,limit):self.limit=limit;self.bytes=0;self.entries=0
    def entry(self,depth):
        self.entries+=1
        if self.entries>ENTRIES or depth>64:raise TrashCapacityError('RAM Trash item is too complex.')
        if memory_available()<64*1024**2:raise TrashCapacityError('Insufficient free RAM.')
    def data(self,count):
        self.bytes+=count
        if self.bytes>self.limit:raise TrashCapacityError('RAM Trash capacity exceeded.')


def copy_at(source,name,destination,target,budget,device,depth=0):
    budget.entry(depth)
    before=os.stat(name,dir_fd=source,follow_symlinks=False)
    assert before.st_dev==device, 'Nested mounts are not trashable.'
    node={'token':token(before),'children':None}
    if stat.S_ISLNK(before.st_mode):
        link=os.readlink(name,dir_fd=source)
        budget.data(len(os.fsencode(link)))
        os.symlink(link,target,dir_fd=destination)
        os.utime(target,ns=(before.st_atime_ns,before.st_mtime_ns),dir_fd=destination,follow_symlinks=False)
    elif stat.S_ISREG(before.st_mode):
        src=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=source)
        try:
            assert token(os.fstat(src))==node['token']
            out=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=destination)
            try:
                count=0
                while block:=os.read(src,1024**2):
                    budget.data(len(block));count+=len(block)
                    if memory_available()<64*1024**2:raise TrashCapacityError('Insufficient free RAM.')
                    view=memoryview(block)
                    while view:
                        written=os.write(out,view)
                        if written<=0:raise OSError('RAM Trash write failed.')
                        view=view[written:]
                assert count==before.st_size and token(os.fstat(src))==node['token'], 'Source changed while copying.'
                os.fchmod(out,stat.S_IMODE(before.st_mode)&0o700)
                os.utime(out,ns=(before.st_atime_ns,before.st_mtime_ns))
                os.fsync(out)
            finally:os.close(out)
        finally:os.close(src)
    elif stat.S_ISDIR(before.st_mode):
        src=os.open(name,DIR,dir_fd=source)
        try:
            assert token(os.fstat(src))==node['token']
            os.mkdir(target,0o700,dir_fd=destination)
            out=os.open(target,DIR,dir_fd=destination)
            try:
                node['children']={child:copy_at(src,child,out,child,budget,device,depth+1)
                                  for child in os.listdir(src)}
                os.utime(out,ns=(before.st_atime_ns,before.st_mtime_ns))
                os.fsync(out)
            finally:os.close(out)
        finally:os.close(src)
    else:raise OSError('Special files cannot be copied into RAM Trash.')
    assert token(os.stat(name,dir_fd=source,follow_symlinks=False))==node['token'], 'Source changed while copying.'
    return node


def verify_at(parent,name,node):
    assert token(os.stat(name,dir_fd=parent,follow_symlinks=False))==node['token'], 'Source changed before deletion.'
    if node['children'] is not None:
        fd=os.open(name,DIR,dir_fd=parent)
        try:
            assert set(os.listdir(fd))==set(node['children'])
            for child,value in node['children'].items():verify_at(fd,child,value)
        finally:os.close(fd)


def delete_at(parent,name,node):
    # Delete only copied, identity-checked entries. Unexpected new children are
    # never recursively removed. On a deletion error the published RAM copy stays.
    assert token(os.stat(name,dir_fd=parent,follow_symlinks=False))==node['token']
    if node['children'] is None:os.unlink(name,dir_fd=parent)
    else:
        fd=os.open(name,DIR,dir_fd=parent)
        try:
            assert set(os.listdir(fd))==set(node['children'])
            for child,value in node['children'].items():delete_at(fd,child,value)
        finally:os.close(fd)
        current=os.stat(name,dir_fd=parent,follow_symlinks=False)
        assert current.st_dev==node['token'][0] and current.st_ino==node['token'][1]
        os.rmdir(name,dir_fd=parent)


def move_at(parent,name,original,trash,limit, *, check=lambda:None):
    """Copy completely and publish recoverable metadata before any deletion."""
    handles=[];stage=None;published=False;info_name=None;info_created=False
    try:
        lock=os.open('.petalos-copy.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=trash);handles.append(lock)
        info=os.fstat(lock)
        assert stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and info.st_nlink==1 and not info.st_mode & 0o077
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for child in ('files','info'):
            try:os.mkdir(child,0o700,dir_fd=trash)
            except FileExistsError:pass
            fd=os.open(child,DIR,dir_fd=trash);handles.append(fd)
            info=os.fstat(fd)
            assert info.st_uid==os.geteuid() and info.st_dev==os.fstat(trash).st_dev
            os.fchmod(fd,0o700)
        files,metadata=handles[-2:]
        check()
        # A cancelled Thunar job may SIGKILL its helper. Under the exclusive
        # lock, reclaim only our unpublished RAM staging copies before retry.
        for leftover in os.listdir(trash):
            if not re.fullmatch(r'\.copy-petalos-private-[a-f0-9]{32}',leftover):continue
            key=leftover.removeprefix('.copy-')
            remove_at(trash,leftover)
            try:os.stat(key,dir_fd=files,follow_symlinks=False)
            except FileNotFoundError:
                try:os.unlink(key+'.trashinfo',dir_fd=metadata)
                except FileNotFoundError:pass
        key='petalos-private-'+secrets.token_hex(16)
        temporary='.copy-'+key
        os.mkdir(temporary,0o700,dir_fd=trash);stage=temporary
        staging=os.open(stage,DIR,dir_fd=trash)
        try:node=copy_at(parent,name,staging,'payload',Budget(limit),os.fstat(parent).st_dev)
        finally:os.close(staging)
        verify_at(parent,name,node)
        check()
        info_name=key+'.trashinfo'
        info=os.open(info_name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=metadata)
        info_created=True
        with os.fdopen(info,'wb') as output:
            output.write(('[Trash Info]\nPath='+quote_from_bytes(os.fsencode(original),safe='/')+
                          '\nDeletionDate='+datetime.now().isoformat(timespec='seconds')+'\n').encode())
            output.flush();os.fsync(output.fileno())
        os.fsync(metadata)
        check()
        staging=os.open(stage,DIR,dir_fd=trash)
        try:rename_new(staging,'payload',files,key)
        finally:os.close(staging)
        published=True;os.fsync(files)
        check()
        delete_at(parent,name,node)
        return key
    finally:
        if stage is not None:
            try:remove_at(trash,stage)
            except FileNotFoundError:pass
        if not published and info_created:
            os.unlink(info_name,dir_fd=metadata)
        for fd in reversed(handles):os.close(fd)


def move(path):
    assert os.getuid()==os.geteuid()==1000
    from compartments import ram_ready
    ram_ready()
    fields=subprocess.check_output(['/usr/bin/findmnt','-n','-o','SOURCE,FSTYPE','--mountpoint',str(PRIVATE)],timeout=5).split()
    assert fields==[b'/dev/mapper/portable_data',b'ext4'], 'Private is not ready.'
    # Resolve parent aliases only; a symlink itself is copied, never its target.
    original=Path(path)
    assert original.is_absolute() and original.name not in ('','.','..')
    parent=original.parent.resolve(strict=True)
    relative=parent.relative_to(PRIVATE)
    handles=[]
    try:
        fd=os.open(PRIVATE,DIR);handles.append(fd)
        # A producer that passes this check already holds a Private descriptor,
        # so the lock controller's subsequent reader drain can identify it.
        check_not_blocked()
        device=os.fstat(fd).st_dev
        assert device==Path('/dev/mapper/portable_data').stat().st_rdev
        for part in relative.parts:
            fd=os.open(part,DIR,dir_fd=fd);handles.append(fd)
            assert os.fstat(fd).st_dev==device
        with trash_directory(expected_device=os.stat('/').st_dev) as trash:
            assert os.fstat(trash).st_dev==os.stat('/').st_dev
            available=memory_available();space=os.fstatvfs(trash)
            limit=min(LIMIT,available//4,space.f_bavail*space.f_frsize//2)
            if available<128*1024**2 or limit<=0:raise TrashCapacityError('Insufficient free RAM.')
            return move_at(fd,original.name,parent/original.name,trash,limit,check=check_not_blocked)
    finally:
        for fd in reversed(handles):os.close(fd)
