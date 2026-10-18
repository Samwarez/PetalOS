#!/usr/bin/env python3
"""Preserve the tested disk and prepare a separate full-capacity hardware image."""
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
CARD = '/dev/disk/by-id/usb-Mass_Storage_Device_121220160204-0:0'


def resume():
    assert os.geteuid() != 0
    runtime = Path('/run/user/' + str(os.getuid()))
    status = runtime / 'petalos-hardware-image.json'
    state = json.loads(status.read_text())
    assert state['phase'] == 'failed'
    image = Path(state['image'])
    assert image.is_file() and not image.is_symlink()
    assert image.resolve().is_relative_to(PROJECT.parent / 'testing/sessions')
    assert image.stat().st_size == state['target_size']
    work = image.parent
    assert not (work / 'hardware-host.pub').exists()
    assert json.loads((work / 'preparation.json').read_text())['image'] == str(image)
    with (runtime / 'petalos-qemu.lock').open('a') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for p in (image, Path(state['source'])):
            assert subprocess.run(['fuser', str(p)], capture_output=True).returncode == 1
        def update(phase):
            state['phase'] = phase
            temp = status.with_suffix('.tmp'); temp.write_text(json.dumps(state, indent=2)); temp.replace(status)
        try:
            update('awaiting-authentication')
            print('Reusing the detached temporary candidate; working disk and physical card untouched.', flush=True)
            subprocess.run(['sudo', '--', '/usr/bin/python3', '-I', str(PROJECT / 'tests/prepare-hardware-image-root.py'), str(image)], check=True)
            public = (work / 'hardware-host.pub').read_text().split()
            assert len(public) >= 2 and public[0] == 'ssh-ed25519'
            keydir = Path.home() / '.local/share/petalos-hardware/ssh'
            known = keydir / ('known_hosts-' + work.name.removeprefix('hardware-'))
            assert not known.exists()
            known.write_text('petalos-hardware ' + ' '.join(public[:2]) + '\n'); known.chmod(0o600)
            state['ssh'] = {'key': str(keydir / 'id_ed25519'), 'known_hosts': str(known)}
            update('ready-for-qemu')
            print('Hardware candidate ready for QEMU validation; physical card untouched. This terminal may close.', flush=True)
        except BaseException:
            update('failed'); raise


def main():
    assert os.geteuid() != 0
    runtime = Path('/run/user/' + str(os.getuid()))
    prior = json.loads((runtime / 'petalos-encrypted-test.json').read_text())
    assert prior['phase'] == 'ready-for-encrypted-boot'
    assert prior['private_migration']['kind'] == 'fresh-volume-key'
    image = Path(prior['image'])
    assert not image.is_symlink() and image.is_file()
    assert image.resolve().is_relative_to(PROJECT.parent / 'testing/sessions')
    assert image.stat().st_size == 16 * 1024**3
    with (runtime / 'petalos-qemu.lock').open('a') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert subprocess.run(['fuser', str(image)], capture_output=True).returncode == 1
        for p in Path('/sys/block').glob('loop*/loop/backing_file'):
            assert Path(p.read_text().strip()).resolve() != image.resolve()
        size = int(subprocess.check_output(['lsblk', '-b', '-dn', '-o', 'SIZE', CARD]))
        assert 230 * 1024**3 < size < 260 * 1024**3
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        work = image.parent / ('hardware-' + stamp); work.mkdir(mode=0o700)
        clone = work / ('hardware-' + stamp + '.img')
        state = {'phase': 'preparing', 'image': str(clone), 'source': str(image),
                 'firmware': str(work / 'OVMF_VARS.fd'), 'release': prior['release'],
                 'target_by_id': CARD, 'target_size': size}
        status = runtime / 'petalos-hardware-image.json'
        def update(phase):
            state['phase'] = phase
            temp = status.with_suffix('.tmp'); temp.write_text(json.dumps(state, indent=2)); temp.replace(status)
        update('preparing')
        try:
            spec = importlib.util.spec_from_file_location('hardware_builder', PROJECT / 'tests/build-hardware-ssh-module.py')
            builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
            module = builder.build(work)
            state['module'] = str(module)
            subprocess.run(['qemu-img', 'convert', '-f', 'raw', '-O', 'raw', '-S', '4k', str(image), str(clone)], check=True)
            shutil.copy2(prior['firmware'], state['firmware'])
            (work / 'preparation.json').write_text(json.dumps(state, indent=2))
            print('Working QEMU disk and physical card preserved. Enter host sudo, then existing QEMU SYSTEM and distinct Private passphrases.', flush=True)
            update('awaiting-authentication')
            subprocess.run(['sudo', '--', '/usr/bin/python3', '-I', str(PROJECT / 'tests/prepare-hardware-image-root.py'), str(clone)], check=True)
            public = (work / 'hardware-host.pub').read_text().split()
            assert len(public) >= 2 and public[0] == 'ssh-ed25519'
            keydir = Path.home() / '.local/share/petalos-hardware/ssh'
            known = keydir / ('known_hosts-' + stamp)
            known.write_text('petalos-hardware ' + ' '.join(public[:2]) + '\n'); known.chmod(0o600)
            state['ssh'] = {'key': str(keydir / 'id_ed25519'), 'known_hosts': str(known)}
            update('ready-for-qemu')
            print('Hardware candidate ready for QEMU validation; physical card untouched. This terminal may close.', flush=True)
        except BaseException:
            update('failed'); raise


if __name__ == '__main__':
    os.umask(0o077)
    try:
        assert sys.argv[1:] in ([], ['--resume'])
        if sys.argv[1:]: resume()
        else: main()
    except Exception:
        raise SystemExit('Preparation stopped. Inspect stage status; original disk and physical card were not written.')
