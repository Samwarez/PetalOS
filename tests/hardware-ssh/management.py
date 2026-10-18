#!/usr/bin/python3 -I
"""Optional hardware-test SSH on one isolated wired interface; never Wi-Fi."""
import os
from pathlib import Path
import re
import signal
import subprocess
import time

NS = 'petalos-hardware-management'
ROOT = Path('/run/petalos-hardware-ssh')


def run(command, **kwargs):
    r = subprocess.run(command, capture_output=True, timeout=10, **kwargs)
    if r.returncode:
        raise RuntimeError('Hardware management operation failed; raw output suppressed.')
    return r.stdout


def ip(*arguments):
    return run(['/usr/sbin/ip', *arguments])


def choose():
    requested = [x.split('=', 1)[1] for x in Path('/proc/cmdline').read_text().split()
                 if x.startswith('petalos_management_if=')]
    assert len(requested) <= 1
    if requested:
        assert re.fullmatch(r'[A-Za-z0-9_-]{1,15}', requested[0])
    for _ in range(60):
        candidates = []
        for p in Path('/sys/class/net').iterdir():
            if (p / 'wireless').exists() or not (p / 'device').exists(): continue
            if (p / 'type').read_text().strip() != '1': continue
            if requested and p.name != requested[0]: continue
            try: connected = (p / 'carrier').read_text().strip() == '1'
            except OSError: connected = False
            if connected: candidates.append(p.name)
        if len(candidates) == 1: return candidates[0]
        if len(candidates) > 1:
            raise RuntimeError('Multiple wired adapters: select the management interface explicitly.')
        time.sleep(1)
    raise RuntimeError('No connected management Ethernet adapter found.')


def main():
    assert os.geteuid() == 0
    assert 'petalos_hardware_ssh=1' in Path('/proc/cmdline').read_text().split()
    assert (ROOT / 'ssh_host_ed25519_key').is_file()
    assert not Path('/run/netns/' + NS).exists()
    interface = choose()
    managed = subprocess.run(['/usr/bin/nmcli', '-g', 'GENERAL.NM-MANAGED',
                              'device', 'show', interface], capture_output=True, timeout=10)
    assert managed.returncode == 0 and managed.stdout.strip() in (b'yes', b'no')
    was_managed = managed.stdout.strip() == b'yes'
    created = moved = False
    daemon = None
    def stop(*_): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        if was_managed:
            run(['/usr/bin/nmcli', 'device', 'set', interface, 'managed', 'no'])
        ip('netns', 'add', NS); created = True
        # Isolate before assigning any management address.
        ip('link', 'set', interface, 'netns', NS); moved = True
        prefix = ['/usr/sbin/ip', 'netns', 'exec', NS]
        run(prefix + ['/usr/sbin/sysctl', '-qw', 'net.ipv6.conf.all.disable_ipv6=1'])
        ip('-n', NS, 'address', 'flush', 'dev', interface)
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
        run(prefix + ['/usr/sbin/nft', '-f', '-'], input=firewall.encode())
        ip('-n', NS, 'address', 'add', '198.18.0.2/30', 'dev', interface)
        ip('-n', NS, 'link', 'set', 'lo', 'up')
        ip('-n', NS, 'link', 'set', interface, 'up')
        assert subprocess.run(prefix + ['/usr/sbin/ip', 'route', 'get', '1.1.1.1'],
                              capture_output=True, timeout=5).returncode != 0
        config = '/etc/petalos-hardware-ssh/sshd_config'
        run(prefix + ['/usr/sbin/sshd', '-t', '-f', config])
        daemon = subprocess.Popen(prefix + ['/usr/sbin/sshd', '-D', '-e', '-f', config],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while daemon.poll() is None: time.sleep(.5)
        raise RuntimeError('Hardware management SSH stopped.')
    except KeyboardInterrupt:
        pass
    finally:
        if daemon is not None:
            daemon.terminate()
            try: daemon.wait(timeout=5)
            except subprocess.TimeoutExpired: daemon.kill(); daemon.wait()
        if created:
            for pid in ip('netns', 'pids', NS).split():
                try: os.kill(int(pid), signal.SIGKILL)
                except ProcessLookupError: pass
            if moved:
                ip('-n', NS, 'link', 'set', interface, 'down')
                ip('-n', NS, 'address', 'flush', 'dev', interface)
                ip('-n', NS, 'link', 'set', interface, 'netns', '1')
            ip('netns', 'delete', NS)
        if was_managed:
            run(['/usr/bin/nmcli', 'device', 'set', interface, 'managed', 'yes'])


if __name__ == '__main__':
    try: main()
    except Exception:
        raise SystemExit('Isolated hardware SSH unavailable; normal Wi-Fi/VPN policy was not relaxed.')
