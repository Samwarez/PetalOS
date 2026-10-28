"""Native-file-manager edit snapshots on fresh synthetic settings trees."""
from pathlib import Path
import contextlib
import json
import os
import tempfile
import subprocess
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from petal_installer import InstallerError, store_editor as editor, store
from petal_installer import editor_client, linux
from petal_installer.plans import make_plan
from test_installer import disk
from test_store_imports import synthetic_profile


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bloom-editor-test-');self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name);self.state = self.root / 'state';self.state.mkdir()
        profiles = self.state / 'Network/Profiles';profiles.mkdir(parents=True)
        (profiles / 'fixture.conf').write_text(synthetic_profile())
        (self.state / 'Files').mkdir();(self.state / 'Files/original.txt').write_bytes(b'original')
        self.workspace = self.root / 'workspace';self.workspace.mkdir(mode=0o700)
        self.fd = os.open(self.workspace, os.O_RDONLY | os.O_DIRECTORY);self.addCleanup(os.close, self.fd)
        self.editing = editor.EditingCopy(self.state, self.fd, os.getuid());self.editing.export()

    def test_exports_editable_settings_only_and_uses_normal_files(self):
        self.assertTrue((self.workspace / 'Network/Profiles/fixture.conf').is_file())
        self.assertEqual((self.workspace / 'Files/original.txt').read_bytes(), b'original')
        self.assertFalse((self.workspace / '.petalos-auth').exists())
        self.assertFalse((self.workspace / 'Private').exists())
        self.assertFalse((self.workspace / 'Applications').exists())

    def test_drag_copy_nested_folder_rename_delete_and_save(self):
        files = self.workspace / 'Files';(files / 'Nested').mkdir()
        (files / 'Nested/new.txt').write_bytes(b'new')
        (files / 'original.txt').rename(files / 'renamed.txt')
        result = self.editing.save()
        self.assertTrue(result['saved']);self.assertFalse(result['private_opened'])
        self.assertEqual((self.state / 'Files/Nested/new.txt').read_bytes(), b'new')
        self.assertEqual((self.state / 'Files/renamed.txt').read_bytes(), b'original')
        self.assertFalse((self.state / 'Files/original.txt').exists())

    def test_no_save_does_not_change_card_files(self):
        (self.workspace / 'Files/original.txt').write_bytes(b'edited only in RAM')
        self.assertEqual((self.state / 'Files/original.txt').read_bytes(), b'original')

    def test_all_changed_profiles_validated_before_any_card_mutation(self):
        (self.workspace / 'Files/original.txt').write_bytes(b'new')
        (self.workspace / 'Network/Profiles/fixture.conf').write_text('[Interface]\nPostUp = /bin/sh\n')
        with self.assertRaisesRegex(InstallerError, 'Invalid VPN profile'):self.editing.save()
        self.assertEqual((self.state / 'Files/original.txt').read_bytes(), b'original')

    def test_active_vpn_deletion_and_unexpected_root_files_refused(self):
        (self.state / 'Network/selected-profile').write_text('fixture\n')
        (self.workspace / 'Network/Profiles/fixture.conf').unlink()
        with self.assertRaisesRegex(InstallerError, 'active VPN'):self.editing.save()
        (self.workspace / 'outside.txt').write_bytes(b'unsupported')
        with self.assertRaises(InstallerError):self.editing.save()

    def test_symlink_hard_link_special_and_outside_folder_refused(self):
        outside = self.root / 'outside';outside.write_bytes(b'preserved')
        path = self.workspace / 'Files/link'
        path.symlink_to(outside)
        with self.assertRaises((OSError, InstallerError)):self.editing.save()
        path.unlink();os.link(outside, path)
        with self.assertRaises(InstallerError):self.editing.save()
        path.unlink();os.mkfifo(path)
        with self.assertRaises(InstallerError):self.editing.save()
        self.assertEqual(outside.read_bytes(), b'preserved')

    def test_external_card_changes_are_not_overwritten(self):
        (self.state / 'Files/original.txt').write_bytes(b'changed elsewhere')
        with self.assertRaisesRegex(InstallerError, 'outside this session'):self.editing.save()

    def test_entry_and_memory_limits_are_checked_before_writes(self):
        with patch.object(editor, 'MAX_TOTAL', 1):
            with self.assertRaisesRegex(InstallerError, '128 MiB'):self.editing.save()
        with patch.object(editor, 'MAX_ENTRIES', 1):
            with self.assertRaisesRegex(InstallerError, '1000 entries'):self.editing.save()

    def test_one_unlock_for_invalid_save_retry_and_final_save(self):
        record = disk();plan = make_plan('system-store', record)
        workspace = self.root / 'session';workspace.mkdir(mode=0o700)
        request = dict(mode='store-editor', device=record['path'], plan_sha256=plan['plan_sha256'], workspace=str(workspace))
        incoming, outgoing = os.pipe();self.addCleanup(os.close, incoming);self.addCleanup(os.close, outgoing)
        calls = [];events = [];credentials = {'system': 'fixture-passphrase'}
        @contextlib.contextmanager
        def session(*args, **kwargs):calls.append(True);yield self.state
        def emit(kind, value):
            events.append(kind)
            if kind == 'editor-ready':
                self.assertEqual(credentials, {})
                (workspace / 'Network/Profiles/fixture.conf').write_text('[Interface]\nPostUp = /bin/sh\n')
                os.write(outgoing,b'{"action":"save"}\n')
            if kind == 'editor-error':
                (workspace / 'Network/Profiles/fixture.conf').write_text(synthetic_profile())
                (workspace / 'Files/new.txt').write_bytes(b'saved once')
                os.write(outgoing,b'{"action":"save"}\n')
        def read(fd):
            data = bytearray()
            while not data.endswith(b'\n'):data.extend(os.read(fd,1))
            return data
        with patch.object(linux, 'choose', return_value=record), patch.object(linux, 'raw_disk', return_value={}), \
             patch.object(linux, 'describe', return_value=record), patch.object(store, 'system_session', session), \
             patch.object(editor, 'workspace_fd', side_effect=lambda *_: os.open(workspace, os.O_RDONLY | os.O_DIRECTORY)):
            result = editor.serve(request, credentials, os.getuid(), incoming, emit, read)
        self.assertTrue(result['saved']);self.assertEqual(len(calls), 1)
        self.assertEqual(events.count('editor-ready'), 1);self.assertEqual(events.count('editor-error'), 1)
        self.assertEqual((self.state / 'Files/new.txt').read_bytes(), b'saved once')

    def test_eof_discards_and_leaves_session_cleanup_to_context_manager(self):
        record = disk();plan = make_plan('system-store', record)
        other = self.root / 'eof';other.mkdir(mode=0o700);closed = []
        @contextlib.contextmanager
        def session(*args, **kwargs):
            try:yield self.state
            finally:closed.append(True)
        request = dict(mode='store-editor',device=record['path'],plan_sha256=plan['plan_sha256'],workspace=str(other))
        with patch.object(linux,'choose',return_value=record),patch.object(store,'system_session',session), \
             patch.object(editor,'workspace_fd',side_effect=lambda *_:os.open(other,os.O_RDONLY|os.O_DIRECTORY)):
            result=editor.serve(request,{'system':'fixture-passphrase'},os.getuid(),-1,lambda *_:None,lambda *_:b'')
        self.assertFalse(result['saved']);self.assertEqual(closed,[True])

    def test_workspace_identity_constraints_reject_arbitrary_host_directories(self):
        with self.assertRaises(InstallerError):editor.workspace_fd(self.workspace,os.getuid())
        with self.assertRaises(InstallerError):editor.workspace_fd('/run/user/1000/bloom-settings-test',0)

    def test_interrupted_save_closes_session_instead_of_offering_retry(self):
        record = disk();plan = make_plan('system-store', record);closed = [];events = []
        workspace = self.root / 'interrupted';workspace.mkdir(mode=0o700)
        credentials = {'system':'fixture-passphrase'}
        @contextlib.contextmanager
        def session(*args, **kwargs):
            try:yield self.state
            finally:closed.append(True)
        request = dict(mode='store-editor',device=record['path'],plan_sha256=plan['plan_sha256'],workspace=str(workspace))
        with patch.object(linux,'choose',return_value=record),patch.object(linux,'raw_disk',return_value={}), \
             patch.object(linux,'describe',return_value=record),patch.object(store,'system_session',session), \
             patch.object(editor,'workspace_fd',side_effect=lambda *_:os.open(workspace,os.O_RDONLY|os.O_DIRECTORY)), \
             patch.object(editor.EditingCopy,'save',side_effect=InterruptedError('Editing session stopped.')):
            with self.assertRaises(InterruptedError):
                editor.serve(request,credentials,os.getuid(),-1,lambda kind,value:events.append(kind),lambda *_:b'{"action":"save"}\n')
        self.assertEqual(closed,[True]);self.assertEqual(credentials,{})
        self.assertNotIn('editor-error',events)


