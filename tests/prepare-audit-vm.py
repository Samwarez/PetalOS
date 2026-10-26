#!/usr/bin/env python3
"""Prepare an empty, separately credentialed audit VM; never clone user data."""
from pathlib import Path
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import secrets
import shutil
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]


def main():
    assert os.geteuid() != 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release', type=Path)
    parser.add_argument('--vpn', type=Path)
    parser.add_argument('--generation', action='store_true')
    parser.add_argument('--graphical-preview', action='store_true',
                        help='Use graphical boot artwork and manual/observed SYSTEM entry instead of serial auto-entry.')
    args = parser.parse_args()
    if args.graphical_preview and not args.generation:
        parser.error('--graphical-preview requires --generation')
    release = args.release.resolve(strict=True)
    assert release.parent == PROJECT.parent / 'releases'
    assert (release / 'manifest.json').is_file()
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    work = PROJECT.parent / 'testing/audit' / stamp
    work.mkdir(parents=True, mode=0o700)
    credentials = {name: 'Audit-' + secrets.token_hex(12) for name in ('system', 'administrator', 'private')}
    (work / 'credentials.json').write_text(json.dumps(credentials))
    (work / 'credentials.json').chmod(0o600)
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'petalos-disposable-audit',
                    '-f', str(work / 'id_ed25519')], check=True)
    spec = importlib.util.spec_from_file_location('builder', PROJECT / 'tests/build-ssh-module.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    layer = module.build(work, public_key=work / 'id_ed25519.pub')
    image = work / 'audit.img'
    with image.open('xb') as output:
        output.truncate(16 * 1024**3)
    shutil.copyfile('/usr/share/OVMF/OVMF_VARS_4M.ms.fd', work / 'OVMF_VARS.fd')
    state = {'phase': 'awaiting-provisioning', 'scope': 'disposable-audit-only',
             'directory': str(work), 'release': str(release), 'image': str(image),
             'ssh_module': str(layer), 'ssh_module_sha256': hashlib.sha256(layer.read_bytes()).hexdigest(),
             'cid': 43, 'port': 2225, 'vpn_provisioned': False,
             'generation_boot': args.generation}
    if args.graphical_preview:
        state['graphical_boot'] = True
    if args.vpn is not None:
        source = args.vpn.resolve(strict=True)
        assert source.is_file()
        state['vpn_source'] = str(source)
    path = work / 'state.json'; path.write_text(json.dumps(state, indent=2))
    print('Fresh audit workspace:', work, flush=True)
    print('Test credentials remain outside build inputs in its mode-0600 credentials.json.', flush=True)
    subprocess.run(['/usr/bin/sudo', '--', '/usr/bin/python3', '-B',
                    str(PROJECT / 'tests/provision-audit-root.py'), str(path)], check=True)
    print('Fresh audit VM prepared. Existing disks and physical media were not modified.', flush=True)


if __name__ == '__main__':
    os.umask(0o077)
    try:
        main()
    except Exception as error:
        print('Audit preparation stopped: ' + type(error).__name__ + '; inspect stage status.', file=sys.stderr)
        sys.exit(1)
