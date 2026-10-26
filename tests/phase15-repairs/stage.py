#!/usr/bin/env python3
"""Stage explicit public inputs into the disposable audit VM's RAM overlay."""
from pathlib import Path
import base64
import hashlib
import importlib.util
import json
import shlex
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('audit', PROJECT/'tests/audit-vm.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
work, state = a.state(PROJECT.parent/'testing/audit/20261017-221958-817753/state.json')
root = PROJECT/'config/includes.chroot'
items = {}
for name in sys.argv[1:]:
    path = root/name
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    assert path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root)
    assert Path(name).parts[0] in ('usr', 'etc')
    data = path.read_bytes()
    items[name] = {'data': base64.b64encode(data).decode(), 'sha256': hashlib.sha256(data).hexdigest(),
                   'mode': path.stat().st_mode & 0o777}
assert items
code = '''import base64,hashlib,json,os,sys,subprocess
from pathlib import Path
assert os.geteuid()==0 and 'toram' in Path('/proc/cmdline').read_text().split()
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
items=json.load(sys.stdin)
for name,item in items.items():
 p=Path(name);assert not p.is_absolute() and '..' not in p.parts and p.parts[0] in ('etc','usr')
 target=Path('/')/p
 assert not any(f.is_symlink() for f in [target,*target.parents])
 data=base64.b64decode(item['data'],validate=True);assert hashlib.sha256(data).hexdigest()==item['sha256']
 target.parent.mkdir(parents=True,exist_ok=True)
 temporary=target.with_name('.'+target.name+'.repair-stage')
 fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:
  with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
  os.chmod(temporary,item['mode']);os.replace(temporary,target)
 finally:temporary.unlink(missing_ok=True)
 assert hashlib.sha256(target.read_bytes()).hexdigest()==item['sha256']
for name in items:
 if name.startswith('etc/apparmor.d/petalos.'):
  subprocess.run(['apparmor_parser','-r','/'+name],check=True,capture_output=True)
print(json.dumps({'public_files_staged':len(items),'all_readbacks_match':True}))
'''
credentials = json.loads((work/'credentials.json').read_text())
payload = credentials['administrator'].encode()+b'\n'+json.dumps(items).encode()
command = shlex.join(['sudo','-S','-p','','--','python3','-I','-c',code])
r = a.ssh(work,command,input=payload,capture_output=True,timeout=120)
for output,stream in ((r.stdout,sys.stdout.buffer),(r.stderr,sys.stderr.buffer)):
    for value in credentials.values():output=output.replace(value.encode(),b'[redacted]')
    stream.write(output[-5000:])
raise SystemExit(r.returncode)
