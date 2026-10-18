"""Keep descriptor-based media out of Parole's saved playlist."""
import os
import subprocess
import sys


def main():
    assert os.getuid() == 955 and sys.argv[1] == '/usr/bin/parole.portable-real'
    subprocess.run(['/usr/bin/xfconf-query', '-c', 'parole', '-p', '/playlist/remember-playlist',
                    '-n', '-t', 'bool', '-s', 'false'], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
    os.execv(sys.argv[1], sys.argv[1:])


if __name__ == '__main__':
    main()
