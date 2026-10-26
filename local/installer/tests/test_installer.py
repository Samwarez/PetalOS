from pathlib import Path
import copy
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'local/installer'))
sys.path.insert(0, str(ROOT / 'config/includes.chroot/usr/local/lib/portable'))
from petal_installer import InstallerError, layout2
from petal_installer.releases import GitHub, SafeRedirect, load_catalog, verify_bundle, CATALOG
from petal_installer.plans import make_plan
from petal_installer.linux import describe
from petal_installer.store import import_file
from petal_installer.image_wipe import wipe_image
from storage_layout import boot_identity


def catalog():
    variants = []
    for ident, ai in [('base', False), ('local-agent', True)]:
        payloads = {}
        for role in ('kernel', 'initrd', 'rootfs', 'shim', 'grub', 'mokmanager'):
            data = (ident + '-' + role).encode()
            payloads[role] = {'asset': ident + '-' + role + '.bin', 'bytes': len(data),
                              'sha256': hashlib.sha256(data).hexdigest()}
        variants.append({'id': ident, 'name': ident.title(), 'description': 'Public synthetic test build',
                         'architecture': 'amd64', 'layout': 2, 'local_ai': ai, 'payloads': payloads})
    return {'format': 1, 'version': 'v0.1.0', 'variants': variants}


def bundle(path):
    path.mkdir()
    data = catalog()
    (path / CATALOG).write_text(json.dumps(data))
    (path / 'selection.json').write_text(json.dumps({'version': data['version'], 'variant': 'base'}))
    for role, item in data['variants'][0]['payloads'].items():
        (path / item['asset']).write_bytes(('base-' + role).encode())
    return path


def disk(layout=2):
    parts = [{'path': '/dev/test1', 'type': 'part', 'label': None, 'fstype': None,
              'size': 2 * 1024**2, 'uuid': None},
             {'path': '/dev/test2', 'type': 'part', 'label': 'PORT_BOOT', 'fstype': 'vfat',
              'size': 1024**3, 'uuid': 'boot'}]
    roles = ['os', 'system', 'private'] if layout == 2 else ['system', 'private']
    for index, role in enumerate(roles, 3):
        parts.append({'path': '/dev/test' + str(index), 'type': 'part',
                      'label': layout2.VOLUMES[role]['label'], 'fstype': 'crypto_LUKS',
                      'size': 16 * 1024**3, 'uuid': str(__import__('uuid').uuid4())})
    return {'path': '/dev/test', 'model': 'Disposable fixture', 'bytes': 64 * 1024**3,
            'identity': '1' * 64, 'eligible': True, 'partitions': parts}


class CatalogTests(unittest.TestCase):
    def test_version_and_ai_variants(self):
        value = load_catalog(json.dumps(catalog()).encode())
        self.assertEqual([v['local_ai'] for v in value['variants']], [False, True])

    def test_catalog_rejects_traversal_duplicate_ids_and_invalid_hashes(self):
        for mutation in ('path', 'duplicate', 'hash', 'length', 'role', 'metadata'):
            with self.subTest(mutation=mutation):
                value = catalog()
                item = value['variants'][0]['payloads']['kernel']
                if mutation == 'path': item['asset'] = '../../key'
                if mutation == 'duplicate': value['variants'][1]['id'] = 'base'
                if mutation == 'hash': item['sha256'] = 'not-a-hash'
                if mutation == 'length': item['bytes'] = -1
                if mutation == 'role': value['variants'][0]['payloads']['root-script'] = item
                if mutation == 'metadata': value['variants'][0]['name'] = '\x1b[31m'
                with self.assertRaises(InstallerError): load_catalog(json.dumps(value).encode())

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(InstallerError): load_catalog(b'{"format":1,"format":1}')

    def test_bundle_corruption_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = bundle(Path(temporary) / 'bundle')
            self.assertEqual(verify_bundle(root)[1]['id'], 'base')
            target = root / 'base-rootfs.bin'
            target.write_bytes(b'corrupt')
            with self.assertRaises(InstallerError): verify_bundle(root)
            target.unlink();target.symlink_to(root / 'base-kernel.bin')
            with self.assertRaises(InstallerError): verify_bundle(root)

    def test_release_pagination_and_prerelease_filter(self):
        client = GitHub()
        first = [{'tag_name': 'v' + str(i), 'draft': False, 'assets': [], 'prerelease': False} for i in range(100)]
        last = [{'tag_name': 'vnext', 'draft': False, 'assets': [], 'prerelease': True}]
        with patch.object(client, 'json', side_effect=[first, last]) as call:
            self.assertEqual(len(client.releases()), 100)
            self.assertEqual(call.call_count, 2)

    def test_redirect_strips_auth_and_refuses_plain_http_or_foreign_host(self):
        redirect = SafeRedirect()
        request = urllib.request.Request('https://api.github.com/repos/a/b/releases/assets/1',
                                         headers={'Authorization': 'Bearer synthetic-not-a-token'})
        result = redirect.redirect_request(request, None, 302, '', {}, 'https://release-assets.githubusercontent.com/file')
        self.assertFalse(result.has_header('Authorization'))
        for url in ('http://github.com/file', 'https://evil.example/file', 'https://github.com@evil.example/file'):
            with self.assertRaises(InstallerError): redirect.redirect_request(request, None, 302, '', {}, url)

    def test_download_verified_and_failed_download_never_published(self):
        data = catalog()
        assets = {item['asset']: {'name': item['asset'], 'id': index + 1, 'size': item['bytes']}
                  for index, item in enumerate(data['variants'][0]['payloads'].values())}
        client = GitHub()
        def response(asset):
            return io.BytesIO(asset['name'].removesuffix('.bin').encode())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(client, 'catalog', return_value=(data, assets, json.dumps(data).encode())), patch.object(client, 'asset', side_effect=response):
                result = client.download('v0.1.0', 'base', root / 'good')
                self.assertTrue(result['verified'])
                verify_bundle(root / 'good')
                with self.assertRaises(InstallerError): client.download('v0.1.0', 'base', root / 'good')
            with patch.object(client, 'catalog', return_value=(data, assets, json.dumps(data).encode())), patch.object(client, 'asset', return_value=io.BytesIO(b'bad')):
                with self.assertRaises(InstallerError): client.download('v0.1.0', 'base', root / 'failed')
            self.assertFalse((root / 'failed').exists())
            self.assertFalse(any(root.glob('.petalos-download-*')))


