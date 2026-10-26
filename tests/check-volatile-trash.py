#!/usr/bin/python3
"""Real disk-to-tmpfs Trash workflows with public, disposable fixtures only."""
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

source=Path(__file__).resolve().parents[1]/'config/includes.chroot/usr/local/lib/portable/volatile_trash.py'
spec=importlib.util.spec_from_file_location('trash',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory(prefix='petalos-trash-source-') as src, tempfile.TemporaryDirectory(prefix='petalos-trash-ram-',dir='/dev/shm') as dest:
        source,ram=Path(src),Path(dest)
        fd=os.open(source,m.DIR);trash=os.open(ram,m.DIR)
        assert os.fstat(fd).st_dev!=os.fstat(trash).st_dev
        try:yield source,ram,fd,trash
        finally:os.close(fd);os.close(trash)


with fixture() as (source,ram,fd,trash):
    (source/'file with spaces').write_bytes(b'public RAM trash fixture')
    os.utime(source/'file with spaces',ns=(1234567890000000000,1234567891000000000))
    key=m.move_at(fd,'file with spaces',source/'file with spaces',trash,1024)
    assert not (source/'file with spaces').exists()
    assert (ram/'files'/key).read_bytes()==b'public RAM trash fixture'
    assert (ram/'files'/key).stat().st_mtime_ns==1234567891000000000
    info=(ram/'info'/(key+'.trashinfo')).read_text()
    assert '%20' in info and '\nDeletionDate=' in info
    # Restore uses the complete copied item and original destination, just as
    # a cross-filesystem file-manager move does. URI/GUI integration is separate.
    import shutil
    shutil.move(str(ram/'files'/key),source/'file with spaces')
    assert (source/'file with spaces').read_bytes()==b'public RAM trash fixture'
    assert not list(ram.glob('.copy-*'))
print('PASS actual cross-filesystem RAM Trash copy, metadata, source removal and file restore')

with fixture() as (source,ram,fd,trash):
    (source/'folder/subfolder').mkdir(parents=True)
    (source/'folder/subfolder/file').write_bytes(b'public directory fixture')
    (source/'outside').write_bytes(b'never follow this link')
    (source/'folder/link').symlink_to(source/'outside')
    key=m.move_at(fd,'folder',source/'folder',trash,1024)
    assert not (source/'folder').exists()
    assert (ram/'files'/key/'subfolder/file').read_bytes()==b'public directory fixture'
    assert (ram/'files'/key/'link').is_symlink()
    assert (source/'outside').read_bytes()==b'never follow this link'
print('PASS directories copy completely; symlinks are copied without reading their targets')

for failure in ('capacity','write','fsync','source-change','special-file','complexity','collision'):
    with fixture() as (source,ram,fd,trash):
        (source/'file').write_bytes(b'public unchanged source')
        from contextlib import ExitStack
        with ExitStack() as stack:
            limit=1024
            if failure=='capacity':limit=1
            elif failure=='write':stack.enter_context(patch.object(m.os,'write',side_effect=OSError('public write failure')))
            elif failure=='fsync':stack.enter_context(patch.object(m.os,'fsync',side_effect=OSError('public sync failure')))
            elif failure=='source-change':
                copy=m.copy_at
                def changing(*args,**kwargs):
                    node=copy(*args,**kwargs)
                    (source/'file').write_bytes(b'public changed source')
                    return node
                stack.enter_context(patch.object(m,'copy_at',side_effect=changing))
            elif failure=='special-file':(source/'file').unlink();os.mkfifo(source/'file')
            elif failure=='complexity':stack.enter_context(patch.object(m,'ENTRIES',0))
            elif failure=='collision':
                (ram/'info').mkdir(mode=0o700)
                (ram/'info/petalos-private-fixed.trashinfo').write_bytes(b'preserve existing metadata')
                stack.enter_context(patch.object(m.secrets,'token_hex',return_value='fixed'))
            try:m.move_at(fd,'file',source/'file',trash,limit)
            except (OSError,AssertionError):pass
            else:raise AssertionError('Failure was ignored: '+failure)
        assert (source/'file').exists()
        if failure!='special-file':
            assert (source/'file').read_bytes()==(b'public changed source' if failure=='source-change' else b'public unchanged source')
        assert not list(ram.glob('.copy-*')) and not list((ram/'files').iterdir())
        if failure=='collision':assert (ram/'info/petalos-private-fixed.trashinfo').read_bytes()==b'preserve existing metadata'
print('PASS capacity, write/sync failure, changing source, FIFO, complexity and collision preserve original data')

with fixture() as (source,ram,fd,trash):
    (source/'file').write_bytes(b'public deletion failure fixture')
    with patch.object(m,'delete_at',side_effect=OSError('public deletion failure')):
        try:m.move_at(fd,'file',source/'file',trash,1024)
        except OSError:pass
        else:raise AssertionError('Deletion failure was ignored')
    assert (source/'file').read_bytes()==b'public deletion failure fixture'
    copies=list((ram/'files').iterdir());assert len(copies)==1
    assert copies[0].read_bytes()==b'public deletion failure fixture'
    assert (ram/'info'/(copies[0].name+'.trashinfo')).is_file()
print('PASS deletion failure retains the published complete RAM copy and its recovery metadata')

with fixture() as (source,ram,fd,trash):
    (source/'file').write_bytes(b'public concurrent fixture')
    lock=os.open(ram/'.petalos-copy.lock',os.O_RDWR|os.O_CREAT,0o600)
    try:
        m.fcntl.flock(lock,m.fcntl.LOCK_EX|m.fcntl.LOCK_NB)
        try:m.move_at(fd,'file',source/'file',trash,1024)
        except BlockingIOError:pass
        else:raise AssertionError('Concurrent copy was accepted')
        assert (source/'file').read_bytes()==b'public concurrent fixture'
    finally:os.close(lock)
print('PASS concurrent Trash copy refuses without deleting the source')

with tempfile.TemporaryDirectory(prefix='petalos-trash-links-',dir='/dev/shm') as work:
    home=Path(work)/'home';home.mkdir();outside=Path(work)/'outside';outside.mkdir()
    (home/'.local').symlink_to(outside)
    try:
        with m.trash_directory(home,uid=os.getuid()):raise AssertionError('Symlink was followed')
    except OSError:pass
    assert not list(outside.iterdir())
print('PASS substituted Trash ancestor is refused without writing outside RAM Trash')

with tempfile.TemporaryDirectory(prefix='petalos-trash-clear-',dir='/dev/shm') as work:
    from types import SimpleNamespace
    import sys
    base=Path(work);home=base/'home';home.mkdir();outside=base/'outside';outside.mkdir()
    (outside/'canary').write_bytes(b'preserve unrelated data')
    with m.trash_directory(home,uid=os.getuid()) as fd:
        os.mkdir('files',0o700,dir_fd=fd);os.mkdir('info',0o700,dir_fd=fd)
        trash=home/'.local/share/Trash'
        (trash/'files/private-fixture').write_bytes(b'public disposable data')
        (trash/'files/link').symlink_to(outside,target_is_directory=True)
        (trash/'info/private-fixture.trashinfo').write_bytes(b'public original-path metadata')
        original=m.trash_directory;actual_stat=os.stat
        def fixture_stat(path,*args,**kwargs):
            return SimpleNamespace(st_dev=os.fstat(fd).st_dev) if path=='/' else actual_stat(path,*args,**kwargs)
        with patch.dict(sys.modules,{'compartments':SimpleNamespace(ram_ready=lambda:None)}), \
             patch.object(m,'trash_directory',side_effect=lambda **kwargs:original(home,uid=os.getuid(),**kwargs)), \
             patch.object(m.os,'stat',side_effect=fixture_stat):
            m.clear()
        assert not list((trash/'files').iterdir()) and not list((trash/'info').iterdir())
        assert (outside/'canary').read_bytes()==b'preserve unrelated data'
        assert (trash/'files').is_dir() and (trash/'info').is_dir()
print('PASS lock cleanup removes RAM data/metadata, preserves watched directories and never follows links to unrelated files')

with fixture() as (source,ram,fd,trash):
    (ram/'files').mkdir(mode=0o700);(ram/'info').mkdir(mode=0o700)
    key='petalos-private-'+'a'*32
    stage=ram/('.copy-'+key);stage.mkdir();(stage/'payload').write_bytes(b'interrupted public copy')
    (ram/'info'/(key+'.trashinfo')).write_bytes(b'interrupted public metadata')
    (source/'file').write_bytes(b'public retry source')
    new=m.move_at(fd,'file',source/'file',trash,1024)
    assert not stage.exists() and not (ram/'info'/(key+'.trashinfo')).exists()
    assert (ram/'files'/new).read_bytes()==b'public retry source'
print('PASS retry reclaims only abandoned RAM staging and unpublished metadata after an interrupted helper')

with tempfile.TemporaryDirectory(prefix='petalos-trash-permissions-',dir='/dev/shm') as work:
    home=Path(work)
    for part in ('.local','.local/share','.local/share/Trash'):
        path=home/part;path.mkdir(exist_ok=True);path.chmod(0o775)
    with m.trash_directory(home,uid=os.getuid()):pass
    assert (home/'.local').stat().st_mode & 0o022==0
    assert (home/'.local/share').stat().st_mode & 0o022==0
    assert (home/'.local/share/Trash').stat().st_mode & 0o777==0o700
    untouched=home/'other';untouched.mkdir()
    try:
        with m.trash_directory(untouched,uid=os.getuid(),expected_device=0):raise AssertionError('Wrong filesystem accepted')
    except AssertionError:pass
    assert not list(untouched.iterdir())
print('PASS normal desktop umask is tightened before copying; a wrong filesystem is rejected before any directory creation')

with fixture() as (source,ram,fd,trash):
    blocked=ram/'root-denial-marker';(source/'file').write_bytes(b'public interrupted lock fixture')
    original=m.copy_at
    def locking_copy(*args,**kwargs):
        node=original(*args,**kwargs);blocked.touch();return node
    with patch.object(m,'BLOCKED',blocked),patch.object(m,'copy_at',side_effect=locking_copy):
        try:m.move_at(fd,'file',source/'file',trash,1024,check=m.check_not_blocked)
        except OSError:pass
        else:raise AssertionError('Copy continued across the lock barrier')
    assert (source/'file').read_bytes()==b'public interrupted lock fixture'
    assert not list((ram/'files').iterdir()) and not list((ram/'info').iterdir())
    assert not list(ram.glob('.copy-*'))
print('PASS lock beginning during a copy prevents publication and deletion; original data remains intact')
