#!/usr/bin/python3
"""Focused disposable VM acceptance using real GPT, dm-crypt and filesystems.

No external NIC, host directory or production data is available to this guest.
Small public payloads and fast test-only PBKDF2 are used; this is not full-image,
Secure Boot, production KDF or desktop acceptance.
"""
from pathlib import Path
import hashlib
import hmac
import importlib.util
import json
import os
import subprocess
import sys
import types

sys.path.insert(0, '/fixture/installer')
sys.path.insert(0, '/usr/local/lib/portable')
from petal_installer import layout2

FIXTURE = Path('/fixture')
DATA = json.loads((FIXTURE / 'test-input.json').read_text())
SECRETS = {k: v.encode() for k, v in DATA['credentials'].items()}
UUIDS = DATA['uuids']
RESULTS = {}


def run(args, payload=None, *, ok=(0,), timeout=90):
    result = subprocess.run(args, input=payload, capture_output=True, timeout=timeout)
    if result.returncode not in ok:
        raise RuntimeError('Guest tool failed: ' + Path(args[0]).name)
    return result


def check(name, condition):
    RESULTS[name] = bool(condition)
    if not condition:
        raise RuntimeError('Guest check failed: ' + name)
    print('SPLIT_PASS ' + name, flush=True)


def part(role):
    return '/dev/vda' + str(layout2.VOLUMES[role]['partition'])


def opened(name):
    return Path('/dev/mapper', name).exists()


def open_volume(role, *, name=None, readonly=False):
    name = name or 'fixture_' + role
    password = SECRETS['private'] if role == 'private' else SECRETS['system']
    args = ['/usr/sbin/cryptsetup', 'open', '--type', 'luks2', '--key-file', '-']
    if readonly:
        args.append('--readonly')
    run([*args, part(role), name], password)
    return '/dev/mapper/' + name


def mount(device, target, *, readonly=False):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    options = ('ro,noload,' if readonly else '') + 'nodev,nosuid,noexec,noatime'
    run(['/usr/bin/mount', '-t', 'ext4', '-o', options, str(device), str(target)])
    return target


def close(name):
    run(['/usr/sbin/cryptsetup', 'close', name])


def unmount(target):
    run(['/usr/bin/umount', str(target)])


