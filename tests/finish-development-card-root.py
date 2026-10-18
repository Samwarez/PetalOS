#!/usr/bin/python3 -I
"""Sam-authorized development shortcut: finish/verify allocated image extents.

Unused source holes are not copied or verified. This is not a production wipe
or full-image checksum verification. Never start from an unrelated target.
"""
from pathlib import Path
import errno
import fcntl
import importlib.util
import json
import os
import stat
import struct
import time
import traceback

spec = importlib.util.spec_from_file_location('installer', Path(__file__).with_name('install-hardware-card-root.py'))
installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)


def extents(fd, size):
    result = []; position = 0
    while position < size:
        try: start = os.lseek(fd, position, os.SEEK_DATA)
        except OSError as e:
            if e.errno == errno.ENXIO: break
            raise
        end = min(os.lseek(fd, start, os.SEEK_HOLE), size)
        assert position <= start < end <= size
        result.append((start, end)); position = end
    assert result and result[0][0] == 0 and result[-1][1] == size
    return result


def main():
    assert os.geteuid() == 0 and int(os.environ['SUDO_UID']) == 1000
    runtime = Path('/run/user/1000')
    state = json.loads((runtime / 'petalos-hardware-image.json').read_text())
    status = runtime / 'petalos-card-install.json'
    prior = json.loads(status.read_text())
    assert state['phase'] == 'validated-for-card'
    assert prior['phase'] == 'failed-do-not-boot'
    assert prior['target_by_id'] == state['target_by_id'] == str(installer.CARD)
    assert prior['image'] == state['image'] and prior['total'] == state['target_size'] == installer.SIZE
    assert 16 * 1024**3 <= prior['bytes'] <= installer.SIZE
    image = Path(state['image']); assert image.is_file() and not image.is_symlink()
    assert image.resolve().is_relative_to(installer.BASE)
    before = image.stat()
    assert before.st_size == installer.SIZE and before.st_mtime_ns == state['image_mtime_ns']
    assert before.st_uid == 1000
    installer.idle(image)
    assert not any((runtime / n).exists() for n in ('petalos-qemu-monitor.sock', 'petalos-hardware-qmp.sock'))
    assert not any(Path(p.read_text().strip()).resolve() == image.resolve()
                   for p in Path('/sys/block').glob('loop*/loop/backing_file'))
    # Original UUID probes are inapplicable after the first 86GB was replaced.
    # Preserve serial/capacity/block-type/mount/holder/busy checks, then compare
    # the already-written primary GPT/boot prefix against this exact image.
    device, identity = installer.check_card(require_original_uuids=False)
    source = os.open(image, os.O_RDONLY | os.O_NOFOLLOW)
    target = None
    completed = 0
    total = 0
    def progress(phase):
        data = {'phase': phase, 'bytes': completed, 'total': total,
                'target_by_id': str(installer.CARD), 'image': str(image),
                'verification': 'allocated-extents-only-development',
                'unused_sectors_overwritten': False}
        temporary = status.with_name('.petalos-dev-install-' + str(os.getpid()))
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as f:
            os.fchown(f.fileno(), 1000, int(os.environ['SUDO_GID'])); json.dump(data, f)
        os.replace(temporary, status)
        print(phase + ': ' + str(round(completed / max(1, total) * 100, 1)) + '%', flush=True)
    try:
        assert os.fstat(source).st_ino == before.st_ino
        ranges = extents(source, before.st_size)
        total = sum(b - a for a, b in ranges)
        assert total < installer.SIZE // 2, 'Sparse shortcut would not save enough work.'
        target = os.open(device, os.O_RDWR | os.O_EXCL | os.O_NOFOLLOW)
        assert stat.S_ISBLK(os.fstat(target).st_mode)
        assert os.fstat(target).st_rdev == identity == installer.CARD.stat().st_rdev
        assert struct.unpack('Q', fcntl.ioctl(target, 0x80081272, bytes(8)))[0] == installer.SIZE
        os.fsync(target); fcntl.ioctl(target, 0x1261)
        assert os.pread(target, 1024**2, 0) == os.pread(source, 1024**2, 0), 'Interrupted-image prefix mismatch.'
        progress('writing-allocated-extents')
        # The old buffered write may have been disconnected before reaching
        # media. Rewrite every allocated extent; never trust its byte counter
        # as proof that queued data reached the card.
        unflushed = 0; last = 0
        for start, end in ranges:
            position = start
            while position < end:
                data = os.pread(source, min(8 * 1024**2, end - position), position); assert data
                view = memoryview(data)
                while view:
                    written = os.pwrite(target, view, position); assert written > 0
                    position += written; view = view[written:]
                    unflushed += written; completed += written
                if unflushed >= 64 * 1024**2:
                    os.fsync(target); unflushed = 0
                    if time.monotonic() - last >= 10:
                        progress('writing-allocated-extents'); last = time.monotonic()
        os.fsync(target); fcntl.ioctl(target, 0x1261)
        last = 0; completed = 0
        for start, end in ranges:
            position = start
            while position < end:
                length = min(8 * 1024**2, end - position)
                expected = os.pread(source, length, position)
                actual = os.pread(target, length, position)
                assert len(expected) == length and actual == expected, 'Allocated extent readback mismatch.'
                position += length; completed += length
                if time.monotonic() - last >= 10:
                    progress('verifying-allocated-extents'); last = time.monotonic()
        after = os.fstat(source)
        assert (after.st_ino, after.st_size, after.st_mtime_ns) == (before.st_ino, before.st_size, before.st_mtime_ns)
        progress('complete-development')
        print('Development card ready: allocated image data matches. Unused sectors were skipped; no full wipe or full-device verification claimed.', flush=True)
    except BaseException:
        progress('failed-development-do-not-boot')
        raise
    finally:
        if target is not None: os.close(target)
        os.close(source)


if __name__ == '__main__':
    try: main()
    except BaseException as error:
        frame = traceback.extract_tb(error.__traceback__)[-1]
        print('Development finish error: ' + type(error).__name__ + '; source ' +
              Path(frame.filename).name + ':' + str(frame.lineno), flush=True)
        raise SystemExit('Stopped. Keep the card connected and report the stage before booting.')
