"""Use the desktop's approved launch interface, then verify real worker labels."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
assert os.geteuid() == 0
sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
from desktop_session import environment
pre = ['setpriv', '--reuid=1000', '--regid=1000', '--clear-groups', '--']
out = {}
for family in ('transmission', 'pan', 'amule', 'sabnzbd', 'tor'):
    started = time.monotonic()
    result = subprocess.run(pre+['sudo', '-n', '--', '/usr/local/sbin/portable-compartment', 'launch', family],
                            env=environment(), capture_output=True, timeout=240)
    out[family] = {'approved_launch_succeeded': result.returncode == 0,
                   'seconds': round(time.monotonic()-started, 2)}
    assert result.returncode == 0, family+' launch failed; output suppressed'
for app in ('transmission', 'pan', 'amule', 'sabnzbd', 'sab-viewer', 'tor', 'browser'):
    record = c.read_record(app)
    result = {'ready': record.get('phase') == 'ready', 'worker_alive': c.worker_alive(record)}
    uid = c.ROLES[app]
    labels = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            if proc.stat().st_uid == uid:
                labels.append((proc/'attr/current').read_text().strip())
        except (FileNotFoundError, ProcessLookupError, PermissionError):pass
    profile = {'tor': 'petalos_isolated_tor', 'sab-viewer': 'petalos_sab_viewer'}.get(app, 'petalos_'+app)
    # The application is profiled; namespace-local D-Bus/accessibility helpers
    # are separate processes. Do not misreport those helpers as app denials.
    result['main_application_profile_enforced'] = profile+' (enforce)' in labels
    out[app] = {**out.get(app, {}), **result,
                'namespace_helper_processes_without_AppArmor_label': labels.count('unconfined')}
    assert all(result.values())
print(json.dumps(out))
