#!/usr/bin/env python3
"""Build pinned Crystal Dock in a dedicated Debian trixie amd64 builder."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,tarfile,tempfile,shutil

VERSION='2.16'
SHA='920b8a36c1ee1eb5a66f85c98c44bec1b2d7f8f14e38aa2f96a0b57781091832'
def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('archive',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args();here=Path(__file__).resolve().parent
    assert os.geteuid()!=0 and 'VERSION_CODENAME=trixie' in Path('/etc/os-release').read_text()
    assert subprocess.check_output(['dpkg','--print-architecture'],text=True).strip()=='amd64'
    assert digest(args.archive)==SHA
    output=args.output or here.parents[1]/'config/includes.chroot/usr/local/share/portable/native-crystal-dock'
    env={**os.environ,'LC_ALL':'C.UTF-8','DEB_BUILD_MAINT_OPTIONS':'hardening=+all'}
    flags={flag:subprocess.check_output(['dpkg-buildflags','--get',flag],env=env,text=True).strip()
           for flag in ('CFLAGS','CPPFLAGS','CXXFLAGS','LDFLAGS')}
    with tempfile.TemporaryDirectory(prefix='petalos-crystal-') as temporary:
        root=Path(temporary)
        with tarfile.open(args.archive) as archive:archive.extractall(root,filter='data')
        source=next(root.iterdir())
        subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(here/'petalos-integration.patch')],cwd=source,check=True)
        build=root/'build'
        subprocess.run(['cmake','-S',str(source/'src'),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release',
                        '-DCMAKE_INSTALL_PREFIX=/usr','-DCMAKE_INSTALL_BINDIR=bin',
                        '-DCMAKE_MODULE_PATH=/usr/share/ECM/find-modules',
                        '-DCMAKE_CXX_FLAGS='+flags['CXXFLAGS']+' '+flags['CPPFLAGS'],
                        '-DCMAKE_C_FLAGS='+flags['CFLAGS']+' '+flags['CPPFLAGS'],
                        '-DCMAKE_EXE_LINKER_FLAGS='+flags['LDFLAGS']],env=env,check=True)
        subprocess.run(['cmake','--build',str(build),'--parallel','4'],env=env,check=True)
        tested=subprocess.run(['ctest','--test-dir',str(build),'--output-on-failure'],env={**env,'QT_QPA_PLATFORM':'offscreen'},capture_output=True,text=True)
        print(tested.stdout[-32000:],flush=True);tested.check_returncode()
        output.mkdir(parents=True,exist_ok=True);shutil.copyfile(build/'crystal-dock',output/'crystal-dock');(output/'crystal-dock').chmod(0o755)
        subprocess.run(['strip',str(output/'crystal-dock')],check=True)
    sha=digest(output/'crystal-dock');(output/'crystal-dock.sha256').write_text(sha+'  crystal-dock\n')
    runtime={name:subprocess.check_output(['dpkg-query','-W','-f=${Version}',name],text=True)
             for name in ('libqt6gui6','liblayershellqtinterface6','qt6-wayland','layer-shell-qt')}
    (output/'provenance.json').write_text(json.dumps({'version':VERSION,'source_sha256':SHA,
        'patch_sha256':digest(here/'petalos-integration.patch'),'builder_sha256':digest(Path(__file__).resolve()),
        'binary_sha256':sha,'ctest':'passed','build_flags':flags,'runtime_versions':runtime},indent=2)+'\n')

if __name__=='__main__':main()
