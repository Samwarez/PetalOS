from pathlib import Path
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'local/installer'))
from petal_installer import InstallerError
from petal_installer import engine
from petal_installer.bridge import request_from_plan, validate_packet
from petal_installer.bundles import PinnedBundle, create_bundle
from petal_installer.plans import make_plan
from petal_installer.target import atomic_copy
from test_installer import bundle, disk


class ExecutionTests(unittest.TestCase):
    def test_separate_passwords_and_byte_limits(self):
        valid = {'system': 'system-test-unique', 'private': 'private-test-unique-longer', 'administrator': 'admin-test-unique'}
        self.assertEqual(engine.credentials_checked(valid, 'install')['system'], b'system-test-unique')
        for invalid in [dict(valid, private=valid['system']), dict(valid, system=''),
                        dict(valid, system='x\ny'), dict(valid, private='x\0y'), dict(valid, system='🌸' * 129)]:
            with self.assertRaises(InstallerError):engine.credentials_checked(invalid, 'install')
        with self.assertRaises(InstallerError):engine.credentials_checked(valid, 'update')

    def test_frontend_request_recreates_exact_confirmed_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = bundle(Path(temporary) / 'bundle')
            for mode in ('install', 'update', 'wipe'):
                target = disk()
                value = make_plan(mode, target, bundle=source if mode != 'wipe' else None,
                                  erase_mode='quick', retention='test')
                request = request_from_plan(value, source if mode != 'wipe' else None)
                actual = make_plan(mode, target, bundle=source if mode != 'wipe' else None,
                    encryption=request.get('encryption', 'balanced'), os_gib=request.get('os_gib'),
                    system_gib=request.get('system_gib'), erase_mode=request.get('erase_mode', 'random'),
                    retention=request.get('retention', 'production'), wipe_method=request.get('wipe_method', 'keys-and-random'))
                self.assertEqual(value['plan_sha256'], actual['plan_sha256'])

    def test_wrong_confirmation_never_opens_target(self):
        record = disk();request = {'mode': 'wipe', 'device': '/dev/test', 'plan_sha256': '0' * 64}
        with patch.object(engine.os, 'geteuid', return_value=0), patch.object(engine.resource, 'setrlimit'), \
             patch.object(engine.ctypes, 'CDLL', return_value=Mock(prctl=Mock(return_value=0))), \
             patch.object(engine.linux, 'choose', return_value=record), patch.object(engine, 'Target') as target:
            with self.assertRaises(InstallerError):engine.execute(request, {})
            target.assert_not_called()

    def test_variant_change_after_plan_validation_never_opens_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = bundle(Path(temporary) / 'bundle');record = disk()
            catalog = json.loads((source / 'petalos-release.json').read_text())
            for role, item in catalog['variants'][1]['payloads'].items():
                (source / item['asset']).write_bytes(('local-agent-' + role).encode())
            value = make_plan('update', record, bundle=source)
            request = request_from_plan(value, source)
            def changed_selection(directory, expected):
                (source / 'selection.json').write_text(json.dumps({'version': catalog['version'], 'variant': 'local-agent'}))
                return PinnedBundle(directory, expected)
            with patch.object(engine.os, 'geteuid', return_value=0), patch.object(engine.resource, 'setrlimit'), \
                 patch.object(engine.ctypes, 'CDLL', return_value=Mock(prctl=Mock(return_value=0))), \
                 patch.object(engine.linux, 'choose', return_value=record), \
                 patch.object(engine, 'PinnedBundle', side_effect=changed_selection), \
                 patch.object(engine, 'Target') as target, patch.object(engine, 'validate_os') as validate:
                with self.assertRaisesRegex(InstallerError, 'Selected build changed'):
                    engine.execute(request, {'system': 'disposable-system'})
                target.assert_not_called();validate.assert_not_called()

    def test_pinned_payload_survives_name_replacement_and_refuses_catalog_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = bundle(Path(temporary) / 'bundle');catalog = root / 'petalos-release.json'
            expected = hashlib.sha256(catalog.read_bytes()).hexdigest()
            with PinnedBundle(root, expected) as pinned:
                original = pinned.paths['rootfs'].read_bytes()
                (root / 'base-rootfs.bin').unlink();(root / 'base-rootfs.bin').write_bytes(b'changed')
                self.assertEqual(pinned.paths['rootfs'].read_bytes(), original)
            catalog.write_text('{}')
            with self.assertRaises(InstallerError):
                with PinnedBundle(root, expected):pass

    def test_changed_payload_never_replaces_existing_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);source = root / 'source';target = root / 'target'
            source.write_bytes(b'new-data');target.write_bytes(b'previous-working-image')
            with self.assertRaises(InstallerError):atomic_copy(source, target, '0' * 64)
            self.assertEqual(target.read_bytes(), b'previous-working-image')
            self.assertFalse(list(root.glob('.petalos-write-*')))
            expected = hashlib.sha256(source.read_bytes()).hexdigest()
            atomic_copy(source, target, expected)
            self.assertEqual(target.read_bytes(), b'new-data')

    def test_backend_packets_have_no_extra_command_channel(self):
        self.assertEqual(validate_packet({'request': {}, 'credentials': {}}), ({}, {}))
        for packet in ({'request': {}, 'credentials': {}, 'shell': 'id'}, {'request': [], 'credentials': {}}, {'credentials': {}}):
            with self.assertRaises(InstallerError):validate_packet(packet)

    def test_explicit_store_replacement_is_atomic_and_scoped(self):
        from petal_installer.store import import_file
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);state = root / 'state';state.mkdir();source = root / 'palette.json'
            source.write_text('{"format":1,"name":"Pink","colors":{"accent":"#ff99cc"}}')
            import_file(state, 'theme', source, 'pink')
            source.write_text('{"format":1,"name":"Rose","colors":{"accent":"#cc4488"}}')
            with self.assertRaises(InstallerError):import_file(state, 'theme', source, 'pink')
            import_file(state, 'theme', source, 'pink', replace=True)
            self.assertEqual(json.loads((state / 'Installer/PendingThemes/pink.json').read_text())['name'], 'Rose')

    def test_package_contains_fixed_backend_and_exact_shared_sources(self):
        spec = importlib.util.spec_from_file_location('package_builder', ROOT / 'local/installer/build-package.py')
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'root';module.stage(root)
            self.assertEqual(root.stat().st_mode & 0o777, 0o755)
            backend = root / 'usr/lib/bloom-installer/backend.py'
            self.assertEqual(backend.stat().st_mode & 0o777, 0o755)
            self.assertIn('/usr/lib/bloom-installer/backend.py', (root / 'usr/share/polkit-1/actions/org.petalos.bloom.policy').read_text())
            self.assertEqual((root / 'usr/lib/bloom-installer/petal_installer/shared/release_generations.py').read_bytes(),
                             (ROOT / 'tests/release_generations.py').read_bytes())

    def test_variant_modules_replace_old_modules_and_verify_before_activation(self):
        helper = engine.helper_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);boot = root / 'boot';osroot = root / 'os';inputs = root / 'inputs'
            for directory in (boot / 'live', osroot / 'live', inputs):directory.mkdir(parents=True)
            sources = {}
            for name in ('vmlinuz', 'initrd.img', 'filesystem.squashfs'):
                source = inputs / name;source.write_bytes(('new-' + name).encode());sources[name] = source
                ((osroot if name == 'filesystem.squashfs' else boot) / 'live' / name).write_bytes(b'old')
            (osroot / 'live/agent.squashfs').write_bytes(b'old-agent')
            module = inputs / 'agent.squashfs';module.write_bytes(b'new-agent')
            config = boot / 'grub.cfg'
            original = "menuentry 'PetalOS' {\n linux /live/vmlinuz boot=live live-media=/dev/mapper/portable_os petalos.layout=2\n initrd /live/initrd.img\n}\n"
            config.write_text(original)
            kwargs = dict(module_sources={'agent.squashfs': module}, module_hashes={'agent.squashfs': '0' * 64})
            with self.assertRaises(AssertionError):
                helper.stage_and_activate(boot, osroot, sources, {n: helper.digest(p) for n, p in sources.items()},
                    [(config, original)], ['filesystem.squashfs', 'agent.squashfs'], **kwargs)
            self.assertEqual(config.read_text(), original)
            kwargs['module_hashes']['agent.squashfs'] = helper.digest(module)
            generation, _ = helper.stage_and_activate(boot, osroot, sources, {n: helper.digest(p) for n, p in sources.items()},
                [(config, original)], ['filesystem.squashfs', 'agent.squashfs'], **kwargs)
            self.assertEqual((osroot / 'petalos/releases' / generation / 'live/agent.squashfs').read_bytes(), b'new-agent')
            self.assertEqual((osroot / 'live/agent.squashfs').read_bytes(), b'old-agent')


if __name__ == '__main__':unittest.main()
