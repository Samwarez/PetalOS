#!/usr/bin/python3
"""Record a bounded public fixture result for an explicitly selected test VM."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('state', type=Path)
parser.add_argument('fixture', type=Path)
parser.add_argument('--credentials', action='store_true')
parser.add_argument('--label')
args = parser.parse_args()
fixture = args.fixture.resolve(strict=True)
assert fixture.is_relative_to(PROJECT/'tests') and fixture.suffix == '.py'
state = args.state.resolve(strict=True)
assert state.parent.parent == PROJECT.parent/'testing/audit'
label = args.label or fixture.stem
assert re.fullmatch(r'[a-zA-Z0-9_-]+', label)
output = PROJECT/'docs/phase15-combined-vm-20261019'
output.mkdir(exist_ok=True)
target = output/(label+'.json')
assert not target.exists(), 'Choose a new label to preserve previous evidence.'
started = time.monotonic()
result = subprocess.run([sys.executable, '-B', str(PROJECT/'tests/audit-vm.py'), str(state),
    'root-credential-script' if args.credentials else 'root-script', str(fixture)],
    capture_output=True, timeout=620)
record = {'fixture': str(fixture.relative_to(PROJECT)), 'VM': state.parent.name,
          'fixture_sha256': hashlib.sha256(fixture.read_bytes()).hexdigest(),
          'exit': result.returncode, 'seconds': round(time.monotonic()-started, 2),
          'stdout': result.stdout.decode(errors='replace')[-65536:],
          'stderr': result.stderr.decode(errors='replace')[-8000:]}
target.write_text(json.dumps(record, indent=2)+'\n')
print(json.dumps(record))
sys.exit(result.returncode)