class FileManagerTests(unittest.TestCase):
    def test_single_worker_handles_save_retry_and_cleans_ram_workspace(self):
        real_popen = subprocess.Popen
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / 'working';workspace.mkdir()
            events = [];credentials = {'system': 'synthetic-only'}
            script = '''import json,sys
packet=json.loads(sys.stdin.readline())
print(json.dumps({'type':'editor-ready','value':{'workspace':packet['request']['workspace']}}),flush=True)
attempt=0
for line in sys.stdin:
 command=json.loads(line);attempt+=1
 if attempt==1:print(json.dumps({'type':'editor-error','value':{'message':'Synthetic validation failure.'}}),flush=True)
 else:
  print(json.dumps({'type':'result','value':{'saved':True}}),flush=True);break
'''
            def event(value):
                events.append(value)
                if value['type'] in ('editor-ready','editor-error'):session.send('save')
            session = editor_client.EditingSession({'device':'/dev/fixture','plan_sha256':'fixture'},credentials,event,workspace=workspace)
            with patch.object(editor_client.portable,'root',return_value=Path(directory)), \
                 patch.object(editor_client.portable,'prepare',return_value=([sys.executable,'-u','-c',script],None)), \
                 patch.object(editor_client.subprocess,'Popen',wraps=real_popen) as launch:
                session.run()
            self.assertEqual(launch.call_count,1);self.assertEqual(credentials,{})
            self.assertFalse(workspace.exists())
            self.assertTrue(events[-1]['value']['saved'])
            self.assertEqual([e['type'] for e in events],['editor-ready','editor-error','editor-closed'])

    def test_opener_runs_as_desktop_user_with_clean_host_library_environment(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(editor_client.subprocess,'Popen') as launch:
            with patch.dict(os.environ, {'LD_LIBRARY_PATH':'/portable/runtime','PYTHONHOME':'/portable/runtime','GTK_PATH':'/portable/runtime','XDG_CURRENT_DESKTOP':'KDE'}):
                editor_client.open_folder(Path(directory))
            self.assertEqual(launch.call_args.args[0], ['/usr/bin/xdg-open',directory])
            environment=launch.call_args.kwargs['env']
            for name in ('LD_LIBRARY_PATH','PYTHONHOME','GTK_PATH'):self.assertNotIn(name,environment)
            self.assertEqual(environment['XDG_CURRENT_DESKTOP'],'KDE')


if __name__=='__main__':unittest.main()
