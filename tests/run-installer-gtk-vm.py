#!/usr/bin/python3 -B
"""Check native GTK in an isolated VM with a read-only OS and no host shares."""
from pathlib import Path
import argparse
import base64
import gzip
import importlib.util
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('split_vm',ROOT/'tests/run-split-storage-vm.py')
vm=importlib.util.module_from_spec(spec);spec.loader.exec_module(vm)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('release',type=Path)
    args=parser.parse_args();release=args.release.resolve(strict=True)
    assert release.parent==ROOT.parent/'releases'
    manifest=json.loads((release/'manifest.json').read_text());iso=release/'build/live-image-amd64.hybrid.iso'
    assert vm.digest(iso)==manifest['live-image-amd64.hybrid.iso']['sha256']
    base=Path('/tmp/petalos-gtk-tests');work,data=vm.prepare(release,base=base)
    overlay=work/'overlay';fixture=overlay/'fixture';gui=fixture/'installer-gui';gui.mkdir()
    shutil.copytree(ROOT/'local/installer/petal_installer',gui/'petal_installer',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    (gui/'tests').mkdir();shutil.copy2(ROOT/'local/installer/tests/test_gui.py',gui/'tests/test_gui.py')
    shutil.copy2(ROOT/'tests/installer-gui-guest.py',gui/'check.py')
    init=overlay/'init';init.write_text(init.read_text().replace('modprobe ext4','modprobe ext4\nmodprobe isofs\nmodprobe squashfs\nmodprobe overlay\nmodprobe loop'))
    (fixture/'test.py').write_text('''#!/usr/bin/python3
from pathlib import Path
import json,shutil,subprocess,sys
sys.stdout=open('/dev/ttyS0','w',buffering=1)
def run(args):
 p=subprocess.run(args,capture_output=True)
 if p.returncode:raise RuntimeError('GUI fixture tool failed: '+Path(args[0]).name)
try:
 for path in ('/mnt/gui-source','/mnt/gui-lower','/mnt/gui-ram'):Path(path).mkdir()
 run(['/usr/bin/mount','-t','iso9660','-o','ro,nodev,nosuid,noexec','/dev/vdb','/mnt/gui-source'])
 run(['/usr/bin/mount','-t','squashfs','-o','ro,loop','/mnt/gui-source/live/filesystem.squashfs','/mnt/gui-lower'])
 run(['/usr/bin/mount','-t','tmpfs','tmpfs','/mnt/gui-ram'])
 for name in ('upper','work','root'):Path('/mnt/gui-ram',name).mkdir()
 target=Path('/mnt/gui-ram/root')
 run(['/usr/bin/mount','-t','overlay','overlay','-o','lowerdir=/mnt/gui-lower,upperdir=/mnt/gui-ram/upper,workdir=/mnt/gui-ram/work',str(target)])
 for name in ('dev','proc','sys'):run(['/usr/bin/mount','--rbind','/'+name,str(target/name)])
 shutil.copytree('/fixture/installer-gui',target/'tmp/installer-gui')
 result=subprocess.run(['/usr/sbin/chroot',str(target),'/usr/bin/python3','-B','/tmp/installer-gui/check.py'],capture_output=True,text=True,timeout=180)
 for line in result.stdout.splitlines():
  if line.startswith('GUI_PREVIEW '):print(line,flush=True)
 if result.returncode:
  for line in (result.stdout+result.stderr)[-16000:].splitlines():print('GUI_TEST_LOG '+line,flush=True)
 print('SPLIT_RESULT '+json.dumps({'passed':result.returncode==0,'stage':'native-gtk','checks':{'five_native_gtk_tests':result.returncode==0}}),flush=True)
except BaseException as error:
 import traceback
 where=traceback.extract_tb(error.__traceback__)[-1]
 print('SPLIT_RESULT '+json.dumps({'passed':False,'failure_type':type(error).__name__,'failure_source':Path(where.filename).name+':'+str(where.lineno)}),flush=True)
finally:subprocess.run(['/bin/busybox','poweroff','-f'])
''')
    with (work/'fixture-initrd.img').open('wb') as out:
        with (release/'build/binary/live/initrd.img').open('rb') as original:shutil.copyfileobj(original,out)
        out.write(gzip.compress(vm.archive_tree(overlay),compresslevel=1))
    print('Native GTK VM:',work,flush=True)
    result=vm.boot(work,data,release,'native-gtk',600,expected_prompts=0,iso=iso,memory=3072,work_root=base)
    report={'passed':True,'result':result,'scope':'Native GTK3 layout, empty/error/automatic selection and contrast checks on a VM-only Broadway display','limits':['Fake release responses; no download/disk/backend operation','OS squashfs mounted read-only with RAM overlay; not a full desktop/polkit test','No host shares, networking, physical media or existing VM images']}
    for line in (work/'native-gtk-bounded.log').read_text(errors='replace').splitlines():
        if 'GUI_PREVIEW ' in line:
            (work/'installer-gui.png').write_bytes(base64.b64decode(line.split('GUI_PREVIEW ',1)[1].strip(),validate=True))
    (work/'gui-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Native GTK checks passed:',work/'gui-results.json')


if __name__=='__main__':main()
