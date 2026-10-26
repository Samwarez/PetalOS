#!/usr/bin/env python3
"""Build the exact Debian trixie Thunar with Private-to-RAM Trash dispatch."""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,subprocess,tarfile,tempfile

SOURCES={
    'thunar_4.20.2.orig.tar.bz2':'71376f6d7ba4998943c412f374db16ec9b709610acd4d27ecb1eef3aca82af05',
    'thunar_4.20.2-1+deb13u1.debian.tar.xz':'dbca892cd73420dd2446c3194af52181053978fa053ef4fcd63e80457164cd63',
}
VERSION='4.20.2-1+deb13u1'


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    assert os.geteuid()!=0, 'Compile as an ordinary user.'
    assert 'VERSION_CODENAME=trixie' in Path('/etc/os-release').read_text()
    assert subprocess.check_output(['dpkg','--print-architecture'],text=True).strip()=='amd64'
    here=Path(__file__).resolve().parent
    destination=args.output or here.parents[1]/'config/includes.chroot/usr/local/share/portable/native-thunar'
    for name,sha in SOURCES.items():assert digest(args.archives/name)==sha
    env={**os.environ,'LC_ALL':'C.UTF-8','GIO_USE_VFS':'local'}
    env['DEB_BUILD_MAINT_OPTIONS']='hardening=+all'
    env['DEB_LDFLAGS_MAINT_APPEND']='-Wl,-O1 -Wl,-z,defs'
    for flag in ('CFLAGS','CPPFLAGS','LDFLAGS'):
        env[flag]=subprocess.check_output(['dpkg-buildflags','--get',flag],env=env,text=True).strip()
    with tempfile.TemporaryDirectory(prefix='petalos-native-thunar-') as temporary:
        root=Path(temporary)
        with tarfile.open(args.archives/'thunar_4.20.2.orig.tar.bz2') as archive:archive.extractall(root,filter='data')
        source=root/'thunar-4.20.2'
        with tarfile.open(args.archives/'thunar_4.20.2-1+deb13u1.debian.tar.xz') as archive:archive.extractall(source,filter='data')
        for line in (source/'debian/patches/series').read_text().splitlines():
            name=line.split('#',1)[0].strip()
            if not name:continue
            assert not Path(name).is_absolute() and '..' not in Path(name).parts and ' ' not in name
            subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(source/'debian/patches'/name)],cwd=source,check=True)
        subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(here/'volatile-trash.patch')],cwd=source,check=True)
        with (source/'thunar/thunar-gio-extensions.c').open('a') as output:output.write('\n'+(here/'ram-trash.c').read_text())
        subprocess.run(['./configure','--prefix=/usr','--disable-gtk-doc'],cwd=source,env=env,check=True)
        subprocess.run(['make','-j4'],cwd=source,env=env,check=True)
        checked=subprocess.run(['make','check'],cwd=source,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        print(checked.stdout[-262144:],flush=True);checked.check_returncode()
        totals=re.findall(r'# TOTAL:\s*(\d+)',checked.stdout)
        test_count=sum(map(int,totals)) if totals else None
        staged=root/'installed'
        subprocess.run(['make','install','DESTDIR='+str(staged)],cwd=source,env=env,check=True)
        executable=staged/'usr/bin/Thunar'
        if not executable.exists():executable=staged/'usr/bin/thunar'
        assert executable.is_file()
        destination.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(executable,destination/'Thunar');(destination/'Thunar').chmod(0o755)
        subprocess.run(['strip',str(destination/'Thunar')],check=True)
    binary=digest(destination/'Thunar')
    (destination/'Thunar.sha256').write_text(binary+'  Thunar\n')
    (destination/'provenance.json').write_text(json.dumps({'debian_package_version':VERSION,
        'sources':SOURCES,'patch_sha256':{name:digest(here/name) for name in ('volatile-trash.patch','ram-trash.c')},
        'binary_sha256':binary,'Debian_patches_applied':True,'make_check':'passed',
        'make_check_test_count':test_count,'builder_sha256':digest(Path(__file__).resolve()),
        'build_flags':{name:env[name] for name in ('CFLAGS','CPPFLAGS','LDFLAGS')},
        'scope':'normal Thunar Private Trash dispatch to an unprivileged RAM-copy helper'},indent=2)+'\n')


if __name__=='__main__':main()
