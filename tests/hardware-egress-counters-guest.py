#!/usr/bin/python3 -I
"""Passive bounded interface counters; no packet files, addresses or payload logs."""
from collections import Counter
import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import time

assert os.geteuid() == 0
assert Path('/sys/class/dmi/id/product_name').read_text().strip() == '21CQCTO1WW'
root = Path('/run/petalos-away-tests')
routes = json.loads(subprocess.check_output(['/usr/sbin/ip', '-j', '-4', 'route', 'show', 'default']))
assert len(routes) == 1
interface = routes[0]['dev']
endpoint = subprocess.check_output(['/usr/bin/wg', 'show', 'wg0', 'endpoints'], text=True).split()[1]
address, port = endpoint.rsplit(':', 1)
expected = (ipaddress.ip_address(address.strip('[]')), int(port))
counts = Counter()
running = True


def stop(*_):
    global running
    running = False


def save():
    path = root / 'egress-counters.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'counts': dict(counts), 'elapsed': round(time.monotonic() - started)}))
    temporary.chmod(0o600)
    os.replace(temporary, path)


signal.signal(signal.SIGTERM, stop)
started = time.monotonic()
last = started
with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3)) as capture:
    capture.bind((interface, 0)); capture.settimeout(1)
    while running and time.monotonic() - started < 45 * 60:
        try:
            frame, source = capture.recvfrom(128)
            if source[2] != socket.PACKET_OUTGOING or len(frame) < 14:
                continue
            protocol = struct.unpack('!H', frame[12:14])[0]
            if protocol == 0x0806:
                counts['ARP'] += 1
            elif protocol == 0x0800 and len(frame) >= 42:
                header = 14 + (frame[14] & 15) * 4
                if frame[23] == 17 and len(frame) >= header + 8:
                    sport, dport = struct.unpack('!HH', frame[header:header + 4])
                    destination = ipaddress.ip_address(frame[30:34])
                    if (destination, dport) == expected:
                        counts['WireGuard'] += 1
                    elif sport == 68 and dport == 67:
                        counts['DHCPv4'] += 1
                    else:
                        counts['unexpected_IP'] += 1
                else:
                    counts['unexpected_IP'] += 1
            elif protocol == 0x86DD:
                if len(frame) >= 62 and frame[20] == 17:
                    sport, dport = struct.unpack('!HH', frame[54:58])
                    destination = ipaddress.ip_address(frame[38:54])
                    if (destination, dport) == expected:
                        counts['WireGuard'] += 1
                    else:
                        counts['unexpected_IP'] += 1
                else:
                    counts['unexpected_IP'] += 1
            else:
                counts['other_link_protocol'] += 1
        except socket.timeout:
            pass
        if time.monotonic() - last >= 10:
            save(); last = time.monotonic()
            try:
                if json.loads((root / 'report.json').read_text())['phase'] in ('complete', 'stopped-with-findings'):
                    break
            except (OSError, ValueError):
                pass
save()
