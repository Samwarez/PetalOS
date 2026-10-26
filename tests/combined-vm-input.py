#!/usr/bin/python3
"""Bounded QMP keyboard/link control for an explicitly selected disposable VM."""
from pathlib import Path
import argparse
import importlib.util
import json
import socket
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('state', type=Path)
parser.add_argument('action', choices=('key', 'text', 'credential', 'link'))
parser.add_argument('value')
args = parser.parse_args()
spec = importlib.util.spec_from_file_location('audit', Path(__file__).with_name('audit-vm.py'))
audit = importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
work, _ = audit.state(args.state)
runtime = Path('/run/user/1000')/('petalos-audit-'+work.name)
assert json.loads((runtime/'running.json').read_text())['image'] == str(work/'audit.img')
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
    connection.settimeout(5);connection.connect(str(runtime/'qmp.sock'))
    stream = connection.makefile('rwb', buffering=0);json.loads(stream.readline())
    def request(command, arguments=None):
        message = {'execute': command}
        if arguments is not None:message['arguments'] = arguments
        stream.write(json.dumps(message).encode()+b'\n')
        while True:
            reply = json.loads(stream.readline())
            assert 'error' not in reply, 'QMP control failed; request contents suppressed.'
            if 'return' in reply:return
    request('qmp_capabilities')
    def key(keys):
        request('send-key', {'keys': [{'type': 'qcode', 'data': k} for k in keys], 'hold-time': 20})
        time.sleep(.06)
    if args.action == 'link':
        assert args.value in ('up', 'down')
        request('set_link', {'name': 'auditnic', 'up': args.value == 'up'})
    elif args.action == 'key':
        keys = args.value.split('+')
        allowed = {'ctrl', 'alt', 'shift', 'ret', 'esc', 'tab', 'spc', 'backspace', 'delete', 'f4', 'home', 'end', 'up', 'down', 'left', 'right'}
        assert 0 < len(keys) <= 4 and all(k in allowed or len(k) == 1 and k.isascii() and k.isalnum() for k in keys)
        key(keys)
    else:
        value = args.value
        if args.action == 'credential':
            assert value in ('system', 'administrator', 'private')
            value = json.loads((work/'credentials.json').read_text())[value]
        assert len(value) <= 512 and all(c.isascii() for c in value)
        for character in value:
            if character == ':':keys = ['shift', 'semicolon']
            elif character in './- ':keys = [{'.': 'dot', '/': 'slash', '-': 'minus', ' ': 'spc'}[character]]
            else:
                assert character.isalnum()
                keys = (['shift'] if character.isupper() else [])+[character.lower()]
            key(keys)
    stream.close()
print('Requested input delivered to the disposable VM; contents omitted.')
