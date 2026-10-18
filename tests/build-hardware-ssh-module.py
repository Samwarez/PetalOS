#!/usr/bin/env python3
"""Public optional hardware management layer: dedicated public key only."""
from pathlib import Path
import os
import shutil
import subprocess

PROJECT = Path(__file__).resolve().parents[1]
KEYDIR = Path.home() / '.local/share/petalos-hardware/ssh'


def build(work):
    assert os.geteuid() != 0
    KEYDIR.mkdir(parents=True, mode=0o700, exist_ok=True)
    assert not KEYDIR.is_symlink() and KEYDIR.stat().st_uid == os.getuid()
    KEYDIR.chmod(0o700)
    key = KEYDIR / 'id_ed25519'
    if not key.exists():
        assert not key.with_suffix('.pub').exists()
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
    assert not key.is_symlink() and key.stat().st_uid == os.getuid()
    key.chmod(0o600)
    public = key.with_suffix('.pub').read_text().split()
    assert len(public) >= 2 and public[0] == 'ssh-ed25519'
    root = work / 'module-root'; root.mkdir(mode=0o755)
    def copy(source, destination, mode=0o644):
        target = root / destination; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target); target.chmod(mode)
    source = PROJECT / 'tests/hardware-ssh'
    copy(source / 'management.py', 'usr/local/lib/petalos-hardware-ssh/management.py')
    copy(source / '9998-petalos-hardware-ssh', 'usr/lib/live/config/9998-petalos-hardware-ssh', 0o755)
    copy(source / 'sshd_config', 'etc/petalos-hardware-ssh/sshd_config')
    copy(source / 'petalos-hardware-ssh.service', 'etc/systemd/system/petalos-hardware-ssh.service')
    copy(PROJECT / 'tests/qemu-ssh/policy-rc.d', 'usr/share/petalos-hardware-ssh/policy-rc.d', 0o755)
    packages = sorted((PROJECT.parent / 'testing/ssh-packages').glob('*.deb'))
    assert len(packages) == 6
    for package in packages: copy(package, 'usr/share/petalos-hardware-ssh/packages/' + package.name)
    authorized = root / 'etc/petalos-hardware-ssh/authorized_keys'
    authorized.write_text('restrict ' + ' '.join(public[:2]) + '\n')
    authorized.chmod(0o644)
    for name in ('etc/systemd/system/ssh.service', 'etc/systemd/system/ssh.socket',
                 'etc/systemd/system-generators/systemd-ssh-generator'):
        target = root / name; target.parent.mkdir(parents=True, exist_ok=True); target.symlink_to('/dev/null')
    for p in (root, *root.rglob('*')):
        if p.is_dir() and not p.is_symlink(): p.chmod(0o755)
    module = work / 'petalos-hardware-ssh.squashfs'
    subprocess.run(['mksquashfs', str(root), str(module), '-noappend', '-all-root',
                    '-comp', 'zstd', '-no-progress', '-processors', '4'], check=True)
    return module
