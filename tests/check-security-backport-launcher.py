#!/usr/bin/python3
"""Exercise the hook against an actual package launcher, without host installs."""
from pathlib import Path
from unittest.mock import patch
import io
import json
import shutil
import subprocess
import tarfile
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
HOOK = 'config/hooks/live/0890-security-backports.hook.chroot'
INPUT = PROJECT/'config/includes.chroot/usr/local/share/portable/security-backports'
metadata = json.loads((INPUT/'manifest.json').read_text())
entry = next(e for e in metadata['packages'] if e['package'] == 'amule')
archive = INPUT/entry['file']
payload = subprocess.check_output(['dpkg-deb', '--fsys-tarfile', str(archive)])
with tarfile.open(fileobj=io.BytesIO(payload)) as package:
    vendor_launcher = package.extractfile('./usr/share/applications/amule.desktop').read()
expected = (PROJECT/'config/includes.chroot/usr/share/applications/amule.desktop').read_bytes()
assert vendor_launcher != expected
real_check_output = subprocess.check_output
real_run = subprocess.run


def exercise(code):
    with tempfile.TemporaryDirectory(prefix='petalos-launcher-regression-') as temporary:
        work = Path(temporary)
        inputs = work/'inputs'; inputs.mkdir()
        shutil.copyfile(archive, inputs/archive.name)
        (inputs/'manifest.json').write_text(json.dumps({**metadata, 'packages': [entry]}))
        launcher = work/'amule.desktop'; launcher.write_bytes(expected)
        report = work/'report.json'
        for original, replacement in (
            ('/usr/local/share/portable/security-backports', inputs),
            ('/usr/share/applications/amule.desktop', launcher),
            ('/usr/share/doc/petalos/security-backports.json', report),
        ):
            code = code.replace(repr(original), repr(str(replacement)))
        installed = [entry['base_version']]
        installs = []

        def check_output(args, **kwargs):
            if args[0] == 'dpkg-query':
                return installed[0]
            return real_check_output(args, **kwargs)

        def run(args, **kwargs):
            if args[0] == 'dpkg-query':
                return subprocess.CompletedProcess(args, 0, 'installed\n'+installed[0], '')
            if args[:3] == ['dpkg', '--force-confold', '--install']:
                assert args[3:] == [str(inputs/archive.name)]
                # Model dpkg replacing its package-owned file using real .deb bytes.
                launcher.write_bytes(vendor_launcher)
                installed[0] = entry['version']; installs.append(True)
                return subprocess.CompletedProcess(args, 0)
            if args == ['dpkg', '--audit']:
                return subprocess.CompletedProcess(args, 0, '', '')
            return real_run(args, **kwargs)

        with patch('os.geteuid', return_value=0), patch('subprocess.run', run), \
                patch('subprocess.check_output', check_output):
            exec(compile(code, HOOK, 'exec'), {'__name__': '__hook_test__'})
        assert installs and json.loads(report.read_text())['installed'][0]['version'] == entry['version']
        return launcher.read_bytes() == expected


assert exercise((PROJECT/HOOK).read_text()), 'Package install lost the maintained launcher.'
baseline = real_check_output(['git', 'show', '04425fe:'+HOOK], cwd=PROJECT, text=True)
assert not exercise(baseline), 'Negative control did not reproduce the package overwrite.'
print('Launcher preservation passed; pre-fix hook reproduces the overwrite. No host packages changed.')
