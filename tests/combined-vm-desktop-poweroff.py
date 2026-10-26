"""Request normal XFCE shutdown in the active desktop, with no unsaved apps."""
from pathlib import Path
import json
import os
import subprocess
import sys
assert os.geteuid() == 0
assert not Path('/dev/mapper/portable_data').exists()
sys.path.insert(0, '/usr/local/lib/portable')
from desktop_session import environment
subprocess.Popen(['setpriv', '--reuid=1000', '--regid=1000', '--clear-groups', '--',
    'xfce4-session-logout', '--halt', '--fast'], env=environment(),
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    start_new_session=True)
print(json.dumps({'normal_XFCE_desktop_shutdown_requested': True}))
