#!/usr/bin/python3 -I
"""Quiesce a disposable role before deleting a symlink-bearing RAM home."""
import json
import os
import pwd
from pathlib import Path
import select
import subprocess
import sys
import tempfile

sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
assert os.geteuid() == 0
app = 'public-cleanup-fixture'
fixture_uid = 61000
assert fixture_uid not in c.ROLES.values(), 'Fixture UID overlaps an application role.'
try:
    pwd.getpwuid(fixture_uid)
except KeyError:
    pass
else:
    raise AssertionError('Fixture UID already belongs to an account.')
assert subprocess.run(['/usr/bin/pgrep', '-u', str(fixture_uid)],
                      stdout=subprocess.DEVNULL).returncode == 1
c.ROLES[app] = fixture_uid
assert not c.worker_alive(c.read_record(app))
c.reset_ram(app)
report = {}
with tempfile.TemporaryDirectory(prefix='petalos-public-cleanup-', dir='/run') as directory:
    root = Path(directory)
    root.chmod(0o755)
    target = root / 'public-target'
    target.write_text('public cleanup canary')
    home = c.home(app)
    (home / 'hostile-link').symlink_to(root)
    code = '''import os,signal,time
signal.signal(signal.SIGTERM,signal.SIG_IGN)
child=os.fork()
if child:print(str(os.getpid())+' '+str(child),flush=True)
while True:time.sleep(1)
'''
    process = subprocess.Popen(['/usr/bin/setpriv', '--reuid=' + str(fixture_uid),
        '--regid=' + str(fixture_uid), '--clear-groups',
        '--bounding-set=-all', '--no-new-privs', '/usr/bin/python3', '-I', '-c', code],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    pinned = []
    try:
        assert select.select([process.stdout], [], [], 5)[0]
        pids = [int(value) for value in process.stdout.readline().split()]
        assert len(pids) == 2
        pinned = [os.pidfd_open(pid) for pid in pids]
        c.reset_ram(app)
        report['term_ignoring_parent_and_child_stopped'] = all(select.select([fd], [], [], 1)[0] for fd in pinned)
        report['role_ram_home_removed'] = not home.exists()
        report['symlink_target_untouched'] = target.read_text() == 'public cleanup canary'
        process.wait(timeout=5)
    finally:
        for fd in pinned:
            try:
                import signal
                signal.pidfd_send_signal(fd, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.close(fd)
        process.stdout.close()
print(json.dumps(report, sort_keys=True))
assert all(report.values())
