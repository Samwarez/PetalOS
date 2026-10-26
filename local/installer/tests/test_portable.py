from pathlib import Path
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from petal_installer import InstallerError, portable
from petal_installer import linux
from petal_installer.bridge import privileged


def fixture(directory):
    files = []
    for name, content in [('app/backend.py', b'public-worker'), ('runtime/usr/bin/tool', b'public-tool')]:
        path = directory / name;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(content)
        files.append({'path': name, 'mode': 0o644, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()})
    value = {'format': 1, 'files': files}
    stream = b''.join(portable.chunks(directory, value))
    value.update(payload_bytes=len(stream), payload_sha256=hashlib.sha256(stream).hexdigest())
    (directory / 'petal-admin').write_bytes(b'bootstrap')
    value['bootstrap_sha256'] = hashlib.sha256(b'bootstrap').hexdigest()
    (directory / 'portable.json').write_text(json.dumps(value))
    return value


class PortableTests(unittest.TestCase):
    def tearDown(self):portable._ROOT = None

    def test_relocation_and_modified_files_are_detected(self):
        with tempfile.TemporaryDirectory(prefix='petal app ') as temporary:
            root = Path(temporary);value = fixture(root)
            self.assertEqual(portable.verify(root)['payload_sha256'], value['payload_sha256'])
            moved = root / 'moved app';moved.mkdir()
            for path in ('app', 'runtime', 'portable.json', 'petal-admin'):(root / path).rename(moved / path)
            portable.verify(moved)
            (moved / 'app/backend.py').write_bytes(b'changed-worker')
            with self.assertRaises(InstallerError):portable.verify(moved)

    def test_stream_is_bounded_and_does_not_include_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);value = fixture(root)
            data = b''.join(portable.chunks(root, value))
            length, mode, size = struct.unpack('<IIQ', data[:16])
            self.assertEqual(data[16:16 + length], b'app/backend.py')
            self.assertEqual(size, len(b'public-worker'));self.assertEqual(mode, 0o644)
            self.assertEqual(data[-16:], bytes(16));self.assertEqual(len(data), value['payload_bytes'])
            (root / 'app/backend.py').unlink();(root / 'app/backend.py').symlink_to('/etc/passwd')
            with self.assertRaises(InstallerError):b''.join(portable.chunks(root, value))

    def test_manifest_rejects_escape_duplicates_modes_and_oversize(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);original = fixture(root)
            for change in ('path', 'duplicate', 'mode', 'size'):
                value = json.loads(json.dumps(original))
                if change == 'path':value['files'][0]['path'] = 'app/../../etc/forbidden'
                elif change == 'duplicate':value['files'].append(value['files'][0])
                elif change == 'mode':value['files'][0]['mode'] = 0o4755
                else:value['payload_bytes'] = 1024**3 + 1
                (root / 'portable.json').write_text(json.dumps(value))
                with self.assertRaises(InstallerError):portable.manifest(root)

    def test_host_authorization_environment_has_no_runtime_or_token_injection(self):
        with patch.dict(os.environ, {'LD_LIBRARY_PATH': '/portable/lib', 'LD_PRELOAD': '/bad.so',
                                    'PYTHONPATH': '/bad', 'GH_TOKEN': 'test-session-only',
                                    'GITHUB_TOKEN': 'test-session-only', 'DISPLAY': ':91'}):
            result = portable.host_environment()
            self.assertEqual(result['DISPLAY'], ':91')
            for key in ('LD_LIBRARY_PATH', 'LD_PRELOAD', 'PYTHONPATH', 'GH_TOKEN', 'GITHUB_TOKEN'):
                self.assertNotIn(key, result)

    def test_portable_transport_uses_its_worker_and_pipe_only_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);value = fixture(root);portable.configure(root)
            worker = root / 'fake-worker.py'
            worker.write_text('''import sys,json
stream=sys.stdin.buffer.read(''' + str(value['payload_bytes']) + ''')
packet=json.loads(sys.stdin.buffer.readline())
assert packet['credentials']['system']=='disposable-test-only'
print(json.dumps({'type':'progress','value':{'stage':'verified-test-worker'}}),flush=True)
print(json.dumps({'type':'result','value':{'ok':True,'mode':packet['request']['mode']}}),flush=True)
''')
            credentials = {'system': 'disposable-test-only'};events = []
            arguments = ['/usr/bin/python3', '-I', str(worker)]
            with patch.object(portable, 'prepare', return_value=(arguments, value)):
                self.assertEqual(privileged({'mode': 'recovery'}, credentials, events.append), {'ok': True, 'mode': 'recovery'})
            self.assertEqual(credentials, {});self.assertEqual(events[0]['stage'], 'verified-test-worker')
            self.assertNotIn('disposable-test-only', ' '.join(arguments))

    def test_cancellation_before_staging_never_sends_a_job(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);value = fixture(root);portable.configure(root)
            cancel = threading.Event();cancel.set()
            worker = root / 'fake-worker.py'
            worker.write_text("import sys\nassert sys.stdin.buffer.read()==b''\n")
            with patch.object(portable, 'prepare', return_value=(['/usr/bin/python3', '-I', str(worker)], value)):
                credentials = {'system': 'disposable-test-only'}
                with self.assertRaises(InstallerError):privileged({'mode': 'recovery'}, credentials, cancel=cancel)
                self.assertEqual(credentials, {})

    def test_runtime_failure_clears_credentials_before_any_authorization(self):
        with tempfile.TemporaryDirectory() as temporary:
            portable.configure(Path(temporary))
            credentials = {'system': 'disposable-test-only'}
            with patch.object(portable, 'prepare', side_effect=InstallerError('Missing portable file.')), \
                 patch('petal_installer.bridge.subprocess.Popen') as process:
                with self.assertRaises(InstallerError):privileged({'mode': 'recovery'}, credentials)
                process.assert_not_called();self.assertEqual(credentials, {})

    def test_private_runtime_observes_new_host_mounts_and_refuses_unknown_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            mounts = Path(temporary) / 'mountinfo'
            record = {'path': '/dev/test', 'type': 'disk', 'maj:min': '8:0',
                      'children': [{'path': '/dev/test1', 'type': 'part', 'maj:min': '8:1'}]}
            mounts.write_text('1 0 0:1 / / rw - tmpfs tmpfs rw\n')
            with patch.object(linux, 'HOST_MOUNTINFO', mounts), \
                 patch.object(linux, 'command', return_value=json.dumps({'blockdevices': [record]}).encode()):
                self.assertEqual(linux.raw_disk('/dev/test'), record)
                mounts.write_text('1 0 0:1 / / rw - tmpfs tmpfs rw\n2 1 8:1 / /media/test rw - ext4 /dev/test1 rw\n')
                with self.assertRaisesRegex(InstallerError, 'host application mounted'):
                    linux.raw_disk('/dev/test')
                mounts.write_text('invalid mount information')
                with self.assertRaises(InstallerError):linux.raw_disk('/dev/test')
                mounts.unlink()
                with self.assertRaises(InstallerError):linux.raw_disk('/dev/test')


if __name__ == '__main__':unittest.main()
