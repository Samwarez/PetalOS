#!/usr/bin/python3 -I
"""Read-only shutdown authorization checks; never requests shutdown/reboot."""
from pathlib import Path
import json
import os
import subprocess


def check(action, subject):
    result = subprocess.run(['/usr/bin/pkcheck', '--action-id', action,
                             '--process', subject], capture_output=True, timeout=8)
    assert result.returncode in (0, 2), 'Authorization query failed.'
    return result.returncode


def main():
    assert os.geteuid() == 0
    pid = subprocess.check_output(['/usr/bin/pgrep', '-u', '1000', '-x',
                                   'xfce4-session'], text=True).strip()
    assert pid.isdecimal(), 'One desktop session is required.'
    start = Path('/proc', pid, 'stat').read_text().split(') ')[1].split()[19]
    subject = pid + ',' + start + ',1000'
    report = {}
    for name in ('power-off', 'power-off-multiple-sessions', 'reboot',
                 'reboot-multiple-sessions', 'suspend', 'suspend-multiple-sessions',
                 'inhibit-delay-sleep', 'inhibit-handle-lid-switch'):
        report[name + '_local_allowed'] = check('org.freedesktop.login1.' + name, subject) == 0
    for action in ('org.freedesktop.login1.power-off-ignore-inhibit',
                   'org.freedesktop.login1.suspend-ignore-inhibit',
                   'org.freedesktop.policykit.exec',
                   'org.freedesktop.systemd1.manage-units',
                   'org.freedesktop.udisks2.modify-device',
                   'org.freedesktop.NetworkManager.settings.modify.system'):
        report[action + '_still_requires_auth'] = check(action, subject) == 2
    # This probe is run from remote maintenance. Its children must not receive
    # the active-local-desktop exception, including a sandbox application UID.
    remote_probe = '''import os,subprocess
from pathlib import Path
pid=str(os.getpid())
start=Path('/proc/self/stat').read_text().split(') ')[1].split()[19]
subject=pid+','+start+','+str(os.getuid())
r=subprocess.run(['/usr/bin/pkcheck','--action-id',
 'org.freedesktop.login1.power-off','--process',subject],capture_output=True)
raise SystemExit(r.returncode)
'''
    for uid in (1000, 944):
        result = subprocess.run(['/usr/bin/setpriv', '--reuid=' + str(uid),
            '--regid=' + str(uid), '--clear-groups', '/usr/bin/python3',
            '-I', '-c', remote_probe],
            capture_output=True, timeout=8)
        report['remote_uid_' + str(uid) + '_requires_auth'] = result.returncode == 2
    print(json.dumps(report, sort_keys=True))
    assert all(report.values()), 'Shutdown authorization boundary check failed.'


if __name__ == '__main__':
    main()
