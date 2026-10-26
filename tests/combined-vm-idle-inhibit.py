"""Download mode must inhibit only idle locking, while Private is open."""
from pathlib import Path
import json
import os
import subprocess
import sys
assert os.geteuid() == 0
sys.path.insert(0, '/usr/local/lib/portable')
from desktop_session import environment
import private_storage as p
assert p.backend().is_unlocked(p.identity())
pre = ['setpriv', '--reuid=1000', '--regid=1000', '--clear-groups', '--']
env = environment()
state = json.loads(subprocess.check_output(pre+['sudo','-n','--','/usr/local/sbin/portable-storage','status'], env=env))
if not state['download_mode']:
    subprocess.run(pre+['sudo','-n','--','/usr/local/sbin/portable-storage','download-toggle'], env=env, check=True, capture_output=True)
r = subprocess.run(pre+['/usr/local/bin/portable-lock','--idle'], env=env, capture_output=True, timeout=30)
checks = {'idle_action_returns_cleanly': r.returncode == 0,
          'download_mode_keeps_Private_open': p.backend().is_unlocked(p.identity()),
          'download_mode_does_not_create_screen_locker': subprocess.run(['pgrep','-u','1000','-x','gtklock'], capture_output=True).returncode == 1}
print(json.dumps(checks))
assert all(checks.values())
