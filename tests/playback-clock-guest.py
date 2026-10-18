#!/usr/bin/python3 -B
"""Compare FIFO playback clocks with synthetic silence in isolated Pulse servers.

Run as the desktop user in QEMU. No media files, hardware, desktop audio modules,
credentials or default devices are used. All temporary state stays in runtime RAM.
"""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time


def measure(root, timing):
    root.mkdir(mode=0o700)
    for name in ('runtime', 'state'):
        (root / name).mkdir(mode=0o700)
    fifo, native, config = (root / name for name in ('pcm.fifo', 'native', 'pulse.pa'))
    config.write_text('\n'.join([
        f'load-module module-native-protocol-unix socket={native} auth-anonymous=1 auth-cookie-enabled=0',
        'load-module module-pipe-sink sink_name=clock_test '
        f'file={fifo} format=s16le rate=48000 channels=2 use_system_clock_for_timing={timing}',
        'set-default-sink clock_test', '',
    ]))
    config.chmod(0o600)
    env = dict(os.environ, PULSE_SERVER='unix:' + str(native),
               PULSE_RUNTIME_PATH=str(root / 'runtime'), PULSE_STATE_PATH=str(root / 'state'))
    server = subprocess.Popen([
        '/usr/bin/dbus-run-session', '--', '/usr/bin/pulseaudio', '-n', '--daemonize=no',
        '--exit-idle-time=-1', '--use-pid-file=no', '--disallow-module-loading', '--file=' + str(config),
    ], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    fd, worker = None, None
    stop = threading.Event()
    try:
        for _ in range(50):
            if native.is_socket() and fifo.exists():
                break
            assert server.poll() is None, 'Isolated audio server exited.'
            time.sleep(.1)
        assert native.is_socket() and fifo.exists(), 'Isolated audio server timed out.'
        fd = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)

        def drain():
            while not stop.is_set():
                try:
                    if not os.read(fd, 65536):
                        time.sleep(.001)
                except BlockingIOError:
                    time.sleep(.001)

        worker = threading.Thread(target=drain)
        worker.start()
        started = time.monotonic()
        result = subprocess.run([
            '/usr/bin/paplay', '--raw', '--format=s16le', '--rate=48000', '--channels=2',
            '--device=clock_test', '--latency-msec=40',
        ], input=bytes(48000 * 2 * 2 * 3), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=12)
        assert result.returncode == 0, 'Synthetic playback failed.'
        return time.monotonic() - started
    finally:
        stop.set()
        if worker:
            worker.join(timeout=2)
            assert not worker.is_alive()
        if fd is not None:
            os.close(fd)
        try:
            os.killpg(server.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            server.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(server.pid, signal.SIGKILL)
            server.wait()


def main():
    runtime = Path('/run/user') / str(os.getuid())
    assert runtime.is_dir() and runtime.stat().st_uid == os.getuid()
    with tempfile.TemporaryDirectory(prefix='petalos-clock-test-', dir=runtime) as temporary:
        unclocked = measure(Path(temporary) / 'unclocked', 'no')
        clocked = measure(Path(temporary) / 'clocked', 'yes')
    print(f'Three seconds of PCM: unclocked={unclocked:.3f}s; system-clocked={clocked:.3f}s')
    assert unclocked < 1.5, 'Expected the unpaced FIFO to reproduce accelerated playback.'
    assert 2.6 <= clocked <= 5.0, 'System-clocked playback did not track elapsed time.'
    print('PASS: system-clock timing prevents fast FIFO consumption from accelerating playback.')


if __name__ == '__main__':
    main()
