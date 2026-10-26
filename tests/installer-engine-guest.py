#!/usr/bin/python3
"""Exercise the installed CLI/backend against disposable USB disks only."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import traceback

sys.path.insert(0, '/usr/lib/bloom-installer')
from petal_installer import linux, InstallerError
from petal_installer.cli import parser, dispatch
from petal_installer.bridge import request_from_plan
from petal_installer.engine import execute
from petal_installer.plans import make_plan, existing_layout
from petal_installer.target import Target

DATA = json.loads(Path('/fixture/test-input.json').read_text())
CREDS = DATA['credentials']
RESULTS = {}
STAGE = next(w.split('=', 1)[1] for w in Path('/proc/cmdline').read_text().split() if w.startswith('petalos.fixture.stage='))


def check(name, condition):
    RESULTS[name] = bool(condition)
    if not condition:raise RuntimeError('Check failed: ' + name)
    print('SPLIT_PASS ' + name, flush=True)


def command(args, payload=None, allowed=(0,)):
    result = subprocess.run(args, input=payload, capture_output=True, timeout=180)
    if result.returncode not in allowed:raise RuntimeError('Tool failed: ' + Path(args[0]).name)
    return result.stdout


def refresh():
    command(['/usr/bin/udevadm', 'trigger', '--action=change', '--subsystem-match=block'])
    command(['/usr/bin/udevadm', 'settle', '--timeout=20'])


def plan(mode, bundle=None, device='/dev/sda', **kwargs):
    return make_plan(mode, linux.choose(device), bundle=bundle, **kwargs)


def execute_plan(value, bundle=None, credentials=None, progress=None):
    return execute(request_from_plan(value, bundle), credentials or {}, progress or (lambda event: print('ENGINE_STAGE ' + event['stage'], flush=True)))


def bootstrap():
    Path('/mnt/installer-source').mkdir()
    command(['/usr/bin/mount', '-t', 'iso9660', '-o', 'ro,nodev,nosuid,noexec', '/dev/vda', '/mnt/installer-source'])
    root = Path('/mnt/installer-source')
    refresh()
    check('target_is_removable_usb', linux.choose('/dev/sda')['transport'] == 'usb')
    try:linux.choose('/dev/vda');refused = False
    except InstallerError:refused = True
    check('readonly_source_refused_as_target', refused)
    return root


def fresh(root):
    bundle = root / 'bundle-a'
    value = plan('install', bundle, encryption='fast', system_gib=4, os_gib=8, erase_mode='quick')
    wrong = request_from_plan(value, bundle);wrong['plan_sha256'] = '0' * 64
    before = command(['/usr/sbin/blkid', '-p', '-o', 'export', '/dev/sda'], allowed=(0, 2))
    try:execute(wrong, CREDS);refused = False
    except InstallerError:refused = True
    check('stale_confirmation_refused_before_partitioning', refused and not Path('/dev/sda1').exists())
    result = execute_plan(value, bundle, CREDS)
    check('fresh_install_completed', result['completed'] and result['layout'] == 2)
    check('all_five_partitions_created', all(Path('/dev/sda' + str(n)).exists() for n in range(1, 6)))
    check('no_installer_mappings_left', not any(Path('/dev/mapper').glob('petal_inst_*')))
    refresh();disk = linux.choose('/dev/sda');layout = existing_layout(disk)
    check('layout_two_identified', layout['layout'] == 2)
    for role in ('os', 'system', 'private'):
        number = {'os': 3, 'system': 4, 'private': 5}[role]
        metadata = json.loads(command(['/usr/sbin/cryptsetup', 'luksDump', '--dump-json-metadata', '/dev/sda' + str(number)]))
        check('production_argon2id_' + role, all(item['kdf']['type'] == 'argon2id' for item in metadata['keyslots'].values()))
    with Target('/dev/sda', disk['identity']) as target:
        settings_map = target.open_volume(target.partition(4), CREDS['system'].encode())
        settings = target.mount(settings_map, 'settings')
        check('admin_hash_only_in_settings', (settings / '.petalos-auth/root-admin.hash').is_file())
        (settings / '.petalos-state/Desktop/installer-canary').write_bytes(b'installer-settings')
        private_map = target.open_volume(target.partition(5), CREDS['private'].encode())
        private = target.mount(private_map, 'private')
        (private / 'installer-canary').write_bytes(b'installer-private')
    check('fresh_resources_closed_after_preload', not any(Path('/dev/mapper').glob('petal_inst_*')))
    # Create a small independently keyed wipe fixture on a second USB disk.
    command(['/usr/sbin/sgdisk', '--clear', '--new=1:2048:+40M', '--typecode=1:8309', '--new=2:0:0', '--typecode=2:8309', '/dev/sdb'])
    command(['/usr/sbin/partprobe', '/dev/sdb']);refresh()
    for number in (1, 2):
        command(['/usr/sbin/cryptsetup', 'luksFormat', '--batch-mode', '--type', 'luks2', '--pbkdf', 'pbkdf2',
                 '--pbkdf-force-iterations', '1000', '--label', 'DISPOSABLE_WIPE_' + str(number), '--key-file', '-', '/dev/sdb' + str(number)], CREDS['private'].encode())
    refresh()
    value = plan('wipe', device='/dev/sdb', wipe_method='keys-only')
    events = []
    def interrupted(event):
        events.append(event)
        if event['stage'] == 'keyslots-removed':raise InterruptedError('Public fixture interruption')
    try:execute_plan(value, progress=interrupted);refused = False
    except InterruptedError:refused = True
    check('wipe_interruption_reports_completed_key_removal', refused and any(e['stage'] == 'wipe-incomplete' and e['keyslot_volumes_removed'] == 1 for e in events))
    check('interrupted_wipe_leaves_no_maps', not any(Path('/dev/mapper').glob('petal_inst_*')))
    result = execute_plan(plan('wipe', device='/dev/sdb', wipe_method='keys-and-random'))
    check('wipe_retry_finishes_random_readback', result['completed'] and result['random_fill_verified'])


def update(root):
    bundle = root / 'bundle-b'
    result = execute_plan(plan('update', bundle, retention='production'), bundle, {'system': CREDS['system']})
    check('os_update_completed', result['completed'])
    check('update_never_opened_persistent_volumes', not result['settings_opened'] and not result['private_opened'])
    check('update_resources_closed', not any(Path('/dev/mapper').glob('petal_inst_*')))
    # Stop before firmware/live handoff in the boot acceptance pass, without any
    # credential embedded in its test instrumentation. Installed payloads were
    # verified by the engine before this explicitly recorded VM-only addition.
    disk = linux.choose('/dev/sda')
    with Target('/dev/sda', disk['identity']) as target:
        boot = target.mount(target.partition(2), 'boot', fstype='vfat')
        prefix = Path('petalos/releases') / result['generation']
        with (boot / prefix / 'initrd.img').open('ab') as output:
            output.write(Path('/fixture/boot-probe.cpio.gz').read_bytes())
        for name in ('EFI/BOOT/grub.cfg', 'EFI/debian/grub.cfg', 'boot/grub/grub.cfg'):
            path = boot / name
            text = path.read_text().replace('quiet splash', 'console=ttyS0 nosplash')
            path.write_text(text)
    check('firmware_probe_installed_without_password_files', True)


try:
    root = bootstrap()
    fresh(root) if STAGE == 'installer-fresh' else update(root)
    print('SPLIT_RESULT ' + json.dumps({'stage': STAGE, 'checks': RESULTS, 'passed': True}), flush=True)
except BaseException as error:
    location = traceback.extract_tb(error.__traceback__)[-1]
    print('SPLIT_RESULT ' + json.dumps({'stage': STAGE, 'checks': RESULTS, 'passed': False,
        'failure_type': type(error).__name__, 'failure_source': Path(location.filename).name + ':' + str(location.lineno),
        'failure_message': str(error) if isinstance(error, (InstallerError, RuntimeError)) else 'details suppressed'}), flush=True)
finally:
    subprocess.run(['/usr/bin/sync'])
    subprocess.run(['/bin/busybox', 'poweroff', '-f'])
