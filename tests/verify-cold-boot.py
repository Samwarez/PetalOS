#!/usr/bin/env python3
"""Bounded, secret-free checks after SYSTEM-only boot unlock of the test VM."""
from pathlib import Path
import importlib.util
import json
import shlex

spec = importlib.util.spec_from_file_location('guest', Path(__file__).with_name('guest-ssh.py'))
guest = importlib.util.module_from_spec(spec); spec.loader.exec_module(guest)
source = '''
from pathlib import Path
import json, os, subprocess
def active(name):
    return subprocess.run(['pgrep','-x',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
def mounted(path):
    return subprocess.run(['findmnt','--mountpoint',path],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
arguments=Path('/proc/cmdline').read_text().split()
checks={
    'Petal UID 1000':os.getuid()==1000 and Path.home().name=='Petal',
    'memory allocation zeroing enabled':arguments.count('init_on_alloc=1')==1,
    'freed memory zeroing enabled':arguments.count('init_on_free=1')==1,
    'RAM live boot': 'toram' in arguments and 'swap=false' in arguments,
    'native compositor running':active('labwc'),
    'XFCE session running':active('xfce4-session'),
    'native wallpaper running':active('swaybg'),
    'idle monitor running':active('swayidle'),
    'Xwayland absent':not active('Xwayland'),
    'Private mapping closed':not Path('/dev/mapper/portable_data').exists(),
    'Private unmounted':not mounted('/mnt/private'),
    'selected SYSTEM state mounted':mounted('/mnt/system-state'),
    'SYSTEM settings link':(Path.home()/'SystemSettings').is_symlink(),
    'no swap':len(Path('/proc/swaps').read_text().splitlines())==1,
}
print(json.dumps(checks))
raise SystemExit(0 if all(checks.values()) else 1)
'''
result = guest.execute('python3 -c '+shlex.quote(source), timeout=20)
if result.stdout:
    for name, passed in json.loads(result.stdout).items():
        print(('PASS' if passed else 'FAIL')+': '+name)
else:
    print('Cold-boot checks unavailable; no guest diagnostics or credentials printed.')
raise SystemExit(result.returncode)
