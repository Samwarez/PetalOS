"""Credential-free plans shared by the CLI and the graphical overlay."""
import hashlib
import json
import math

from .releases import require, verify_bundle, file_digest, CATALOG
from .encryption import PROFILES as ENCRYPTION

GIB = 1024**3
WIPE_METHODS = ('keys-and-random', 'keys-only', 'random')
WIPE_LIMITS = [
    'Keyslot removal disables the current on-card LUKS password slots. It does not erase external header backups, volume-key copies or an already unlocked mapping.',
    'Flash wear levelling can leave old key/data pages outside host-addressable sectors. Neither keyslot removal nor a random fill proves physical SD sanitization.',
    'Random fill covers the complete logical drive and requires flush plus full readback verification. Cancellation after key removal is irreversible; incomplete fill is reported separately.',
]


def existing_layout(disk):
    partitions = disk['partitions']
    require(len(partitions) in (4, 5) and all(p['type'] == 'part' for p in partitions),
            'Expected a recognized PetalOS partition layout.')
    boot = [p for p in partitions if p['label'] == 'PORT_BOOT' and p['fstype'] == 'vfat']
    system = [p for p in partitions if p['label'] == 'PORTABLE_SYSTEM' and p['fstype'] == 'crypto_LUKS']
    private = [p for p in partitions if p['label'] == 'PORTABLE_DATA' and p['fstype'] == 'crypto_LUKS']
    require(len(boot) == len(system) == len(private) == 1,
            'Existing PetalOS BOOT, encrypted SYSTEM and Private volumes were not identified.')
    os_volume = [p for p in partitions if p['label'] == 'PORTABLE_OS' and p['fstype'] == 'crypto_LUKS']
    require((len(partitions) == 4 and not os_volume) or (len(partitions) == 5 and len(os_volume) == 1),
            'OS partition does not match the PetalOS layout.')
    return {'layout': 2 if os_volume else 1, 'boot': boot[0], 'system': system[0], 'private': private[0],
            **({'os': os_volume[0]} if os_volume else {})}


