#!/usr/bin/python3 -I
"""Bounded read-only ThinkPad lid/resume observer, independent of SSH survival.

Stage in a root-only RAM directory with qt-file-chooser-guest.py. Start while
Private is unlocked, then have the user close/reopen the lid and unlock with
SYSTEM. This helper never requests sleep, unlocks storage or reconnects VPN.
"""
from pathlib import Path
import json
import os
import re
import subprocess
import sys
import time

ROOT = Path('/run/petalos-hardware-resume-test')
RESULT = Path('/tmp/petalos-hardware-suspend-result.json')


def command(args, timeout=15):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def kernel_sleep_counts():
    text = command(['journalctl', '-b', '-k', '--no-pager', '-o', 'cat']).stdout
    return {'entries': len(re.findall(r'PM: suspend entry', text)),
            'exits': len(re.findall(r'PM: suspend exit', text)),
            'GPU_hangs': len(re.findall(r'GPU HANG|GPU reset|amdgpu.*timeout|ring.*timeout', text, re.I)),
            'storage_errors': len(re.findall(r'I/O error|Buffer I/O', text, re.I))}


def state():
    return {'Private_mapping': Path('/dev/mapper/portable_data').exists(),
            'lid_closed': any('closed' in p.read_text() for p in
                              Path('/proc/acpi/button/lid').glob('*/state')),
            'locker_running': command(['pgrep', '-u', '1000', '-x', 'gtklock'], 5).returncode == 0}


report = {'phase': 'starting', 'events': []}
try:
    assert os.geteuid() == 0 and sys.argv[1:] == []
    assert Path('/sys/class/dmi/id/product_name').read_text().strip() == '21CQCTO1WW'
    assert ROOT.stat().st_uid == 0 and ROOT.stat().st_mode & 0o077 == 0
    sys.path.insert(0, '/usr/local/lib/portable')
    import compartments as c
    import system_state
    c.ram_ready()
    assert c.private_available(), 'Begin this test with Private open.'
    initial = kernel_sleep_counts()
    began = time.clock_gettime(time.CLOCK_BOOTTIME)
    original_gap = began - time.monotonic()
    report['Private_initially_open'] = True
    (ROOT/'ready').touch(mode=0o600, exist_ok=False)
    last = None
    suspended = False
    locker_seen = False
    while time.clock_gettime(time.CLOCK_BOOTTIME) - began < 600:
        now = time.clock_gettime(time.CLOCK_BOOTTIME)
        current = state()
        sleep_seconds = now - time.monotonic() - original_gap
        if sleep_seconds >= 2 and not suspended:
            report['last_observation_before_detected_suspend'] = last
            report['first_observation_after_suspend'] = current
            suspended = True
        locker_seen |= current['locker_running']
        if current != last and len(report['events']) < 64:
            report['events'].append(dict(current, elapsed=round(now-began, 2)))
        last = current
        if suspended and locker_seen and not current['locker_running'] and not current['lid_closed']:
            time.sleep(3)
            report['phase'] = 'resumed_and_desktop_unlocked'
            break
        time.sleep(.5)
    else:
        report['phase'] = 'timed_out_waiting_for_suspend_and_unlock'
    final = kernel_sleep_counts()
    report['kernel_event_deltas'] = {k: final[k]-initial[k] for k in final}
    report['suspend_time_observed_seconds'] = round(
        time.clock_gettime(time.CLOCK_BOOTTIME)-time.monotonic()-original_gap, 2)
    report['locker_observed'] = locker_seen
    report['Private_mapping_closed_after_resume'] = not Path('/dev/mapper/portable_data').exists()
    report['Private_unmounted_after_resume'] = command([
        'findmnt', '-n', '--mountpoint', '/mnt/private']).returncode != 0
    report['SYSTEM_state_ready'] = system_state.ready()
    report['no_swap'] = len(Path('/proc/swaps').read_text().splitlines()) == 1
    report['desktop_components_running'] = {name: command([
        'pgrep', '-u', '1000', '-x', name], 5).returncode == 0
        for name in ('labwc', 'xfce4-panel', 'swaybg', 'conky')}
    report['no_failed_units'] = not command([
        'systemctl', '--failed', '--no-legend', '--plain']).stdout.strip()
    firewall = json.loads(command(['/usr/sbin/nft', '-j', 'list', 'table', 'inet', 'portable_vpn']).stdout)
    policies = {x['chain']['name']: x['chain'].get('policy') for x in firewall['nftables'] if 'chain' in x}
    report['firewall_default_drop'] = all(policies.get(n) == 'drop' for n in ('input', 'output', 'forward'))
    if report['phase'] == 'resumed_and_desktop_unlocked' and report['Private_mapping_closed_after_resume']:
        result = command(['/usr/bin/python3', '-I', str(ROOT/'qt-file-chooser-guest.py')], 30)
        report['locked_Private_Qt_sidebar_fixture'] = {
            'exit': result.returncode,
            'result': json.loads(result.stdout) if result.stdout.strip() else None}
except BaseException as error:
    report['phase'] = 'observer_failed'
    report['error_type'] = type(error).__name__
finally:
    fd = os.open(RESULT, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as output:
        json.dump(report, output, indent=2)
        output.write('\n')
        os.fchown(output.fileno(), 1000, 1000)
