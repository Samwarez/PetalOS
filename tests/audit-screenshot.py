#!/usr/bin/env python3
"""Capture only the disposable audit display; lossless PPM-to-PNG conversion."""
from pathlib import Path
import importlib.util
import json
import os
import socket
import struct
import sys
import zlib

assert os.geteuid() != 0 and len(sys.argv) == 2
spec = importlib.util.spec_from_file_location('audit', Path(__file__).with_name('audit-vm.py'))
audit = importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
work, _ = audit.state(sys.argv[1])
runtime = Path('/run/user') / str(os.getuid()) / ('petalos-audit-' + work.name)
assert json.loads((runtime / 'running.json').read_text())['image'] == str(work / 'audit.img')
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
    connection.settimeout(5);connection.connect(str(runtime / 'qmp.sock'))
    stream = connection.makefile('rwb', buffering=0);json.loads(stream.readline())
    for request in [{'execute': 'qmp_capabilities'}, {'execute': 'screendump',
                    'arguments': {'filename': str(runtime / 'audit-screen.ppm')}}]:
        stream.write(json.dumps(request).encode() + b'\n')
        while True:
            reply = json.loads(stream.readline())
            assert 'error' not in reply
            if 'return' in reply:break
    stream.close()
with (runtime / 'audit-screen.ppm').open('rb') as f:
    assert f.readline().strip() == b'P6'
    width, height = map(int, f.readline().split())
    assert 0 < width <= 4096 and 0 < height <= 4096 and f.readline().strip() == b'255'
    pixels = f.read(width * height * 3 + 1)
assert len(pixels) == width * height * 3


def chunk(kind, value):
    return struct.pack('>I', len(value)) + kind + value + struct.pack('>I', zlib.crc32(kind + value))


raw = b''.join(b'\0' + pixels[y * width * 3:(y + 1) * width * 3] for y in range(height))
png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
target = runtime / 'audit-screen.png'
target.write_bytes(png + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
print(target)
