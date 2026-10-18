#!/usr/bin/python3 -I
"""Temporary isolated host Ethernet peer; preserve the active host uplink."""
from pathlib import Path
import json
import os
import signal
import socket
import subprocess
import time

INTERFACE = 'enp2s0'
EXPECTED_MAC = '74:86:e2:10:a2:9f'
NAMESPACE = 'petalos-host-management'


def run(argv, **kwargs):
    r = subprocess.run(argv, capture_output=True, timeout=10, **kwargs)
    assert r.returncode == 0, 'Management link operation failed; raw diagnostics suppressed.'
    return r.stdout


def main():
    assert os.geteuid() == 0
    assert int(os.environ['SUDO_UID']) == 1000
    interface = Path('/sys/class/net') / INTERFACE
    assert interface.exists() and (interface / 'device').exists()
    assert not (interface / 'wireless').exists()
    assert (interface / 'address').read_text().strip() == EXPECTED_MAC
    addresses = json.loads(run(['/usr/sbin/ip', '-j', 'address', 'show', 'dev', INTERFACE]))
    assert len(addresses) == 1
    assert all(a['family'] == 'inet6' and a['scope'] == 'link' for a in addresses[0]['addr_info']), 'Spare interface has non-link-local addresses; refuse moving it.'
    originally_up = 'UP' in addresses[0]['flags']
    assert not json.loads(run(['/usr/sbin/ip', '-j', 'route', 'show', 'dev', INTERFACE]))
    assert not Path('/run/netns/' + NAMESPACE).exists()
    managed = run(['/usr/bin/nmcli', '-g', 'GENERAL.NM-MANAGED', 'device', 'show', INTERFACE]).strip()
    assert managed in (b'yes', b'no')
    ipv6_setting = (Path('/proc/sys/net/ipv6/conf') / INTERFACE / 'disable_ipv6').read_text().strip()
    assert ipv6_setting in ('0', '1')
    with socket.socket() as test: test.bind(('127.0.0.1', 2224))
    created = moved = False; relay = None
    def stop(*_): raise KeyboardInterrupt
    signal.signal(signal.SIGINT, stop); signal.signal(signal.SIGTERM, stop)
    try:
        if managed == b'yes':
            run(['/usr/bin/nmcli', 'device', 'set', INTERFACE, 'managed', 'no'])
        run(['/usr/sbin/ip', 'netns', 'add', NAMESPACE]); created = True
        run(['/usr/sbin/ip', 'link', 'set', INTERFACE, 'netns', NAMESPACE]); moved = True
        prefix = ['/usr/sbin/ip', 'netns', 'exec', NAMESPACE]
        run(prefix + ['/usr/sbin/sysctl', '-qw', 'net.ipv6.conf.all.disable_ipv6=1'])
        run(prefix + ['/usr/sbin/nft', '-f', '-'], input=b'''table inet hardware_peer {
 chain input { type filter hook input priority 0; policy drop;
  iifname "lo" accept
  ip saddr 198.18.0.2 tcp sport 22 ct state established accept
 }
 chain output { type filter hook output priority 0; policy drop;
  oifname "lo" accept
  ip daddr 198.18.0.2 tcp dport 22 ct state new,established accept
 }
 chain forward { type filter hook forward priority 0; policy drop; }
}
''')
        run(['/usr/sbin/ip', '-n', NAMESPACE, 'address', 'add', '198.18.0.1/30', 'dev', INTERFACE])
        run(['/usr/sbin/ip', '-n', NAMESPACE, 'link', 'set', 'lo', 'up'])
        run(['/usr/sbin/ip', '-n', NAMESPACE, 'link', 'set', INTERFACE, 'up'])
        assert not run(['/usr/sbin/ip', '-n', NAMESPACE, 'route', 'show', 'default']).strip()
        # Fixed raw TCP relay only; SSH remains end-to-end key authenticated.
        command = ['/usr/bin/socat', 'TCP4-LISTEN:2224,bind=127.0.0.1,reuseaddr,fork',
                   'EXEC:/usr/bin/python3 -I ' + str(Path(__file__).with_name('host-hardware-connect.py'))]
        relay = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
        print('Isolated ThinkPad Ethernet peer active. Pinned SSH relay: 127.0.0.1:2224.', flush=True)
        print('Leave this terminal open during hardware testing; Ctrl+C restores the spare interface.', flush=True)
        while relay.poll() is None: time.sleep(1)
        raise RuntimeError('Management relay stopped.')
    except KeyboardInterrupt:
        pass
    finally:
        if relay is not None:
            try: os.killpg(relay.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: relay.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(relay.pid, signal.SIGKILL); relay.wait()
        if created:
            for pid in run(['/usr/sbin/ip', 'netns', 'pids', NAMESPACE]).split():
                try: os.kill(int(pid), signal.SIGKILL)
                except ProcessLookupError: pass
            if moved:
                run(['/usr/sbin/ip', '-n', NAMESPACE, 'link', 'set', INTERFACE, 'down'])
                run(['/usr/sbin/ip', '-n', NAMESPACE, 'address', 'flush', 'dev', INTERFACE])
                run(['/usr/sbin/ip', '-n', NAMESPACE, 'link', 'set', INTERFACE, 'netns', '1'])
                run(['/usr/sbin/sysctl', '-qw', 'net.ipv6.conf.' + INTERFACE + '.disable_ipv6=' + ipv6_setting])
                if originally_up:
                    run(['/usr/sbin/ip', 'link', 'set', INTERFACE, 'up'])
            run(['/usr/sbin/ip', 'netns', 'delete', NAMESPACE])
        if managed == b'yes':
            run(['/usr/bin/nmcli', 'device', 'set', INTERFACE, 'managed', 'yes'])


if __name__ == '__main__':
    try: main()
    except Exception:
        raise SystemExit('Host management setup stopped. Active uplink and its VPN/firewall were not modified.')
