#!/usr/bin/python3 -I
"""QEMU: write public canaries in each app's delegated encrypted download dir."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
assert os.geteuid() == 0
assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
c.private_ready()
for app in ('transmission', 'pan', 'amule', 'sabnzbd'):
    c.home(app); c.storage_setup(app)
    name = '.public-write-probe-' + secrets.token_hex(16)
    code = '''import json,os,socket,sys
from pathlib import Path
app,name=sys.argv[1:]
root=Path('/mnt/private/Downloads')/app
path=root/name
try:
 path.write_text('public download permission fixture')
 writable=path.read_text()=='public download permission fixture'
finally:path.unlink(missing_ok=True)
print(json.dumps({'app':app,'real_uid':os.getuid(), 'own_download_writable':writable,
 'private_alias_present':Path.home().joinpath('Private').is_symlink(),
 'downloads_alias_matches':Path.home().joinpath('Downloads').resolve()==Path('/mnt/ram/Downloads')/app,
 'bookmarked':('file://'+str(root)) in Path.home().joinpath('.config/gtk-3.0/bookmarks').read_text(),
 'other_app_hidden':not Path('/mnt/private/Downloads').joinpath('pan' if app!='pan' else 'transmission').exists(),
 'vpn_profiles_hidden':not Path('/mnt/private/Network').exists(),
 'parent_home_hidden':not Path('/home/Petal').exists()}))
'''
    result = subprocess.run(c.sandbox(app, ['/usr/bin/aa-exec', '-p', 'petalos_' + app,
                            '--', '/usr/bin/python3', '-I', '-c', code, app, name]),
                            capture_output=True, text=True, timeout=15)
    if result.returncode:
        print(json.dumps({'app': app, 'probe_exit': result.returncode}))
        raise RuntimeError('Download fixture failed; raw output suppressed.')
    report = json.loads(result.stdout)
    print(json.dumps(report, sort_keys=True))
    assert report['real_uid'] == c.ROLES[app]
    assert all(value is True for key, value in report.items() if key not in ('app', 'real_uid'))
