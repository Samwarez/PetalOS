"""Root-only mount setup before bwrap; process UIDs and app boundaries stay distinct."""
import ctypes
import os
from pathlib import Path
import subprocess
import sys


def main():
    sys.path.insert(0, '/usr/local/lib/portable')
    import compartments as c
    assert os.geteuid() == 0 and len(sys.argv) > 3
    app = sys.argv[1]
    command = sys.argv[2:]
    assert app in c.ROLES and command[0] == '/usr/bin/bwrap'
    expected = set()
    if app in c.OFFLINE or app in ('browser', 'transmission', 'pan', 'amule', 'sabnzbd'):
        category = 'Documents' if app in c.OFFLINE else 'Downloads'
        name = c.OFFLINE[app][0] if app in c.OFFLINE else ('TorBrowser' if app == 'browser' else app)
        expected = {Path('/home/Petal')/category/name, c.PRIVATE/category/name}
    binds = []
    for i, item in enumerate(command[:-2]):
        if item == '--bind' and Path(command[i+1]) in expected:
            binds.append(i+1)
    if binds:
        base = c.protected(Path('/run/portable-content-views'))
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.unshare(0x00020000) != 0:  # CLONE_NEWNS, before creating threads
            raise OSError(ctypes.get_errno(), 'Cannot isolate content mounts')
        c.run(['mount', '--make-rprivate', '/'])
        c.run(['mount', '-t', 'tmpfs', '-o', 'mode=0700,nodev,nosuid,size=1M', 'content-views', str(base)])
        for number, index in enumerate(binds):
            source = Path(command[index])
            # Walk without following symlinks, pin the delegated directory, and
            # pass only that inode to mount. Its contents remain the same files.
            fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
            try:
                for component in source.parts[1:]:
                    child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    os.close(fd); fd = child
                assert os.fstat(fd).st_uid == 1000
                target = base/str(number); target.mkdir(mode=0o700)
                # util-linux 2.41: filesystem ID 1000 is presented as the role
                # ID. Confirm the result instead of trusting option parsing.
                c.run(['mount', '--no-canonicalize', '--bind', '-o', 'X-mount.idmap=1000:' + str(c.ROLES[app]) + ':1',
                       '/proc/self/fd/' + str(fd), str(target)], pass_fds=(fd,))
                assert target.stat().st_uid == c.ROLES[app] and target.stat().st_gid == c.ROLES[app]
                command[index] = str(target)
            finally:
                os.close(fd)
    # All mapped mounts disappear with this private namespace when bwrap exits.
    os.execv(command[0], command)


if __name__ == '__main__':
    main()
