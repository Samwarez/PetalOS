#!/usr/bin/python3 -I
"""Disposable QEMU fixture for isolated, key-only hardware management.

Uses two new network namespaces and a virtual cable. No physical interfaces,
main-namespace firewall, persistent keys or boot configuration are changed.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

assert os.geteuid() == 0
assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')


def run(argv, **kwargs):
    return subprocess.run(argv, capture_output=True, timeout=15, **kwargs)


def checked(argv, **kwargs):
    result = run(argv, **kwargs)
    assert result.returncode == 0, 'Management fixture command failed; raw diagnostics suppressed.'
    return result.stdout


def snapshot():
    return [checked(command) for command in (
        ['/usr/sbin/nft', '-j', 'list', 'ruleset'],
        ['/usr/sbin/ip', '-j', 'route', 'show', 'table', 'all'],
        ['/usr/sbin/ip', '-j', '-6', 'route', 'show', 'table', 'all'],
        ['/usr/sbin/ip', '-j', 'rule', 'show'],
        ['/usr/sbin/ip', '-j', '-6', 'rule', 'show'])]


before = snapshot()
suffix = secrets.token_hex(4)
peer, management = 'pm-peer-' + suffix, 'pm-guest-' + suffix
left, right = 'pmp' + suffix, 'pmg' + suffix
created = []
daemon = None
checks = {}
try:
    with tempfile.TemporaryDirectory(prefix='petalos-netns-', dir='/run') as directory:
        root = Path(directory)
        root.chmod(0o755)
        for name in (peer, management):
            checked(['/usr/sbin/ip', 'netns', 'add', name]); created.append(name)
        checked(['/usr/sbin/ip', 'link', 'add', left, 'type', 'veth', 'peer', 'name', right])
        checked(['/usr/sbin/ip', 'link', 'set', left, 'netns', peer])
        checked(['/usr/sbin/ip', 'link', 'set', right, 'netns', management])
        for namespace, interface, address in ((peer, left, '198.18.0.1/29'),
                                              (management, right, '198.18.0.2/29')):
            checked(['/usr/sbin/ip', '-n', namespace, 'link', 'set', 'lo', 'up'])
            checked(['/usr/sbin/ip', '-n', namespace, 'address', 'add', address, 'dev', interface])
            checked(['/usr/sbin/ip', '-n', namespace, 'link', 'set', interface, 'up'])
        # Disable IPv6 only on these disposable fixture interfaces.
        for namespace in (peer, management):
            checked(['/usr/sbin/ip', 'netns', 'exec', namespace, '/usr/sbin/sysctl', '-qw',
                     'net.ipv6.conf.all.disable_ipv6=1'])
        firewall = '''table inet management {
 chain input { type filter hook input priority 0; policy drop;
  iifname "lo" accept
  ip saddr 198.18.0.1 tcp dport 22 ct state new,established accept
 }
 chain output { type filter hook output priority 0; policy drop;
  oifname "lo" accept
  ip daddr 198.18.0.1 tcp sport 22 ct state established accept
 }
 chain forward { type filter hook forward priority 0; policy drop; }
}
'''
        checked(['/usr/sbin/ip', 'netns', 'exec', management, '/usr/sbin/nft', '-f', '-'],
                input=firewall.encode())
        for name in ('host', 'client', 'wrong-client'):
            checked(['/usr/bin/ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(root / name)])
        public = (root / 'client.pub').read_text().split()
        (root / 'authorized_keys').write_text('restrict ' + ' '.join(public[:2]) + '\n')
        host = (root / 'host.pub').read_text().split()
        (root / 'known_hosts').write_text('petalos-netns-fixture ' + ' '.join(host[:2]) + '\n')
        config = root / 'sshd_config'
        config.write_text('''Port 22
ListenAddress 198.18.0.2
PermitRootLogin no
AllowUsers Petal
PubkeyAuthentication yes
AuthenticationMethods publickey
PasswordAuthentication no
KbdInteractiveAuthentication no
UsePAM yes
DisableForwarding yes
PermitTTY no
PermitUserEnvironment no
MaxAuthTries 2
LoginGraceTime 5
LogLevel QUIET
''' + 'HostKey ' + str(root / 'host') + '\nAuthorizedKeysFile ' + str(root / 'authorized_keys') + '\n')
        prefix = ['/usr/sbin/ip', 'netns', 'exec', management]
        checked(prefix + ['/usr/sbin/sshd', '-t', '-f', str(config)])
        daemon = subprocess.Popen(prefix + ['/usr/sbin/sshd', '-D', '-e', '-f', str(config)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ssh = ['/usr/sbin/ip', 'netns', 'exec', peer, '/usr/bin/ssh', '-F', '/dev/null',
               '-T', '-i', str(root / 'client'), '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
               '-o', 'StrictHostKeyChecking=yes', '-o', 'HostKeyAlias=petalos-netns-fixture',
               '-o', 'UserKnownHostsFile=' + str(root / 'known_hosts'),
               '-o', 'GlobalKnownHostsFile=/dev/null', '-o', 'ConnectTimeout=2']
        for _ in range(20):
            result = run(ssh + ['Petal@198.18.0.2', "printf 'public-out'; printf 'public-err' >&2; exit 7"])
            if result.returncode == 7: break
            assert daemon.poll() is None, 'Fixture SSH daemon stopped.'
            time.sleep(.1)
        checks['stdout_stderr_exit_status'] = (result.returncode == 7 and
            result.stdout == b'public-out' and result.stderr == b'public-err')
        wrong = ssh.copy(); wrong[wrong.index(str(root / 'client'))] = str(root / 'wrong-client')
        checks['wrong_key_refused'] = run(wrong + ['Petal@198.18.0.2', 'true']).returncode == 255
        checked(['/usr/sbin/ip', '-n', peer, 'address', 'add', '198.18.0.3/29', 'dev', left])
        result = run(['/usr/sbin/ip', 'netns', 'exec', peer, '/usr/bin/python3', '-c',
            "import socket;s=socket.socket();s.settimeout(.8);s.bind(('198.18.0.3',0));"
            "s.connect(('198.18.0.2',22))"])
        checks['unauthorized_peer_blocked'] = result.returncode != 0
        checks['no_external_route'] = run(prefix + ['/usr/sbin/ip', 'route', 'get', '1.1.1.1']).returncode != 0
        checks['management_namespace_distinct'] = checked(prefix + ['/usr/bin/readlink', '/proc/self/ns/net']) != checked(['/usr/bin/readlink', '/proc/self/ns/net'])
        checks['main_firewall_and_routes_unchanged'] = before == snapshot()
finally:
    if daemon is not None:
        daemon.terminate()
        try: daemon.wait(timeout=5)
        except subprocess.TimeoutExpired: daemon.kill(); daemon.wait()
    for name in reversed(created):
        pids = run(['/usr/sbin/ip', 'netns', 'pids', name]).stdout.split()
        for pid in pids:
            try: os.kill(int(pid), 9)
            except ProcessLookupError: pass
        checked(['/usr/sbin/ip', 'netns', 'delete', name])
    checks['cleanup_main_firewall_and_routes_unchanged'] = before == snapshot()
print(json.dumps(checks, sort_keys=True))
assert all(checks.values()), 'Isolated management fixture failed.'
