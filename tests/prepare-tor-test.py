#!/usr/bin/env python3
"""Preserve the working encrypted disk and provision a new Tor-test clone."""
from pathlib import Path
import datetime
import fcntl
import importlib.util
import json
import os
import shutil
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]


def main():
    if os.geteuid() == 0:
        raise RuntimeError('Run the coordinator as Sam.')
    spec = importlib.util.spec_from_file_location('provision', PROJECT / 'tests/provision-tor-root.py')
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    helper.verified_assets()  # Only signed public software is selected.
    runtime = Path(f'/run/user/{os.getuid()}')
    status = runtime / 'petalos-encrypted-test.json'
    prior = json.loads(status.read_text())
    if prior['phase'] != 'ready-for-encrypted-boot':
        raise RuntimeError('Working encrypted test disk is not ready.')
    image = Path(prior['image']); allowed = PROJECT.parent / 'testing/sessions'
    if image.is_symlink() or not image.is_file() or not image.resolve().is_relative_to(allowed.resolve()):
        raise RuntimeError('Unexpected source disk.')
    with (runtime / 'petalos-qemu.lock').open('a') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if subprocess.run(['fuser', str(image)], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode != 1:
            raise RuntimeError('Working disk is busy or busy state is unknown.')
        for backing in Path('/sys/block').glob('loop*/loop/backing_file'):
            if Path(backing.read_text().strip()).resolve() == image.resolve():
                raise RuntimeError('Working disk is attached.')
        if image.stat().st_size != 16 * 1024**3:
            raise RuntimeError('Unexpected working disk size.')
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        clone = image.parent / f'encrypted-boot-{stamp}.img'
        firmware = image.parent / f'encrypted-OVMF-{stamp}.fd'
        if clone.exists() or firmware.exists():
            raise RuntimeError('Candidate already exists.')
        transfer = runtime / 'petalos-tor-transfer.json'
        candidate = {'phase': 'cloning', 'image': str(clone), 'prior_image': str(image)}

        def update(phase):
            candidate['phase'] = phase
            temp = transfer.with_suffix('.tmp'); temp.write_text(json.dumps(candidate, indent=2)); temp.replace(transfer)

        try:
            update('cloning')
            print('Creating a new sparse Tor-test disk; working encrypted disk is preserved.', flush=True)
            subprocess.run(['qemu-img', 'convert', '-f', 'raw', '-O', 'raw', '-S', '4k',
                            str(image), str(clone)], check=True)
            shutil.copy2(prior['firmware'], firmware)
            update('awaiting-authentication')
            print('Enter sudo authentication and then the QEMU test DATA-volume password.', flush=True)
            subprocess.run(['/usr/bin/sudo', '--', '/usr/bin/python3', '-B',
                            str(PROJECT / 'tests/provision-tor-root.py'), str(clone)], check=True)
            state = {**prior, 'image': str(clone), 'firmware': str(firmware)}
            temp = status.with_suffix('.tmp'); temp.write_text(json.dumps(state, indent=2)); temp.replace(status)
            update('complete')
            print('Verified Tor archive provisioned; new Tor-test disk is ready to boot.', flush=True)
        except BaseException:
            update('failed'); raise


if __name__ == '__main__':
    os.umask(0o077)
    try: main()
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
