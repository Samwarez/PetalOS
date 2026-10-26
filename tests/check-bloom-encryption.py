#!/usr/bin/python3 -B
"""Actual Bloom tier calibration and LUKS2 header checks on new private files.

No block-device paths, root privileges, mappings or personal credentials are
accepted. The test's secrets stay in memory and never appear in arguments/logs.
"""
from pathlib import Path
import argparse
import datetime
import json
import os
import secrets
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'local/installer'))
from petal_installer import encryption, layout2, linux


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/bloom-encryption-native-20261025.json')
    args = parser.parse_args();os.umask(0o077)
    work = Path(tempfile.mkdtemp(prefix='bloom-encryption-', dir='/tmp'))
    report = {'passed': False, 'scope': 'Real cryptsetup/Argon2id and LUKS2 headers in fresh regular files; no physical media or open mappings.', 'tiers': {}}
    for profile in encryption.PROFILES:
        calibration = encryption.calibrate(profile)
        checks = {}
        for role in layout2.VOLUMES:
            image = work / (profile + '-' + role + '.img')
            with image.open('xb') as stream:stream.truncate(64 * 1024**2)
            image.chmod(0o600);password = secrets.token_urlsafe(32).encode()
            linux.command(layout2.encryption_arguments(image, role, str(uuid.uuid4()), profile=profile, calibration=calibration), payload=password, timeout=180)
            metadata = json.loads(linux.command(['/usr/sbin/cryptsetup', 'luksDump', '--dump-json-metadata', str(image)]))
            encryption.verify_header(metadata, profile, calibration)
            checks[role + '_actual_header_matches'] = True
            if role == 'os':
                arguments = ['/usr/sbin/cryptsetup', 'open', '--type', 'luks2', '--test-passphrase', '--key-file', '-', str(image)]
                linux.command(arguments, payload=password, timeout=180)
                wrong = subprocess.run(arguments, input=secrets.token_urlsafe(32).encode(), capture_output=True, timeout=180)
                assert wrong.returncode == 2, 'Wrong disposable credential unexpectedly accepted.'
                checks['correct_passphrase_accepted'] = True;checks['wrong_passphrase_refused'] = True
            password = None
        report['tiers'][profile] = {'calibration': calibration, 'checks': checks}
        print('Native Bloom encryption tier passed:', profile, flush=True)
    report['passed'] = True
    args.output.write_text(json.dumps(report, indent=2) + '\n');args.output.chmod(0o644)
    print('Native encryption acceptance:', args.output, flush=True)


if __name__ == '__main__':main()
