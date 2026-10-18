#!/usr/bin/env python3
"""Operate only the separately provisioned disposable audit VM."""
from pathlib import Path
import fcntl
import json
import os
import shlex
import signal
import socket
import subprocess
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]


def state(path):
    p = Path(path)
    assert p.resolve(strict=True) == p and p.name == 'state.json'
    assert p.parent.parent == PROJECT.parent / 'testing/audit'
    s = json.loads(p.read_text())
    assert p.parent.stat().st_uid == os.getuid() and not p.parent.stat().st_mode & 0o077
    credentials = p.parent / 'credentials.json'
    assert not credentials.is_symlink() and credentials.stat().st_uid == os.getuid()
    assert not credentials.stat().st_mode & 0o077
    assert s['scope'] == 'disposable-audit-only' and s['phase'] == 'ready-for-audit-boot'
    assert s['directory'] == str(p.parent) and s['cid'] == 43 and s['port'] == 2225
    return p.parent, s


def ssh(work, command, **kwargs):
    return subprocess.run(['ssh', '-F', '/dev/null', '-T', '-p', '2225',
        '-i', str(work / 'id_ed25519'), '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
        '-o', 'StrictHostKeyChecking=yes', '-o', 'HostKeyAlias=petalos-audit',
        '-o', 'UserKnownHostsFile=' + str(work / 'known_hosts'), '-o', 'GlobalKnownHostsFile=/dev/null',
        '-o', 'ConnectTimeout=3', '-o', 'ServerAliveInterval=10', '-o', 'ServerAliveCountMax=3',
        'Petal@127.0.0.1', command], **kwargs)


def unlock_screen(work):
    probe = 'pgrep -u 1000 -x gtklock >/dev/null'
    assert ssh(work, probe, capture_output=True, timeout=10).returncode == 0
    runtime = Path('/run/user') / str(os.getuid()) / ('petalos-audit-' + work.name)
    password = json.loads((work / 'credentials.json').read_text())['system']
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(5);connection.connect(str(runtime / 'qmp.sock'))
        stream = connection.makefile('rwb', buffering=0)
        json.loads(stream.readline())

        def request(command, arguments=None):
            message = {'execute': command}
            if arguments is not None:message['arguments'] = arguments
            stream.write(json.dumps(message).encode() + b'\n')
            while True:
                reply = json.loads(stream.readline())
                if 'error' in reply:raise RuntimeError('QMP input request failed.')
                if 'return' in reply:return

        request('qmp_capabilities')
        for character in password:
            code = 'minus' if character == '-' else character.lower()
            assert code in 'abcdefghijklmnopqrstuvwxyz0123456789' or code == 'minus'
            keys = ([{'type': 'qcode', 'data': 'shift'}] if character.isupper() else [])
            keys.append({'type': 'qcode', 'data': code})
            request('send-key', {'keys': keys, 'hold-time': 20});time.sleep(.06)
        request('send-key', {'keys': [{'type': 'qcode', 'data': 'ret'}], 'hold-time': 20})
        stream.close()
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if ssh(work, probe, capture_output=True, timeout=10).returncode == 1:
            print('Audit desktop unlocked using the disposable SYSTEM credential.')
            return
        time.sleep(1)
    raise RuntimeError('Desktop unlock did not complete.')


