"""Open only broker-mounted media before dropping to the offline player UID."""
import os
import re
import stat
import sys


def main():
    assert os.geteuid() == 0
    split = sys.argv.index('--')
    paths = sys.argv[1:split]
    command = sys.argv[split + 1:]
    assert 1 <= len(paths) <= 32
    assert command[:5] == ['/usr/bin/setpriv', '--reuid', '955', '--regid', '955']
    assert '/usr/bin/parole.portable-real' in command
    for path in paths:
        assert re.fullmatch(r'/run/petalos-opened/item-[0-9]+\.[A-Za-z0-9]{1,16}', path)
        assert path in command
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        assert stat.S_ISREG(os.fstat(fd).st_mode)
        os.set_inheritable(fd, True)
        command = ['fd://' + str(fd) if arg == path else arg for arg in command]
    os.execv(command[0], command)


if __name__ == '__main__':
    main()
