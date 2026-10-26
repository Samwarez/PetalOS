#!/usr/bin/env python3
"""Format only a newly allocated regular audit file, with pinned loop identity."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
BASE = PROJECT.parent / 'testing/audit'


def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(1024**2), b''):h.update(block)
    return h.hexdigest()


def run(args, payload=None, allowed=(0,)):
    r = subprocess.run(args, input=payload, stdin=subprocess.DEVNULL if payload is None else None,
                       capture_output=True, timeout=180)
    if r.returncode not in allowed:
        raise RuntimeError('Tool failed; raw output suppressed.')
    return r


def main():
    assert os.geteuid() == 0 and len(sys.argv) == 2
    uid = int(os.environ['SUDO_UID']); gid = int(os.environ['SUDO_GID'])
    statefile = Path(sys.argv[1])
    assert statefile.resolve(strict=True) == statefile and statefile.name == 'state.json'
    work = statefile.parent
    assert work.parent == BASE and re.fullmatch(r'\d{8}-\d{6}-\d+', work.name)
    assert work.stat().st_uid == uid and not work.stat().st_mode & 0o077
    s = json.loads(statefile.read_text())
    assert s['phase'] == 'awaiting-provisioning' and s['scope'] == 'disposable-audit-only'
    assert s['directory'] == str(work)
    image = work / 'audit.img'; assert s['image'] == str(image)
    assert not image.is_symlink() and image.is_file()
    initial = image.stat()
    assert initial.st_uid == uid and initial.st_size == 16 * 1024**3
    assert initial.st_blocks < 1024  # Refuse any populated image, including a failed prior attempt.
    assert run(['/usr/bin/fuser', str(image)], allowed=(1,)).returncode == 1
    for p in Path('/sys/block').glob('loop*/loop/backing_file'):
        assert Path(p.read_text().strip()).resolve() != image.resolve()
    credentials = work / 'credentials.json'
    assert not credentials.is_symlink() and credentials.stat().st_uid == uid
    assert stat.S_IMODE(credentials.stat().st_mode) == 0o600
    secrets = json.loads(credentials.read_text())
    assert set(secrets) == {'system', 'administrator', 'private'} and len(set(secrets.values())) == 3
    assert all(re.fullmatch(r'Audit-[0-9a-f]{24}', v) for v in secrets.values())
    release = Path(s['release'])
    assert release.resolve(strict=True) == release and release.parent == PROJECT.parent / 'releases'
    manifest = json.loads((release / 'manifest.json').read_text())
    sources = {}
    for name in ('vmlinuz', 'initrd.img', 'filesystem.squashfs'):
        rel = 'binary/live/' + name; p = release / 'build' / rel
        assert not p.is_symlink() and digest(p) == manifest[rel]['sha256']
        sources[name] = p
    module = work / 'petalos-qemu-ssh.squashfs'
    assert s['ssh_module'] == str(module) and not module.is_symlink()
    assert digest(module) == s['ssh_module_sha256']
    profile = None
    if s.get('vpn_source'):
        source = Path(s['vpn_source'])
        assert source.resolve(strict=True) == source and source.stat().st_uid == uid
        spec = importlib.util.spec_from_file_location('vpn_profiles', PROJECT / 'config/includes.chroot/usr/local/lib/portable/vpn_profiles.py')
        vpn = importlib.util.module_from_spec(spec);spec.loader.exec_module(vpn)
        profile = vpn.serialize(vpn.read_profile(source, protected=False))
    assets = PROJECT.parent / 'provisioning/TorBrowser/verified-15.0.25'
    archive = assets / 'tor-browser-linux-x86_64-15.0.25.tar.xz'
    signature = assets / (archive.name + '.asc')
    assert not archive.is_symlink() and not signature.is_symlink()
    run(['/usr/bin/gpgv', '--keyring', str(PROJECT / 'config/includes.chroot/usr/local/share/portable/tor-browser-developers.keyring'),
         str(signature), str(archive)])
    loop = None; mappings = []; mounts = []
    temporary = Path(tempfile.mkdtemp(prefix='petalos-empty-audit-', dir='/run'))

    def status(phase):
        s['phase'] = phase; statefile.write_text(json.dumps(s, indent=2));os.chown(statefile, uid, gid)
        print('Audit stage:', phase, flush=True)

    def identity():
        now = image.stat()
        assert (now.st_dev, now.st_ino, now.st_size) == (initial.st_dev, initial.st_ino, initial.st_size)
        assert Path('/sys/class/block', Path(loop).name, 'loop/backing_file').read_text().strip() == str(image)

    def partition(n):
        identity(); p = Path(loop + 'p' + str(n))
        assert Path('/sys/class/block', p.name).resolve().parent.name == Path(loop).name
        return p

    def mounted(device, name, fs):
        target = temporary / name; target.mkdir()
        run(['/usr/bin/mount', '-t', fs, '-o', 'nodev,nosuid,noexec', str(device), str(target)])
        mounts.append(target);return target

    try:
        status('creating-new-partition-table')
        loop = run(['/usr/sbin/losetup', '--find', '--show', '--partscan', str(image)]).stdout.decode().strip()
        identity()
        run(['/usr/sbin/sgdisk', '--clear', '--new=1:2048:+2M', '--typecode=1:EF02',
             '--new=2:0:+1G', '--typecode=2:EF00', '--new=3:0:+4G', '--typecode=3:8309',
             '--new=4:0:0', '--typecode=4:8309', loop])
        run(['/usr/sbin/partprobe', loop]);run(['/usr/bin/udevadm', 'settle', '--timeout=10'])
        run(['/usr/sbin/mkfs.vfat', '-F', '32', '-n', 'PORT_BOOT', str(partition(2))])
        devices = {}
        for number, kind, label, fslabel in [(3, 'system', 'PORTABLE_SYSTEM', 'LIVE_SYSTEM'),
                                            (4, 'private', 'PORTABLE_DATA', 'LIVE_DATA')]:
            status('formatting-fresh-' + kind)
            dev = partition(number); password = secrets[kind].encode()
            run(['/usr/sbin/cryptsetup', 'luksFormat', '--batch-mode', '--type', 'luks2',
                 '--label', label, '--pbkdf', 'argon2id', '--pbkdf-memory', '262144',
                 '--pbkdf-parallel', '2', '--iter-time', '2000', '--key-file', '-', str(dev)], password)
            mapper = 'petal_audit_' + kind + '_' + work.name[-6:]
            assert not Path('/dev/mapper', mapper).exists()
            run(['/usr/sbin/cryptsetup', 'open', '--key-file', '-', str(dev), mapper], password)
            mappings.append(mapper); mapped = Path('/dev/mapper', mapper)
            info = mapped.stat()
            slaves = list(Path(f'/sys/dev/block/{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}/slaves').iterdir())
            assert len(slaves) == 1 and slaves[0].name == dev.name
            run(['/usr/sbin/mkfs.ext4', '-q', '-L', fslabel, str(mapped)])
            devices[kind] = mapped
        status('checking-credential-separation')
        for n, wrong in [(3, 'private'), (4, 'system'), (3, 'administrator'), (4, 'administrator')]:
            assert run(['/usr/sbin/cryptsetup', 'open', '--test-passphrase', '--key-file', '-',
                        str(partition(n))], secrets[wrong].encode(), allowed=(2,)).returncode == 2
        status('installing-verified-public-release')
        boot = mounted(partition(2), 'boot', 'vfat')
        system = mounted(devices['system'], 'system', 'ext4')
        private = mounted(devices['private'], 'private', 'ext4')
        os.chown(private, 1000, 1000);private.chmod(0o700)
        boot_payload = boot / 'live'
        live_payload = system / 'live'
        generation = None
        if s.get('generation_boot'):
            metadata = {'format': 1, 'os': {name: digest(p) for name, p in sources.items()},
                        'modules': {module.name: digest(module)}}
            encoded = json.dumps(metadata, sort_keys=True, separators=(',', ':')).encode()
            generation = hashlib.sha256(encoded).hexdigest()[:24]
            relative = Path('petalos/releases') / generation
            boot_payload = boot / relative
            live_payload = system / relative / 'live'
            for directory in (boot_payload, live_payload.parent):
                directory.mkdir(parents=True)
                (directory / 'generation.json').write_bytes(encoded)
            s['generation'] = generation
        boot_payload.mkdir(parents=True, exist_ok=True)
        live_payload.mkdir(parents=True, exist_ok=True)
        for name in ('vmlinuz', 'initrd.img'):
            shutil.copyfile(sources[name], boot_payload / name)
            assert digest(boot_payload / name) == digest(sources[name])
        for src in (sources['filesystem.squashfs'], module):
            shutil.copyfile(src, live_payload / src.name)
            assert digest(live_payload / src.name) == digest(src)
        (live_payload / 'filesystem.module').write_text('filesystem.squashfs\npetalos-qemu-ssh.squashfs\n')
        selected = system / '.petalos-state'
        selected.mkdir(mode=0o750);os.chown(selected, 0, 1000)
        for name in ['Network', 'Network/Profiles', 'Desktop', 'Applications', 'Applications/TorBrowser']:
            p = selected / name;p.mkdir(mode=0o700);os.chown(p, 1000, 1000)
        if profile is not None:
            p = selected / 'Network/Profiles/audit.conf';p.write_text(profile);p.chmod(0o600);os.chown(p, 1000, 1000)
            p = selected / 'Network/selected-profile';p.write_text('audit\n');p.chmod(0o600);os.chown(p, 1000, 1000)
            s['vpn_provisioned'] = True
        for source in (archive, signature):
            target = selected / 'Applications/TorBrowser' / source.name
            shutil.copyfile(source, target);target.chmod(0o600);os.chown(target, 1000, 1000)
            assert digest(target) == digest(source)
        auth = system / '.petalos-auth';auth.mkdir(mode=0o700)
        salt = 'rounds=100000$' + os.urandom(8).hex()
        hashed = run(['/usr/bin/openssl', 'passwd', '-6', '-salt', salt, '-stdin'],
                     secrets['administrator'].encode() + b'\n').stdout
        credential = auth / 'root-admin.hash';credential.write_bytes(hashed);credential.chmod(0o600)
        host = system / '.petalos-qemu-ssh';host.mkdir(mode=0o700)
        run(['/usr/bin/ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'petalos-disposable-audit-host',
             '-f', str(host / 'ssh_host_ed25519_key')])
        pub = (host / 'ssh_host_ed25519_key.pub').read_text().split()
        known = work / 'known_hosts';known.write_text('petalos-audit ' + ' '.join(pub[:2]) + '\n')
        known.chmod(0o600);os.chown(known, uid, gid)
        efi = boot / 'EFI/BOOT';efi.mkdir(parents=True)
        for src, name in [('/usr/lib/shim/shimx64.efi.signed', 'BOOTX64.EFI'),
                          ('/usr/lib/shim/mmx64.efi.signed', 'mmx64.efi'),
                          ('/usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed', 'grubx64.efi')]:
            shutil.copyfile(src, efi / name)
        grub = '''set timeout=1
set default=0
search --no-floppy --label PORT_BOOT --set=root
menuentry 'PetalOS disposable audit VM' {
 linux /live/vmlinuz boot=live components username=Petal hostname=PetalOS toram swap=false init_on_alloc=1 init_on_free=1 live-media=/dev/mapper/portable_system petalos_qemu_ssh=1 console=tty0 console=ttyS0,115200
 initrd /live/initrd.img
}
'''
        if generation is not None:
            prefix = '/petalos/releases/' + generation
            grub = grub.replace('/live/vmlinuz', prefix + '/vmlinuz').replace(
                '/live/initrd.img', prefix + '/initrd.img').replace(
                'live-media=/dev/mapper/portable_system',
                'live-media=/dev/mapper/portable_system live-media-path=' + prefix + '/live')
        if s.get('graphical_boot'):
            assert generation is not None
            grub=grub.replace('set timeout=1','set timeout=5').replace(' console=ttyS0,115200','')
            grub=grub.replace('console=tty0','console=tty0 quiet splash')
            grub=grub.replace('PetalOS disposable audit VM','PetalOS Phase 2 preview')
        for p in (efi / 'grub.cfg', boot / 'EFI/debian/grub.cfg', boot / 'boot/grub/grub.cfg'):
            p.parent.mkdir(parents=True, exist_ok=True);p.write_text(grub)
        if s.get('graphical_boot'):
            spec=importlib.util.spec_from_file_location('boot_branding',PROJECT/'tests/boot_branding.py')
            branding=importlib.util.module_from_spec(spec);spec.loader.exec_module(branding)
            style=branding.verified(release/'build/binary/boot/grub/petalos');assert style is not None
            configs=[(p,p.read_text()) for p in (efi/'grub.cfg',boot/'EFI/debian/grub.cfg',boot/'boot/grub/grub.cfg')]
            installed=branding.install(boot,style,configs,identity=identity)
            assert all(digest(path)==sha for path,sha in installed.items())
        status('flushing-and-detaching')
        for target in mounts:run(['/usr/bin/sync', '-f', str(target)])
    except BaseException:
        status('failed')
        raise
    finally:
        for target in reversed(mounts):run(['/usr/bin/umount', str(target)])
        for mapper in reversed(mappings):run(['/usr/sbin/cryptsetup', 'close', mapper])
        if loop:identity();run(['/usr/sbin/losetup', '-d', loop])
        for p in temporary.iterdir():p.rmdir()
        temporary.rmdir()
    with image.open('rb') as f:os.fsync(f.fileno())
    status('ready-for-audit-boot')


if __name__ == '__main__':
    os.umask(0o077)
    try:main()
    except BaseException as error:
        print('Audit provisioner stopped: ' + type(error).__name__ + '; no physical-media operation was requested.', file=sys.stderr)
        sys.exit(1)
