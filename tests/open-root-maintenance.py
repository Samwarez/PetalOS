#!/usr/bin/python3
"""Keep authenticated guest maintenance on this SSH stdin, never a listener.

Stage tests/root-maintenance-guest.py at /tmp/petalos-public-maintenance.py
first. The user enters the credential only in the guest's graphical askpass.
"""
import json
import os
from pathlib import Path
import shlex
import termios

state = json.loads(Path(f'/run/user/{os.getuid()}/petalos-encrypted-test.json').read_text())
ssh = state['ssh']
directory = Path.home() / '.local/share/petalos-qemu/ssh'
assert ssh['key'] == str(directory / 'id_ed25519')
assert ssh['known_hosts'] == str(directory / 'known_hosts')
assert ssh.get('user') == 'Petal'
code = '''import os,pathlib,subprocess
pid=subprocess.check_output(['pgrep','-u','1000','-x','xfce4-session'],text=True).strip()
e=dict(x.split('=',1) for x in pathlib.Path('/proc/'+pid+'/environ').read_bytes().decode().split('\\0') if '=' in x)
e['SUDO_ASKPASS']='/usr/local/bin/portable-askpass'
if e.get('XDG_SESSION_TYPE') == 'wayland':
 e.pop('DISPLAY',None);e.pop('XAUTHORITY',None)
os.execvpe('/usr/bin/sudo',['sudo','-A','--','/bin/sh','-c','install -o root -g root -m 600 /tmp/petalos-public-maintenance.py /run/petalos-root-maintenance.py && exec /usr/bin/python3 -I /run/petalos-root-maintenance.py'],e)
'''
if os.isatty(0):
    attributes = termios.tcgetattr(0)
    attributes[3] &= ~(termios.ICANON | termios.ECHO)
    attributes[6][termios.VMIN] = 1
    attributes[6][termios.VTIME] = 0
    termios.tcsetattr(0, termios.TCSANOW, attributes)
command = ['ssh', '-F', '/dev/null', '-T', '-p', '2222', '-i', ssh['key'],
           '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
           '-o', 'StrictHostKeyChecking=yes', '-o', 'HostKeyAlias=petalos-qemu',
           '-o', 'UserKnownHostsFile=' + ssh['known_hosts'],
           '-o', 'GlobalKnownHostsFile=/dev/null', '-o', 'ConnectTimeout=5',
           'Petal@127.0.0.1', 'python3 -c ' + shlex.quote(code)]
os.execvp(command[0], command)
