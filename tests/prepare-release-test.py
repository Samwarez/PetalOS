#!/usr/bin/env python3
"""Preserve the working encrypted disk and update a fresh release clone."""
from pathlib import Path
import datetime
import fcntl
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]


def main():
    if os.geteuid() == 0:
        raise RuntimeError('Run the coordinator as Sam.')
    if len(sys.argv) != 2:
        raise RuntimeError('Provide the completed release directory.')
    release = Path(sys.argv[1])
    if (release.parent != PROJECT.parent / 'releases' or
            not re.fullmatch(r'\d{8}-\d{6}-\d+', release.name) or
            release.resolve(strict=True) != release):
        raise RuntimeError('Unexpected release directory.')
    if not (release / 'manifest.json').is_file():
        raise RuntimeError('Completed release manifest is missing.')
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
        transfer = runtime / 'petalos-release-transfer.json'
        candidate = {'phase': 'cloning', 'image': str(clone), 'prior_image': str(image)}

        def update(phase):
            candidate['phase'] = phase
            temp = transfer.with_suffix('.tmp'); temp.write_text(json.dumps(candidate, indent=2)); temp.replace(transfer)

        try:
            update('cloning')
            print('Creating a new sparse release-test disk; working encrypted disk is preserved.', flush=True)
            subprocess.run(['qemu-img', 'convert', '-f', 'raw', '-O', 'raw', '-S', '4k',
                            str(image), str(clone)], check=True)
            shutil.copy2(prior['firmware'], firmware)
            update('awaiting-authentication')
            print('Enter sudo authentication and then the QEMU test SYSTEM-volume password.', flush=True)
            if prior.get('ssh'):
                work=image.parent/('release-management-'+stamp);work.mkdir(mode=0o700)
                spec=importlib.util.spec_from_file_location('ssh_module',PROJECT/'tests/build-ssh-module.py')
                builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
                module=builder.build(work)
                command=[str(PROJECT/'tests/provision-release-root.py'),str(clone),str(release),str(module)]
            else:
                command=[str(PROJECT/'tests/update-encrypted-clone.py'),str(clone),str(release)]
            subprocess.run(['/usr/bin/sudo','--','/usr/bin/python3','-B',*command],check=True)
            state = {**prior, 'image': str(clone), 'firmware': str(firmware), 'release': str(release)}
            state.pop('configuration_module',None)
            if prior.get('ssh'):
                state['ssh']={**prior['ssh'],'user':'Petal','prior_image':str(image)}
            temp = status.with_suffix('.tmp'); temp.write_text(json.dumps(state, indent=2)); temp.replace(status)
            update('complete')
            print('Updated release installed; new encrypted test disk is ready to boot.', flush=True)
        except BaseException:
            update('failed'); raise


if __name__ == '__main__':
    os.umask(0o077)
    try: main()
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
