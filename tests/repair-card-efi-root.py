#!/usr/bin/python3 -I
"""Repair only the identified development card's public EFI boot chain."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import traceback

spec = importlib.util.spec_from_file_location('installer', Path(__file__).with_name('install-hardware-card-root.py'))
i = importlib.util.module_from_spec(spec); spec.loader.exec_module(i)


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    assert os.geteuid() == 0 and int(os.environ['SUDO_UID']) == 1000
    statefile = Path('/run/user/1000/petalos-efi-repair.json')
    state = json.loads(statefile.read_text()); assert state['phase'] == 'tested-ready'
    bundle = Path(state['bundle'])
    assert bundle.is_dir() and not bundle.is_symlink()
    assert bundle.resolve().is_relative_to(Path('/home/sam/portable-live/provisioning/EFI'))
    manifest = json.loads((bundle / 'manifest.json').read_text())
    names = ['EFI/BOOT/grubx64.efi', 'EFI/BOOT/mmx64.efi', 'EFI/BOOT/grub.cfg',
             'EFI/debian/grub.cfg', 'EFI/BOOT/BOOTX64.EFI']
    assert set(manifest['files']) == set(names) and manifest['secure_boot_test_passed'] is True
    for name in names:
        p = bundle / name; assert not p.is_symlink() and digest(p) == manifest['files'][name]
        if name.lower().endswith('.efi'):
            r = subprocess.run(['/usr/bin/sbverify', '--list', str(p)], capture_output=True, text=True)
            assert r.returncode == 0 and 'signature 1' in r.stdout
    device, identity = i.check_card(require_original_uuids=False)
    boot = Path(str(i.CARD) + '-part2').resolve(strict=True)
    assert (Path('/sys/class/block') / boot.name).resolve().parent.name == device.name
    assert i.output(['/usr/sbin/blkid', '-p', '-s', 'TYPE', '-o', 'value', str(boot)]) == 'vfat'
    assert i.output(['/usr/sbin/blkid', '-p', '-s', 'UUID', '-o', 'value', str(boot)]) == manifest['boot_uuid']
    work = Path(tempfile.mkdtemp(prefix='petalos-efi-repair-', dir='/run')); mounted = False
    backup = bundle / 'before-card-repair'; assert not backup.exists(); backup.mkdir(mode=0o700)
    try:
        subprocess.run(['/usr/bin/mount', '-t', 'vfat', '-o', 'nodev,nosuid,noexec', str(boot), str(work)], check=True)
        mounted = True
        assert i.CARD.stat().st_rdev == identity
        assert i.output(['/usr/bin/findmnt', '-n', '-o', 'MAJ:MIN', '--mountpoint', str(work)]) == f'{os.major(boot.stat().st_rdev)}:{os.minor(boot.stat().st_rdev)}'
        assert digest(work / 'EFI/BOOT/BOOTX64.EFI') == manifest['old_loader_sha256']
        assert digest(work / 'boot/grub/grub.cfg') == manifest['boot_config_sha256']
        print('Verified card and public boot volume; installing tested signed EFI files only.', flush=True)
        for name in names:
            dest = work / name
            assert not dest.is_symlink()
            if dest.exists():
                saved = backup / name; saved.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(dest, saved)
            dest.parent.mkdir(parents=True, exist_ok=True)
            temporary = dest.with_name('.petalos-new-' + dest.name)
            assert not temporary.exists()
            with (bundle / name).open('rb') as src, temporary.open('xb') as out:
                shutil.copyfileobj(src, out); out.flush(); os.fsync(out.fileno())
            assert digest(temporary) == manifest['files'][name]
            os.replace(temporary, dest)
        subprocess.run(['/usr/bin/sync', '-f', str(work)], check=True)
        subprocess.run(['/usr/bin/umount', str(work)], check=True); mounted = False
        # Reopen read-only after unmount for file-level readback verification.
        subprocess.run(['/usr/bin/mount', '-t', 'vfat', '-o', 'ro,nodev,nosuid,noexec', str(boot), str(work)], check=True); mounted = True
        assert all(digest(work / name) == manifest['files'][name] for name in names)
        assert digest(work / 'boot/grub/grub.cfg') == manifest['boot_config_sha256']
        state['phase'] = 'card-repaired'; state['readback_passed'] = True
        statefile.write_text(json.dumps(state, indent=2))
        print('Signed EFI repair and readback passed. SYSTEM and Private were not opened.', flush=True)
    finally:
        if mounted: subprocess.run(['/usr/bin/umount', str(work)], check=True)
        work.rmdir()


if __name__ == '__main__':
    try: main()
    except BaseException as e:
        f = traceback.extract_tb(e.__traceback__)[-1]
        raise SystemExit('EFI repair stopped: ' + type(e).__name__ + '; ' + Path(f.filename).name + ':' + str(f.lineno))
