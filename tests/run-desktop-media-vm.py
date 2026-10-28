#!/usr/bin/python3 -B
"""Exercise real UDisks/GVFS and bundled media in an isolated disposable VM."""
from pathlib import Path
import argparse
import gzip
import importlib.util
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('split_vm', ROOT/'tests/run-split-storage-vm.py')
vm = importlib.util.module_from_spec(spec);spec.loader.exec_module(vm)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release', type=Path)
    parser.add_argument('--clean-release',action='store_true',help='Test only the completed build without production-file overlays')
    parser.add_argument('--work-root',type=Path,default=Path('/tmp/petalos-desktop-media-tests'))
    parser.add_argument('--usb-only',action='store_true',help='Short regression/debug run without Tor/media checks')
    args = parser.parse_args();release = args.release.resolve(strict=True)
    assert not (args.clean_release and args.usb_only)
    assert release.parent == ROOT.parent/'releases'
    iso = release/'build/live-image-amd64.hybrid.iso'
    manifest = json.loads((release/'manifest.json').read_text())
    if args.clean_release:
        spec=importlib.util.spec_from_file_location('fullboot',ROOT/'tests/run-split-fullboot-vm.py')
        fullboot=importlib.util.module_from_spec(spec);spec.loader.exec_module(fullboot)
        fullboot.check_clean_release(release,manifest)
    assert vm.digest(iso) == manifest['live-image-amd64.hybrid.iso']['sha256']
    base = args.work_root
    work, data = vm.prepare(release, base=base)
    flash = work/'usb.img'
    with flash.open('xb') as f:f.truncate(128*1024**2)
    overlay = work/'overlay';fixture = overlay/'fixture'
    if args.usb_only:(fixture/'usb-only').touch()
    shutil.copy2(ROOT/'tests/desktop-media-guest.py', fixture/'inside.py')
    public = ROOT/'config/includes.chroot'
    for name in (() if args.clean_release else ('etc/udev/rules.d/99-portable-storage.rules',
                 'usr/share/applications/portable-test-media.desktop',
                 'usr/local/libexec/portable-wayland-session-client')):
        target = fixture/'delta'/name;target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(public/name, target)
    media = public/'usr/share/petalos/test-media'
    if not args.clean_release and (media/'hardware-test.webm').exists():
        shutil.copytree(media,fixture/'delta/usr/share/petalos/test-media')
    elif not args.clean_release:shutil.copy2(ROOT/'scripts/generate-test-media.py',fixture/'generate-test-media.py')
    tor_specimen = None if args.usb_only else {'production_pin': True,
        'version': json.loads((ROOT/'config/tor-browser.json').read_text())['version']}
    # Prefer the prepared production bundle. A cached signed public specimen
    # remains available for offline development before the build input exists.
    if not args.clean_release and not args.usb_only:
        module = fixture/'delta/usr/local/lib/portable/tor_archives.py';module.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(public/'usr/local/lib/portable/tor_archives.py',module)
        prepared = public/'usr/local/share/portable/tor-browser'
        if (prepared/'manifest.json').is_file():
            pin = json.loads((ROOT/'config/tor-browser.json').read_text())
            bundle_record = json.loads((prepared/'manifest.json').read_text())
            assert bundle_record == pin
            spec=importlib.util.spec_from_file_location('prepare_tor',ROOT/'scripts/prepare-tor-browser.py')
            prepare_tor=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare_tor)
            prepare_tor.validate(prepared,pin)
            archive = prepared/pin['archive']
        else:
            cached = ROOT.parent/'provisioning/TorBrowser/verified-15.0.25'
            archive = next(cached.glob('tor-browser-linux-x86_64-*.tar.xz'))
            bundle_record = {'archive':archive.name,'sha256':vm.digest(archive),'version':'15.0.25'}
            tor_specimen = {'production_pin':False,'version':'15.0.25'}
        bundle = fixture/'delta/usr/local/share/portable/tor-browser';bundle.mkdir(parents=True)
        shutil.copyfile(archive,bundle/archive.name)
        shutil.copyfile(str(archive)+'.asc',bundle/(archive.name+'.asc'))
        (bundle/'manifest.json').write_text(json.dumps(bundle_record))
    (fixture/'delta').mkdir(exist_ok=True)
    shutil.copy2(ROOT/'tests/check-test-media.py',fixture/'check-test-media.py')
    vm.copy_executable('/usr/sbin/mkfs.exfat',overlay)
    init = overlay/'init'
    init.write_text(init.read_text().replace('modprobe ext4',
        'modprobe ext4\nmodprobe exfat\nmodprobe isofs\nmodprobe squashfs\nmodprobe overlay\nmodprobe loop\nmodprobe xhci_pci\nmodprobe usb_storage\nmodprobe sd_mod\nmodprobe vfat\nmodprobe nls_cp437\nmodprobe nls_ascii'))
    (fixture/'test.py').write_text('''from pathlib import Path
import json,shutil,subprocess,sys,os,signal,time
sys.stdout=open('/dev/ttyS0','w',buffering=1)
def run(args):subprocess.run(args,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 assert not Path('/dev/sda1').exists()
 props=subprocess.check_output(['udevadm','info','-q','property','-n','/dev/sda'],text=True)
 assert 'PETALOS_GUI_USB_TEST' in props
 run(['sgdisk','--clear','--new=1:2048:0','--typecode=1:0700','/dev/sda'])
 run(['partprobe','/dev/sda'])
 run(['udevadm','settle','--timeout=15'])
 run(['mkfs.exfat','-L','PETAL_TEST','/dev/sda1'])
 run(['mkfs.ext4','-F','-L','PETAL_OUTPUT','/dev/vda'])
 for p in ('/mnt/source','/mnt/lower','/mnt/ram'):Path(p).mkdir()
 run(['mount','-t','iso9660','-o','ro','/dev/vdb','/mnt/source'])
 run(['mount','-t','squashfs','-o','ro,loop','/mnt/source/live/filesystem.squashfs','/mnt/lower'])
 run(['mount','-t','tmpfs','tmpfs','/mnt/ram'])
 for p in ('upper','work','root'):Path('/mnt/ram',p).mkdir()
 root=Path('/mnt/ram/root')
 run(['mount','-t','overlay','overlay','-o','lowerdir=/mnt/lower,upperdir=/mnt/ram/upper,workdir=/mnt/ram/work',str(root)])
 for p in ('dev','proc','sys','run'):run(['mount','--rbind','/'+p,str(root/p)])
 shutil.copytree('/fixture',root/'tmp/desktop-media-fixture')
 shutil.copytree('/fixture/delta',root,dirs_exist_ok=True)
 run(['udevadm','control','--exit'])
 # Wait for the initramfs daemon/workers to leave before starting the full OS
 # daemon. Both see the same sysfs and would otherwise race to rewrite udev data.
 stale=[]
 for process in Path('/proc').iterdir():
  if not process.name.isdecimal():continue
  try:
   if os.readlink(process/'exe').endswith('/systemd-udevd'):
    stale.append(int(process.name));os.kill(int(process.name),signal.SIGTERM)
  except (OSError,ProcessLookupError):pass
 for _ in range(50):
  if not any(Path('/proc',str(pid)).exists() for pid in stale):break
  time.sleep(.1)
 for pid in stale:
  try:os.kill(pid,signal.SIGKILL)
  except ProcessLookupError:pass
 result=subprocess.run(['chroot',str(root),'/usr/bin/python3','-u','-B','/tmp/desktop-media-fixture/inside.py'],stdout=sys.stdout,stderr=sys.stdout,text=True,timeout=540)
 if result.returncode:print('SPLIT_RESULT '+json.dumps({'passed':False,'stage':'desktop-media'}),flush=True)
except BaseException as e:
 print('FIXTURE_ERROR '+type(e).__name__,flush=True)
 print('SPLIT_RESULT '+json.dumps({'passed':False,'stage':'desktop-media'}),flush=True)
finally:subprocess.run(['/bin/busybox','poweroff','-f'])
''')
    with (work/'fixture-initrd.img').open('wb') as output:
        with (release/'build/binary/live/initrd.img').open('rb') as original:shutil.copyfileobj(original,output)
        output.write(gzip.compress(vm.archive_tree(overlay),compresslevel=1))
    print('Desktop/media VM:',work,flush=True)
    result = vm.boot(work,data,release,'desktop-media',720,expected_prompts=0,iso=iso,
                     memory=4096,work_root=base,usb_image=flash)
    report = {'passed':True,'result':result,'base_release':release.name,'clean_release':args.clean_release,'usb_only':args.usb_only,
              'bundled_tor_specimen':tor_specimen,
              'limits':['Production-file overlays: '+str(not args.clean_release)+'; not a hardware test',
                        'No NIC, host share, existing image or physical media']}
    (work/'desktop-media-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Desktop/media checks passed:',work/'desktop-media-results.json')


if __name__ == '__main__':main()
