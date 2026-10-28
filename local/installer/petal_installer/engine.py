"""Executable Linux installer operations. No media mutation occurs on import."""
from pathlib import Path
import contextlib
import ctypes
import hashlib
import importlib.util
import json
import os
import re
import resource
import secrets
import signal
import string
import uuid

from . import InstallerError
from . import layout2, linux
from .bundles import PinnedBundle
from .plans import make_plan, existing_layout, WIPE_LIMITS
from .releases import require, file_digest
from .target import Target, atomic_copy, write_public, random_fill
from .encryption import PROFILES, calibrate, verify_header
from .passwords import MINIMUM_CHARACTERS, ROLE_NAMES

CONFIGS = ('EFI/BOOT/grub.cfg', 'EFI/debian/grub.cfg', 'boot/grub/grub.cfg')


def credentials_checked(credentials, mode, *, encryption='balanced'):
    expected = {'system', 'private', 'administrator'} if mode == 'install' else {'system'} if mode in ('update', 'store', 'recovery') else set()
    require(type(credentials) is dict and set(credentials) == expected, 'Unexpected credential fields.')
    encoded = {}
    for role, value in credentials.items():
        require(isinstance(value, str), 'Invalid credential type.')
        value = value.encode('utf-8')
        require(value and len(value) <= 512 and not any(c in value for c in (b'\0', b'\n', b'\r')),
                'Passwords must be nonempty and at most 512 UTF-8 bytes, without line breaks.')
        encoded[role] = value
    if mode == 'install':
        require(encryption in PROFILES, 'Unknown encryption tier.')
        for role, minimum in MINIMUM_CHARACTERS.items():
            require(len(credentials[role]) >= minimum,
                    ROLE_NAMES[role] + ' requires at least ' + str(minimum) + ' characters. Use unique, randomly chosen words or characters; length alone does not ensure strength.')
        require(len(set(encoded.values())) == 3, 'SYSTEM, Private and PetalOS administrator passwords must be different.')
    return encoded


def helper_module():
    shared = Path(__file__).with_name('shared') / 'release_generations.py'
    source = shared if shared.exists() else Path(__file__).resolve().parents[3] / 'tests/release_generations.py'
    spec = importlib.util.spec_from_file_location('petalos_installer_generations', source)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def validate_os(bundle, *, fresh):
    require(bundle.variant['layout'] == 2, 'This build does not support split storage.')
    roles = ('kernel', 'shim', 'grub', 'mokmanager') if fresh else ('kernel',)
    for role in roles:
        require(role in bundle.paths, 'Required signed firmware/kernel payload is missing.')
        linux.command(['/usr/bin/sbverify', '--list', str(bundle.paths[role])], pass_fds=(bundle.fds[role],))
    listing = linux.command(['/usr/bin/lsinitramfs', str(bundle.paths['initrd'])], timeout=120,
                            pass_fds=(bundle.fds['initrd'],)).decode().splitlines()
    require(any(name in listing for name in ('usr/bin/portable-unlock-pair', 'bin/portable-unlock-pair'))
            and 'scripts/init-premount/portable-unlock' in listing,
            'Build initramfs does not contain split-storage unlocking; rebuild before installing.')
    require(not any(name.startswith(('fixture/', 'petalos-tests/')) or name.endswith('credentials.json') for name in listing),
            'Refused a disposable test initrd containing test access/credential files.')
    linux.command(['/usr/bin/unsquashfs', '-s', str(bundle.paths['rootfs'])],
                  pass_fds=(bundle.fds['rootfs'],))
    for role in bundle.paths:
        if role.startswith('module:'):
            linux.command(['/usr/bin/unsquashfs', '-s', str(bundle.paths[role])], pass_fds=(bundle.fds[role],))


