"""Executable wipe fixture for explicitly selected regular files, never disks.

This is development tooling. It does not certify flash or physical-media erasure.
"""
from pathlib import Path
import fcntl
import hashlib
import os
import stat
import subprocess
from .portable import tool_command, tool_environment

from . import InstallerError
from .plans import WIPE_LIMITS, WIPE_METHODS
from .releases import require


def wipe_image(path, method, confirmation, progress=lambda event: None):
    path = Path(path).absolute()
    require(method in WIPE_METHODS, 'Unknown wipe method.')
    require(confirmation == 'WIPE ' + str(path), 'Confirmation must be WIPE followed by the absolute image path.')
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Image paths must not contain symbolic links.')
    before = path.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid() and before.st_nlink == 1,
            'Only an owned, singly linked regular image file is accepted; block devices are refused.')
    require(before.st_size > 0, 'Image is empty.')
    idle = subprocess.run(tool_command(['/usr/bin/fuser', str(path)]), env=tool_environment(), capture_output=True, timeout=10)
    require(idle.returncode == 1, 'Image is already open by a process, or its idle state could not be established.')
    for backing in Path('/sys/block').glob('loop*/loop/backing_file'):
        try:
            require(Path(backing.read_text().strip()).resolve() != path.resolve(),
                    'Refused an image attached to a loop device.')
        except PermissionError:
            raise InstallerError('Could not establish loop-device state.') from None
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    lockfd = None
    keys_removed = False
    try:
        # cryptsetup takes its own flock on the image. A separate coordinator
        # lock avoids deadlocking its child while serializing our whole wipe.
        lockpath = path.parent / ('.petalos-image-wipe-' + str(before.st_dev) + '-' + str(before.st_ino) + '.lock')
        lockfd = os.open(lockpath, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        lockinfo = os.fstat(lockfd)
        require(stat.S_ISREG(lockinfo.st_mode) and lockinfo.st_uid == os.geteuid() and lockinfo.st_nlink == 1
                and not lockinfo.st_mode & 0o077, 'Image coordinator lock is unsafe.')
        fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        current = os.fstat(fd)
        require((current.st_dev, current.st_ino, current.st_size, current.st_nlink) ==
                (before.st_dev, before.st_ino, before.st_size, 1), 'Image identity changed.')
        if method != 'random':
            # /proc/self/fd pins the already-open inode across cryptsetup calls.
            pinned = '/proc/self/fd/' + str(fd)
            def crypt(*args):
                try:
                    result = subprocess.run(tool_command(['/usr/sbin/cryptsetup', *args, pinned]),
                        env=tool_environment(), capture_output=True, pass_fds=(fd,), timeout=60)
                except (OSError, subprocess.TimeoutExpired):
                    raise InstallerError('Image keyslot operation failed or timed out.') from None
                require(result.returncode == 0, 'Image LUKS operation failed; raw output suppressed.')
                return result.stdout
            import json
            header = json.loads(crypt('luksDump', '--dump-json-metadata'))
            require(header.get('keyslots') and all(s.get('type') == 'luks2' for s in header['keyslots'].values()),
                    'Expected active LUKS2 keyslots in this single-volume image.')
            crypt('erase', '--batch-mode')
            os.fsync(fd)
            keys_removed = True
            after = json.loads(crypt('luksDump', '--dump-json-metadata'))
            require(not after.get('keyslots'), 'Keyslot removal did not verify.')
            progress({'stage': 'keyslots-removed', 'keyslots_removed': True})
        written = hashlib.sha256()
        count = 0
        if method != 'keys-only':
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.lseek(fd, 0, os.SEEK_SET)
            while count < before.st_size:
                chunk = os.urandom(min(1024**2, before.st_size - count))
                view = memoryview(chunk)
                while view:
                    amount = os.write(fd, view)
                    require(amount > 0, 'Image write stopped before completion.')
                    view = view[amount:]
                written.update(chunk)
                count += len(chunk)
                if count % (16 * 1024**2) == 0 or count == before.st_size:
                    os.fsync(fd)
                    progress({'stage': 'random-fill', 'bytes': count, 'total': before.st_size,
                              'keyslots_removed': keys_removed})
            os.fsync(fd)
            if hasattr(os, 'posix_fadvise'):
                os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
            os.lseek(fd, 0, os.SEEK_SET)
            actual = hashlib.sha256()
            checked = 0
            while chunk := os.read(fd, 1024**2):
                actual.update(chunk)
                checked += len(chunk)
            require(checked == before.st_size and actual.digest() == written.digest(),
                    'Random-fill readback verification failed.')
        require(os.fstat(fd).st_size == before.st_size, 'Image size changed during wiping.')
        return {'stage': 'complete', 'scope': 'regular-image-fixture-only',
                'keyslots_removed': keys_removed, 'random_fill_verified': method != 'keys-only',
                'bytes': count, 'limits': WIPE_LIMITS}
    except BaseException:
        progress({'stage': 'incomplete', 'keyslots_removed': keys_removed, 'random_fill_verified': False})
        raise
    finally:
        os.close(fd)
        if lockfd is not None:
            os.close(lockfd)