def make_plan(mode, disk, *, bundle=None, encryption='balanced', system_gib=None, os_gib=None,
              wipe_method='keys-and-random', erase_mode='random', retention='production'):
    require(mode in {'install', 'update', 'wipe', 'system-store'}, 'Unknown installer mode.')
    require(disk['eligible'], 'The selected drive is not idle and eligible.')
    plan = {'format': 1, 'mode': mode,
            'target': {k: disk[k] for k in ('path', 'model', 'bytes', 'identity')},
            'destructive': mode in {'install', 'wipe'},
            'execution': 'explicit-confirmation-and-administrator-required', 'steps': [], 'preserves': [],
            'requires': ['Recheck target identity, mounts and holders immediately before execution.']}
    if mode in {'install', 'update'}:
        require(bundle is not None, 'Choose and download a release bundle first.')
        catalog, variant = verify_bundle(bundle)
        from pathlib import Path
        plan['catalog_sha256'] = file_digest(Path(bundle) / CATALOG)
        require(variant['layout'] == 2, 'New installations and updates require a split-storage (layout 2) build.')
        plan['release'] = {'version': catalog['version'], 'variant': variant['id'],
                           'name': variant['name'], 'local_ai': variant['local_ai'],
                           'layout': variant['layout'], 'payloads': variant['payloads']}
        plan['requires'].append('Use a trusted build source; the administrator backend rechecks catalog and payload hashes.')
        size = variant['payloads']['rootfs']['bytes'] + sum(item['bytes'] for item in variant.get('modules', {}).values())
        if mode == 'install':
            require(encryption in ENCRYPTION, 'Unknown encryption profile.')
            require({'shim', 'grub', 'mokmanager'} <= variant['payloads'].keys(),
                    'Fresh installation requires the signed EFI boot assets in this bundle.')
            # Two payloads during replacement plus selected settings and ext4/LUKS headroom.
            minimum = max(8, math.ceil((2 * size + 2 * GIB) / GIB))
            capacity = minimum if os_gib is None else os_gib
            require(type(capacity) is int and capacity >= minimum,
                    'OS allocation is too small for safe replacement staging.')
            settings_capacity = 8 if system_gib is None else system_gib
            require(type(settings_capacity) is int and settings_capacity >= 4,
                    'SYSTEM settings requires at least 4 GiB.')
            boot_size = max(GIB, math.ceil((2 * sum(variant['payloads'][r]['bytes']
                            for r in ('kernel', 'initrd')) + 256 * 1024**2) / GIB) * GIB)
            overhead = 16 * 1024**2
            private_size = disk['bytes'] - (capacity + settings_capacity) * GIB - boot_size - overhead
            require(private_size >= 2 * GIB, 'Drive needs more space for encrypted OS, SYSTEM settings and Private.')
            plan['allocation'] = {'bios_boot_bytes': 2 * 1024**2, 'efi_boot_bytes': boot_size,
                                  'os_bytes': capacity * GIB, 'system_bytes': settings_capacity * GIB, 'private_approx_bytes': private_size,
                                  'partition_alignment_and_headers_reserve_bytes': overhead}
            plan['encryption'] = dict(ENCRYPTION[encryption], id=encryption)
            plan['requires'].append('Calibrate Argon2id with CPU/RAM headroom before erasing; refuse a tier that cannot meet its minimum settings.')
            require(erase_mode in ('random', 'quick'), 'Unknown installation erase mode.')
            plan['erase_mode'] = erase_mode
            plan['boot_support'] = 'UEFI x86_64'
            if erase_mode == 'quick':
                plan['requires'].append('Quick install replaces partitioning and keys; it does not securely erase old flash contents.')
            plan['requires'].extend(['Explicit whole-drive erase confirmation.',
                'Three separately confirmed SYSTEM, Private and administrator passphrases; collect only at execution.'])
            plan['steps'] = ['Replace the partition table and create BOOT, OS, SYSTEM settings and Private volumes.',
                'Create independent fresh LUKS2 keys for OS, SYSTEM settings and Private; OS and settings share the SYSTEM passphrase.',
                'Create filesystems and the selected SYSTEM settings structure.',
                'Install and read back the verified OS payload and signed EFI boot chain.',
                'Store administrator authentication inside encrypted SYSTEM, then flush and close all mappings.']
        else:
            layout = existing_layout(disk)
            require(layout['layout'] == 2, 'Legacy combined OS/settings media needs a separately authorized migration; update cannot repartition it.')
            require(layout['os']['size'] > size + GIB, 'OS partition cannot hold this payload and replacement reserve.')
            plan['existing_layout'] = layout
            require(retention in ('production', 'test'), 'Unknown update retention mode.')
            plan['retention'] = retention
            plan['steps'] = ['Unlock only OS with the SYSTEM passphrase; keep SYSTEM settings and Private closed.',
                'Verify the current OS and actual free space in the OS partition.',
                'Stage and read back a complete new OS generation before switching boot selectors.',
                'Activate the verified OS, retire known old OS files according to retention, flush and close.']
            plan['preserves'] = ['Partition table and encryption keys', 'Entire encrypted SYSTEM settings partition, including administrator authentication',
                                  'Entire independently encrypted Private partition']
            plan['requires'].extend(['Run outside the PetalOS installation being updated.',
                'Check on-volume free space after unlock; total partition size alone does not establish readiness.',
                'Production retention: current OS only after verified activation. Test mode: at most one previous OS.',
                'OS contents and required BOOT selectors only; never format, unlock or write SYSTEM settings or Private during an update.'])
    elif mode == 'wipe':
        require(wipe_method in WIPE_METHODS, 'Unknown wipe method.')
        luks = [p for p in disk['partitions'] if p['fstype'] == 'crypto_LUKS']
        require(luks or wipe_method == 'random', 'No LUKS volumes found; choose random overwrite for this drive.')
        plan['wipe_method'] = wipe_method
        plan['luks_volumes'] = [{'path': p['path'], 'uuid': p['uuid']} for p in luks]
        plan['limits'] = WIPE_LIMITS
        plan['requires'].append('Explicit irreversible wipe confirmation; never automatically delete header backups.')
        if wipe_method != 'random':
            plan['steps'].extend(['Confirm all encrypted mappings are closed and verify every LUKS header.',
                'Remove all active keyslots on each encrypted volume; verify no active keyslots remain and flush.'])
        if wipe_method != 'keys-only':
            plan['steps'].extend(['Overwrite every logical byte of the selected whole drive with random data, flushing periodically.',
                'Flush, invalidate caches where supported, and read back the entire device to verify the written digest.'])
    else:
        layout = existing_layout(disk)
        plan['existing_layout'] = layout
        plan['steps'] = ['Prompt for the SYSTEM passphrase and open only its pinned encrypted volume.',
            'Expose only .petalos-state; keep the full OS mount read-only, nodev,nosuid,noexec.',
            'List files or explicitly import a validated VPN profile, wallpaper or theme asset.',
            'Flush, unmount all views and close SYSTEM on exit.']
        plan['preserves'] = ['Private stays closed', 'OS payload and administrator credentials']
        plan['requires'].extend(['Read-only browsing by default; enable edits explicitly.',
            'Existing PetalOS boot code does not load arbitrary Mods/Overrides; staged packs must remain inactive until a reviewed loader exists.'])
    encoded = json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()
    plan['plan_sha256'] = hashlib.sha256(encoded).hexdigest()
    return plan