class PlanTests(unittest.TestCase):
    def test_install_has_three_separate_encrypted_allocations(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan = make_plan('install', disk(), bundle=bundle(Path(temporary) / 'bundle'))
            self.assertEqual(set(plan['allocation']) & {'os_bytes', 'system_bytes'}, {'os_bytes', 'system_bytes'})
            self.assertIn('independent fresh LUKS2 keys', ' '.join(plan['steps']))
            self.assertNotIn('passphrase', plan['target'])

    def test_update_preserves_entire_settings_and_private_and_refuses_legacy(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = bundle(Path(temporary) / 'bundle')
            value = make_plan('update', disk(), bundle=source)
            self.assertTrue(any('Entire encrypted SYSTEM' in x for x in value['preserves']))
            self.assertTrue(any('keep SYSTEM settings and Private closed' in x for x in value['steps']))
            with self.assertRaises(InstallerError): make_plan('update', disk(1), bundle=source)

    def test_insufficient_space_and_inuse_target_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = bundle(Path(temporary) / 'bundle')
            target = disk();target['bytes'] = 8 * 1024**3
            with self.assertRaises(InstallerError): make_plan('install', target, bundle=source)
            target = disk();target['eligible'] = False
            with self.assertRaises(InstallerError): make_plan('wipe', target)

    def test_wipe_covers_all_three_encrypted_volumes(self):
        value = make_plan('wipe', disk())
        self.assertEqual(len(value['luks_volumes']), 3)
        self.assertEqual(value['wipe_method'], 'keys-and-random')
        self.assertTrue(any('backups' in text for text in value['limits']))

    def test_disk_mount_and_holder_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            sysroot = Path(temporary)
            (sysroot / 'test/holders').mkdir(parents=True)
            (sysroot / 'test1/holders').mkdir(parents=True)
            raw = {'path': '/dev/test', 'type': 'disk', 'ro': False, 'rm': True, 'tran': 'usb',
                   'maj:min': '240:0', 'size': 64 * 1024**3,
                   'children': [{'path': '/dev/test1', 'type': 'part', 'size': 1024, 'mountpoints': []}]}
            self.assertTrue(describe(raw, sysroot)['eligible'])
            self.assertFalse(describe(dict(raw, size=0), sysroot)['eligible'])
            raw['children'][0]['mountpoints'] = ['/']
            self.assertFalse(describe(raw, sysroot)['eligible'])
            raw['children'][0]['mountpoints'] = []
            (sysroot / 'test1/holders/dm-0').touch()
            self.assertFalse(describe(raw, sysroot)['eligible'])


class BootContractTests(unittest.TestCase):
    def test_vm_console_records_accept_journal_prefix(self):
        spec = importlib.util.spec_from_file_location('split_fixture_runner', ROOT / 'tests/run-split-storage-vm.py')
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual(module.console_record('[123] python3[42]: SPLIT_PASS example'), ('SPLIT_PASS ', 'example'))
        self.assertEqual(module.console_record('SPLIT_RESULT {"passed": true}'), ('SPLIT_RESULT ', '{"passed": true}'))
        self.assertEqual(module.console_record('unrelated boot output'), (None, None))

    def test_boot_identity_roundtrip_and_fail_closed(self):
        values = {role: str(__import__('uuid').uuid4()) for role in layout2.VOLUMES}
        text = ' '.join(layout2.boot_arguments(values))
        self.assertEqual(boot_identity(text)['uuids']['os'], values['os'])
        self.assertEqual(boot_identity(text)['layout'], 2)
        for bad in (text + ' petalos.layout=2', text.replace('petalos.layout=2', ''),
                    text.replace(values['system'], values['os']), text.replace('portable_os', 'portable_system')):
            with self.assertRaises((RuntimeError, ValueError)): boot_identity(bad)

    def test_production_format_never_reuses_key_material(self):
        identity = str(__import__('uuid').uuid4())
        for role in layout2.VOLUMES:
            args = layout2.encryption_arguments('/dev/mock', role, identity)
            self.assertIn('argon2id', args)
            self.assertNotIn('--volume-key-file', args)
            self.assertNotIn('--header-backup-file', args)
        self.assertIn('--readonly', (ROOT / 'local/split-unlock/unlock-pair.c').read_text())


class StoreTests(unittest.TestCase):
    def test_wallpaper_import_no_overwrite_and_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);state = root / 'settings';state.mkdir()
            source = ROOT / 'local/installer/petal_installer/assets/petal-emblem.png'
            result = import_file(state, 'wallpaper', source, 'pink')
            self.assertTrue(result['available_to_current_os'])
            with self.assertRaises(InstallerError): import_file(state, 'wallpaper', source, 'pink')
            with self.assertRaises(InstallerError): import_file(state, 'wallpaper', source, '../outside')
            self.assertEqual((state / 'Wallpapers/pink.png').read_bytes(), source.read_bytes())

    def test_arbitrary_mod_code_rejected_and_safe_override_inactive(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / 'settings';state.mkdir()
            source = Path(temporary) / 'public.json'
            source.write_text(json.dumps({'format': 1, 'run': '/bin/sh'}))
            with self.assertRaises(InstallerError): import_file(state, 'override', source, 'mod')
            source.write_text(json.dumps({'format': 1, 'double_click_ms': 500}))
            self.assertFalse(import_file(state, 'override', source, 'desktop')['available_to_current_os'])

    def test_symlink_directory_and_vpn_hooks_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);state = root / 'settings';state.mkdir()
            outside = root / 'outside';outside.mkdir()
            (state / 'Wallpapers').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(InstallerError): import_file(state, 'wallpaper',
                ROOT / 'local/installer/petal_installer/assets/petal-emblem.png', 'escape')
            source = root / 'fixture.conf';source.write_text('[Interface]\nPostUp=/bin/sh\n')
            with self.assertRaises(InstallerError): import_file(state, 'vpn', source, 'rejected')


class WipeTests(unittest.TestCase):
    def test_random_fill_verified_and_links_and_wrong_confirmation_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'disposable.img';path.write_bytes(b'canary' * 1000)
            before = path.read_bytes()
            with self.assertRaises(InstallerError): wipe_image(path, 'random', 'wrong')
            self.assertEqual(path.read_bytes(), before)
            result = wipe_image(path, 'random', 'WIPE ' + str(path))
            self.assertTrue(result['random_fill_verified'])
            self.assertEqual(path.stat().st_size, len(before))
            self.assertNotEqual(path.read_bytes(), before)
            link = path.with_name('link');link.symlink_to(path)
            with self.assertRaises(InstallerError): wipe_image(link, 'random', 'WIPE ' + str(link))
            hard = path.with_name('hard');os.link(path, hard)
            with self.assertRaises(InstallerError): wipe_image(path, 'random', 'WIPE ' + str(path))

    @unittest.skipUnless(Path('/usr/sbin/cryptsetup').exists(), 'cryptsetup unavailable')
    def test_real_luks_key_removal_and_backup_recovery_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'disposable.luks'
            with path.open('xb') as out: out.truncate(32 * 1024**2)
            password = os.urandom(24).hex().encode()
            def crypt(args, ok=0, payload=None):
                result = subprocess.run(['/usr/sbin/cryptsetup', *args], input=payload,
                                        capture_output=True, timeout=60)
                self.assertEqual(result.returncode, ok, 'Disposable cryptsetup operation did not match expected status.')
            crypt(['luksFormat', '--batch-mode', '--type', 'luks2', '--pbkdf', 'pbkdf2',
                   '--pbkdf-force-iterations', '1000', '--key-file', '-', str(path)], payload=password)
            backup = Path(temporary) / 'header-backup'
            crypt(['luksHeaderBackup', '--header-backup-file', str(backup), str(path)])
            result = wipe_image(path, 'keys-only', 'WIPE ' + str(path))
            self.assertTrue(result['keyslots_removed'])
            crypt(['open', '--test-passphrase', '--key-file', '-', str(path)], ok=1, payload=password)
            crypt(['luksHeaderRestore', '--batch-mode', '--header-backup-file', str(backup), str(path)])
            crypt(['open', '--test-passphrase', '--key-file', '-', str(path)], payload=password)


if __name__ == '__main__': unittest.main()
