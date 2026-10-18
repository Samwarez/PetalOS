"""Selective settings on encrypted SYSTEM; never opens Private or reads its key."""
import os
from pathlib import Path
import stat
import subprocess

STATE = Path('/mnt/system-state')
FULL = Path('/run/portable-storage/system-volume')
SUBDIR = '.petalos-state'
ENV = {'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LC_ALL':'C.UTF-8'}


def mounted_root(path, root, *, readonly=None):
    try:
        result = subprocess.run(['/usr/bin/findmnt','-n','-o','FSROOT,MAJ:MIN,FSTYPE,OPTIONS','--mountpoint',str(path)],
            capture_output=True,text=True,timeout=5,env=ENV)
        fields=result.stdout.split()
        device=Path('/dev/mapper/portable_system').stat()
        return (result.returncode==0 and len(fields)==4 and fields[0]==root
                and fields[1]==f'{os.major(device.st_rdev)}:{os.minor(device.st_rdev)}'
                and fields[2]=='ext4' and {'nodev','nosuid','noexec'} <= set(fields[3].split(','))
                and (readonly is None or ('ro' in fields[3].split(',')) == readonly))
    except (OSError,ValueError):return False


def ready():
    return (not STATE.is_symlink() and mounted_root(STATE,'/'+SUBDIR)
            and STATE.stat().st_uid==0 and STATE.stat().st_gid==1000
            and stat.S_IMODE(STATE.stat().st_mode)==0o750
            and mounted_root(FULL,'/',readonly=True))


def require():
    if not ready():raise RuntimeError('Encrypted system settings are unavailable.')


def prepare(identity=None):
    assert os.geteuid()==0
    from private_storage import backend, identity as pinned_identity, directory, command
    from compartments import ram_ready
    ram_ready();directory()
    state=identity if identity is not None else pinned_identity()
    backend().verify_mapping(state,'system')
    assert not FULL.is_symlink() and not STATE.is_symlink()
    if ready():return
    FULL.mkdir(mode=0o700,exist_ok=True)
    if not mounted_root(FULL,'/'):
        assert not os.path.ismount(FULL)
        command(['/usr/bin/mount','-o','nodev,nosuid,noexec,noatime','/dev/mapper/portable_system',str(FULL)])
    folder=FULL/SUBDIR
    assert not folder.is_symlink()
    folder.mkdir(mode=0o700,exist_ok=True)
    assert folder.stat().st_uid in (0,1000)
    os.chown(folder,0,1000);folder.chmod(0o750)
    for name in ('Network','Network/Profiles','Desktop','Applications','Applications/TorBrowser'):
        p=folder/name
        assert not any(q.is_symlink() for q in (p,*p.parents))
        p.mkdir(mode=0o700,exist_ok=True)
        assert p.stat().st_uid in (0,1000)
        os.chown(p,1000,1000);p.chmod(0o700)
    STATE.mkdir(mode=0o700,exist_ok=True)
    if not mounted_root(STATE,'/'+SUBDIR,readonly=False):
        assert not os.path.ismount(STATE)
        command(['/usr/bin/mount','--bind',str(folder),str(STATE)])
        command(['/usr/bin/mount','-o','remount,bind,nodev,nosuid,noexec',str(STATE)])
    # Only the selected subdirectory bind remains writable. This changes
    # per-mount flags, not the underlying filesystem's writable bind.
    command(['/usr/bin/mount','-o','remount,bind,ro,nodev,nosuid,noexec',str(FULL)])
    require()


def unmount():
    assert os.geteuid()==0
    from private_storage import command
    if os.path.ismount(STATE):
        assert mounted_root(STATE,'/'+SUBDIR)
        command(['/usr/bin/umount',str(STATE)])
    if os.path.ismount(FULL):
        assert mounted_root(FULL,'/')
        command(['/usr/bin/umount',str(FULL)])


def migrate_from_private():
    """Explicit test/install migration of VPN profiles and validated panel settings.

    Keeps originals. No arbitrary files, personal documents or DATA key included.
    Call only while both stores are unlocked; never as a boot-side copy fallback.
    """
    assert os.geteuid()==0
    require()
    from compartments import private_ready
    private_ready()
    from vpn_profiles import checked_name, read_profile, serialize, atomic_write
    old=Path('/mnt/private/Network');target=STATE/'Network'
    count=0
    candidates=[]
    profiles=old/'Profiles'
    if profiles.is_dir() and not profiles.is_symlink():
        for p in profiles.glob('*.conf'):
            checked_name(p.stem);candidates.append((p,target/'Profiles'/p.name))
    if (old/'wg0.conf').is_file():candidates.append((old/'wg0.conf',target/'wg0.conf'))
    for source,destination in candidates:
        profile=read_profile(source)
        # Never replace a system-store profile without a separate user action.
        assert not destination.exists() and not destination.is_symlink()
        atomic_write(destination,serialize(profile),1000);count+=1
    marker=old/'selected-profile'
    if marker.exists():
        assert not marker.is_symlink() and marker.stat().st_size<=65
        name=checked_name(marker.read_text().strip())
        assert (target/'Profiles'/(name+'.conf')).is_file()
        atomic_write(target/'selected-profile',name+'\n',1000)
    settings=Path('/mnt/private/PortableSettings/desktop-settings.tar')
    copied_settings=False
    if settings.exists():
        from desktop_settings import validate_archive
        fd=os.open(settings,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as source:
            assert stat.S_ISREG(os.fstat(source.fileno()).st_mode)
            validate_archive(source);source.seek(0)
            destination=STATE/'Desktop/desktop-settings.tar'
            assert not destination.exists() and not destination.is_symlink()
            with destination.open('xb') as output:
                import shutil
                shutil.copyfileobj(source,output,1024**2);output.flush();os.fsync(output.fileno())
            os.chown(destination,1000,1000);destination.chmod(0o600)
            copied_settings=True
    return {'vpn_profiles_migrated':count,'desktop_settings_migrated':copied_settings}
