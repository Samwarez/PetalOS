#!/usr/bin/python3 -I
"""Check real Qt sidebar defaults and access boundaries in the KeePass role.

Close KeePassXC first. Only its disposable RAM app home is reset; Documents
and any saved database remain outside that home. Run once with Private open
and once with it closed to check both actual storage states.
"""
import json
import os
import subprocess
import sys

assert os.geteuid() == 0
sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c

app = 'offline-keepassxc'
probe = '''from pathlib import Path
import json,socket,sys
from PyQt5.QtWidgets import QApplication,QFileDialog,QListView
available=sys.argv[1]=='open'
app=QApplication([])
dialog=QFileDialog()
sidebar=dialog.findChild(QListView,'sidebar')
urls=[url.toString() for url in dialog.sidebarUrls()]
labels=[sidebar.model().data(sidebar.model().index(i,0)) for i in range(sidebar.model().rowCount())]
private=Path.home()/'Private'
checks={
 'RAM_Documents_in_actual_sidebar':(Path.home()/'Documents').as_uri() in urls,
 'Private_sidebar_matches_storage_state':(private.as_uri() in urls)==available,
 'Private_label_matches_storage_state':('Private' in labels)==available,
 'Private_navigation_matches_storage_state':private.is_dir()==available,
 'sibling_app_folder_hidden':not Path('/mnt/private/Documents/geany').exists(),
 'SYSTEM_hidden':not Path('/mnt/system-state').exists(),
}
for family,key in ((socket.AF_INET,'IPv4_denied'),(socket.AF_INET6,'IPv6_denied')):
 try:s=socket.socket(family);s.close();checks[key]=False
 except PermissionError:checks[key]=True
print(json.dumps({'checks':checks,'sidebar_labels':labels}))
assert all(checks.values())
'''
# A user may launch the app just after screen unlock. Serialize the entire
# reset/probe with the normal broker; never race a new GUI's RAM home.
with c.action_lock(app):
    assert not c.worker_alive(c.read_record(app)), 'Close KeePassXC before this check.'
    available = c.private_available()
    c.reset_ram(app)
    c.home(app)
    c.storage_setup(app)
    result = subprocess.run(c.sandbox(app, [
        '/usr/bin/aa-exec', '-p', 'petalos_offline_keepassxc', '--',
        '/usr/bin/python3', '-I', '-c', probe, 'open' if available else 'closed',
    ], environment={'QT_QPA_PLATFORM': 'offscreen'}),
        capture_output=True, text=True, timeout=20)
report = {'Private_open': available, 'exit': result.returncode,
          'result': json.loads(result.stdout) if result.stdout.strip() else None}
print(json.dumps(report))
assert result.returncode == 0, 'Qt chooser regression failed; raw errors suppressed.'
