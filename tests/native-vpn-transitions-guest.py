#!/usr/bin/python3 -I
"""QEMU tunnel transitions with packet-header counters, never capture files."""
import collections
import ipaddress
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import threading
import time

sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
from vpn_profiles import select as selected_profile

assert os.geteuid() == 0
assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
c.gate('transmission')
selected, _ = selected_profile()
missing = 'petalos-missing-transition-fixture'
assert not (c.PRIVATE / 'Network/Profiles' / (missing + '.conf')).exists()
endpoint = subprocess.check_output(['/usr/bin/wg', 'show', 'wg0', 'endpoints'], text=True).split()[1]
host, port = endpoint.rsplit(':', 1)
expected = (ipaddress.ip_address(host.strip('[]')), int(port))
route = json.loads(subprocess.check_output(['/usr/sbin/ip', '-j', '-4', 'route', 'show', 'default'], text=True))
assert len(route) == 1
interface = route[0]['dev']
capture = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
capture.bind((interface, 0)); capture.settimeout(.25)
counts = collections.Counter()
finished = threading.Event()

def observe():
    while not finished.is_set():
        try:
            frame, address = capture.recvfrom(65535)
        except socket.timeout:
            continue
        if address[2] != socket.PACKET_OUTGOING or len(frame) < 14:
            continue
        protocol = struct.unpack('!H', frame[12:14])[0]
        if protocol == 0x0800 and len(frame) >= 34:
            packet = frame[14:]; size = (packet[0] & 15) * 4
            if packet[9] == 17 and len(packet) >= size + 8:
                sport, dport = struct.unpack('!HH', packet[size:size+4])
                destination = ipaddress.ip_address(packet[16:20])
                if (destination, dport) == expected:counts['wireguard'] += 1
                elif sport == 68 and dport == 67:counts['dhcp'] += 1
                else:counts['unexpected_ip'] += 1
            else:counts['unexpected_ip'] += 1
        elif protocol == 0x86DD:
            # This VM uses an IPv4 tunnel endpoint and has no approved physical
            # IPv6 egress. Count all such frames conservatively.
            counts['unexpected_ip'] += 1

def command(args, timeout=100):
    return subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=timeout).returncode

def blocked_probe(uid):
    code = '''import socket
for target in [('198.51.100.1',443),('1.1.1.1',53),('1.1.1.1',123)]:
 s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(.5)
 try:s.sendto(b'petalos-public-killswitch-canary',target)
 except OSError:pass
 finally:s.close()
'''
    assert command(['/usr/bin/setpriv', '--reuid='+str(uid), '--regid='+str(uid), '--clear-groups',
        '--bounding-set=-all', '--no-new-privs', '/usr/bin/python3', '-I', '-c', code], 5) == 0

report = {}
thread = threading.Thread(target=observe, daemon=True); thread.start()
try:
    for app in ('browser', 'tor', 'transmission', 'pan', 'amule', 'sab-viewer', 'sabnzbd'):
        c.stop(app)
    report['disconnect_succeeds'] = command(['/usr/local/sbin/portable-vpn', 'disconnect']) == 0
    report['repeated_disconnect_succeeds'] = command(['/usr/local/sbin/portable-vpn', 'disconnect']) == 0
    report['current_gate_rejects_disconnected'] = command(['/usr/local/sbin/portable-check-network-ready'], 25) != 0
    for uid in (0, 1000, 940, 942, 943, 944, 945):blocked_probe(uid)
    report['invalid_profile_fails_closed'] = command(['/usr/local/sbin/portable-vpn', 'connect', missing]) != 0
    report['failed_connect_leaves_no_tunnel'] = command(['/usr/sbin/ip', 'link', 'show', 'wg0'], 5) != 0
    for uid in (0, 1000, 943):blocked_probe(uid)
    reconnect = ['/usr/local/sbin/portable-vpn', 'connect'] + ([] if selected == 'legacy' else [selected])
    report['reconnect_succeeds'] = command(reconnect) == 0
    report['current_gate_accepts_reconnected'] = command(['/usr/local/sbin/portable-check-network-ready'], 25) == 0
    if selected != 'legacy':
        report['same_profile_switch_succeeds'] = command(['/usr/local/sbin/portable-vpn', 'switch', selected]) == 0
        report['current_gate_accepts_switched'] = command(['/usr/local/sbin/portable-check-network-ready'], 25) == 0
    time.sleep(1)
finally:
    finished.set();thread.join(timeout=2);capture.close()
    # Restore the selected usable profile even if a fixture assertion failed.
    if command(['/usr/sbin/ip', 'link', 'show', 'wg0'], 5) != 0:
        command(['/usr/local/sbin/portable-vpn', 'connect'] + ([] if selected == 'legacy' else [selected]))
report['wireguard_transport_observed'] = counts['wireguard'] > 0
report['no_unexpected_physical_ip_egress_observed'] = counts['unexpected_ip'] == 0
print(json.dumps({'checks': report, 'packet_counts': dict(counts)}, sort_keys=True))
assert all(report.values())
