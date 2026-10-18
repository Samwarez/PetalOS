#!/usr/bin/env python3
"""Build the public QEMU management layer; no host or guest private keys."""
from pathlib import Path
import shutil
import subprocess

PROJECT=Path(__file__).resolve().parents[1]

def build(work, public_key=None):
    root=work/'ssh-module-root';root.mkdir()
    source=PROJECT/'tests/qemu-ssh'
    def copy(origin,name,mode=0o644):
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(origin,target);target.chmod(mode)
    copy(source/'9999-petalos-qemu-ssh','usr/lib/live/config/9999-petalos-qemu-ssh',0o755)
    copy(source/'policy-rc.d','usr/share/petalos-qemu-ssh/policy-rc.d',0o755)
    copy(source/'sshd_config','etc/petalos-qemu-ssh/sshd_config')
    for name in ['petalos-qemu-ssh.service','petalos-qemu-vsock.service']:
        copy(source/name,'etc/systemd/system/'+name)
    public=(public_key or Path.home()/'.local/share/petalos-qemu/ssh/id_ed25519.pub').read_text().split()
    if len(public)<2 or public[0]!='ssh-ed25519':raise RuntimeError('Unexpected dedicated public key.')
    (root/'etc/petalos-qemu-ssh/authorized_keys').write_text('restrict '+' '.join(public[:2])+'\n')
    packages=sorted((PROJECT.parent/'testing/ssh-packages').glob('*.deb'))
    if len(packages)!=6:raise RuntimeError('Unexpected cached trixie SSH package set.')
    for package in packages:copy(package,'usr/share/petalos-qemu-ssh/packages/'+package.name)
    for name in ['etc/systemd/system/ssh.service','etc/systemd/system/ssh.socket','etc/systemd/system-generators/systemd-ssh-generator']:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.symlink_to('/dev/null')
    for path in [root,*root.rglob('*')]:
        if not path.is_symlink() and path.is_dir():path.chmod(0o755)
    (root/'etc/petalos-qemu-ssh/authorized_keys').chmod(0o644)
    module=work/'petalos-qemu-ssh.squashfs'
    subprocess.run(['mksquashfs',str(root),str(module),'-noappend','-all-root','-comp','zstd','-no-progress','-processors','4'],check=True)
    return module
