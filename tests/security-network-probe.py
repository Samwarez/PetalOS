#!/usr/bin/python3
"""QEMU-only short packet metadata probe; no captures or payload logging."""
import collections
import ipaddress
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time


def main():
    assert os.geteuid() == 0
    assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
    endpoint_lines = subprocess.check_output(['/usr/bin/wg', 'show', 'wg0', 'endpoints'], text=True).splitlines()
    assert len(endpoint_lines) == 1
    endpoint = endpoint_lines[0].split()[1]
    host, port = endpoint.rsplit(':', 1)
    expected = (ipaddress.ip_address(host.strip('[]')), int(port))
    route = json.loads(subprocess.check_output(['ip', '-j', '-4', 'route', 'show', 'default'], text=True))
    assert len(route) == 1
    interface = route[0]['dev']
    sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
    sock.bind((interface, 0))
    sock.settimeout(1)
    counters = collections.Counter()
    deadline = time.monotonic() + 15
    try:
        while time.monotonic() < deadline:
            try:
                frame, address = sock.recvfrom(65535)
            except socket.timeout:
                continue
            if address[2] != socket.PACKET_OUTGOING or len(frame) < 14:
                continue
            protocol = struct.unpack('!H', frame[12:14])[0]
            counters['outgoing_frames'] += 1
            if protocol == 0x0806:
                counters['arp'] += 1
            elif protocol == 0x0800 and len(frame) >= 34:
                packet = frame[14:]
                ihl = (packet[0] & 15) * 4
                if packet[9] == 17 and len(packet) >= ihl + 8:
                    sport, dport = struct.unpack('!HH', packet[ihl:ihl + 4])
                    destination = ipaddress.ip_address(packet[16:20])
                    if (destination, dport) == expected:
                        counters['wireguard_transport'] += 1
                    elif sport == 68 and dport == 67:
                        counters['dhcp'] += 1
                    else:
                        counters['unexpected_ipv4_udp'] += 1
                else:
                    counters['unexpected_ipv4_non_udp'] += 1
            elif protocol == 0x86DD and len(frame) >= 54:
                packet = frame[14:]
                if packet[6] == 17 and len(packet) >= 48:
                    destination = ipaddress.ip_address(packet[24:40])
                    dport = struct.unpack('!H', packet[42:44])[0]
                    if (destination, dport) == expected:
                        counters['wireguard_transport'] += 1
                    else:
                        counters['unexpected_ipv6'] += 1
                else:
                    counters['unexpected_ipv6'] += 1
            else:
                counters['other_link_protocol'] += 1
    finally:
        sock.close()
    result = {'window_seconds': 15, 'counts': dict(counters),
              'observed_wireguard': counters['wireguard_transport'] > 0,
              'no_unexpected_ip_egress': not any(counters[name] for name in ('unexpected_ipv4_udp', 'unexpected_ipv4_non_udp', 'unexpected_ipv6'))}
    print(json.dumps(result, sort_keys=True))
    assert result['observed_wireguard'] and result['no_unexpected_ip_egress']


if __name__ == '__main__':
    main()
