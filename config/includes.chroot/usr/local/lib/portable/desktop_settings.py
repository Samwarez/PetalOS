"""Validated, selective desktop persistence, separate from Private documents."""
from pathlib import Path, PurePosixPath
import tarfile

ROOTS=tuple('.config/xfce4/xfconf/xfce-perchannel-xml/'+name+'.xml'
            for name in ('xfce4-panel','xfce4-desktop','xsettings','xfwm4'))+(
    '.config/xfce4/panel','.config/gtk-3.0/settings.ini','.gtkrc-2.0',
    '.config/labwc/themerc-override')
LEGACY_ROOTS=('.config/xfce4/xfconf','.config/xfce4/panel','.config/gtk-3.0','.gtkrc-2.0',
              '.config/labwc/themerc-override')
MAX=64*1024**2


def allowed(member, roots=ROOTS):
    name=str(PurePosixPath(member.name))
    return any(name==root or (root in ('.config/xfce4/panel',) or roots==LEGACY_ROOTS) and name.startswith(root+'/') or
               (member.isdir() and root.startswith(name+'/')) for root in roots)


def validate_archive(source, *, legacy=False):
    import os
    assert os.fstat(source.fileno()).st_size<=MAX
    source.seek(0)
    with tarfile.open(fileobj=source,mode='r:') as archive:
        count=0;size=0
        for member in archive:
            count+=1;size+=member.size
            assert count<=4096 and size<=MAX
            path=PurePosixPath(member.name);name=str(path)
            assert not path.is_absolute() and '..' not in path.parts and (member.isfile() or member.isdir())
            assert allowed(member, LEGACY_ROOTS if legacy else ROOTS)
    source.seek(0)


def restore(source,home):
    validate_archive(source,legacy=True)
    with tarfile.open(fileobj=source,mode='r:') as archive:
        archive.extractall(home,members=[m for m in archive if allowed(m)],filter='data')


def sanitize(destination):
    """One-time format migration: discard legacy file-chooser/other app state."""
    import os,tempfile
    destination=Path(destination)
    fd=os.open(destination,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as source:
        validate_archive(source,legacy=True)
        with tarfile.open(fileobj=source,mode='r:') as archive:
            if all(allowed(m) for m in archive):return
        source.seek(0)
        fd,name=tempfile.mkstemp(prefix='.desktop-sanitize-',dir=destination.parent)
        try:
            with os.fdopen(fd,'w+b') as output:
                with tarfile.open(fileobj=source,mode='r:') as old, tarfile.open(fileobj=output,mode='w:') as new:
                    for member in old:
                        if allowed(member):new.addfile(member,old.extractfile(member) if member.isfile() else None)
                validate_archive(output);output.flush();os.fsync(output.fileno())
            os.replace(name,destination)
            fd=os.open(destination.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:os.fsync(fd)
            finally:os.close(fd)
        finally:Path(name).unlink(missing_ok=True)


def save(home,destination):
    import os,tempfile
    home=Path(home);destination=Path(destination)
    assert not destination.is_symlink()
    paths=[p for p in ROOTS if (home/p).exists()]
    assert paths
    fd,name=tempfile.mkstemp(prefix='.desktop-settings-',dir=destination.parent)
    try:
        with os.fdopen(fd,'w+b') as output:
            with tarfile.open(fileobj=output,mode='w:',dereference=False) as archive:
                for p in paths:archive.add(home/p,arcname=p)
            validate_archive(output);output.flush();os.fsync(output.fileno())
        os.replace(name,destination)
        fd=os.open(destination.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:Path(name).unlink(missing_ok=True)
