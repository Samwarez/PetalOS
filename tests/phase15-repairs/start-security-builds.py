#!/usr/bin/env python3
"""Run the four public backport builders as Petal in disposable VM RAM."""
from pathlib import Path
import argparse,hashlib,importlib.util,io,json,re,shlex,sys,tarfile
project=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--run-id',required=True)
parser.add_argument('--packages',nargs='+',choices=('amule','libxml2','policykit-1','poppler'),required=True)
args=parser.parse_args();assert re.fullmatch('[a-z0-9-]{1,32}',args.run_id)
tool_root='/tmp/petalos-security-build-tools-'+args.run_id
output_root='/tmp/petalos-security-outputs-'+args.run_id
spec=importlib.util.spec_from_file_location('audit',project/'tests/audit-vm.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
work,state=a.state(project.parent/'testing/audit/20261017-221958-817753/state.json')
data=io.BytesIO();hashes={}
with tarfile.open(fileobj=data,mode='w') as archive:
 for p in sorted((project/'local/security-backports').iterdir()):
  assert p.is_file() and not p.is_symlink();content=p.read_bytes()
  info=tarfile.TarInfo(p.name);info.size=len(content);info.mode=0o600
  archive.addfile(info,io.BytesIO(content));hashes[p.name]=hashlib.sha256(content).hexdigest()
r=a.ssh(work,'umask 077; mkdir '+shlex.quote(tool_root)+' && tar -xf - -C '+shlex.quote(tool_root),
 input=data.getvalue(),capture_output=True,timeout=20);assert r.returncode==0
driver='root_name='+repr(output_root)+'\ntool_name='+repr(tool_root)+'\npackages='+repr(args.packages)+'\n'+r'''from pathlib import Path
import json,os,subprocess,time
root=Path(root_name);root.mkdir(mode=0o700,exist_ok=False)
status=root/'status.json'
try:
 status.write_text(json.dumps({'phase':'waiting_for_build_dependencies'}))
 deadline=time.monotonic()+1250
 while time.monotonic()<deadline:
  dep=json.loads(Path('/run/petalos-backport-deps/status.json').read_text())
  if dep['phase']=='complete':break
  if dep['phase']=='failed':raise RuntimeError('Dependency installation failed')
  time.sleep(5)
 else:raise TimeoutError('Dependency installation did not complete')
 for package in packages:
  status.write_text(json.dumps({'phase':'building','package':package,'started':int(time.time())}))
  command=['python3','-B',tool_name+'/build.py',package,
    '/tmp/petalos-security-backports/'+package,str(root/package)]
  p=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  tail=b''
  while chunk:=p.stdout.read(65536):
   tail=(tail+chunk)[-2*1024**2:];(root/(package+'-build-tail.txt')).write_bytes(tail)
  assert p.wait()==0,'Package build failed: '+package
 status.write_text(json.dumps({'phase':'complete','packages':len(packages)}))
except BaseException as error:
 status.write_text(json.dumps({'phase':'failed','error':type(error).__name__,'package':globals().get('package')}));raise
'''
launcher='import subprocess; p=subprocess.Popen('+repr(['python3','-I','-c',driver])+',stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True); print(p.pid)'
r=a.ssh(work,shlex.join(['python3','-I','-c',launcher]),capture_output=True,timeout=15);assert r.returncode==0
record={'public_tools_sha256':hashes,'builder_pid':int(r.stdout),'scope':'ordinary-user builds in disposable guest RAM'}
(project/('docs/phase15-repairs/security-build-start-'+args.run_id+'.json')).write_text(json.dumps(record,indent=2))
print(json.dumps(record))
