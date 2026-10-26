#!/usr/bin/env python3
"""Stage verified public Debian backports; package archives remain outside Git."""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,subprocess
HERE=Path(__file__).resolve().parent
def digest(p):
 with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('directories',nargs=4,type=Path)
 parser.add_argument('--output',type=Path,default=HERE.parents[1]/'config/includes.chroot/usr/local/share/portable/security-backports')
 args=parser.parse_args();assert os.geteuid()!=0
 expected=json.loads((HERE/'sources.json').read_text());seen=set();entries=[]
 for directory in args.directories:
  assert directory.is_dir() and not directory.is_symlink()
  meta=json.loads((directory/'provenance.json').read_text())
  matches=[s for s in expected if meta['source']==expected[s]];assert len(matches)==1
  source=matches[0];assert source not in seen;seen.add(source)
  assert meta['Debian_build_completed_with_tests_enabled'] and meta['architecture']=='amd64'
  patch=HERE/expected[source]['patch']['file'];assert digest(patch)==expected[source]['patch']['sha256']
  for name,info in meta['debs'].items():
   assert re.fullmatch('[a-zA-Z0-9+_.:%~-]+[.]deb',name)
   package=info['package'];assert re.fullmatch('[a-z0-9][a-z0-9+.-]+',package)
   # Debug symbols are never needed by the production image.
   if package.endswith('-dbgsym'):continue
   archive=directory/name;assert archive.is_file() and not archive.is_symlink()
   assert digest(archive)==info['sha256'] and info['version']==expected[source]['package_version']
   identity=subprocess.check_output(['dpkg-deb','-f',str(archive),'Package','Version','Architecture'],text=True).splitlines()
   assert identity[:2]==['Package: '+package,'Version: '+info['version']]
   assert identity[2] in ('Architecture: amd64','Architecture: all')
   entries.append((archive,dict(info,file=name,source=source,base_version=expected[source]['version'])))
 assert seen==set(expected)
 assert len({e['package'] for _,e in entries})==len(entries)
 args.output.mkdir(mode=0o755,parents=True,exist_ok=False)
 for archive,info in entries:
  shutil.copyfile(archive,args.output/info['file']);(args.output/info['file']).chmod(0o644)
 (args.output/'manifest.json').write_text(json.dumps({'format':1,'sources':expected,'packages':[e for _,e in entries]},indent=2)+'\n')
 print(json.dumps({'public_packages_staged':len(entries),'output':str(args.output)}))
if __name__=='__main__':main()
