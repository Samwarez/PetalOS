#!/usr/bin/env python3
"""Test hardware image using an added isolated virtual Ethernet cable."""
from pathlib import Path
import fcntl
import json
import os
import socket
import subprocess
import time


def qmp(path, command, arguments=None):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(5); s.connect(str(path)); f = s.makefile('rwb', buffering=0)
        assert 'QMP' in json.loads(f.readline())
        for name, args in (('qmp_capabilities', {}), (command, arguments or {})):
            f.write(json.dumps({'execute': name, 'arguments': args}).encode() + b'\n')
            while True:
                response = json.loads(f.readline())
                if 'return' in response: break
                assert 'error' not in response, 'QMP operation rejected.'


def main():
    assert os.geteuid() != 0
    runtime = Path('/run/user/' + str(os.getuid()))
    status = runtime / 'petalos-hardware-image.json'
    state = json.loads(status.read_text())
    assert state['phase'] == 'ready-for-qemu'
    image = Path(state['image'])
    assert image.is_file() and not image.is_symlink()
    assert image.resolve().is_relative_to(Path(__file__).resolve().parents[2] / 'testing/sessions')
    assert image.stat().st_size == state['target_size']
    firmware = Path(state['firmware']); assert firmware.is_file() and not firmware.is_symlink()
    monitor = runtime / 'petalos-hardware-qmp.sock'
    assert not monitor.exists() and not (runtime / 'petalos-qemu-monitor.sock').exists()
    with (runtime / 'petalos-qemu.lock').open('a') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert subprocess.run(['fuser', str(image)], capture_output=True).returncode == 1
        for p in Path('/sys/block').glob('loop*/loop/backing_file'):
            assert Path(p.read_text().strip()).resolve() != image.resolve()
        with socket.socket() as reservation: reservation.bind(('127.0.0.1', 2223))
        command = ['qemu-system-x86_64', '-enable-kvm', '-machine', 'q35', '-cpu', 'host',
            '-smp', '4', '-m', '8192',
            '-drive', 'if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd',
            '-drive', 'if=pflash,format=raw,file=' + str(firmware),
            '-drive', 'format=raw,if=virtio,file=' + str(image),
            '-global', 'virtio-blk-pci.bootindex=1', '-boot', 'order=c',
            '-netdev', 'user,id=uplink', '-device', 'virtio-net-pci,netdev=uplink,id=uplink-nic',
            '-netdev', 'user,id=management,net=198.18.0.0/24,host=198.18.0.1,restrict=on,hostfwd=tcp:127.0.0.1:2223-198.18.0.2:22',
            '-device', 'virtio-net-pci,netdev=management,id=management-nic,addr=0x6',
            '-device', 'virtio-vga', '-display', 'gtk', '-serial', 'none', '-monitor', 'none',
            '-qmp', 'unix:' + str(monitor) + ',server=on,wait=off',
            '-name', 'PetalOS hardware-image Ethernet management test']
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            for _ in range(100):
                assert process.poll() is None, 'Hardware QEMU launch failed.'
                if monitor.exists(): break
                time.sleep(.1)
            # Only management Ethernet has carrier during adapter selection.
            # Re-enable the original uplink once management SSH is verified.
            qmp(monitor, 'set_link', {'name': 'uplink-nic', 'up': False})
            print('Hardware-image VM running; SYSTEM boot unlock required. Added Ethernet SSH is localhost:2223.', flush=True)
            tail = bytearray()
            while chunk := process.stderr.read1(4096):
                tail.extend(chunk); del tail[:-65536]
            assert process.wait() == 0, 'Hardware QEMU stopped with an error.'
        finally:
            if process.poll() is None: process.terminate(); process.wait()
            monitor.unlink(missing_ok=True)


if __name__ == '__main__':
    try: main()
    except Exception as e:
        raise SystemExit(str(e))
