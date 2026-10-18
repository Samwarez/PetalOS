#!/usr/bin/env python3
"""Run a bounded RAM-only aMule trial; save results before rollback.

Stage verified public files as root in /run/petalos-amule-source-test first.
Never install this diagnostic as a normal desktop or sudo action.
"""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import sys
import time

ROOT = Path('/run/petalos-amule-source-test')
EXE = Path('/usr/bin/amule.portable-real')
ORIGINAL = 'c96577736b3c0bb818ada0dcbed200269a29a38c806748d28de8ef92ef07fa4a'


def read(path, limit=32 * 1024 * 1024):
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid or info.st_mode & 0o022 or info.st_size > limit:
            raise RuntimeError('Unsafe staged public file')
        return f.read()


def main():
    if os.geteuid() or ROOT.is_symlink() or ROOT.stat().st_uid or stat.S_IMODE(ROOT.stat().st_mode) != 0o700:
        raise RuntimeError('Requires the root-only RAM staging directory')
    config = json.loads(read(ROOT / 'trial.json', 8192))
    seconds = config['seconds']
    if type(seconds) is not int or not 60 <= seconds <= 300:
        raise RuntimeError('Invalid observation duration')
    candidate = read(ROOT / 'candidate')
    if hashlib.sha256(candidate).hexdigest() != config['candidate_sha256']:
        raise RuntimeError('Candidate checksum mismatch')
    original = read(EXE)
    if hashlib.sha256(original).hexdigest() != ORIGINAL:
        raise RuntimeError('Original executable changed')
    if Path('/dev/mapper/portable_data').exists():
        raise RuntimeError('Keep Private closed for this diagnostic')
    baseline_layout = json.loads(read(ROOT / 'original-layout.json', 8192))
    candidate_layout = json.loads(read(ROOT / 'candidate-layout.json', 8192))
    if candidate_layout['binary_sha256'] != config['candidate_sha256']:
        raise RuntimeError('Candidate layout mismatch')
    sys.path.insert(0, '/usr/local/lib/portable')
    import compartments as c
    module = importlib.util.spec_from_file_location('kad_state', ROOT / 'state.py')
    state = importlib.util.module_from_spec(module)
    module.loader.exec_module(state)
    began = time.monotonic()
    report = {'version': 1, 'phase': 'preflight', 'samples': [], 'restored': False}

    def save(phase):
        report['phase'] = phase
        report['elapsed_seconds'] = round(time.monotonic() - began, 2)
        path = ROOT / ('.report-' + str(os.getpid()))
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(report, f, sort_keys=True)
        os.replace(path, ROOT / 'report.json')

    def stop():
        record = c.read_record('amule')
        mains = []
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():
                continue
            try:
                if p.stat().st_uid == 944 and (p / 'comm').read_text().strip().startswith('amule'):
                    mains.append(int(p.name))
            except OSError:
                continue
        if len(mains) > 1:
            raise RuntimeError('Ambiguous aMule process identity')
        if mains:
            fd = os.pidfd_open(mains[0])
            try:
                signal.pidfd_send_signal(fd, signal.SIGTERM)
            finally:
                os.close(fd)
        deadline = time.monotonic() + 60
        while c.worker_alive(record) and time.monotonic() < deadline:
            time.sleep(.25)
        if c.worker_alive(record):
            raise RuntimeError('Graceful aMule stop timed out')

    def install(data):
        path = EXE.with_name('.petalos-amule-source-trial-' + str(os.getpid()))
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o755)
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            os.fchmod(f.fileno(), 0o755)
        os.replace(path, EXE)
        if read(EXE) != data:
            raise RuntimeError('Installed executable verification failed')

    def start():
        with (c.BASE / 'broker.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            c.gate('amule')
            c.start('amule')

    changed = False
    try:
        c.gate('amule')
        report['baseline'] = state.sample(baseline_layout)
        backup = ROOT / 'original'
        if backup.exists():
            if read(backup) != original:
                raise RuntimeError('Existing rollback copy differs')
        else:
            fd = os.open(str(backup), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(original)
        if read(backup) != original:
            raise RuntimeError('Rollback copy verification failed')
        save('stopping-original')
        stop()
        changed = True
        install(candidate)
        save('starting-candidate')
        start()
        start_time = time.monotonic()
        for elapsed in range(0, seconds + 1, 30):
            time.sleep(max(0, start_time + elapsed - time.monotonic()))
            report['samples'].append({'seconds': elapsed, 'state': state.sample(candidate_layout)})
            save('observing-candidate')
    except Exception as error:
        report['error_type'] = type(error).__name__
        save('trial-error')
    finally:
        if changed:
            save('restoring-original')
            stopped = False
            try:
                stop()
                stopped = True
            except Exception as error:
                report['stop_error_type'] = type(error).__name__
            # Restore the launch path even if a running process takes longer to
            # exit. Never replace data under an existing executable's inode.
            install(original)
            report['restored'] = True
            if stopped:
                try:
                    start()
                    report['original_restarted'] = True
                except Exception as error:
                    report['restart_error_type'] = type(error).__name__
            else:
                report['candidate_process_may_remain'] = True
        save('finished')


if __name__ == '__main__':
    main()
