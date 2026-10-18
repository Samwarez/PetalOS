#!/usr/bin/python3
"""Query active QEMU desktop authorization without requesting any privilege."""
import json
import os
from pathlib import Path
import subprocess


def main():
    assert os.getuid() == 1000
    assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
    active = False
    sessions = subprocess.check_output(['loginctl', 'list-sessions', '--no-legend'], text=True).splitlines()
    for line in sessions:
        session = line.split()[0]
        fields = subprocess.check_output(['loginctl', 'show-session', session, '-p', 'Name', '-p', 'Type', '-p', 'Active'], text=True).splitlines()
        values = dict(x.split('=', 1) for x in fields if '=' in x)
        if values.get('Name') == 'Petal' and values.get('Type') == 'x11' and values.get('Active') == 'yes':
            active = True
    assert active, 'Unlock the test desktop before querying its permissions.'
    result = {'desktop_active': active, 'blanket_live_rule_removed': not Path('/usr/share/polkit-1/rules.d/sudo_on_live.rules').exists()}
    subjects = []
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid == 1000 and (process / 'comm').read_text().strip() == 'xfce4-session':
                start = (process / 'stat').read_text().split(') ')[1].split()[19]
                subjects.append(process.name + ',' + start + ',1000')
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            pass
    assert len(subjects) == 1, 'Unexpected desktop process inventory.'
    for action in ('org.freedesktop.policykit.exec', 'org.freedesktop.systemd1.manage-units', 'org.freedesktop.udisks2.modify-device', 'org.freedesktop.NetworkManager.settings.modify.system'):
        check = subprocess.run(['pkcheck', '--action-id', action, '--process', subjects[0]], capture_output=True, timeout=5, env={**os.environ, 'LC_ALL': 'C'})
        result[action + '_needs_auth'] = check.returncode == 2 and b'requires authentication' in check.stderr
    print(json.dumps(result, sort_keys=True))
    assert all(result.values())


if __name__ == '__main__':
    main()
