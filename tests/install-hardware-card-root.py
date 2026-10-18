#!/usr/bin/python3 -I
"""Install one validated image to Sam's explicitly authorized PetalOS card.

Full logical-device write and readback; never a forensic flash-erasure claim.
No guessed device names, partition migration, credentials or key output.
"""
from pathlib import Path
import fcntl
import hashlib
import json
import os
import re
import stat
import struct
import subprocess
import time
import traceback

CARD = Path('/dev/disk/by-id/usb-Mass_Storage_Device_121220160204-0:0')
SIZE = 255869321216
SERIAL = '121220160204'
SYSTEM_UUID = '1507aff9-177a-42ff-bda5-24d1398591ee'
DATA_UUID = '40a119d3-df5e-4c81-bd00-67e4c1ddae0b'
BASE = Path('/home/sam/portable-live/testing/sessions')


def output(command):
    r = subprocess.run(command, capture_output=True, timeout=15)
    assert r.returncode == 0, 'Pre-write identity check failed; raw output suppressed.'
    return r.stdout.decode().strip()


def idle(path):
    assert subprocess.run(['/usr/bin/fuser', str(path)], capture_output=True).returncode == 1


def check_card(*, require_original_uuids=True):
    device = CARD.resolve(strict=True)
    info = device.stat(); assert stat.S_ISBLK(info.st_mode)
    assert (Path('/sys/class/block') / device.name / 'removable').read_text().strip() == '1'
    properties = dict(line.split('=', 1) for line in output([
        '/usr/bin/udevadm', 'info', '--query=property', '--name', str(device)]).splitlines() if '=' in line)
    assert properties.get('ID_SERIAL_SHORT') == SERIAL
    data = json.loads(output(['/usr/bin/lsblk', '--tree', '-J', '-b', '-o', 'PATH,TYPE,SIZE,MOUNTPOINTS', str(device)]))['blockdevices']
    assert len(data) == 1 and data[0]['type'] == 'disk' and int(data[0]['size']) == SIZE
    children = data[0].get('children', []); assert len(children) == 4
    for record in (data[0], *children):
        assert not any(record.get('mountpoints') or [])
        p = Path(record['path']); idle(p)
        assert not any((Path('/sys/class/block') / p.name / 'holders').iterdir())
    if require_original_uuids:
        for child, expected in ((children[2], SYSTEM_UUID), (children[3], DATA_UUID)):
            assert output(['/usr/sbin/blkid', '-p', '-s', 'UUID', '-o', 'value', child['path']]) == expected
    return device, info.st_rdev


def main():
    assert os.geteuid() == 0
    uid = int(os.environ['SUDO_UID']); gid = int(os.environ['SUDO_GID'])
    assert uid == 1000
    runtime = Path('/run/user/' + str(uid))
    state = json.loads((runtime / 'petalos-hardware-image.json').read_text())
    if state['phase'] == 'ready-for-qemu':
        assert state.get('acceptance') and all(state['acceptance'].values())
        pending_image = state['image']
        print('Waiting for the complete image checksum. The card will not be opened for writing until it passes.', flush=True)
        deadline = time.monotonic() + 1800
        while state['phase'] == 'ready-for-qemu':
            assert time.monotonic() < deadline, 'Image checksum wait expired.'
            time.sleep(1)
            state = json.loads((runtime / 'petalos-hardware-image.json').read_text())
            assert state['image'] == pending_image
    assert state['phase'] == 'validated-for-card'
    assert state['target_by_id'] == str(CARD) and state['target_size'] == SIZE
    assert re.fullmatch('[a-f0-9]{64}', state['image_sha256'])
    image = Path(state['image'])
    assert image.is_file() and not image.is_symlink() and image.resolve().is_relative_to(BASE)
    initial = image.stat(); assert initial.st_size == SIZE and initial.st_uid == uid
    assert initial.st_mtime_ns == state['image_mtime_ns']
    assert not any((runtime / n).exists() for n in ('petalos-qemu-monitor.sock', 'petalos-hardware-qmp.sock'))
    idle(image)
    for p in Path('/sys/block').glob('loop*/loop/backing_file'):
        assert Path(p.read_text().strip()).resolve() != image.resolve()
    status = runtime / 'petalos-card-install.json'
    def progress(phase, count):
        record = {'phase': phase, 'bytes': count, 'total': SIZE,
                  'target_by_id': str(CARD), 'image': str(image)}
        temporary = status.with_name('.petalos-card-install-' + str(os.getpid()))
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as f:
            os.fchown(f.fileno(), uid, gid);json.dump(record, f)
        os.replace(temporary, status)
        print(phase + ': ' + str(round(100 * count / SIZE, 1)) + '%', flush=True)
    progress('checking-identities', 0)
    device, expected_device = check_card()
    source = target = None
    count = 0
    try:
        source = os.open(image, os.O_RDONLY | os.O_NOFOLLOW)
        info = os.fstat(source)
        assert (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) == (initial.st_dev, initial.st_ino, SIZE, initial.st_mtime_ns)
        # Kernel exclusive block-device open refuses a mounted/in-use target.
        target = os.open(device, os.O_RDWR | os.O_EXCL | os.O_NOFOLLOW)
        assert os.fstat(target).st_rdev == expected_device == CARD.stat().st_rdev
        assert struct.unpack('Q', fcntl.ioctl(target, 0x80081272, bytes(8)))[0] == SIZE
        print('Installing full-capacity image to verified PetalOS card; all existing logical sectors will be replaced.', flush=True)
        written = hashlib.sha256(); last = 0
        while chunk := os.read(source, 16 * 1024**2):
            written.update(chunk); view = memoryview(chunk)
            while view:
                n = os.write(target, view); assert n > 0
                view = view[n:]; count += n
            if time.monotonic() - last >= 10:
                progress('writing', count); last = time.monotonic()
        assert count == SIZE and written.hexdigest() == state['image_sha256']
        assert os.fstat(source).st_mtime_ns == initial.st_mtime_ns
        progress('flushing', count); os.fsync(target)
        # Flush/invalidate block buffers before the complete readback.
        fcntl.ioctl(target, 0x1261)
        os.lseek(target, 0, os.SEEK_SET)
        verified = hashlib.sha256(); count = 0; last = 0
        while count < SIZE:
            chunk = os.read(target, min(16 * 1024**2, SIZE - count)); assert chunk
            verified.update(chunk); count += len(chunk)
            if time.monotonic() - last >= 10:
                progress('verifying', count); last = time.monotonic()
        assert verified.hexdigest() == state['image_sha256']
        progress('complete', SIZE)
        print('Full-card readback matches the validated image. Do not remove the card until this terminal finishes.', flush=True)
    except BaseException:
        progress('failed-do-not-boot', count)
        raise
    finally:
        if target is not None: os.close(target)
        if source is not None: os.close(source)


if __name__ == '__main__':
    try: main()
    except BaseException as error:
        frame = traceback.extract_tb(error.__traceback__)[-1]
        print('Installer error: ' + type(error).__name__ + '; source ' +
              Path(frame.filename).name + ':' + str(frame.lineno), flush=True)
        raise SystemExit('Card installation stopped. Inspect bounded stage status before retrying; do not assume the card is bootable.')
