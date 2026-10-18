#!/usr/bin/env python3
"""Checksum a detached, accepted hardware image before physical installation."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import time


def main():
    assert os.geteuid() == 1000
    runtime = Path('/run/user/1000')
    status = runtime / 'petalos-hardware-image.json'
    state = json.loads(status.read_text())
    assert state['phase'] == 'ready-for-qemu'
    assert state['acceptance'] and all(state['acceptance'].values())
    assert not any((runtime / n).exists() for n in ('petalos-qemu-monitor.sock', 'petalos-hardware-qmp.sock'))
    image = Path(state['image'])
    assert image.is_file() and not image.is_symlink()
    assert image.resolve().is_relative_to(Path(__file__).resolve().parents[2] / 'testing/sessions')
    before = image.stat(); assert before.st_size == state['target_size']
    assert subprocess.run(['fuser', str(image)], capture_output=True).returncode == 1
    for p in Path('/sys/block').glob('loop*/loop/backing_file'):
        assert Path(p.read_text().strip()).resolve() != image.resolve()
    h = hashlib.sha256(); count = 0; last = 0
    with image.open('rb') as source:
        while chunk := source.read(16 * 1024**2):
            h.update(chunk); count += len(chunk)
            if time.monotonic() - last >= 10:
                print('Image checksum: ' + str(round(100 * count / before.st_size, 1)) + '%', flush=True)
                last = time.monotonic()
    after = image.stat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    state.update(phase='validated-for-card', image_sha256=h.hexdigest(), image_mtime_ns=after.st_mtime_ns)
    temporary = status.with_suffix('.tmp'); temporary.write_text(json.dumps(state, indent=2)); temporary.replace(status)
    print('Detached hardware image verified: ' + h.hexdigest(), flush=True)


if __name__ == '__main__':
    main()
