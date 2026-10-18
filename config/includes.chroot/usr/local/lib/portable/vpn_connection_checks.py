"""Bounded post-connect probes and RAM-only presentation; never app authorization."""
from concurrent.futures import ThreadPoolExecutor
import ipaddress
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time

REPORT = Path('/run/portable-vpn-checks.json')
IFINDEX = Path('/sys/class/net/wg0/ifindex')
RESOLV = Path('/etc/resolv.conf')
EXPECTED_RESOLV = Path('/run/portable-vpn/resolv.conf')
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': '/nonexistent', 'LC_ALL': 'C'}


def command(arguments, timeout=8):
    return subprocess.run(arguments, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, timeout=timeout, env=ENV, cwd='/')


def route_uses_tunnel(address):
    value = ipaddress.ip_address(address)
    result = command(['/usr/sbin/ip', '-' + str(value.version), 'route', 'get', str(value)])
    words = result.stdout.split()
    return result.returncode == 0 and 'dev' in words and words[words.index('dev') + 1:][:1] == ['wg0']


def public_address(family):
    endpoint = 'https://api.ipify.org' if family == 4 else 'https://api6.ipify.org'
    try:
        result = command(['/usr/bin/curl', '--disable', '--silent', '--fail', '--noproxy', '*',
                          '--interface', 'wg0', '-' + str(family), '--connect-timeout', '5',
                          '--max-time', '12', '--max-filesize', '128', endpoint], timeout=15)
        value = ipaddress.ip_address(result.stdout.strip())
        if result.returncode != 0 or value.version != family or not value.is_global:
            raise ValueError()
        return {'status': 'passed', 'address': str(value)}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {'status': 'failed' if family == 4 else 'warning'}


def dns_check():
    try:
        expected = EXPECTED_RESOLV.read_bytes()
        actual = RESOLV.read_bytes()
        if len(expected) > 4096 or actual != expected:
            return {'status': 'failed'}
        servers = [line.split()[1] for line in expected.decode('ascii').splitlines()
                   if line.startswith('nameserver ') and len(line.split()) == 2]
        if not servers or not all(route_uses_tunnel(server) for server in servers):
            return {'status': 'failed'}
        result = command(['/usr/bin/getent', 'ahostsv4', 'api.ipify.org'])
        return {'status': 'passed' if result.returncode == 0 and result.stdout.strip() else 'failed'}
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        return {'status': 'failed'}


def collect():
    # Caller holds portable-vpn.lock through collection and publication. Repeat
    # the existing live guard after clock synchronization, never trust history.
    guard = command(['/usr/local/sbin/portable-check-vpn'], timeout=20)
    if guard.returncode != 0 or not route_uses_tunnel('1.1.1.1'):
        raise RuntimeError('Current tunnel checks failed.')
    index = int(IFINDEX.read_text())
    with ThreadPoolExecutor(max_workers=3) as executor:
        four = executor.submit(public_address, 4)
        six = executor.submit(public_address, 6)
        dns = executor.submit(dns_check)
        results = {'tunnel': {'status': 'passed'}, 'ipv4': four.result(),
                   'ipv6': six.result(), 'dns': dns.result()}
    if not route_uses_tunnel('2606:4700:4700::1111'):
        results['ipv6'] = {'status': 'warning'}
    clock = command(['/usr/bin/chronyc', 'waitsync', '1', '0.5', '0', '1'], timeout=4)
    results['clock'] = {'status': 'passed' if clock.returncode == 0 else 'warning'}
    if int(IFINDEX.read_text()) != index:
        raise RuntimeError('Tunnel changed during checks.')
    return {'version': 1, 'checked_at': int(time.time()), 'ifindex': index, 'checks': results}


def publish(record):
    filesystem = command(['/usr/bin/findmnt', '-n', '-o', 'FSTYPE', '--target', str(REPORT.parent)])
    if filesystem.returncode or filesystem.stdout.strip() != 'tmpfs':
        raise RuntimeError('Connection reports require RAM storage.')
    fd, temporary = tempfile.mkstemp(prefix='.portable-vpn-checks-', dir=REPORT.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump(record, output)
            output.flush()
            os.fchmod(output.fileno(), 0o644)
        os.replace(temporary, REPORT)
    finally:
        Path(temporary).unlink(missing_ok=True)


def current_report():
    """Read presentation for this interface lifetime; no authorization use."""
    try:
        fd = os.open(REPORT, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd) as source:
            info = os.fstat(source.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022
                    or info.st_nlink != 1 or info.st_size > 4096):
                return None
            record = json.load(source)
        if (record['version'] != 1 or record['ifindex'] != int(IFINDEX.read_text())
                or not 0 <= time.time() - record['checked_at']):
            return None
        checks = record['checks']
        for name in ('tunnel', 'ipv4', 'ipv6', 'dns', 'clock'):
            if checks[name]['status'] not in ('passed', 'warning', 'failed'):
                return None
        for family in (4, 6):
            entry = checks['ipv' + str(family)]
            if entry['status'] == 'passed':
                address = ipaddress.ip_address(entry['address'])
                if address.version != family or not address.is_global:
                    return None
        return record
    except (OSError, ValueError, KeyError, TypeError):
        return None


def summary(record):
    if record is None:
        return 'VPN connected, but the automatic check report is unavailable.'
    checks = record['checks']
    lines = ['VPN connected. Checks at connection:', 'Firewall, routing and VPN peer: passed.']
    for family in (4, 6):
        entry = checks['ipv' + str(family)]
        lines.append('IPv' + str(family) + ': ' +
                     (entry['address'] if entry['status'] == 'passed' else 'check failed.'))
    lines.append('VPN DNS: ' + ('passed.' if checks['dns']['status'] == 'passed' else 'check failed.'))
    lines.append('Clock: ' + ('synchronized.' if checks['clock']['status'] == 'passed'
                             else 'not synchronized; keep Tor closed.'))
    if checks['ipv6']['status'] != 'passed':
        lines.append('IPv6 is unverified; IPv4 remains available.')
    return '\n'.join(lines)
