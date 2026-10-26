#!/usr/bin/python3
"""Send only public built-input hashes to a disposable guest for boot checks."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import shlex

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('state', type=Path)
parser.add_argument('--offline', action='store_true')
args = parser.parse_args()
spec = importlib.util.spec_from_file_location('audit', Path(__file__).with_name('audit-vm.py'))
audit = importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
work, state = audit.state(args.state)
public = Path(state['release'])/'build/config/includes.chroot'
metadata = json.loads((public/'usr/local/share/portable/security-backports/manifest.json').read_text())
skip = {'usr/local/share/portable/security-backports/'+e['file'] for e in metadata['packages']}
mapping = {'usr/local/share/portable/native-parole/parole': 'usr/bin/parole.portable-real',
           'usr/local/share/portable/native-conky/conky': 'usr/bin/conky',
           'usr/local/share/portable/native-keepassxc/keepassxc': 'usr/bin/keepassxc.portable-real',
           'usr/local/share/portable/native-keepassxc/keepassxc-cli': 'usr/bin/keepassxc-cli'}
items = {}
for path in public.rglob('*'):
    if not path.is_file():continue
    relative = str(path.relative_to(public))
    if relative not in skip:
        items[mapping.get(relative, relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
payload = json.dumps({'generation': state['generation'], 'public_files': items, 'offline': args.offline}).encode()
code = 'from pathlib import Path;import sys;Path("/tmp/petalos-combined-expected.json").write_bytes(sys.stdin.buffer.read())'
result = audit.ssh(work, shlex.join(['python3','-I','-c',code]), input=payload, capture_output=True, timeout=15)
assert result.returncode == 0, 'Public expectation staging failed; raw output suppressed.'
print('Public expectation hashes staged; no production guest files changed.')
