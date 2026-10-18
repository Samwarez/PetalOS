#!/usr/bin/env python3
"""Add host-key-pinned SSH to a preserved encrypted test clone, not the release."""
from pathlib import Path
import datetime
import fcntl
import json
import os
import shutil
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
KEYDIR = Path.home() / '.local/share/petalos-qemu/ssh'

def main():
    if os.geteuid() == 0:
        raise RuntimeError('Run the coordinator as Sam.')
    runtime = Path(f'/run/user/{os.getuid()}')
    statefile = runtime / 'petalos-encrypted-test.json'
    prior = json.loads(statefile.read_text())
    if prior.get('ssh'):
        # Retry from the preserved working disk, not a failed SSH candidate.
        original = Path(prior['ssh']['prior_image'])
        original_firmware = original.with_name(original.name.replace('encrypted-boot-', 'encrypted-OVMF-')).with_suffix('.fd')
        if not original_firmware.is_file() or original_firmware.is_symlink():
            raise RuntimeError('Preserved working firmware is unavailable.')
        prior = {**prior, 'image': str(original), 'firmware': str(original_firmware)}
        prior.pop('ssh')
    image = Path(prior['image'])
    sessions = PROJECT.parent / 'testing/sessions'
    if (prior['phase'] != 'ready-for-encrypted-boot' or image.is_symlink() or
            not image.is_file() or not image.resolve().is_relative_to(sessions.resolve()) or
            image.stat().st_size != 16 * 1024**3):
        raise RuntimeError('Unexpected working image.')
    with (runtime / 'petalos-qemu.lock').open('a') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if subprocess.run(['fuser', str(image)], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode != 1:
            raise RuntimeError('Working image is busy or state is unknown.')
        for backing in Path('/sys/block').glob('loop*/loop/backing_file'):
            if Path(backing.read_text().strip()).resolve() == image.resolve():
                raise RuntimeError('Working image is attached.')
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        work = image.parent / ('ssh-' + stamp)
        work.mkdir(mode=0o700)
        clone = image.parent / f'encrypted-boot-{stamp}.img'
        firmware = image.parent / f'encrypted-OVMF-{stamp}.fd'
        root = work / 'module'; root.mkdir()
        def copy(source, relative, mode=0o644):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target); target.chmod(mode)
        source = PROJECT / 'tests/qemu-ssh'
        copy(source / '9999-petalos-qemu-ssh', 'usr/lib/live/config/9999-petalos-qemu-ssh', 0o755)
        copy(source / 'policy-rc.d', 'usr/share/petalos-qemu-ssh/policy-rc.d', 0o755)
        copy(source / 'sshd_config', 'etc/petalos-qemu-ssh/sshd_config')
        for unit in ('petalos-qemu-ssh.service', 'petalos-qemu-vsock.service'):
            copy(source / unit, 'etc/systemd/system/' + unit)
        auth = root / 'etc/petalos-qemu-ssh/authorized_keys'
        public = (KEYDIR / 'id_ed25519.pub').read_text().strip().split()
        if len(public) < 2 or public[0] != 'ssh-ed25519':
            raise RuntimeError('Unexpected dedicated public key.')
        auth.write_text('restrict ' + ' '.join(public[:2]) + '\n'); auth.chmod(0o644)
        for relative in ('etc/systemd/system/ssh.service', 'etc/systemd/system/ssh.socket',
                         'etc/systemd/system-generators/systemd-ssh-generator'):
            path = root / relative; path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to('/dev/null')
        packages = sorted((PROJECT.parent / 'testing/ssh-packages').glob('*.deb'))
        if len(packages) != 6:
            raise RuntimeError('Unexpected SSH package set.')
        for package in packages:
            copy(package, 'usr/share/petalos-qemu-ssh/packages/' + package.name)
        # The coordinator's restrictive umask protects host artifacts, but the
        # overlay's public system directories must preserve ordinary traversal.
        root.chmod(0o755)
        for directory in root.rglob('*'):
            if directory.is_dir() and not directory.is_symlink():
                directory.chmod(0o755)
        module = work / 'petalos-qemu-ssh.squashfs'
        subprocess.run(['mksquashfs', str(root), str(module), '-noappend', '-all-root',
                        '-comp', 'zstd', '-no-progress', '-processors', '4'], check=True)
        print('Preserving the working disk and cloning for SSH provisioning.', flush=True)
        subprocess.run(['qemu-img', 'convert', '-f', 'raw', '-O', 'raw', '-S', '4k',
                        str(image), str(clone)], check=True)
        shutil.copy2(prior['firmware'], firmware)
        public_output = image.parent / ('ssh-host-' + stamp + '.pub')
        subprocess.run(['sudo', '--', '/usr/bin/python3', '-B',
                        str(PROJECT / 'tests/provision-ssh-root.py'), str(clone),
                        prior['release'], str(module), str(public_output)], check=True)
        host = public_output.read_text().split()
        known = KEYDIR / 'known_hosts'
        known.write_text('petalos-qemu ' + ' '.join(host[:2]) + '\n'); known.chmod(0o600)
        state = {**prior, 'image': str(clone), 'firmware': str(firmware),
                 'ssh': {'cid': 42, 'port': 2222, 'key': str(KEYDIR / 'id_ed25519'),
                         'known_hosts': str(known), 'prior_image': str(image)}}
        temporary = statefile.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, indent=2)); temporary.replace(statefile)
        print('SSH clone ready; host identity is pinned before first connection.', flush=True)

if __name__ == '__main__':
    os.umask(0o077)
    try: main()
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
