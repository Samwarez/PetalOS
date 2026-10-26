#!/usr/bin/python3 -B
"""Verify the complete portable artifact in a fresh, networkless disposable VM."""
from pathlib import Path
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import select
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('portable_vm_base', ROOT / 'tests/run-split-storage-vm.py')
vm = importlib.util.module_from_spec(spec);spec.loader.exec_module(vm)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release', type=Path);parser.add_argument('portable', type=Path)
    args = parser.parse_args();release = args.release.resolve(strict=True);app = args.portable.resolve(strict=True)
    assert release.parent == ROOT.parent / 'releases'
    assert (app / 'portable.json').is_file() and (app / 'bloom-admin').is_file()
    os.umask(0o077)
    work, inputs = vm.prepare(release, base=Path('/tmp/petalos-portable-tests'))
    source = work / 'iso';source.mkdir()
    shutil.copytree(app, source / 'app', copy_function=os.link)
    shutil.copy2(ROOT / 'local/installer/tests/test_gui.py', source / 'test_gui.py')
    canary = work / 'initrd-canary';canary.mkdir()
    (canary / 'portable-runtime-canary').write_bytes(b'public runtime fixture')
    (source / 'public-initrd.img').write_bytes(gzip.compress(vm.archive_tree(canary, devices=False)))
    (source / 'gtk-check.py').write_text('''from pathlib import Path
import os,sys,unittest
root=Path('/mnt/portable');app=root/'app'
sys.path.insert(0,str(app/'app'));sys.path.insert(0,str(root))
assert sys.prefix.startswith(str(app/'runtime'))
import gi
assert gi.__file__.startswith(str(app/'runtime'))
import test_gui
assert test_gui.DISPLAY
test_gui.Gtk.Settings.get_default().set_property('gtk-enable-animations',False)
suite=unittest.defaultTestLoader.loadTestsFromTestCase(test_gui.GuiTests)
result=unittest.TextTestRunner(verbosity=2).run(suite)
assert result.wasSuccessful() and not result.skipped
from gi.repository import GdkPixbuf
svg=next((app/'runtime/usr/share/icons/Adwaita').rglob('folder-symbolic.svg'))
assert GdkPixbuf.Pixbuf.new_from_file(str(svg)).get_width()>0
libraries=[line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines() if '.so' in line and '/' in line]
assert libraries and all(path.startswith(str(app/'runtime')) for path in libraries), libraries
print('PORTABLE_GTK_PASSED '+str(result.testsRun),flush=True)
''')
    iso = work / 'portable.iso'
    subprocess.run(['/usr/bin/xorriso', '-as', 'mkisofs', '-quiet', '-r', '-J', '-o', str(iso), str(source)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    overlay = work / 'overlay'
    shutil.copy2(ROOT / 'tests/portable-installer-guest.py', overlay / 'fixture/test.py')
    for program in ('/usr/bin/sha256sum', '/usr/bin/fuser', '/usr/bin/dirname'):
        vm.copy_executable(program, overlay)
    init = overlay / 'init'
    init.write_text(init.read_text().replace('mount -t devpts devpts /dev/pts',
        'mount -t devpts devpts /dev/pts\nmkdir -p /dev/shm\nmount -t tmpfs -o mode=1777,nosuid,nodev tmpfs /dev/shm').replace('modprobe ext4',
        'modprobe ext4\nmodprobe isofs\nmodprobe xhci_pci\nmodprobe usb_storage\nmodprobe sd_mod\nmodprobe algif_hash'))
    with (work / 'fixture-initrd.img').open('wb') as out:
        with (release / 'build/binary/live/initrd.img').open('rb') as original:shutil.copyfileobj(original, out)
        out.write(gzip.compress(vm.archive_tree(overlay), compresslevel=1))
    image = work / 'disposable.img'
    assert image.stat().st_blocks == 0 and vm.digest(iso)
    assert subprocess.run(['/usr/bin/fuser', str(image)], capture_output=True).returncode == 1
    # Baseline amd64 avoids expensive emulated AVX/SHA paths on TCG and checks
    # that this runtime does not require the build host's CPU extensions.
    acceleration = ['-accel', 'kvm', '-cpu', 'host'] if Path('/dev/kvm').exists() else ['-accel', 'tcg,thread=multi', '-cpu', 'qemu64']
    arguments = ['/usr/bin/qemu-system-x86_64', *acceleration, '-machine', 'q35', '-smp', '2', '-m', '4096',
                 '-kernel', str(release / 'build/binary/live/vmlinuz'), '-initrd', str(work / 'fixture-initrd.img'),
                 '-append', 'console=ttyS0 panic=1', '-device', 'qemu-xhci',
                 '-drive', f'file={image},format=raw,if=none,id=target',
                 '-device', 'usb-storage,drive=target,removable=on,serial=PETAL-PORTABLE-TEST',
                 '-drive', f'file={iso},format=raw,if=virtio,readonly=on',
                 '-device', 'virtio-rng-pci', '-nic', 'none', '-display', 'none', '-monitor', 'none',
                 '-serial', 'stdio', '-no-reboot']
    print('Portable installer VM:', work, flush=True)
    process = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    pending = bytearray();tail = bytearray();result = None;start = time.monotonic()
    try:
        while process.poll() is None:
            if time.monotonic() - start > 1800:raise RuntimeError('Portable VM exceeded its time limit.')
            if not select.select([process.stdout], [], [], 1)[0]:continue
            data = os.read(process.stdout.fileno(), 65536)
            if not data:break
            pending.extend(data);tail.extend(data);del tail[:-256*1024]
            while b'\n' in pending:
                line, _, rest = pending.partition(b'\n');pending[:] = rest
                text = line.decode(errors='replace').strip()
                kind, value = vm.console_record(text)
                if kind == 'SPLIT_PASS ':print(kind + value, flush=True)
                elif kind == 'SPLIT_RESULT ':result = json.loads(value);print('Portable VM result:', json.dumps(result), flush=True)
                elif text.startswith(('PORTABLE_RUNTIME_ERROR ', 'PORTABLE_GTK_ERROR ', 'PORTABLE_WORKER_ERROR ')):print(text, flush=True)
        process.wait(timeout=10)
    finally:
        if process.poll() is None:process.kill();process.wait()
        output = bytes(tail)
        for value in inputs['credentials'].values():output = output.replace(value.encode(), b'<redacted disposable credential>')
        (work / 'bounded.log').write_bytes(output)
    assert result and result['passed'], 'Portable VM checks failed; inspect its bounded log.'
    report = {'passed': True, 'result': result, 'artifact': app.name,
              'acceleration': 'kvm' if Path('/dev/kvm').exists() else 'tcg',
              'cpu': 'host' if Path('/dev/kvm').exists() else 'qemu64',
              'artifact_manifest_sha256': vm.digest(app / 'portable.json'), 'elapsed_seconds': round(time.monotonic()-start, 1),
              'limits': ['Networkless synthetic VM; generic pkexec/desktop authorization interaction untested.',
                         'Real portable worker random-wipe/cancel/readback on a new disposable USB; full OS installation/update not repeated.',
                         'No physical media, existing writable images, host shares or production credentials.']}
    (work / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Portable acceptance passed:', work / 'results.json')


if __name__ == '__main__':main()
