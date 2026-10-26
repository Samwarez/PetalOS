#!/usr/bin/env python3
"""Build reviewed, versioned trixie security backports as ordinary Debian packages."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys

HERE=Path(__file__).resolve().parent
SOURCE_FILES={'amule':'src/ServerSocket.cpp','libxml2':'dict.c',
              'policykit-1':'src/polkitagent/polkitagenthelperprivate.c','poppler':'poppler/Decrypt.cc'}
def digest(p):
 with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('package',choices=SOURCE_FILES)
 parser.add_argument('archives',type=Path)
 parser.add_argument('output',type=Path)
 args=parser.parse_args();assert os.geteuid()!=0,'Build as an ordinary user.'
 assert 'VERSION_CODENAME=trixie' in Path('/etc/os-release').read_text()
 assert subprocess.check_output(['dpkg','--print-architecture'],text=True).strip()=='amd64'
 meta=json.loads((HERE/'sources.json').read_text())[args.package]
 for name,sha in meta['files'].items():assert digest(args.archives/name)==sha
 patch=HERE/meta['patch']['file'];assert digest(patch)==meta['patch']['sha256']
 args.output=args.output.resolve();args.output.mkdir(mode=0o700,parents=True,exist_ok=False)
 source=args.output/'source';dsc=next(args.archives.glob('*.dsc'))
 subprocess.run(['dpkg-source','--no-check','-x',str(dsc.resolve()),str(source)],check=True)
 assert subprocess.check_output(['dpkg-parsechangelog','-SVersion'],cwd=source,text=True).strip()==meta['version']
 original=args.output/'original-source.txt';original.write_bytes((source/SOURCE_FILES[args.package]).read_bytes())
 (source/'debian/patches').mkdir(exist_ok=True)
 name='petalos-'+patch.name;shutil.copyfile(patch,source/'debian/patches'/name)
 with (source/'debian/patches/series').open('a') as f:f.write('\n'+name+'\n')
 subprocess.run(['dpkg-source','--before-build',str(source)],check=True)
 regression=json.loads(subprocess.check_output([sys.executable,'-B',str(HERE/'regression.py'),args.package,
                 str(original),str(source/SOURCE_FILES[args.package])],text=True))
 print(json.dumps(regression),flush=True)
 changelog=source/'debian/changelog'
 changelog.write_text(f"{args.package} ({meta['package_version']}) trixie; urgency=medium\n\n"
  f"  * PetalOS reviewed security backport: {patch.name}.\n\n"
  " -- PetalOS Maintainers <maintainers@petalos.invalid>  Mon, 19 Oct 2026 12:00:00 +0000\n\n"+changelog.read_text())
 # Debian's normal build flags, feature selection and tests remain enabled.
 # Build-time GIO accesses local source files, not the live desktop's GVFS
 # service. Keep fatal warnings/tests enabled while avoiding desktop activation.
 env={**os.environ,'LC_ALL':'C.UTF-8','DEB_BUILD_OPTIONS':'parallel=4','GIO_USE_VFS':'local'}
 subprocess.run(['dpkg-buildpackage','-us','-uc','-b','-j4'],cwd=source,env=env,check=True)
 packages={}
 for p in args.output.glob('*.deb'):
  version=subprocess.check_output(['dpkg-deb','-f',str(p),'Version'],text=True).strip()
  assert version==meta['package_version']
  packages[p.name]={'sha256':digest(p),'package':subprocess.check_output(['dpkg-deb','-f',str(p),'Package'],text=True).strip(),'version':version}
 assert packages
 (args.output/'provenance.json').write_text(json.dumps({'source':meta,'debs':packages,
  'Debian_build_completed_with_tests_enabled':True,'architecture':'amd64',
  'build_environment':{'GIO_USE_VFS':'local','DEB_BUILD_OPTIONS':'parallel=4'},
  'source_regression':regression,
  'upstream_test_limitations':(['Debian omits the external PDF test corpus and permits dh_auto_test failure; inspect and record test results separately.'] if args.package=='poppler' else []),
  'regression_scope':'bounded source regressions; installed-package workflow tests are separate'},indent=2)+'\n')
 print(json.dumps({'package':args.package,'debs_built':len(packages),'version':meta['package_version']}))

if __name__=='__main__':main()
