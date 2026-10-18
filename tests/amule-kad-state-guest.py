#!/usr/bin/env python3
"""Read only Kad test counters, using matching public ELF/DWARF metadata.

Diagnostic only: never use this report to authorize network applications.
No IPs, client hashes, filenames, keys or general memory dumps are returned.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys


def sample(layout):
    if os.geteuid() != 0 or sys.byteorder != 'little':
        raise RuntimeError('Requires root on the tested little-endian guest')
    processes = []
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid == 944 and (process / 'comm').read_text().strip().startswith('amule'):
                processes.append(process)
        except OSError:
            continue
    if len(processes) != 1:
        raise RuntimeError('Expected exactly one confined aMule main process')
    process = processes[0]
    with (process / 'exe').open('rb') as executable:
        if hashlib.file_digest(executable, 'sha256').hexdigest() != layout['binary_sha256']:
            raise RuntimeError('Executable does not match the public debug layout')
    mappings = []
    base = None
    for line in (process / 'maps').read_text().splitlines():
        fields = line.split()
        first, last = (int(value, 16) for value in fields[0].split('-'))
        if fields[1].startswith('r'):
            mappings.append((first, last))
        if len(fields) >= 6 and fields[2] == '00000000' and fields[-1].endswith('/amule.portable-real'):
            base = first
    if base is None:
        raise RuntimeError('Cannot identify the executable mapping')
    fd = os.open(str(process / 'mem'), os.O_RDONLY)
    try:
        def read(address, size):
            if size not in (1, 2, 4, 8) or not any(a <= address and address + size <= b for a, b in mappings):
                raise RuntimeError('Counter address is not readable')
            data = os.pread(fd, size, address)
            if len(data) != size:
                raise RuntimeError('Counter read was incomplete')
            return int.from_bytes(data, 'little')

        instance = read(base + layout['instance'], 8)
        if not instance:
            return {'kad_running': False}
        prefs = read(instance + layout['prefs_pointer'], 8)
        if not prefs:
            raise RuntimeError('Kad preferences are unavailable')
        result = {'kad_running': bool(read(base + layout['running'], 1))}
        for name, (offset, size) in layout['prefs'].items():
            result[name] = read(prefs + offset, size)
        for name, offset in layout['udp'].items():
            result[name] = read(base + offset, 1)
        return result
    finally:
        os.close(fd)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: amule-kad-state-guest.py protected-public-layout.json')
    fd = os.open(sys.argv[1], os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid or info.st_mode & 0o077 or info.st_size > 8192:
            raise SystemExit('Unsafe public debug layout')
        print(json.dumps(sample(json.load(source)), sort_keys=True))
