"""Public wallpaper seeds on selective SYSTEM state; never replace user files."""
import os
from pathlib import Path
import stat

ASSETS=Path('/usr/share/backgrounds/petalos-defaults')
STATE=Path('/mnt/system-state/Wallpapers')
NAME='04-petal-drift.png'
DEFAULT=str(STATE/NAME)
FALLBACK=str(ASSETS/NAME)
DIR=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC


def seed(target, assets=ASSETS, *, uid=1000):
    """Add missing supplied PNGs atomically, preserving existing custom files."""
    import secrets
    parent=os.open(target,DIR)
    try:
        info=os.fstat(parent)
        assert info.st_uid==uid and stat.S_IMODE(info.st_mode)==0o700
        for source in sorted(assets.glob('*.png')):
            assert not source.is_symlink() and source.stat().st_size<=16*1024**2
            name=source.name
            try:
                os.stat(name,dir_fd=parent,follow_symlinks=False)
                # A user-managed entry is never read or replaced as root.
                continue
            except FileNotFoundError:pass
            temporary='.petalos-wallpaper-'+secrets.token_hex(12)
            fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
            try:
                with os.fdopen(fd,'wb') as stream:
                    stream.write(source.read_bytes());stream.flush();os.fsync(stream.fileno())
                    if os.geteuid()==0:os.fchown(stream.fileno(),uid,uid)
                # Hard-link publication cannot overwrite a concurrently added file.
                try:os.link(temporary,name,src_dir_fd=parent,dst_dir_fd=parent,follow_symlinks=False)
                except FileExistsError:pass
                os.fsync(parent)
            finally:os.unlink(temporary,dir_fd=parent)
    finally:os.close(parent)
