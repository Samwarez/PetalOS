#!/usr/bin/env python3
"""Run a bounded command through the pinned QEMU-only SSH management channel."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys

def execute(command, timeout=30):
    runtime = Path(f'/run/user/{os.getuid()}')
    state = json.loads((runtime / 'petalos-encrypted-test.json').read_text())
    ssh = state['ssh']
    login = ssh.get('user', 'user')
    if login not in ('user', 'Petal'):
        raise RuntimeError('Unexpected live account identity.')
    if not (runtime / 'petalos-qemu-monitor.sock').exists():
        raise RuntimeError('The managed VM is not running.')
    keydir = Path.home() / '.local/share/petalos-qemu/ssh'
    if ssh['key'] != str(keydir / 'id_ed25519') or ssh['known_hosts'] != str(keydir / 'known_hosts'):
        raise RuntimeError('Unexpected management key identity.')
    return subprocess.run(['ssh', '-F', '/dev/null', '-T', '-p', '2222',
        '-i', ssh['key'], '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
        '-o', 'StrictHostKeyChecking=yes', '-o', 'HostKeyAlias=petalos-qemu',
        '-o', 'UserKnownHostsFile=' + ssh['known_hosts'], '-o', 'GlobalKnownHostsFile=/dev/null',
        '-o', 'ConnectTimeout=5', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=2',
        login+'@127.0.0.1', command], capture_output=True, timeout=timeout)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--timeout', type=int, default=30)
    parser.add_argument('command', help='Remote shell command; never include credentials or print secret files.')
    args = parser.parse_args()
    try:
        result = execute(args.command, args.timeout)
        if args.json:
            print(json.dumps({'stdout': result.stdout.decode(errors='replace'),
                              'stderr': result.stderr.decode(errors='replace'), 'exit_code': result.returncode}))
        else:
            sys.stdout.buffer.write(result.stdout); sys.stderr.buffer.write(result.stderr)
        sys.exit(result.returncode)
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(255)
