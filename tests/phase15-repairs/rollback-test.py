#!/usr/bin/env python3
"""Select retained public boot configurations in the disposable VM only."""
from pathlib import Path
import importlib.util,json,shlex,sys
project=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('audit',project/'tests/audit-vm.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
work,state=a.state(project.parent/'testing/audit/20261017-221958-817753/state.json')
assert sys.argv[1:] in (['baseline'],['candidate'])
values=json.loads((work/'credentials.json').read_text())
preparation=json.loads((project/'docs/phase15-repairs/coldboot-preparation.json').read_text())
generations=[json.loads(line)['generation'] for line in preparation['stdout'].splitlines() if line.startswith('{"generation":')]
assert len(generations)==1
code=Path(__file__).with_name('rollback-test-guest.py').read_text()
r=a.ssh(work,shlex.join(['sudo','-S','-p','','--','python3','-I','-c',code]),
 input=values['administrator'].encode()+b'\n'+json.dumps({'direction':sys.argv[1],'generation':generations[0]}).encode(),capture_output=True,timeout=30)
for value in values.values():
 r.stdout=r.stdout.replace(value.encode(),b'[redacted]');r.stderr=r.stderr.replace(value.encode(),b'[redacted]')
record={'exit':r.returncode,'stdout':r.stdout.decode(),'stderr':r.stderr.decode()}
(project/'docs/phase15-repairs'/('rollback-select-'+sys.argv[1]+'.json')).write_text(json.dumps(record,indent=2))
print(json.dumps(record));sys.exit(r.returncode)
