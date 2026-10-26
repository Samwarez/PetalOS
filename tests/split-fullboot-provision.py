#!/usr/bin/python3
"""Provision only the full-boot fixture's newly allocated virtual disk."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, '/fixture/installer')
from petal_installer import layout2

data = json.loads(Path('/fixture/test-input.json').read_text())
secrets = {key: value.encode() for key, value in data['credentials'].items()}
results = {}


def run(args, payload=None):
    result = subprocess.run(args, input=payload, capture_output=True, timeout=240)
    if result.returncode:
        raise RuntimeError('Full-boot fixture tool failed: ' + Path(args[0]).name)
    return result


def check(name, condition):
    results[name] = bool(condition)
    if not condition:
        raise RuntimeError('Full-boot fixture check failed: ' + name)
    print('SPLIT_PASS ' + name, flush=True)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


try:
    check('fresh_virtual_disk_only', Path('/sys/class/block/vda/device').resolve().name.startswith('virtio') and not Path('/dev/vda1').exists())
    run(layout2.partition_arguments('/dev/vda', boot_mib=256, os_mib=4096, system_mib=512))
    run(['/usr/sbin/partprobe', '/dev/vda']);run(['/usr/bin/udevadm', 'settle', '--timeout=10'])
    iso = Path('/mnt/base-iso');iso.mkdir()
    run(['/usr/bin/mount', '-t', 'iso9660', '-o', 'ro,nodev,nosuid,noexec', '/dev/vdb', str(iso)])
    base = iso / 'live/filesystem.squashfs'
    check('base_rootfs_matches_completed_release', digest(base) == data['base_rootfs_sha256'])
    for role, volume in layout2.VOLUMES.items():
        part = '/dev/vda' + str(volume['partition'])
        password = secrets['private'] if role == 'private' else secrets['system']
        run(layout2.encryption_arguments(part, role, data['uuids'][role], fixture_kdf=True), password)
        mapper = 'fixture_full_' + role
        run(['/usr/sbin/cryptsetup', 'open', '--key-file', '-', part, mapper], password)
        mapped = '/dev/mapper/' + mapper
        run(['/usr/sbin/mkfs.ext4', '-q', '-L', volume['filesystem'], mapped])
        target = Path('/mnt/full-' + role);target.mkdir()
        run(['/usr/bin/mount', '-o', 'nodev,nosuid,noexec', mapped, str(target)])
        if role == 'os':
            live = target / 'live';live.mkdir()
            shutil.copyfile(base, live / 'filesystem.squashfs')
            modules = 'filesystem.squashfs\n'
            if data['runtime_delta_sha256'] is not None:
                shutil.copyfile('/fixture/layout2-runtime.squashfs', live / 'layout2-runtime.squashfs')
                modules += 'layout2-runtime.squashfs\n'
            (live / 'filesystem.module').write_text(modules)
            check('installed_real_rootfs_readback', digest(live / 'filesystem.squashfs') == data['base_rootfs_sha256'])
            if data['runtime_delta_sha256'] is not None:
                check('installed_runtime_delta_readback', digest(live / 'layout2-runtime.squashfs') == data['runtime_delta_sha256'])
            else:
                check('clean_rootfs_without_runtime_overlay', not (live / 'layout2-runtime.squashfs').exists()
                      and (live / 'filesystem.module').read_text() == 'filesystem.squashfs\n')
        elif role == 'system':
            state = layout2.initialize_settings(target)
            (state / 'Desktop/fullboot-canary').write_bytes(b'fullboot-independent-settings')
            sys.path.insert(0, '/usr/local/lib/portable')
            from account_auth import encode_secret
            (target / '.petalos-auth/root-admin.hash').write_bytes(encode_secret(secrets['administrator']) + b'\n')
        else:
            (target / 'fullboot-canary').write_bytes(b'fullboot-independent-private')
        run(['/usr/bin/sync', '-f', str(target)])
        run(['/usr/bin/umount', str(target)]);run(['/usr/sbin/cryptsetup', 'close', mapper])
    run(['/usr/bin/umount', str(iso)])
    run(['/usr/sbin/mkfs.vfat', '-F', '32', '-n', 'PORT_BOOT', '/dev/vda2'])
    check('full_image_provisioned_with_all_mappings_closed', not any(Path('/dev/mapper').glob('fixture_full_*')))
    print('SPLIT_RESULT ' + json.dumps({'stage': 'full-provision', 'checks': results, 'passed': True}), flush=True)
except BaseException as error:
    print('SPLIT_RESULT ' + json.dumps({'checks': results, 'passed': False, 'failure_type': type(error).__name__}), flush=True)
finally:
    subprocess.run(['/usr/bin/sync'])
    subprocess.run(['/bin/busybox', 'poweroff', '-f'])
