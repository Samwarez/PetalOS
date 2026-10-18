#!/usr/bin/python3
"""QEMU-only real DHCP/MAC checks; run after VPN disconnect over vsock SSH."""
from pathlib import Path
import json
import os
import select
import socket
import subprocess
import threading

assert os.geteuid() == 0
assert 'QEMU' in Path('/sys/class/dmi/id/sys_vendor').read_text()
assert not Path('/sys/class/net/wg0').exists()
before = json.loads(subprocess.check_output(['/usr/sbin/nft', '-j', 'list', 'ruleset']))
policies = {x['chain']['name']: x['chain']['policy'] for x in before['nftables']
            if 'chain' in x and x['chain']['table'] == 'portable_vpn'}
assert policies == {'input': 'drop', 'forward': 'drop', 'output': 'drop'}
assert all(not x['set'].get('elem') for x in before['nftables']
           if 'set' in x and x['set']['table'] == 'portable_vpn')
rows = subprocess.check_output(['nmcli', '-t', '-f', 'UUID,TYPE,DEVICE',
                                'connection', 'show', '--active'], text=True).splitlines()
wired = [r.split(':') for r in rows if ':802-3-ethernet:' in r]
assert len(wired) == 1
uuid, _, iface = wired[0]
packet = socket.socket(socket.AF_PACKET, socket.SOCK_DGRAM, socket.htons(3))
packet.bind((iface, 3)); packet.setblocking(False)
stop = threading.Event()
observations = []

def capture():
    while not stop.is_set():
        if not select.select([packet], [], [], 0.2)[0]:
            continue
        data, link = packet.recvfrom(4096)
        if len(data) < 28 or data[0] >> 4 != 4 or data[9] != 17 or link[2] != 4:
            continue
        header = (data[0] & 15) * 4
        if data[header:header+4] != b'\x00D\x00C':
            continue
        bootp = data[header+8:]
        if len(bootp) < 240 or bootp[0] != 1 or bootp[236:240] != b'\x63\x82\x53\x63':
            continue
        options = {}; index = 240
        while index < len(bootp):
            kind = bootp[index]; index += 1
            if kind == 255:
                break
            if kind == 0:
                continue
            if index >= len(bootp):
                break
            length = bootp[index]; index += 1
            options[kind] = bootp[index:index+length]; index += length
        # Retain booleans only, never hostnames, identifiers or packet payloads.
        observations.append({'hostname_sent': 12 in options or 81 in options,
                             'client_matches_mac': options.get(61) == b'\x01'+bootp[28:34]})

worker = threading.Thread(target=capture, daemon=True); worker.start()
macs = [Path(f'/sys/class/net/{iface}/address').read_text().strip()]
try:
    for _ in range(2):
        subprocess.run(['nmcli', '-w', '10', 'device', 'disconnect', iface],
                       check=True, capture_output=True, timeout=12)
        subprocess.run(['nmcli', '-w', '20', 'connection', 'up', 'uuid', uuid, 'ifname', iface],
                       check=True, capture_output=True, timeout=22)
        mac = Path(f'/sys/class/net/{iface}/address').read_text().strip(); macs.append(mac)
        assert int(mac.split(':')[0], 16) & 3 == 2
        assert before == json.loads(subprocess.check_output(['/usr/sbin/nft', '-j', 'list', 'ruleset']))
finally:
    stop.set(); worker.join(timeout=2); packet.close()
assert len(set(macs)) == 3
assert observations and all(not x['hostname_sent'] and x['client_matches_mac'] for x in observations)
print(json.dumps({'mac_changes': 2, 'locally_administered_unicast': True,
                  'dhcp_packets_checked': len(observations), 'hostname_absent': True,
                  'client_id_matches_random_mac': True, 'firewall_unchanged': True}))
