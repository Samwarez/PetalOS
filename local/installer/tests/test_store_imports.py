"""Synthetic imports only; never read host profiles or select a real drive."""
from pathlib import Path
import base64
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from petal_installer import InstallerError, store
from petal_installer.releases import plain_file


def synthetic_profile():
    # Public, deterministic fixture bytes and documentation-only IP addresses.
    private = base64.b64encode(bytes(range(32))).decode()
    public = base64.b64encode(bytes(reversed(range(32)))).decode()
    return ('[Interface]\nPrivateKey = ' + private + '\nAddress = 10.23.0.2/32\n'
            'DNS = 192.0.2.53\n[Peer]\nPublicKey = ' + public + '\n'
            'AllowedIPs = 0.0.0.0/0, ::/0\nEndpoint = 192.0.2.10:51820\n')


class StoreImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='bloom-import-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.downloads = self.root / 'other-filesystem' / 'Downloads'
        self.downloads.mkdir(parents=True)
        self.alias = self.root / 'Downloads'
        self.alias.symlink_to(self.downloads, target_is_directory=True)
        self.profile = self.downloads / 'synthetic.conf'
        self.profile.write_text(synthetic_profile())
        self.state = self.root / 'settings';self.state.mkdir()

    def test_regular_vpn_in_linked_downloads_imports_and_keeps_selection(self):
        source = self.alias / self.profile.name
        self.assertFalse(source.is_symlink())
        network = self.state / 'Network';network.mkdir()
        selection = network / 'selected';selection.write_text('existing\n')
        result = store.import_file(self.state, 'vpn', source, 'synthetic')
        self.assertTrue(result['imported'])
        target = network / 'Profiles/synthetic.conf'
        self.assertTrue(target.read_text() == synthetic_profile())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(selection.read_text(), 'existing\n')

    def test_linked_home_ancestor_and_alias_retarget_do_not_redirect_resolved_read(self):
        home = self.root / 'home-link';home.symlink_to(self.root / 'other-filesystem', target_is_directory=True)
        self.assertTrue(store.read_import(home / 'Downloads' / self.profile.name, 16384) == self.profile.read_bytes())
        alternate = self.root / 'alternate';alternate.mkdir()
        (alternate / self.profile.name).write_bytes(b'different target')
        actual = store.directory_fd
        def retarget(path):
            self.alias.unlink();self.alias.symlink_to(alternate, target_is_directory=True)
            return actual(path)
        with patch.object(store, 'directory_fd', side_effect=retarget):
            self.assertTrue(store.read_import(self.alias / self.profile.name, 16384) == self.profile.read_bytes())

    def test_file_symlinks_and_last_moment_file_swap_are_rejected(self):
        linked = self.downloads / 'shortcut.conf';linked.symlink_to(self.profile)
        with self.assertRaisesRegex(InstallerError, 'import file is a symbolic link'):
            store.checked_payload('vpn', self.alias / linked.name)
        actual = store.directory_fd
        def replace_file(path):
            fd = actual(path)
            self.profile.rename(self.downloads / 'original.conf')
            self.profile.symlink_to(self.downloads / 'original.conf')
            return fd
        with patch.object(store, 'directory_fd', side_effect=replace_file):
            with self.assertRaises(InstallerError):store.checked_payload('vpn', self.alias / self.profile.name)

    def test_resolved_directory_swap_is_rejected_before_reading(self):
        actual = store.directory_fd
        alternate = self.root / 'alternate';alternate.mkdir()
        (alternate / self.profile.name).write_bytes(b'different target')
        def replace_directory(path):
            self.downloads.rename(self.root / 'original-downloads')
            self.downloads.symlink_to(alternate, target_is_directory=True)
            return actual(path)
        with patch.object(store, 'directory_fd', side_effect=replace_directory):
            with self.assertRaises(InstallerError):store.read_import(self.alias / self.profile.name, 16384)

    def test_missing_loop_fifo_directory_and_oversized_sources_are_safe_errors(self):
        loop = self.root / 'loop';loop.symlink_to(loop, target_is_directory=True)
        fifo = self.downloads / 'pipe';os.mkfifo(fifo)
        large = self.downloads / 'large';large.write_bytes(b'x' * 16385)
        for source in (self.alias / 'missing', loop / 'file', self.alias / fifo.name, self.alias, self.alias / large.name):
            with self.subTest(source=source.name):
                with self.assertRaises(InstallerError) as caught:store.checked_payload('vpn', source)
                self.assertNotIn('release inputs', str(caught.exception))

    def test_linked_source_does_not_relax_destination_or_release_guards(self):
        outside = self.root / 'outside';outside.mkdir()
        (self.state / 'Network').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(InstallerError):store.import_file(self.state, 'vpn', self.alias / self.profile.name, 'synthetic')
        self.assertFalse(list(outside.iterdir()))
        with self.assertRaisesRegex(InstallerError, 'release inputs'):plain_file(self.alias / self.profile.name)

    def test_linked_source_still_rejects_executable_vpn_hooks_without_writing(self):
        self.profile.write_text(synthetic_profile().replace('[Interface]\n', '[Interface]\nPostUp = /bin/sh\n'))
        with self.assertRaisesRegex(InstallerError, 'Invalid VPN profile'):
            store.import_file(self.state, 'vpn', self.alias / self.profile.name, 'synthetic')
        self.assertFalse(list(self.state.iterdir()))


if __name__ == '__main__':unittest.main()
