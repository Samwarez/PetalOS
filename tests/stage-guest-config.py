#!/usr/bin/env python3
"""Stage explicit public build configuration files into the guest RAM root."""
from pathlib import Path
import base64
import importlib.util
import json
import os
import shlex
import subprocess
import sys

PROJECT=Path(__file__).resolve().parents[1]
root=PROJECT/'config/includes.chroot'
spec=importlib.util.spec_from_file_location('build_check',PROJECT/'tests/rebuild-release.py')
check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)
check.validate_inputs(PROJECT/'config')
payload={}
for name in sys.argv[1:]:
    path=root/name
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise RuntimeError('Only explicit regular public build inputs are accepted.')
    if '..' in Path(name).parts or Path(name).is_absolute():raise RuntimeError('Invalid destination.')
    payload[name]={'data':base64.b64encode(path.read_bytes()).decode(),'mode':path.stat().st_mode&0o777}
if not payload:raise RuntimeError('Select the public files to stage.')
state=json.loads(Path(f'/run/user/{os.getuid()}/petalos-encrypted-test.json').read_text())['ssh']
login=state.get('user','user')
if login not in ('user','Petal'):raise RuntimeError('Unexpected live account.')
code='''import base64,json,os,sys
from pathlib import Path
assert os.geteuid()==0
assert 'toram' in Path('/proc/cmdline').read_text().split()
os.umask(0o022)
items=json.loads(sys.stdin.read(1048577))
for name,item in items.items():
 path=Path(name)
 assert not path.is_absolute() and '..' not in path.parts and path.parts[0] in ('etc','usr')
 target=Path('/')/path
 for parent in [target,*target.parents]:assert not parent.is_symlink()
 target.parent.mkdir(parents=True,exist_ok=True)
 target.write_bytes(base64.b64decode(item['data'],validate=True));target.chmod(item['mode'])
print('Staged '+str(len(items))+' public configuration files in the guest RAM root.')
'''
remote='DISPLAY=:0 XAUTHORITY="$HOME/.Xauthority" SUDO_ASKPASS=/usr/local/bin/portable-askpass sudo -A python3 -c '+shlex.quote(code)
cmd=['ssh','-F','/dev/null','-T','-p','2222','-i',state['key'],'-o','IdentitiesOnly=yes',
     '-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','HostKeyAlias=petalos-qemu',
     '-o','UserKnownHostsFile='+state['known_hosts'],'-o','GlobalKnownHostsFile=/dev/null',
     '-o','ConnectTimeout=5',login+'@127.0.0.1',remote]
result=subprocess.run(cmd,input=json.dumps(payload).encode(),capture_output=True,timeout=180)
sys.stdout.buffer.write(result.stdout);sys.stderr.buffer.write(result.stderr)
sys.exit(result.returncode)
