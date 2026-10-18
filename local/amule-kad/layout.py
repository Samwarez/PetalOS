#!/usr/bin/env python3
"""Generate a numeric-only diagnostic layout from matching public ELF/DWARF."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('executable', type=Path)
p.add_argument('debug_symbols', type=Path)
args = p.parse_args()


def build_id(path):
    result = subprocess.check_output(['readelf', '-n', str(path)], text=True)
    return re.search(r'Build ID: ([a-f0-9]+)', result).group(1)


assert build_id(args.executable) == build_id(args.debug_symbols)
lines = subprocess.check_output(['nm', '-C', '--defined-only', str(args.debug_symbols)], text=True).splitlines()
symbols = {}
for line in lines:
    fields = line.split(maxsplit=2)
    if len(fields) == 3:
        symbols[fields[2]] = int(fields[0], 16)
code = '''import gdb,json
t=gdb.lookup_type('Kademlia::CPrefs')
fields={f.name:f for f in t.fields()}
k=gdb.lookup_type('Kademlia::CKademlia')
pointer=next(f for f in k.fields() if f.name=='m_prefs')
assert int(pointer.type.sizeof)==8
print(json.dumps({'prefs_pointer':int(pointer.bitpos)//8,'fields':{n:[int(fields[n].bitpos)//8,int(fields[n].type.sizeof)] for n in ['m_recheckip','m_firewalled','m_externKadPort']}}))
'''
result = subprocess.check_output(['gdb', '-batch', str(args.debug_symbols), '-ex', 'python exec(' + repr(code) + ')'], text=True)
types = json.loads(next(line for line in result.splitlines() if line.startswith('{')))
layout = {
    'binary_sha256': hashlib.sha256(args.executable.read_bytes()).hexdigest(),
    'instance': symbols['Kademlia::CKademlia::instance'],
    'running': symbols['Kademlia::CKademlia::m_running'],
    'prefs_pointer': types['prefs_pointer'],
    'prefs': {label: types['fields'][field] for label, field in [
        ('tcp_replies', 'm_recheckip'), ('tcp_confirmations', 'm_firewalled'),
        ('external_udp_port', 'm_externKadPort')]},
    'udp': {label: symbols['Kademlia::CUDPFirewallTester::' + field] for label, field in [
        ('udp_finished', 'm_fwChecksFinishedUDP'), ('udp_running', 'm_fwChecksRunningUDP'),
        ('udp_timed_out', 'm_timedOut'), ('udp_node_search', 'm_nodeSearchStarted'),
        ('udp_verified', 'm_isFWVerifiedUDP'), ('udp_previous_firewalled', 'm_firewalledLastStateUDP'),
        ('udp_firewalled', 'm_firewalledUDP')]}}
print(json.dumps(layout, sort_keys=True))
