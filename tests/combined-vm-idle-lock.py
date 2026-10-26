"""Invoke the real idle action with inhibition off and an open Private store."""
from pathlib import Path
import json
import os
import subprocess
import sys
assert os.geteuid() == 0
sys.path.insert(0, '/usr/local/lib/portable')
from desktop_session import environment
import private_storage as p
values = json.load(sys.stdin)
assert p.unlock(values['private'].encode(), raise_errors=True)
pre = ['setpriv', '--reuid=1000', '--regid=1000', '--clear-groups', '--']
env = environment()
state = json.loads(subprocess.check_output(pre+['sudo','-n','--','/usr/local/sbin/portable-storage','status'], env=env))
if state['download_mode']:
    subprocess.run(pre+['sudo','-n','--','/usr/local/sbin/portable-storage','download-toggle'], env=env, check=True, capture_output=True)
# gtklock's daemon inherits stdio; a capture pipe would wait for unlock rather
# than for portable-lock's successful return after the compositor handshake.
r = subprocess.run(pre+['/usr/local/bin/portable-lock','--idle'], env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=35)
checks = {'idle_action_succeeded': r.returncode == 0,
          'idle_action_closed_Private_mapping': not Path('/dev/mapper/portable_data').exists(),
          'graphical_locker_established': subprocess.run(['pgrep','-u','1000','-x','gtklock'], capture_output=True).returncode == 0}
print(json.dumps(checks))
assert all(checks.values())