def launch(work, s):
    assert os.geteuid() != 0
    image = work / 'audit.img';assert s['image'] == str(image)
    assert image.is_file() and not image.is_symlink() and image.stat().st_size == 16 * 1024**3
    for backing in Path('/sys/block').glob('loop*/loop/backing_file'):
        assert Path(backing.read_text().strip()).resolve() != image.resolve()
    assert subprocess.run(['fuser', str(image)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 1
    assert os.access('/dev/vhost-vsock', os.R_OK | os.W_OK)
    runtime = Path('/run/user') / str(os.getuid()) / ('petalos-audit-' + work.name)
    runtime.mkdir(mode=0o700, exist_ok=True)
    qmp = runtime / 'qmp.sock';serial = runtime / 'serial.sock'
    assert not qmp.exists() and not serial.exists()
    with socket.socket() as check:
        check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        check.bind(('127.0.0.1', 2225))
    args = ['qemu-system-x86_64', '-enable-kvm', '-machine', 'q35,smm=on', '-cpu', 'host',
            '-smp', '8', '-m', '16384', '-global', 'driver=cfi.pflash01,property=secure,value=on',
            '-drive', 'if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.secboot.fd',
            '-drive', 'if=pflash,format=raw,file=' + str(work / 'OVMF_VARS.fd'),
            '-drive', 'format=raw,if=virtio,file=' + str(image),
            '-global', 'virtio-blk-pci.bootindex=1',
            '-boot', 'order=c', '-nic', 'user,model=virtio-net-pci',
            '-device', 'vhost-vsock-pci,guest-cid=43',
            '-object', 'rng-random,filename=/dev/urandom,id=entropy', '-device', 'virtio-rng-pci,rng=entropy',
            '-device', 'virtio-vga,xres=1280,yres=800', '-display', 'gtk,zoom-to-fit=off',
            '-audiodev', 'pa,id=sound', '-device', 'ich9-intel-hda', '-device', 'hda-output,audiodev=sound',
            '-serial', 'unix:' + str(serial) + ',server=on,wait=on', '-monitor', 'none',
            '-qmp', 'unix:' + str(qmp) + ',server=on,wait=off', '-name', 'PetalOS DISPOSABLE Phase 1.5 audit']
    process = None;relay = None
    error_tail = bytearray()
    console_tail = bytearray()

    def console_status(data):
        console_tail.extend(data);del console_tail[:-32768]
        status = {'passphrase_prompt_seen': b'Enter passphrase' in console_tail,
                  'passphrase_rejected': b'No key available with this passphrase' in console_tail,
                  'boot_failed': b'BOOT FAILED' in console_tail or b'No supported filesystem images' in console_tail,
                  'live_config_seen': b'live-config' in console_tail,
                  'login_prompt_seen': b'login:' in console_tail}
        (runtime / 'console-status.json').write_text(json.dumps(status))

    def drain_errors():
        try:
            for name in ('console-status.json', 'audit-screen.ppm', 'audit-screen.png'):
                (runtime / name).unlink(missing_ok=True)
            while chunk := process.stderr.read(8192):
                error_tail.extend(chunk);del error_tail[:-65536]
        except BlockingIOError:
            pass
        (runtime / 'qemu.log').write_bytes(error_tail)

    with (work / 'vm.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            os.set_blocking(process.stderr.fileno(), False)
            deadline = time.monotonic() + 20
            while not serial.exists():
                drain_errors()
                assert process.poll() is None and time.monotonic() < deadline
                time.sleep(.2)
            connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            connection.connect(str(serial));connection.settimeout(1)
            relay = subprocess.Popen(['socat', 'TCP4-LISTEN:2225,bind=127.0.0.1,reuseaddr,fork',
                                      'VSOCK-CONNECT:43:22'], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, start_new_session=True)
            credentials = json.loads((work / 'credentials.json').read_text())
            sent = False;buffer = b'';deadline = time.monotonic() + 180
            print('Audit VM booting; SYSTEM entry is automated from test-only credentials.', flush=True)
            while not sent and time.monotonic() < deadline:
                drain_errors()
                assert process.poll() is None
                try:data = connection.recv(8192)
                except socket.timeout:continue
                if not data:raise RuntimeError('Serial channel closed during unlock.')
                console_status(data)
                buffer = (buffer + data)[-16384:]
                if b'Enter passphrase for ' in buffer or b'Enter passphrase:' in buffer:
                    time.sleep(.5)
                    connection.sendall(credentials['system'].encode() + b'\r');sent = True
            assert sent
            # Discard serial data after the unlock; never persist console input.
            connection.setblocking(False)
            (runtime / 'running.json').write_text(json.dumps({'pid':process.pid,'qmp':str(qmp),'image':str(image)}))
            print('SYSTEM entry sent. Pinned audit SSH relay: 127.0.0.1:2225.', flush=True)
            while process.poll() is None:
                drain_errors()
                try:console_status(connection.recv(65536))
                except BlockingIOError:pass
                time.sleep(.2)
            drain_errors()
            assert process.returncode == 0
        finally:
            if relay is not None:
                try:os.killpg(relay.pid, signal.SIGTERM)
                except ProcessLookupError:pass
                relay.wait()
            if process is not None and process.poll() is None:
                process.terminate();process.wait()
            for p in (qmp, serial, runtime / 'running.json'):
                p.unlink(missing_ok=True)


def main():
    assert os.geteuid() != 0 and len(sys.argv) >= 3
    work, s = state(sys.argv[1]);action = sys.argv[2]
    if action == 'launch':
        assert len(sys.argv) == 3;launch(work, s)
    elif action == 'unlock-screen':
        assert len(sys.argv) == 3;unlock_screen(work)
    elif action == 'ssh':
        assert len(sys.argv) == 4
        r = ssh(work, sys.argv[3], capture_output=True, timeout=60)
        credentials = json.loads((work / 'credentials.json').read_text())
        for output, stream in ((r.stdout, sys.stdout.buffer), (r.stderr, sys.stderr.buffer)):
            for value in credentials.values():output = output.replace(value.encode(), b'[test credential redacted]')
            stream.write(output[-65536:])
        return r.returncode
    elif action in ('root-script', 'root-credential-script'):
        assert len(sys.argv) == 4
        code = Path(sys.argv[3]).read_text()
        credentials = json.loads((work / 'credentials.json').read_text())
        command = shlex.join(['sudo', '-S', '-p', '', '--', '/usr/bin/python3', '-I', '-c', code])
        payload = credentials['administrator'].encode() + b'\n'
        if action == 'root-credential-script':payload += json.dumps(credentials).encode() + b'\n'
        r = ssh(work, command, input=payload,
                capture_output=True, timeout=600)
        for output, stream in ((r.stdout, sys.stdout.buffer), (r.stderr, sys.stderr.buffer)):
            for value in credentials.values():output = output.replace(value.encode(), b'[test credential redacted]')
            stream.write(output[-65536:])
        return r.returncode
    else:raise RuntimeError('Unknown audit action.')
    return 0


if __name__ == '__main__':
    try:sys.exit(main())
    except Exception as error:
        print('Audit VM operation stopped: ' + type(error).__name__ + '; inspect bounded runtime status.', file=sys.stderr)
        sys.exit(1)
