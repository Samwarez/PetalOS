#!/usr/bin/env python3
"""Graphically authenticated RAM-only QEMU maintenance in the main network ns."""
import importlib.util
import os
from pathlib import Path
import shlex
import sys
import termios

spec = importlib.util.spec_from_file_location('hardware_ssh', Path(__file__).with_name('hardware-guest-ssh.py'))
ssh = importlib.util.module_from_spec(spec); spec.loader.exec_module(ssh)
code = '''import os,pathlib,subprocess
pid=subprocess.check_output(['pgrep','-u','1000','-x','xfce4-session'],text=True).strip()
e=dict(x.split('=',1) for x in pathlib.Path('/proc/'+pid+'/environ').read_bytes().decode().split('\\0') if '=' in x)
e['SUDO_ASKPASS']='/usr/local/bin/portable-askpass'
e.pop('DISPLAY',None);e.pop('XAUTHORITY',None)
os.execvpe('/usr/bin/sudo',['sudo','-A','--','/usr/bin/nsenter','--target','1','--net','--mount','--','/bin/sh','-c','install -o root -g root -m 600 /tmp/petalos-public-maintenance.py /run/petalos-root-maintenance.py && exec /usr/bin/python3 -I /run/petalos-root-maintenance.py'],e)
'''
if os.isatty(0):
    attributes = termios.tcgetattr(0)
    attributes[3] &= ~(termios.ICANON | termios.ECHO)
    attributes[6][termios.VMIN] = 1; attributes[6][termios.VTIME] = 0
    termios.tcsetattr(0, termios.TCSANOW, attributes)
assert sys.argv[1:] in ([], ['--physical'])
command = [*ssh.arguments(physical=sys.argv[1:] == ['--physical']), 'python3 -c ' + shlex.quote(code)]
os.execvp(command[0], command)
