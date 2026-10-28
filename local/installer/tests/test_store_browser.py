"""Confined browser operations on fresh temporary settings trees only."""
from pathlib import Path
import contextlib
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from petal_installer import InstallerError, engine, store_browser as browser
from petal_installer.plans import make_plan
from test_installer import disk
from test_store_imports import synthetic_profile


class BrowserTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='bloom-browser-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name);self.state = self.root / 'state';self.state.mkdir()

    def request(self, action, path='Files', **fields):
        return dict(mode='store', device='/dev/fixture', plan_sha256='fixture', action=action, path=path, **fields)

    def put(self, path='Files', name='example.txt', data=b'fixture', replace=False):
        source = self.root / 'source';source.write_bytes(data)
        request = self.request('put', path, name=name, source=str(source), replace=replace)
        return browser.change(self.state, request, browser.prepare_upload(request))

    def test_root_lists_only_saved_settings_and_never_authentication_or_private(self):
        (self.state / '.petalos-auth').mkdir()
        (self.state / 'unrelated').mkdir()
        listing = browser.browse(self.state)
        self.assertEqual({e['path'] for e in listing['entries']}, set(browser.FOLDERS))
        self.assertFalse(listing['private_opened']);self.assertFalse(listing['can_add'])

    def test_other_files_add_replace_rename_and_delete_preserve_existing_files(self):
        self.put()
        with self.assertRaises(InstallerError):self.put(data=b'different')
        self.assertEqual((self.state / 'Files/example.txt').read_bytes(), b'fixture')
        self.put(data=b'replaced', replace=True)
        self.put(name='occupied.txt')
        with self.assertRaises(FileExistsError):browser.change(self.state, self.request('rename', name='example.txt', new_name='occupied.txt'))
        result = browser.change(self.state, self.request('rename', name='example.txt', new_name='new.txt'))
        self.assertEqual((self.state / 'Files/new.txt').read_bytes(), b'replaced')
        self.assertIn('File renamed', result['status'])
        browser.change(self.state, self.request('delete', name='new.txt'))
        self.assertFalse((self.state / 'Files/new.txt').exists())

    def test_new_folders_nested_browsing_and_only_empty_folder_removal(self):
        browser.change(self.state, self.request('mkdir', name='Notes'))
        listing = browser.browse(self.state, 'Files/Notes')
        self.assertEqual(listing['parent'], 'Files')
        self.put(path='Files/Notes')
        with self.assertRaises(OSError):browser.change(self.state, self.request('delete', name='Notes'))
        browser.change(self.state, self.request('delete', 'Files/Notes', name='example.txt'))
        browser.change(self.state, self.request('delete', name='Notes'))
        self.assertFalse((self.state / 'Files/Notes').exists())

    def test_vpn_upload_still_validates_profile_and_preserves_active_selection(self):
        self.put(path='Network/Profiles', name='synthetic.conf', data=synthetic_profile().encode())
        (self.state / 'Network/selected-profile').write_text('synthetic\n')
        for action, fields in [('delete', {}), ('rename', {'new_name': 'changed.conf'})]:
            with self.assertRaisesRegex(InstallerError, 'active profile'):
                browser.change(self.state, self.request(action, 'Network/Profiles', name='synthetic.conf', **fields))
        with self.assertRaisesRegex(InstallerError, 'Invalid VPN profile'):
            self.put(path='Network/Profiles', name='bad.conf', data=b'[Interface]\nPostUp = /bin/sh\n')
        self.assertFalse((self.state / 'Network/Profiles/bad.conf').exists())

    def test_typed_folders_reject_wrong_extensions_and_invalid_payloads(self):
        for path, name in [('Network/Profiles', 'file.txt'), ('Wallpapers', 'file.txt'), ('Installer/PendingThemes', 'file.txt')]:
            with self.assertRaises(InstallerError):self.put(path=path, name=name)
        with self.assertRaisesRegex(InstallerError, 'PNG'):self.put(path='Wallpapers', name='fake.png')
        self.put(path='Installer/PendingThemes', name='pink.json', data=b'{"format":1,"name":"Pink","colors":{"accent":"#ff99cc"}}')

    def test_general_file_size_limit_is_checked_before_writing(self):
        source = self.root / 'oversized'
        with source.open('wb') as output:output.truncate(browser.MAX_FILE_BYTES + 1)
        request = self.request('put', source=str(source), name='large.bin')
        with self.assertRaisesRegex(InstallerError, 'size-bounded'):browser.prepare_upload(request)
        self.assertFalse(list(self.state.iterdir()))

    def test_path_traversal_managed_writes_and_extra_packet_fields_are_refused(self):
        for path in ('../Private', '/Files', 'Files/../Desktop', '.petalos-auth', 'Files//Nested'):
            with self.assertRaises(InstallerError):browser.browse(self.state, path)
        for path in ('Desktop', 'Applications/TorBrowser', ''):
            with self.assertRaises(InstallerError):browser.validate(self.request('put', path, name='x', source='/fixture'))
        for name in ('../x', '/x', '.', '..', 'x\n', 'x\0'):
            with self.assertRaises(InstallerError):browser.validate(self.request('delete', name=name))
        with self.assertRaises(InstallerError):browser.validate(self.request('browse', shell='id'))
        with self.assertRaises(InstallerError):browser.validate(self.request('mkdir', 'Wallpapers', name='nested'))

    def test_symlinks_and_special_files_are_not_followed_or_managed(self):
        outside = self.root / 'outside';outside.mkdir();(outside / 'canary').write_bytes(b'preserved')
        (self.state / 'Files').symlink_to(outside, target_is_directory=True)
        for operation in (lambda: browser.browse(self.state, 'Files'), lambda: self.put()):
            with self.assertRaises((OSError, InstallerError)):operation()
        (self.state / 'Files').unlink();(self.state / 'Files').mkdir()
        (self.state / 'Files/link').symlink_to(outside, target_is_directory=True)
        self.assertEqual(browser.browse(self.state, 'Files')['entries'][0]['kind'], 'blocked')
        with self.assertRaises((OSError, InstallerError)):browser.browse(self.state, 'Files/link')
        with self.assertRaises(InstallerError):browser.change(self.state, self.request('delete', name='link'))
        self.assertEqual((outside / 'canary').read_bytes(), b'preserved')

    def test_browser_requests_open_only_settings_and_browse_read_only(self):
        record = disk();plan = make_plan('system-store', record)
        calls = []
        @contextlib.contextmanager
        def session(device, *, writable, passphrase):
            calls.append(writable);yield self.state
        request = dict(self.request('browse', path=''), device=record['path'], plan_sha256=plan['plan_sha256'])
        with patch.object(engine.linux, 'choose', return_value=record), patch('petal_installer.store.system_session', session):
            result = engine.perform(request, {'system': 'fixture-existing'})
            self.assertFalse(result['private_opened']);self.assertEqual(calls, [False])
            request.update(action='mkdir', path='Files', name='New')
            engine.perform(request, {'system': 'fixture-existing'})
            self.assertEqual(calls, [False, True])


if __name__ == '__main__':unittest.main()
