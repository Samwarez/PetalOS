#!/usr/bin/env python3
"""Preserve the current working guest; install public changes without a rebuild."""
from pathlib import Path
import argparse
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]

def prepare_layer(work, prior, packages=None):
    root=work/'module'
    root.mkdir()
    if packages is not None:
        packages=Path(packages)
        cache_root=PROJECT.parent/'testing/public-packages'
        if packages.is_symlink() or not packages.resolve().is_relative_to(cache_root.resolve()):
            raise RuntimeError('Unexpected public package cache.')
        entries=json.loads((packages/'manifest.json').read_text())
        spec=importlib.util.spec_from_file_location('package_cache',PROJECT/'tests/cache-wayland-test-packages.py')
        approved=importlib.util.module_from_spec(spec);spec.loader.exec_module(approved)
        if {entry['package']:entry['version'] for entry in entries} != approved.PACKAGES or len(entries)!=len(approved.PACKAGES):
            raise RuntimeError('Package set differs from approved trixie versions.')
        for entry in entries:
            if entry['file'] != entry['package']+'.deb':
                raise RuntimeError('Unexpected package archive path.')
            archive=packages/entry['file']
            if archive.is_symlink() or hashlib.sha256(archive.read_bytes()).hexdigest()!=entry['sha256']:
                raise RuntimeError('Public package archive integrity failure.')
            subprocess.run(['dpkg-deb','-x',str(archive),str(root)],check=True)
    shutil.copytree(PROJECT/'config/includes.chroot',root,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    hook=root/'usr/lib/live/config/9999-petalos-qemu-ssh'
    hook.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(PROJECT/'tests/qemu-ssh/9999-petalos-qemu-ssh',hook)
    hook.chmod(0o755)
    diagnostic=root/'usr/share/petalos-qemu-ssh/admin-status.py'
    diagnostic.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(PROJECT/'tests/qemu-ssh/admin-status.py',diagnostic)
    units=root/'etc/systemd/system';units.mkdir(parents=True,exist_ok=True)
    (units/'petalos-qemu-admin-status.service').write_text('[Unit]\nDescription=QEMU-only boolean administrator boot diagnostic\nAfter=live-config.service portable-admin-setup.service\nConditionKernelCommandLine=petalos_qemu_ssh=1\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 -I /usr/share/petalos-qemu-ssh/admin-status.py\nUMask=0022\n')
    wanted=units/'multi-user.target.wants';wanted.mkdir(parents=True,exist_ok=True)
    (wanted/'petalos-qemu-admin-status.service').symlink_to('../petalos-qemu-admin-status.service')
    # The existing SSH layer is preserved; override only its public account policy.
    target=root/'etc/petalos-qemu-ssh/sshd_config';target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(PROJECT/'tests/qemu-ssh/sshd_config',target)
    units=root/'etc/systemd/system';units.mkdir(parents=True,exist_ok=True)
    for name in ('tor.service','tor@.service','tor@default.service','avahi-daemon.service',
                 'avahi-daemon.socket','cups.service','cups.socket','cups.path',
                 'cups-browsed.service','ssh.service','ssh.socket'):
        path=units/name
        if path.exists() or path.is_symlink():raise RuntimeError('Unexpected source unit at mask destination.')
        path.symlink_to('/dev/null')
    for parent,name in [('timers.target.wants','portable-telemetry.timer'),('multi-user.target.wants','portable-apparmor.service'),('graphical.target.wants','portable-admin-setup.service')]:
        directory=units/parent;directory.mkdir(parents=True,exist_ok=True)
        (directory/name).symlink_to('../'+name)
    for path in [root,*root.rglob('*')]:
        if path.is_symlink():continue
        if path.is_dir():path.chmod(0o755)
        elif path.is_file():
            mode = 0o440 if path.parent == root/'etc/sudoers.d' else (0o755 if path.stat().st_mode&0o111 else 0o644)
            path.chmod(mode)
        else:raise RuntimeError('Unexpected nonregular public build input.')
    module=work/'petalos-wayland-test-v5.squashfs'
    subprocess.run(['mksquashfs',str(root),str(module),'-noappend','-all-root','-comp','zstd','-no-progress','-processors','4'],check=True)
    manifest={'base_release':prior['release'],'module_sha256':hashlib.sha256(module.read_bytes()).hexdigest(),
              'source_image':prior['image'], 'packages':str(packages) if packages else None,'scope':'public OS account and hardening configuration; no personal credentials'}
    (work/'manifest.json').write_text(json.dumps(manifest,indent=2))
    return module

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packages',type=Path)
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--module',type=Path)
    args=parser.parse_args()
    if args.prepare_only and args.module:raise RuntimeError('Choose preparation or installation.')

    if os.geteuid()==0:raise RuntimeError('Run this coordinator as Sam.')
    runtime=Path(f'/run/user/{os.getuid()}')
    statefile=runtime/'petalos-encrypted-test.json'
    prior=json.loads(statefile.read_text())
    image=Path(prior['image']);sessions=PROJECT.parent/'testing/sessions'
    if (prior['phase']!='ready-for-encrypted-boot' or not prior.get('ssh') or
        image.is_symlink() or not image.is_file() or
        not image.resolve().is_relative_to(sessions.resolve()) or image.stat().st_size!=16*1024**3):
        raise RuntimeError('Unexpected working encrypted guest.')
    if args.prepare_only:
        if args.packages is None:raise RuntimeError('Cold-boot preparation needs the approved package cache.')
        spec=importlib.util.spec_from_file_location('rebuild',PROJECT/'tests/rebuild-release.py')
        rebuild=importlib.util.module_from_spec(spec);spec.loader.exec_module(rebuild)
        rebuild.validate_inputs(PROJECT/'config')
        stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        work=image.parent/('config-'+stamp);work.mkdir(mode=0o700)
        print('Prepared public cold-boot layer:',prepare_layer(work,prior,args.packages),flush=True)
        return
    with (runtime/'petalos-qemu.lock').open('a') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (runtime/'petalos-qemu-monitor.sock').exists():raise RuntimeError('QEMU monitor still present.')
        if subprocess.run(['fuser',str(image)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode!=1:
            raise RuntimeError('Working disk is busy or its state is unknown.')
        for backing in Path('/sys/block').glob('loop*/loop/backing_file'):
            if Path(backing.read_text().strip()).resolve()==image.resolve():raise RuntimeError('Working disk is attached.')
        spec=importlib.util.spec_from_file_location('rebuild',PROJECT/'tests/rebuild-release.py')
        rebuild=importlib.util.module_from_spec(spec);spec.loader.exec_module(rebuild)
        rebuild.validate_inputs(PROJECT/'config')
        stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        work=image.parent/('config-'+stamp);work.mkdir(mode=0o700)
        if args.module:
            module=Path(args.module)
            if module.is_symlink() or module.name not in ('petalos-config.squashfs','petalos-wayland-test.squashfs','petalos-wayland-test-v2.squashfs','petalos-wayland-test-v3.squashfs','petalos-wayland-test-v4.squashfs','petalos-wayland-test-v5.squashfs') or not module.resolve().is_relative_to(image.parent.resolve()):
                raise RuntimeError('Unexpected prepared configuration layer.')
            manifest=json.loads((module.parent/'manifest.json').read_text())
            if manifest['source_image']!=str(image) or manifest['base_release']!=prior['release'] or hashlib.sha256(module.read_bytes()).hexdigest()!=manifest['module_sha256']:
                raise RuntimeError('Prepared layer integrity or base identity mismatch.')
        else:
            module=prepare_layer(work,prior,args.packages)
        clone=image.parent/f'encrypted-boot-{stamp}.img';firmware=image.parent/f'encrypted-OVMF-{stamp}.fd'
        transfer=runtime/'petalos-config-transfer.json'
        candidate={'phase':'cloning','image':str(clone),'prior_image':str(image),'module':str(module)}
        def update(phase):
            candidate['phase']=phase;temp=transfer.with_suffix('.tmp');temp.write_text(json.dumps(candidate,indent=2));temp.replace(transfer)
        update('cloning')
        subprocess.run(['qemu-img','convert','-f','raw','-O','raw','-S','4k',str(image),str(clone)],check=True)
        shutil.copy2(prior['firmware'],firmware)
        update('awaiting-authentication')
        print('Working disk preserved. Enter host sudo authentication, then the QEMU SYSTEM-volume password.',flush=True)
        try:
            subprocess.run(['sudo','--','/usr/bin/python3','-B',str(PROJECT/'tests/provision-config-root.py'),str(clone),prior['release'],str(module)],check=True)
            state={**prior,'image':str(clone),'firmware':str(firmware),'configuration_module':str(module),
                   'ssh':{**prior['ssh'],'user':'Petal','prior_image':str(image)}}
            temporary=statefile.with_suffix('.tmp');temporary.write_text(json.dumps(state,indent=2));temporary.replace(statefile)
            update('complete')
            print('Updated configuration clone ready to boot. This terminal may now close.',flush=True)
        except BaseException:
            update('failed');raise

if __name__=='__main__':
    os.umask(0o077)
    try:main()
    except Exception as error:
        print(str(error),file=sys.stderr);sys.exit(1)
