"""Account credentials only in encrypted SYSTEM or RAM; never print payloads."""
from contextlib import contextmanager
from pathlib import Path
import os
import re
import secrets
import stat
import string
import subprocess
import tempfile

ACCOUNT = 'Petal'
ADMIN_HASH_FILE = 'root-admin.hash'
HASH_PATTERN = re.compile(rb'\$6\$rounds=100000\$[A-Za-z0-9]{16}\$[./A-Za-z0-9]{86}\n?\Z')

def validate_hash(value):
    if not HASH_PATTERN.fullmatch(value):
        raise RuntimeError('The protected account credential is invalid.')
    return value.rstrip(b'\n')

def encode_secret(secret):
    if not secret or len(secret) > 4096 or any(v in secret for v in (b'\n', b'\r', b'\x00')):
        raise RuntimeError('The supplied account credential is invalid.')
    salt = 'rounds=100000$' + ''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(16))
    result = subprocess.run(['/usr/bin/openssl', 'passwd', '-6', '-salt', salt, '-stdin'],
        input=secret+b'\n', capture_output=True, timeout=10)
    if result.returncode:
        raise RuntimeError('Could not prepare the account credential.')
    return validate_hash(result.stdout)

@contextmanager
def system_filesystem(write=False):
    if os.geteuid() != 0:
        raise RuntimeError('Account setup requires administration privileges.')
    device = Path('/dev/mapper/portable_system')
    for tag, expected in [('LABEL', 'LIVE_SYSTEM'), ('TYPE', 'ext4')]:
        value = subprocess.check_output(['/usr/sbin/blkid', '-s', tag, '-o', 'value', str(device)], text=True).strip()
        if value != expected:
            raise RuntimeError('Unexpected encrypted SYSTEM filesystem.')
    info = device.stat()
    slaves = list(Path(f'/sys/dev/block/{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}/slaves').iterdir())
    if len(slaves) != 1:
        raise RuntimeError('Unexpected SYSTEM mapper backing device.')
    label = subprocess.check_output(['/usr/sbin/blkid', '-s', 'LABEL', '-o', 'value', '/dev/'+slaves[0].name], text=True).strip()
    if label != 'PORTABLE_SYSTEM':
        raise RuntimeError('Unexpected encrypted SYSTEM backing partition.')
    from system_state import FULL, mounted_root
    if not write and mounted_root(FULL, '/'):
        # Reuse the verified full SYSTEM mount behind its root-only RAM parent.
        # Never mount the same active filesystem with conflicting options.
        yield FULL
        return
    directory = Path(tempfile.mkdtemp(prefix='petal-auth-', dir='/run'))
    mounted = False
    try:
        options = ('rw' if write else 'ro,noload')+',nodev,nosuid,noexec,noatime'
        subprocess.run(['/usr/bin/mount', '-t', 'ext4', '-o', options, str(device), str(directory)],
                       check=True, capture_output=True, timeout=10)
        mounted = True
        actual = subprocess.check_output(['/usr/bin/findmnt','-n','-o','SOURCE','--mountpoint',str(directory)], text=True).strip()
        if Path(actual).stat().st_rdev != device.stat().st_rdev:
            raise RuntimeError('Unexpected SYSTEM mount identity.')
        yield directory
    finally:
        if mounted:
            subprocess.run(['/usr/bin/umount',str(directory)],check=True,capture_output=True,timeout=10)
        if not os.path.ismount(directory):directory.rmdir()

def store_hash(value):
    value = validate_hash(value)
    with system_filesystem(write=True) as system:
        directory = system/'.petalos-auth'
        if directory.is_symlink():raise RuntimeError('Unsafe credential directory.')
        directory.mkdir(mode=0o700,exist_ok=True)
        info = directory.stat()
        if info.st_uid != 0 or info.st_mode & 0o077:raise RuntimeError('Unsafe credential directory.')
        target = directory/ADMIN_HASH_FILE
        if target.is_symlink():raise RuntimeError('Unsafe credential destination.')
        fd, name = tempfile.mkstemp(prefix='.credential-',dir=directory)
        temp = Path(name)
        try:
            with os.fdopen(fd,'wb') as output:
                output.write(value+b'\n');output.flush();os.fsync(output.fileno())
            os.replace(temp,target)
            fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
        finally:temp.unlink(missing_ok=True)

def load_hash():
    with system_filesystem() as system:
        directory=system/'.petalos-auth'
        if directory.is_symlink():raise RuntimeError('Unsafe credential directory.')
        info=directory.stat()
        if info.st_uid!=0 or info.st_mode&0o077:raise RuntimeError('Unsafe credential directory.')
        fd=os.open(directory/ADMIN_HASH_FILE,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o077 or info.st_size>256:
                raise RuntimeError('Unsafe credential file.')
            return validate_hash(stream.read(257))

def apply_hash(login,value):
    if login not in ('Petal','user'):raise RuntimeError('Unexpected live account.')
    subprocess.run(['/usr/sbin/chpasswd','-e'],input=login.encode()+b':'+validate_hash(value)+b'\n',
                   check=True,capture_output=True,timeout=10)

def apply_admin_hash(value):
    subprocess.run(['/usr/sbin/chpasswd','-e'],input=b'root:'+validate_hash(value)+b'\n',
                   check=True,capture_output=True,timeout=10)

def require_sudo_auth(login=ACCOUNT):
    if login not in ('Petal','user'):raise RuntimeError('Unexpected live account.')
    target=Path('/etc/sudoers.d/live')
    if target.is_symlink():raise RuntimeError('Unsafe live sudo policy.')
    content=(f'{login} ALL=(ALL:ALL) PASSWD: ALL\n'
             f'Defaults:{login} rootpw, timestamp_type=tty, timestamp_timeout=0\n')
    fd,name=tempfile.mkstemp(prefix='.petal-sudo-',dir=target.parent)
    temp=Path(name)
    try:
        with os.fdopen(fd,'w') as output:output.write(content);output.flush();os.fsync(output.fileno())
        temp.chmod(0o440)
        subprocess.run(['/usr/sbin/visudo','-c','-f',str(temp)],check=True,capture_output=True,timeout=5)
        os.replace(temp,target)
    finally:temp.unlink(missing_ok=True)
