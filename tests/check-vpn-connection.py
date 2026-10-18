#!/usr/bin/python3 -B
"""Synthetic post-connect probes: no real VPN, DNS, HTTP or privileged changes."""
import copy
import importlib.util
import io
import contextlib
import json
import os
from pathlib import Path
import runpy
import stat
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

project = Path(__file__).resolve().parents[1]
path = project / 'config/includes.chroot/usr/local/lib/portable/vpn_connection_checks.py'
spec = importlib.util.spec_from_file_location('vpn_connection_checks', path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
calls = []
failure = ''


def command(arguments, timeout=8):
    calls.append(arguments)
    status, output = 0, ''
    if arguments[0].endswith('portable-check-vpn'):
        status = int(failure == 'guard')
    elif arguments[0].endswith('/ip'):
        output = arguments[-1] + ' dev ' + ('eth0' if failure == 'route' else 'wg0')
    elif arguments[0].endswith('/curl'):
        assert '--disable' in arguments and '--noproxy' in arguments
        assert arguments[arguments.index('--interface') + 1] == 'wg0'
        assert '--max-time' in arguments and '--max-filesize' in arguments
        six = '-6' in arguments
        status = int(failure == ('ipv6' if six else 'ipv4'))
        output = '2606:4700:4700::1111' if six else '1.1.1.1'
        if failure == 'private-ip':
            output = 'fd00::1' if six else '192.168.1.1'
    elif arguments[0].endswith('/getent'):
        status, output = int(failure == 'dns'), '1.1.1.1 STREAM api.ipify.org'
    elif arguments[0].endswith('/chronyc'):
        status = int(failure == 'clock')
    elif arguments[0].endswith('/findmnt'):
        output = 'tmpfs' if failure != 'persistent-report' else 'ext4'
    else:
        raise AssertionError('Unexpected probe command')
    return SimpleNamespace(returncode=status, stdout=output)


with tempfile.TemporaryDirectory(prefix='petalos-vpn-check-fixture-') as directory:
    root = Path(directory)
    m.IFINDEX = root / 'ifindex'; m.IFINDEX.write_text('5')
    m.RESOLV = root / 'resolv'; m.EXPECTED_RESOLV = root / 'expected'
    m.REPORT = root / 'report.json'
    for p in (m.RESOLV, m.EXPECTED_RESOLV):
        p.write_text('nameserver 10.0.0.1\n')
    with patch.object(m, 'command', command):
        record = m.collect()
        assert all(v['status'] == 'passed' for v in record['checks'].values())
        for failure in ('ipv6', 'clock'):
            result = m.collect()
            assert result['checks'][failure]['status'] == 'warning'
            assert result['checks']['ipv4']['status'] == 'passed'
        for failure in ('ipv4', 'dns'):
            assert m.collect()['checks'][failure]['status'] == 'failed'
        failure = 'private-ip'
        assert m.public_address(4)['status'] == 'failed'
        assert m.public_address(6)['status'] == 'warning'
        for failure in ('guard', 'route'):
            try:
                m.collect()
            except RuntimeError:
                pass
            else:
                raise AssertionError('Invalid current tunnel accepted')
        failure = ''
        m.RESOLV.write_text('nameserver 9.9.9.9\n')
        assert m.dns_check()['status'] == 'failed'
        m.RESOLV.write_text(m.EXPECTED_RESOLV.read_text())
        m.publish(record)
        assert json.loads(m.REPORT.read_text()) == record
        assert stat.S_IMODE(m.REPORT.stat().st_mode) == 0o644
        failure = 'persistent-report'
        try:
            m.publish(record)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Persistent report location accepted')
        failure = ''
    print('PASS bounded tunnel-bound probes, IPv6/clock warnings, required failures, private IP rejection and DNS mismatch')

    # The privileged entry point must not publish failed required checks.
    helper = project / 'config/includes.chroot/usr/local/sbin/portable-test-vpn-connection'
    for failed in (None, 'ipv6', 'clock', 'ipv4', 'dns', 'tunnel'):
        value = copy.deepcopy(record)
        if failed:
            value['checks'][failed] = {'status': 'warning' if failed in ('ipv6', 'clock') else 'failed'}
        published = []
        with patch.dict(sys.modules, {'vpn_connection_checks': m}), \
             patch.object(m, 'collect', return_value=value), \
             patch.object(m, 'publish', side_effect=published.append), \
             patch('os.geteuid', return_value=0), \
             patch('sys.argv', [str(helper)]), contextlib.redirect_stderr(io.StringIO()):
            try:
                runpy.run_path(str(helper), run_name='__main__')
            except SystemExit as error:
                assert failed in ('ipv4', 'dns', 'tunnel') and error.code == 1
        assert bool(published) == (failed not in ('ipv4', 'dns', 'tunnel'))
    print('PASS required failures reject publication; IPv6 and clock warnings preserve IPv4')

    real_fstat = os.fstat
    def trusted(fd):
        value = real_fstat(fd)
        return SimpleNamespace(st_mode=value.st_mode, st_uid=0, st_nlink=value.st_nlink, st_size=value.st_size)

    def write(value):
        m.REPORT.write_text(json.dumps(value)); m.REPORT.chmod(0o644)

    write(record)
    with patch.object(m.os, 'fstat', trusted):
        assert m.current_report() == record
        m.IFINDEX.write_text('6'); assert m.current_report() is None
        m.IFINDEX.write_text('5')
        future = copy.deepcopy(record); future['checked_at'] = time.time() + 300
        write(future); assert m.current_report() is None
        write(record); m.REPORT.chmod(0o666); assert m.current_report() is None
        m.REPORT.unlink(); m.REPORT.symlink_to(m.RESOLV); assert m.current_report() is None
        m.REPORT.unlink()
    print('PASS report rejects changed interface, future timestamp, writable file and symlink')

    warning = copy.deepcopy(record); warning['checks']['ipv6'] = {'status': 'warning'}
    assert 'IPv4 remains available' in m.summary(warning)
    print('PASS connection summary distinguishes optional IPv6 failure')
