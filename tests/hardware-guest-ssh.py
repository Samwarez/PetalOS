#!/usr/bin/env python3
"""Bounded, pinned SSH to the optional hardware-image QEMU management link."""
from pathlib import Path
import json
import os
import re
import subprocess
import sys


def arguments(*, physical=False):
    state = json.loads(Path(f'/run/user/{os.getuid()}/petalos-hardware-image.json').read_text())
    ssh = state['ssh']
    directory = Path.home() / '.local/share/petalos-hardware/ssh'
    assert ssh['key'] == str(directory / 'id_ed25519')
    known = Path(ssh['known_hosts'])
    assert known.parent == directory and re.fullmatch(r'known_hosts-\d{8}-\d{6}-\d+', known.name)
    if physical:
        assert Path('/run/netns/petalos-host-management').exists()
    else:
        assert Path(f'/run/user/{os.getuid()}/petalos-hardware-qmp.sock').is_socket()
    return ['ssh', '-F', '/dev/null', '-T', '-p', '2224' if physical else '2223', '-i', ssh['key'],
        '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
        '-o', 'StrictHostKeyChecking=yes', '-o', 'HostKeyAlias=petalos-hardware',
        '-o', 'UserKnownHostsFile=' + str(known), '-o', 'GlobalKnownHostsFile=/dev/null',
        '-o', 'ConnectTimeout=5', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=2',
        'Petal@127.0.0.1']


def execute(command, timeout=30, *, physical=False):
    return subprocess.run([*arguments(physical=physical), command], capture_output=True, timeout=timeout)


if __name__ == '__main__':
    assert len(sys.argv) == 2
    result = execute(sys.argv[1])
    print(json.dumps({'stdout': result.stdout.decode(errors='replace'),
                      'stderr': result.stderr.decode(errors='replace'), 'exit_code': result.returncode}))
    raise SystemExit(result.returncode)