def filehash(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def volume_key(role):
    # Only ephemeral test keys, only RAM, never emitted into test output.
    path = Path('/run/test-volume-key-' + role)
    result = run(['/usr/sbin/cryptsetup', 'luksDump', '--dump-volume-key', '--volume-key-file', str(path),
                  '--key-file', '-', part(role)], SECRETS['private'] if role == 'private' else SECRETS['system'])
    data = path.read_bytes()
    path.unlink()
    check('test_key_length_' + role, len(data) in (32, 64))
    return data


def production_boot_unlock():
    result = subprocess.run(['/bin/sh', '/scripts/init-premount/portable-unlock'], timeout=180)
    check('production_boot_script_succeeded', result.returncode == 0)
    check('os_mapping_open', opened('portable_os'))
    check('system_mapping_open', opened('portable_system'))
    check('private_not_opened_by_boot', not opened('portable_data'))
    check('os_mapping_readonly', run(['/usr/sbin/blockdev', '--getro', '/dev/mapper/portable_os']).stdout.strip() == b'1')


def production_settings_boot():
    # The initramfs root is RAM, but is not the full live overlay that ram_ready
    # deliberately requires. Only that environmental precondition and desktop
    # Trash/wallpaper behavior are replaced; all volume identity/mount/key paths
    # below use the actual production modules and real block devices.
    import private_storage as storage
    import system_state
    sys.modules['compartments'] = types.SimpleNamespace(ram_ready=lambda: None)
    sys.modules['volatile_trash'] = types.SimpleNamespace(block_private_trash=lambda: None)
    sys.modules['wallpapers'] = types.SimpleNamespace(seed=lambda _: None)
    storage.boot_unlock()
    check('settings_ready_via_production_module', system_state.ready())
    check('os_key_closed_after_ram_phase', not opened('portable_os'))
    check('private_stays_closed_after_ram_phase', not opened('portable_data'))
    check('settings_canary_persisted', (system_state.STATE / 'Desktop/canary').read_bytes() == b'fixture-settings')
    import account_auth
    stored = account_auth.load_hash()
    salt = stored.decode().split('$')[2] + '$' + stored.decode().split('$')[3]
    actual = run(['/usr/bin/openssl', 'passwd', '-6', '-salt', salt, '-stdin'], SECRETS['administrator'] + b'\n').stdout.strip()
    check('administrator_auth_persisted_separately', hmac.compare_digest(actual, stored))
    check('system_auth_accepts_system', storage.authenticate_system(SECRETS['system']))
    check('system_auth_rejects_private', not storage.authenticate_system(SECRETS['private']))
    check('system_auth_rejects_administrator', not storage.authenticate_system(SECRETS['administrator']))
    adapter = storage.backend()
    identity = storage.identity()
    adapter.unlock(identity, SECRETS['private'])
    check('private_unlock_accepts_only_private', adapter.is_unlocked(identity))
    check('private_canary_persisted', (storage.PRIVATE / 'canary').read_bytes() == b'fixture-private')
    adapter.close_private(identity)
    check('private_mapping_closed_after_lock', not opened('portable_data'))
    check('screen_auth_does_not_reopen_private', storage.authenticate_system(SECRETS['system']) and not opened('portable_data'))
    system_state.unmount()
    adapter.close_system(identity)


def recovery_and_imports():
    from petal_installer import linux, recovery, store
    def fixture_target(device):
        # The only discovery exception: this dedicated virtual disk is not USB.
        # All mount/holder/partition identity checks still come from real lsblk
        # and sysfs. There is no host block device or share attached to this VM.
        assert device == '/dev/vda'
        records = [item for item in linux.devices() if item['path'] == device]
        assert len(records) == 1
        disk = records[0]
        assert disk['blocked_reasons'] == ['Not identified as removable media or a USB drive.']
        disk['eligible'] = True
        return disk
    recovery.choose = fixture_target
    store.choose = fixture_target
    store.ROOT = Path('/fixture/source')
    report = recovery.verify_pair('/dev/vda', SECRETS['system'].decode())
    check('recovery_verifies_both_headers_without_opening', report['verified'] and not opened('portable_os')
          and not opened('portable_system') and not opened('portable_data'))
    try:
        recovery.verify_pair('/dev/vda', SECRETS['private'].decode())
        refused = False
    except Exception:
        refused = True
    check('recovery_rejects_private_password', refused and not opened('portable_data'))
    with store.system_session('/dev/vda', passphrase=SECRETS['system'].decode()) as selected:
        check('offline_store_lists_saved_settings', 'canary' in store.inventory(selected)['Desktop'])
        opts = run(['/usr/bin/findmnt', '-n', '-o', 'OPTIONS', '--mountpoint', str(selected)]).stdout.decode().split(',')
        check('offline_store_readonly_by_default', 'ro' in [o.strip() for o in opts])
        try:
            (selected / 'Desktop/no-write').write_bytes(b'no')
            refused = False
        except OSError:
            refused = True
        check('offline_store_default_rejects_writes', refused)
    fixture_vpn = Path('/run/public-fixture.conf')
    fixture_vpn.write_text('[Interface]\nPrivateKey = AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\nAddress = 10.0.0.2/32\nDNS = 1.1.1.1\n'
                           '[Peer]\nPublicKey = AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\nAllowedIPs = 0.0.0.0/0, ::/0\nEndpoint = 203.0.113.1:51820\n')
    with store.system_session('/dev/vda', writable=True, passphrase=SECRETS['system'].decode()) as selected:
        check('offline_store_imports_wallpaper', store.import_file(selected, 'wallpaper', '/fixture/wallpaper.png', 'fixture')['imported'])
        check('offline_store_imports_validated_vpn', store.import_file(selected, 'vpn', fixture_vpn, 'fixture')['imported'])
    check('offline_store_closes_its_mapping', not any(Path('/dev/mapper').glob('petalos_installer_*')))
    check('offline_store_never_opened_os_or_private', not opened('portable_os') and not opened('portable_data'))


def provision():
    check('fixture_device_is_virtio', Path('/sys/class/block/vda/device').resolve().name.startswith('virtio'))
    check('no_existing_partitions', not Path('/dev/vda1').exists())
    run(layout2.partition_arguments('/dev/vda', boot_mib=32, os_mib=128, system_mib=128))
    run(['/usr/sbin/partprobe', '/dev/vda'])
    run(['/usr/bin/udevadm', 'settle', '--timeout=10'])
    for role in layout2.VOLUMES:
        run(layout2.encryption_arguments(part(role), role, UUIDS[role], fixture_kdf=True),
            SECRETS['private'] if role == 'private' else SECRETS['system'])
    keys = [volume_key(role) for role in layout2.VOLUMES]
    check('three_independent_volume_keys', len(set(keys)) == 3)
    del keys
    # Wrong passwords install neither key.
    rejection = run(['/bin/portable-unlock-pair', '--stdin', part('os'), part('system')], SECRETS['private'], ok=(2,))
    check('wrong_system_opens_neither_volume', not opened('portable_os') and not opened('portable_system'))
    # Correct OS password with a deliberately different settings passphrase
    # must close the partially opened OS, then fail without prompting twice.
    run(layout2.encryption_arguments(part('system'), 'system', UUIDS['system'], fixture_kdf=True), SECRETS['administrator'])
    run(['/bin/portable-unlock-pair', '--stdin', part('os'), part('system')], SECRETS['system'], ok=(3,))
    check('settings_mismatch_rolls_back_os_key', not opened('portable_os') and not opened('portable_system'))
    run(layout2.encryption_arguments(part('system'), 'system', UUIDS['system'], fixture_kdf=True), SECRETS['system'])
    for role in layout2.VOLUMES:
        mapping = open_volume(role)
        run(['/usr/sbin/mkfs.ext4', '-q', '-L', layout2.VOLUMES[role]['filesystem'], mapping])
        root = mount(mapping, '/mnt/fixture-' + role)
        if role == 'os':
            (root / 'live').mkdir()
            (root / 'live/filesystem.squashfs').write_bytes(b'fixture-old-rootfs')
            (root / 'live/filesystem.module').write_text('filesystem.squashfs\n')
        elif role == 'system':
            state = layout2.initialize_settings(root)
            (state / 'Desktop/canary').write_bytes(b'fixture-settings')
            import account_auth
            (root / '.petalos-auth/root-admin.hash').write_bytes(account_auth.encode_secret(SECRETS['administrator']) + b'\n')
        else:
            (root / 'canary').write_bytes(b'fixture-private')
        unmount(root)
        close('fixture_' + role)
    run(['/usr/sbin/mkfs.vfat', '-F', '32', '-n', 'PORT_BOOT', '/dev/vda2'])
    boot = Path('/mnt/fixture-boot');boot.mkdir()
    run(['/usr/bin/mount', '-o', 'nodev,nosuid,noexec', '/dev/vda2', str(boot)])
    (boot / 'live').mkdir()
    (boot / 'live/vmlinuz').write_bytes(b'fixture-old-kernel')
    (boot / 'live/initrd.img').write_bytes(b'fixture-old-initrd')
    (boot / 'boot/grub').mkdir(parents=True)
    (boot / 'boot/grub/grub.cfg').write_text(layout2.grub_config(UUIDS))
    (boot / 'petalos-layout.json').write_text(layout2.layout_record(UUIDS))
    unmount(boot)
    production_boot_unlock()
    production_settings_boot()
    recovery_and_imports()
    update()


def update():
    settings_before, private_before = filehash(part('system')), filehash(part('private'))
    mapping = open_volume('os', name='fixture_update_os')
    osroot = mount(mapping, '/mnt/update-os')
    boot = Path('/mnt/update-boot');boot.mkdir()
    run(['/usr/bin/mount', '-o', 'nodev,nosuid,noexec', '/dev/vda2', str(boot)])
    inputs = Path('/run/replacement');inputs.mkdir()
    sources = {}
    for name in ('vmlinuz', 'initrd.img', 'filesystem.squashfs'):
        sources[name] = inputs / name
        sources[name].write_bytes(('fixture-new-' + name).encode())
    spec = importlib.util.spec_from_file_location('release_generations', '/fixture/release_generations.py')
    helper = importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    config = boot / 'boot/grub/grub.cfg'
    generation, installed = helper.stage_and_activate(boot, osroot, sources,
        {name: filehash(path) for name, path in sources.items()}, [(config, config.read_text())],
        ['filesystem.squashfs'], retention='production')
    check('update_new_payload_readback', all(filehash(path) == expected for path, expected in installed.items()))
    check('update_os_has_no_settings_or_admin', not (osroot / '.petalos-state').exists() and not (osroot / '.petalos-auth').exists())
    check('update_selects_verified_generation', helper.selected_release(config.read_text()) == generation)
    check('update_preserves_uuid_arguments', all(value in config.read_text() for value in UUIDS.values()))
    unmount(boot);unmount(osroot);close('fixture_update_os')
    check('update_settings_partition_byte_identical', settings_before == filehash(part('system')))
    check('update_private_partition_byte_identical', private_before == filehash(part('private')))
    check('update_did_not_open_settings_or_private', not opened('portable_system') and not opened('portable_data'))


def verify_reboot():
    production_boot_unlock()
    osroot = mount('/dev/mapper/portable_os', '/mnt/reboot-os', readonly=True)
    check('updated_generation_survived_reboot', any((osroot / 'petalos/releases').glob('*/live/filesystem.squashfs')))
    check('os_has_no_persistent_settings', not (osroot / '.petalos-state').exists() and not (osroot / '.petalos-auth').exists())
    try:
        (osroot / 'should-not-write').write_bytes(b'no')
        readonly = False
    except OSError:
        readonly = True
    check('os_filesystem_write_refused', readonly)
    unmount(osroot)
    production_settings_boot()
    # Verify explicit preloads survived the update and reboot too.
    mapping = open_volume('system', name='fixture_verify_settings', readonly=True)
    root = mount(mapping, '/mnt/verify-preloads', readonly=True)
    check('preloaded_wallpaper_survived_update_and_reboot', (root / '.petalos-state/Wallpapers/fixture.png').read_bytes() == Path('/fixture/wallpaper.png').read_bytes())
    check('preloaded_vpn_survived_update_and_reboot', (root / '.petalos-state/Network/Profiles/fixture.conf').is_file())
    unmount(root);close('fixture_verify_settings')


try:
    stage = next(word.split('=', 1)[1] for word in Path('/proc/cmdline').read_text().split() if word.startswith('petalos.fixture.stage='))
    provision() if stage == 'provision' else verify_reboot()
    print('SPLIT_RESULT ' + json.dumps({'stage': stage, 'checks': RESULTS, 'passed': True}), flush=True)
except BaseException as error:
    import traceback
    location = traceback.extract_tb(error.__traceback__)[-1]
    print('SPLIT_RESULT ' + json.dumps({'checks': RESULTS, 'passed': False, 'failure_type': type(error).__name__,
                                      'failure_source': Path(location.filename).name + ':' + str(location.lineno),
                                      'failure_location': str(error) if isinstance(error, RuntimeError) else 'details suppressed'}), flush=True)
finally:
    run(['/usr/bin/sync'])
    subprocess.run(['/bin/busybox', 'poweroff', '-f'])
