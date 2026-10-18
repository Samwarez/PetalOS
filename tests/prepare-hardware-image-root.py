#!/usr/bin/python3 -I
"""Prepare only a detached regular-file hardware candidate; never a card."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import traceback

BASE = Path('/home/sam/portable-live/testing/sessions')
STAGE = 'initial validation'


def stage(name):
    global STAGE
    STAGE = name
    print('Preparation stage: ' + name, flush=True)


def run(command, **kwargs):
    r = subprocess.run(command, capture_output=True, timeout=300, **kwargs)
    if r.returncode:
        if command[0] == '/usr/sbin/resize2fs':
            # This tool reports filesystem geometry/errors, never file contents
            # or credentials. Limit output to its bounded public error message.
            print('resize2fs diagnostic: ' + r.stderr.decode(errors='replace')[:2048], flush=True)
        raise RuntimeError('Tool ' + Path(command[0]).name + ' exited ' + str(r.returncode))
    return r.stdout.decode().strip()


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()


def main():
    assert os.geteuid() == 0 and len(sys.argv) == 2
    image = Path(sys.argv[1])
    assert image.is_file() and not image.is_symlink() and image.resolve().is_relative_to(BASE)
    assert re.fullmatch(r'hardware-\d{8}-\d{6}-\d+\.img', image.name)
    assert image.stat().st_uid == int(os.environ['SUDO_UID'])
    module = image.parent / 'petalos-hardware-ssh.squashfs'
    assert module.is_file() and not module.is_symlink()
    assert subprocess.run(['fuser', str(image)], capture_output=True).returncode == 1
    for p in Path('/sys/block').glob('loop*/loop/backing_file'):
        assert Path(p.read_text().strip()).resolve() != image.resolve()
    system_name, data_name = 'petal_hardware_system', 'petal_hardware_data'
    assert not any(Path('/dev/mapper/' + n).exists() for n in (system_name, data_name))
    # Capacity was recorded from the card by the unprivileged coordinator.
    metadata = json.loads((image.parent / 'preparation.json').read_text())
    size = metadata['target_size']
    assert type(size) is int and 230 * 1024**3 < size < 260 * 1024**3 and size % 512 == 0
    assert image.stat().st_size in (16 * 1024**3, size)
    initial = image.stat()
    loop = None; opened = []; mounted = []
    work = Path(tempfile.mkdtemp(prefix='petalos-hardware-', dir='/run'))
    public = image.parent / 'hardware-host.pub'
    assert not public.exists()
    try:
        stage('expand disposable image partition table')
        with image.open('r+b') as f: f.truncate(size)
        run(['/usr/sbin/sgdisk', '-e', str(image)])
        table = json.loads(run(['/usr/sbin/sfdisk', '--json', str(image)]))['partitiontable']
        parts = table['partitions']; assert table['label'] == 'gpt' and len(parts) == 4
        assert parts[1]['size'] == 2097152 and parts[2]['size'] == 8388608
        old = parts[3]
        run(['/usr/sbin/sgdisk', '--delete=4', '--new=4:' + str(old['start']) + ':0',
             '--typecode=4:8300', '--partition-guid=4:' + old['uuid'], str(image)])
        run(['/usr/sbin/sgdisk', '--verify', str(image)])
        stage('attach disposable image')
        loop = run(['/usr/sbin/losetup', '--find', '--show', '--partscan', str(image)])
        run(['/usr/bin/udevadm', 'settle', '--timeout=10'])
        def verify():
            assert image.stat().st_ino == initial.st_ino and image.stat().st_dev == initial.st_dev
            assert image.stat().st_size == size
            assert Path(Path('/sys/class/block') / Path(loop).name / 'loop/backing_file').read_text().strip() == str(image)
        def partition(n):
            verify(); p = Path(loop + 'p' + str(n))
            assert (Path('/sys/class/block') / p.name).resolve().parent.name == Path(loop).name
            return p
        def tag(p, key): return run(['/usr/sbin/blkid', '-s', key, '-o', 'value', str(p)])
        for n, label in ((2, 'PORT_BOOT'), (3, 'PORTABLE_SYSTEM'), (4, 'PORTABLE_DATA')):
            stage('validate partition ' + str(n) + ' identity')
            assert tag(partition(n), 'LABEL') == label
        def unlock(n, name, label):
            stage('unlock candidate ' + label)
            verify()
            print('Enter the existing QEMU ' + label + ' passphrase for the NEW image only.', flush=True)
            subprocess.run(['/usr/sbin/cryptsetup', 'open', str(partition(n)), name], check=True)
            opened.append(name)
            mapper = Path('/dev/mapper/' + name); dev = mapper.stat().st_rdev
            slaves = Path(f'/sys/dev/block/{os.major(dev)}:{os.minor(dev)}/slaves')
            assert [p.name for p in slaves.iterdir()] == [partition(n).name]
            assert tag(mapper, 'TYPE') == 'ext4'
            return mapper
        system = unlock(3, system_name, 'SYSTEM')
        data = unlock(4, data_name, 'distinct Private')
        stage('check independent Private key-slot metadata')
        luks = json.loads(run(['/usr/sbin/cryptsetup', 'luksDump', '--dump-json-metadata', str(partition(4))]))
        assert set(luks['keyslots']) == {'0'} and luks['keyslots']['0']['kdf']['type'] == 'argon2id'
        stage('check Private filesystem before expansion')
        fsck = subprocess.run(['/usr/sbin/e2fsck', '-f', '-p', str(data)], capture_output=True, timeout=300)
        assert fsck.returncode in (0, 1)
        stage('expand Private filesystem')
        run(['/usr/sbin/resize2fs', str(data)])
        stage('verify expanded Private filesystem')
        fsck = subprocess.run(['/usr/sbin/e2fsck', '-fn', str(data)], capture_output=True, timeout=300)
        assert fsck.returncode == 0
        def mount(device, name, kind):
            verify(); p = work / name; p.mkdir()
            run(['/usr/bin/mount', '-t', kind, '-o', 'nodev,nosuid,noexec,noatime', str(device), str(p)])
            mounted.append(p); return p
        stage('mount candidate boot and SYSTEM')
        boot = mount(partition(2), 'boot', 'vfat')
        system = mount(system, 'system', 'ext4')
        stage('verify obsolete key absent and selected modules')
        assert not (system / '.portable-keys/data.key').exists()
        live = system / 'live'
        assert (live / 'filesystem.module').read_text().split() == ['filesystem.squashfs', 'petalos-qemu-ssh.squashfs']
        stage('install public hardware management module')
        target = live / module.name; assert not target.exists()
        shutil.copyfile(module, target); target.chmod(0o644)
        assert digest(module) == digest(target)
        stage('create encrypted hardware host identity')
        folder = system / '.petalos-state/.hardware-ssh'; assert not folder.exists()
        folder.mkdir(mode=0o700)
        host = folder / 'ssh_host_ed25519_key'
        run(['/usr/bin/ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(host)])
        shutil.copyfile(host.with_suffix('.pub'), public)
        os.chown(public, int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID'])); public.chmod(0o600)
        (live / 'filesystem.module').write_text('filesystem.squashfs\npetalos-hardware-ssh.squashfs\n')
        stage('select hardware boot configuration')
        configs = list(boot.rglob('grub.cfg')); changed = 0
        for config in configs:
            assert not config.is_symlink()
            content = config.read_text()
            if 'live-media=/dev/mapper/portable_system' not in content: continue
            output = []
            for line in content.splitlines():
                words = line.split()
                if words and words[0] in ('linux', 'linuxefi'):
                    assert {'toram', 'swap=false', 'init_on_alloc=1', 'init_on_free=1'} <= set(words)
                    assert not any(w.startswith('petalos_hardware_ssh=') for w in words)
                    line = ' '.join(w for w in words if not w.startswith('petalos_qemu_ssh=')) + ' petalos_hardware_ssh=1'
                    changed += 1
                output.append(line)
            config.write_text('\n'.join(output) + '\n')
        assert changed > 0
        stage('install signed removable EFI boot chain')
        # QEMU source disks can contain grub-install's unsigned fallback.
        # Hardware candidates require the signed Debian shim -> GRUB chain.
        efi_files = {
            'grubx64.efi': Path('/usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed'),
            'mmx64.efi': Path('/usr/lib/shim/mmx64.efi.signed'),
            'BOOTX64.EFI': Path('/usr/lib/shim/shimx64.efi.signed')}
        for source in [*efi_files.values(), boot / 'live/vmlinuz']:
            checked = subprocess.run(['/usr/bin/sbverify', '--list', str(source)], capture_output=True, text=True)
            assert checked.returncode == 0 and 'signature 1' in checked.stdout
        uuid = tag(partition(2), 'UUID'); assert re.fullmatch('[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}', uuid)
        redirect = 'search --no-floppy --fs-uuid --set=root ' + uuid + '\nset prefix=($root)/boot/grub\nconfigfile $prefix/grub.cfg\n'
        for directory in (boot / 'EFI/BOOT', boot / 'EFI/debian'):
            assert not directory.is_symlink(); directory.mkdir(parents=True, exist_ok=True)
            (directory / 'grub.cfg').write_text(redirect)
        for name, source in efi_files.items():
            destination = boot / 'EFI/BOOT' / name
            assert not destination.is_symlink()
            shutil.copyfile(source, destination)
            assert digest(source) == digest(destination)
        run(['/usr/bin/sync', '-f', str(system)]); run(['/usr/bin/sync', '-f', str(boot)])
        print('Hardware image prepared: Private expanded, independent slot retained, public management layer installed.', flush=True)
    finally:
        for p in reversed(mounted): run(['/usr/bin/umount', str(p)])
        for name in reversed(opened): run(['/usr/sbin/cryptsetup', 'close', name])
        if loop: run(['/usr/sbin/losetup', '--detach', loop])
        for p in work.iterdir(): p.rmdir()
        work.rmdir()
    print('All preparation mounts and mappings closed. Physical card untouched.', flush=True)


if __name__ == '__main__':
    os.umask(0o077)
    try: main()
    except Exception as error:
        frame = traceback.extract_tb(error.__traceback__)[-1]
        print('Failed stage: ' + STAGE + '; exception ' + type(error).__name__ +
              '; source ' + Path(frame.filename).name + ':' + str(frame.lineno), flush=True)
        if isinstance(error, RuntimeError):
            # Only our fixed tool/exit summary; never command arguments/output.
            message = str(error)
            if re.fullmatch(r'Tool [A-Za-z0-9_.-]+ exited -?\d+', message):
                print(message, flush=True)
        print('Hardware image preparation stopped; source disk and physical card remain untouched.', flush=True)
        raise SystemExit(1)