def fresh_install(target, plan, bundle, credentials, progress, *, calibration=None):
    require(calibration is not None, 'Encryption must be calibrated before starting a fresh installation.')
    if plan['erase_mode'] == 'random':
        progress({'stage': 'erasing-old-data'})
        random_fill(target, progress)
    progress({'stage': 'partitioning'})
    allocation = plan['allocation']
    target.run(layout2.partition_arguments(target.device, boot_mib=allocation['efi_boot_bytes'] // 1024**2,
        os_mib=allocation['os_bytes'] // 1024**2, system_mib=allocation['system_bytes'] // 1024**2))
    target.run(['/usr/sbin/partprobe', target.device])
    target.run(['/usr/bin/udevadm', 'settle', '--timeout=15'])
    identifiers = {role: str(uuid.uuid4()) for role in layout2.VOLUMES}
    mounts = {}
    for role, spec in layout2.VOLUMES.items():
        part = target.partition(spec['partition'])
        password = credentials['private'] if role == 'private' else credentials['system']
        progress({'stage': 'encrypting-' + role})
        target.run(layout2.encryption_arguments(part, role, identifiers[role], profile=plan['encryption']['id'],
                                               calibration=calibration), payload=password)
        metadata = json.loads(target.run(['/usr/sbin/cryptsetup', 'luksDump', '--dump-json-metadata', str(part)]))
        verify_header(metadata, plan['encryption']['id'], calibration)
        mapper = target.open_volume(part, password)
        target.run(['/usr/sbin/mkfs.ext4', '-q', '-L', spec['filesystem'], str(mapper)])
        mounts[role] = target.mount(mapper, role)
    target.run(['/usr/sbin/mkfs.vfat', '-F', '32', '-n', 'PORT_BOOT', str(target.partition(2))])
    boot = target.mount(target.partition(2), 'boot', fstype='vfat')
    osroot, settings, private = (mounts[r] for r in ('os', 'system', 'private'))
    state = layout2.initialize_settings(settings)
    os.chown(private, 1000, 1000);private.chmod(0o700)
    # Hash only in RAM, then write solely to encrypted SYSTEM settings.
    salt = 'rounds=100000$' + ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
    hashed = linux.command(['/usr/bin/openssl', 'passwd', '-6', '-salt', salt, '-stdin'],
                           payload=credentials['administrator'] + b'\n')
    require(re.fullmatch(rb'\$6\$rounds=100000\$[A-Za-z0-9]{16}\$[./A-Za-z0-9]{86}\n', hashed),
            'Could not prepare administrator authentication.')
    auth = settings / '.petalos-auth/root-admin.hash'
    fd = os.open(auth, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as output:output.write(hashed);output.flush();os.fsync(output.fileno())
    hashes = {name: bundle.hashes[role] for name, role in [('vmlinuz', 'kernel'), ('initrd.img', 'initrd'), ('filesystem.squashfs', 'rootfs')]}
    modules = {name: bundle.hashes['module:' + name] for name in bundle.variant.get('modules', {})}
    metadata = json.dumps({'format': 1, 'os': hashes, 'modules': modules}, sort_keys=True, separators=(',', ':')).encode()
    generation = hashlib.sha256(metadata).hexdigest()[:24]
    prefix = Path('petalos/releases') / generation
    for root, relative in ((boot, prefix), (osroot, prefix / 'live')):
        (root / relative).mkdir(parents=True, mode=0o755)
        manifest = root / prefix / 'generation.json'
        write_public(metadata, manifest, check=target.check)
    for name, role in [('vmlinuz', 'kernel'), ('initrd.img', 'initrd')]:
        progress({'stage': 'installing-' + role})
        atomic_copy(bundle.paths[role], boot / prefix / name, bundle.hashes[role], check=target.check, progress=progress)
    live = osroot / prefix / 'live'
    atomic_copy(bundle.paths['rootfs'], live / 'filesystem.squashfs', hashes['filesystem.squashfs'], check=target.check, progress=progress)
    for name, expected in modules.items():
        atomic_copy(bundle.paths['module:' + name], live / name, expected, check=target.check, progress=progress)
    write_public(('\n'.join(['filesystem.squashfs', *sorted(modules)]) + '\n').encode(), live / 'filesystem.module', check=target.check)
    for role, filename in [('shim', 'BOOTX64.EFI'), ('grub', 'grubx64.efi'), ('mokmanager', 'mmx64.efi')]:
        folder = boot / 'EFI/BOOT';folder.mkdir(parents=True, exist_ok=True)
        atomic_copy(bundle.paths[role], folder / filename, bundle.hashes[role], check=target.check)
    grub = helper_module().rewrite_config(layout2.grub_config(identifiers), generation, None)
    grub = 'set menu_color_normal=light-magenta/black\nset menu_color_highlight=white/magenta\n' + grub
    for name in CONFIGS:
        path = boot / name;path.parent.mkdir(parents=True, exist_ok=True)
        write_public(grub.encode(), path, check=target.check)
    write_public(layout2.layout_record(identifiers).encode(), boot / 'petalos-layout.json', check=target.check)
    require(not (osroot / '.petalos-state').exists() and not (osroot / '.petalos-auth').exists(),
            'Persistent settings or administrator credentials appeared on OS.')
    for root in (boot, osroot, settings, private):target.run(['/usr/bin/sync', '-f', str(root)], timeout=180)
    return {'completed': True, 'mode': 'install', 'version': bundle.catalog['version'],
            'variant': bundle.variant['id'], 'generation': generation, 'boot_support': 'UEFI x86_64',
            'layout': 2, 'encryption': plan['encryption']['id'], 'calibration': calibration, 'erase_mode': plan['erase_mode']}


def update_os(target, plan, bundle, credentials, progress):
    layout = existing_layout(target.disk)
    require(layout['layout'] == 2, 'Legacy layout migration must be handled separately.')
    part = target.partition(3)
    require(linux.command(['/usr/sbin/cryptsetup', 'luksUUID', str(part)]).decode().strip() == layout['os']['uuid'],
            'OS partition identity changed.')
    progress({'stage': 'unlocking-os'})
    mapper = target.open_volume(part, credentials['system'])
    osroot = target.mount(mapper, 'os')
    boot = target.mount(target.partition(2), 'boot', fstype='vfat')
    require(not (osroot / '.petalos-state').exists() and not (osroot / '.petalos-auth').exists(),
            'OS appears to contain combined settings; update refused.')
    record_path = boot / 'petalos-layout.json'
    require(record_path.is_file() and not record_path.is_symlink() and record_path.stat().st_size < 4096,
            'Missing split-storage installation record.')
    record = json.loads(record_path.read_bytes())
    expected = {'os': layout['os']['uuid'], 'system': layout['system']['uuid'], 'private': layout['private']['uuid']}
    require(record.get('format') == 2 and record.get('volumes') == expected, 'Installation record and drive UUIDs differ.')
    configs = []
    for name in CONFIGS:
        path = boot / name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size < 65536, 'Boot selector is missing or unsafe.')
        contents = path.read_text()
        require(all(value in contents for value in expected.values()) and 'petalos.layout=2' in contents
                and 'live-media=/dev/mapper/portable_os' in contents, 'Boot selector points to unexpected storage.')
        configs.append((path, contents))
    sources = {name: bundle.paths[role] for name, role in [('vmlinuz', 'kernel'), ('initrd.img', 'initrd'), ('filesystem.squashfs', 'rootfs')]}
    hashes = {name: bundle.hashes[role] for name, role in [('vmlinuz', 'kernel'), ('initrd.img', 'initrd'), ('filesystem.squashfs', 'rootfs')]}
    modules = sorted(bundle.variant.get('modules', {}))
    helper = helper_module()
    generation, installed = helper.stage_and_activate(boot, osroot, sources, hashes, configs,
        ['filesystem.squashfs', *modules], identity=target.check,
        checkpoint=lambda stage: progress({'stage': stage}), retention=plan['retention'],
        module_sources={name: bundle.paths['module:' + name] for name in modules},
        module_hashes={name: bundle.hashes['module:' + name] for name in modules})
    require(all(file_digest(path) == expected for path, expected in installed.items()), 'Final OS update readback mismatch.')
    target.run(['/usr/bin/sync', '-f', str(boot)], timeout=180)
    target.run(['/usr/bin/sync', '-f', str(osroot)], timeout=180)
    return {'completed': True, 'mode': 'update', 'version': bundle.catalog['version'],
            'variant': bundle.variant['id'], 'generation': generation, 'retention': plan['retention'],
            'settings_opened': False, 'private_opened': False}


def wipe(target, plan, progress):
    removed = []
    try:
        if plan['wipe_method'] != 'random':
            for volume in plan['luks_volumes']:
                path = volume['path']
                require(target.run(['/usr/sbin/cryptsetup', 'luksUUID', path]).decode().strip() == volume['uuid'],
                        'Wipe volume identity changed.')
                header = json.loads(target.run(['/usr/sbin/cryptsetup', 'luksDump', '--dump-json-metadata', path]))
                require(all(s.get('type') == 'luks2' for s in header.get('keyslots', {}).values()), 'Unsupported keyslot type.')
                progress({'stage': 'removing-keyslots', 'volumes_done': len(removed), 'volumes_total': len(plan['luks_volumes'])})
                if header.get('keyslots'):
                    target.run(['/usr/sbin/cryptsetup', 'erase', '--batch-mode', path])
                after = json.loads(target.run(['/usr/sbin/cryptsetup', 'luksDump', '--dump-json-metadata', path]))
                require(not after.get('keyslots'), 'Keyslot removal did not verify.')
                removed.append(volume['uuid'])
                target.run(['/usr/bin/sync', '-f', path])
                progress({'stage': 'keyslots-removed', 'volumes_done': len(removed), 'volumes_total': len(plan['luks_volumes'])})
        if plan['wipe_method'] != 'keys-only':random_fill(target, progress)
        return {'completed': True, 'mode': 'wipe', 'keyslot_volumes_removed': len(removed),
                'random_fill_verified': plan['wipe_method'] != 'keys-only', 'limits': WIPE_LIMITS}
    except BaseException:
        progress({'stage': 'wipe-incomplete', 'keyslot_volumes_removed': len(removed), 'random_fill_verified': False})
        raise


def execute(request, credentials, progress=lambda event: None):
    require(os.geteuid() == 0, 'Administrator rights are required for execution.')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    require(ctypes.CDLL('libc.so.6').prctl(4, 0, 0, 0, 0) == 0, 'Could not protect credential process memory.')
    require(type(request) is dict and request.keys() <= {'mode', 'device', 'bundle', 'encryption', 'os_gib',
            'system_gib', 'wipe_method', 'erase_mode', 'retention', 'plan_sha256'}, 'Unexpected installer request.')
    mode = request.get('mode')
    require(mode in ('install', 'update', 'wipe'), 'Unsupported write operation.')
    encoded = credentials_checked(credentials, mode, encryption=request.get('encryption', 'balanced'))
    disk = linux.choose(request['device'])
    plan = make_plan(mode, disk, bundle=request.get('bundle'), encryption=request.get('encryption', 'balanced'),
        os_gib=request.get('os_gib'), system_gib=request.get('system_gib'),
        wipe_method=request.get('wipe_method', 'keys-and-random'), erase_mode=request.get('erase_mode', 'random'),
        retention=request.get('retention', 'production'))
    require(request.get('plan_sha256') == plan['plan_sha256'], 'Plan changed since confirmation; review it again.')
    os.umask(0o077)
    def interrupted(signum, frame):raise InterruptedError('Installer interrupted.')
    old = {}
    # CLI/backend runs in the main thread. Tests may call the core in a worker.
    import threading
    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):old[signum] = signal.signal(signum, interrupted)
    try:
        context = PinnedBundle(request['bundle'], plan['catalog_sha256']) if mode != 'wipe' else contextlib.nullcontext()
        with context as bundle:
            if bundle:
                require(bundle.catalog['version'] == plan['release']['version']
                        and bundle.variant['id'] == plan['release']['variant'],
                        'Selected build changed since review; review the bundle again.')
                validate_os(bundle, fresh=mode == 'install')
            calibration = None
            if mode == 'install':
                progress({'stage': 'calibrating-encryption', 'tier': plan['encryption']['id']})
                calibration = calibrate(plan['encryption']['id'])
                progress({'stage': 'encryption-calibrated', **calibration})
            with Target(request['device'], disk['identity'], progress) as target:
                progress({'stage': 'validated-target', 'mode': mode})
                if mode == 'install':result = fresh_install(target, plan, bundle, encoded, progress, calibration=calibration)
                elif mode == 'update':result = update_os(target, plan, bundle, encoded, progress)
                else:result = wipe(target, plan, progress)
        progress({'stage': 'complete', 'mode': mode})
        return result
    except BaseException:
        progress({'stage': 'failed', 'mode': mode})
        raise
    finally:
        encoded.clear()
        for signum, handler in old.items():signal.signal(signum, handler)


def perform(request, credentials, progress=lambda event: None):
    """The installed worker exposes only fixed operations, never shell commands."""
    if request.get('mode') in ('install', 'update', 'wipe'):
        return execute(request, credentials, progress)
    mode = request.get('mode')
    require(mode in ('store', 'recovery'), 'Unsupported administrator operation.')
    require(request.keys() <= {'mode', 'device', 'plan_sha256', 'action', 'kind', 'source', 'name', 'replace', 'path', 'new_name'},
            'Unexpected maintenance request.')
    encoded = credentials_checked(credentials, mode)
    plan = make_plan('system-store', linux.choose(request['device']))
    require(request.get('plan_sha256') == plan['plan_sha256'], 'Selected settings drive changed; review again.')
    if mode == 'recovery':
        from .recovery import verify_pair
        return verify_pair(request['device'], credentials['system'])
    from . import store_browser
    if request.get('action') in store_browser.ACTIONS:
        store_browser.validate(request)
        payload = store_browser.prepare_upload(request) if request['action'] == 'put' else None
        try:
            from .store import system_session
            with system_session(request['device'], writable=request['action'] != 'browse', passphrase=credentials['system']) as selected:
                return store_browser.browse(selected, request['path']) if request['action'] == 'browse' else store_browser.change(selected, request, payload)
        except OSError:
            raise InstallerError('Settings operation stopped. Refresh the folder to check its current state. Only empty folders can be removed.') from None
        finally:encoded.clear()
    require(request.get('action') in ('list', 'import'), 'Unsupported settings action.')
    from .store import system_session, inventory, import_file, checked_payload
    if request['action'] == 'import':
        checked_payload(request['kind'], request['source'])
        require(type(request.get('replace', False)) is bool, 'Invalid replacement option.')
    progress({'stage': 'unlocking-system-settings'})
    try:
        with system_session(request['device'], writable=request['action'] == 'import', passphrase=credentials['system']) as selected:
            return inventory(selected) if request['action'] == 'list' else import_file(selected,
                request['kind'], request['source'], request['name'], replace=request.get('replace', False))
    finally:encoded.clear()
