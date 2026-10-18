#!/usr/bin/python3
"""Emit a public source-only frame for an already authenticated root session."""
import base64
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1] / 'config/includes.chroot'
payload = {}
for name in sys.argv[1:]:
    relative = Path(name)
    assert not relative.is_absolute() and '..' not in relative.parts
    path = root / relative
    assert path.is_file() and not path.is_symlink()
    assert path.resolve().is_relative_to(root.resolve())
    payload[name] = {'data': base64.b64encode(path.read_bytes()).decode(),
                     'mode': path.stat().st_mode & 0o755}
code = '''import base64,os
from pathlib import Path
assert os.geteuid()==0 and 'toram' in Path('/proc/cmdline').read_text().split()
items=PAYLOAD
for name,item in items.items():
 p=Path('/')/name
 assert not any(q.is_symlink() for q in (p,*p.parents))
 p.parent.mkdir(parents=True,exist_ok=True)
 p.write_bytes(base64.b64decode(item['data'],validate=True));p.chmod(item['mode'])
print('Staged '+str(len(items))+' explicit public files into guest RAM.')
'''.replace('PAYLOAD', repr(payload))
print(json.dumps({'op': 'exec', 'source': code}))
