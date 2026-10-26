#!/usr/bin/env python3
"""Preserve public VM-built packages outside Git, verifying every recorded hash."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,shlex
project=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--run-id',default='initial')
parser.add_argument('packages',nargs='+',choices=('amule','libxml2','policykit-1','poppler'))
args=parser.parse_args();assert re.fullmatch('[a-z0-9-]{1,32}',args.run_id)
spec=importlib.util.spec_from_file_location('audit',project/'tests/audit-vm.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
work,state=a.state(project.parent/'testing/audit/20261017-221958-817753/state.json')
remote='/tmp/petalos-security-outputs'+('' if args.run_id=='initial' else '-'+args.run_id)
target=project.parent/'testing/artifacts/phase15-dependency-repairs/packages'/args.run_id
target.mkdir(mode=0o700,parents=True,exist_ok=True)
for package in args.packages:
 r=a.ssh(work,shlex.join(['cat',remote+'/'+package+'/provenance.json']),capture_output=True,timeout=15)
 assert r.returncode==0
 meta=json.loads(r.stdout);assert meta['Debian_build_completed_with_tests_enabled']
 assert 1<=len(meta['debs'])<=40
 folder=target/package;folder.mkdir(mode=0o700,exist_ok=True)
 for name,entry in meta['debs'].items():
  assert re.fullmatch('[a-zA-Z0-9+_.:%~-]+[.]deb',name)
  assert re.fullmatch('[a-f0-9]{64}',entry['sha256'])
  p=folder/name
  if p.exists():
   assert not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==entry['sha256']
   continue
  r=a.ssh(work,shlex.join(['cat',remote+'/'+package+'/'+name]),capture_output=True,timeout=120)
  assert r.returncode==0 and hashlib.sha256(r.stdout).hexdigest()==entry['sha256']
  assert len(r.stdout)<300*1024**2
  with p.open('xb') as stream:stream.write(r.stdout)
 record=json.dumps(meta,indent=2)+'\n'
 provenance=folder/'provenance.json'
 if provenance.exists():assert provenance.read_text()==record
 else:provenance.write_text(record)
 (project/('docs/phase15-repairs/'+package+'-backport-provenance.json')).write_text(record)
 print(json.dumps({'package':package,'verified_public_packages':len(meta['debs']),'directory':str(folder)}))
