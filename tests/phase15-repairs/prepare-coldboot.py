#!/usr/bin/env python3
"""Build an explicit public repair layer, only inside the disposable audit VM."""
from pathlib import Path
import hashlib, importlib.util, io, json, os, shlex, subprocess, sys, tarfile
PROJECT=Path(__file__).resolve().parents[2]
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path)
 value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
a=module('audit',PROJECT/'tests/audit-vm.py')
build=module('build',PROJECT/'tests/rebuild-release.py');build.validate_inputs(PROJECT/'config')
work,state=a.state(PROJECT.parent/'testing/audit/20261017-221958-817753/state.json')
paths=subprocess.check_output(['git','diff','--name-only','-z'],cwd=PROJECT).split(b'\0')
paths+=subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=PROJECT).split(b'\0')
items={}
for raw in paths:
 path=Path(os.fsdecode(raw))
 if str(path).startswith('config/includes.chroot/'):
  source=PROJECT/path
  assert source.is_file() and not source.is_symlink()
  items['root/'+str(path.relative_to('config/includes.chroot'))]=source
native=PROJECT/'config/includes.chroot/usr/local/share/portable/native-keepassxc'
items['root/usr/bin/keepassxc.portable-real']=native/'keepassxc'
items['root/usr/bin/keepassxc-cli']=native/'keepassxc-cli'
items['generation.py']=PROJECT/'tests/release_generations.py'
items['toram-hook']=PROJECT/'config/hooks/live/0912-generation-ram-copy.hook.chroot'
payload=io.BytesIO()
manifest={}
with tarfile.open(fileobj=payload,mode='w') as archive:
 for name,source in sorted(items.items()):
  data=source.read_bytes();info=tarfile.TarInfo(name);info.size=len(data)
  info.mode=source.stat().st_mode&0o777;info.uid=info.gid=0
  archive.addfile(info,io.BytesIO(data));manifest[name]=hashlib.sha256(data).hexdigest()
data=payload.getvalue();checksum=hashlib.sha256(data).hexdigest()
r=a.ssh(work,'umask 077; cat > /tmp/petalos-public-repairs.tar',input=data,capture_output=True,timeout=60)
assert r.returncode==0
values=json.loads((work/'credentials.json').read_text())
control={'credentials':values,'sha256':checksum,'manifest':manifest}
code=(Path(__file__).with_name('prepare-coldboot-guest.py')).read_text()
command=shlex.join(['sudo','-S','-p','','--','python3','-I','-c',code])
r=a.ssh(work,command,input=values['administrator'].encode()+b'\n'+json.dumps(control).encode(),capture_output=True,timeout=600)
for value in values.values():
 r.stdout=r.stdout.replace(value.encode(),b'[redacted]');r.stderr=r.stderr.replace(value.encode(),b'[redacted]')
record={'exit':r.returncode,'public_input_sha256':checksum,'files':manifest,'stdout':r.stdout.decode()[-20000:],'stderr':r.stderr.decode()[-4000:]}
(PROJECT/'docs/phase15-repairs/coldboot-preparation.json').write_text(json.dumps(record,indent=2))
print(json.dumps({'exit':r.returncode,'public_files':len(manifest)}))
print(record['stdout']);print(record['stderr'],file=sys.stderr)
sys.exit(r.returncode)
