#!/usr/bin/env python3
"""Bounded boot comparison using public Tails USB-image copies, no network.

Never supplies credentials. Only the probe's external initramfs is changed;
the negative control changes a kernel byte to check signature enforcement.
All writes stay in the explicit disposable artifact directory or user RAM.
"""
from pathlib import Path
import argparse, hashlib, json, os, shutil, socket, struct, subprocess, time, zlib

BASE = Path('/home/sam/portable-live/testing/artifacts/tails-boot-comparison-20261019')
MARKER = 'PETALOS_TAILS_UNSIGNED_INITRD_MARKER'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(command, **kwargs):
    result = subprocess.run(command, capture_output=True, timeout=240, **kwargs)
    if result.returncode:
        raise RuntimeError(Path(command[0]).name + ': ' + result.stderr.decode(errors='replace')[-1600:])
    return result


def qmp(path, command, arguments=None):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(8); s.connect(str(path)); stream=s.makefile('rwb',buffering=0)
        json.loads(stream.readline())
        for request in ({'execute':'qmp_capabilities'}, {'execute':command, **({'arguments':arguments} if arguments else {})}):
            stream.write(json.dumps(request).encode()+b'\n')
            while True:
                reply=json.loads(stream.readline())
                assert 'error' not in reply, reply
                if 'return' in reply:break
        return reply['return']


def screenshot(qmp_path, target):
    ppm=target.with_suffix('.ppm');qmp(qmp_path,'screendump',{'filename':str(ppm)})
    with ppm.open('rb') as stream:
        assert stream.readline().strip()==b'P6'
        w,h=map(int,stream.readline().split());assert stream.readline().strip()==b'255'
        assert 0<w<=4096 and 0<h<=4096
        pixels=stream.read(w*h*3+1);assert len(pixels)==w*h*3
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    raw=b''.join(b'\0'+pixels[y*w*3:(y+1)*w*3] for y in range(h))
    target.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))
    ppm.unlink()


def boot(mode):
    original=BASE/'tails-original.img'
    image=BASE/({'baseline':'tails-original.img','probe':'tails-probe-minimal.img','probe-observed':'tails-probe-observed.img',
                'kernel-negative':'tails-kernel-negative.img','kernel-signature-control':'tails-kernel-negative.img'}[mode])
    assert image.is_file() and not image.is_symlink()
    assert digest(original)==json.loads((BASE/'usb-download-verification.json').read_text())['sha256']
    result_dir=BASE/('usb8-boot-'+mode);result_dir.mkdir(mode=0o700,exist_ok=False)
    overlay=result_dir/'image.qcow2'
    run(['qemu-img','create','-f','qcow2','-F','raw','-b',str(image),str(overlay),'8G'])
    runtime=Path('/run/user')/str(os.getuid())/('tails-boot-'+mode+'-'+str(os.getpid()))
    runtime.mkdir(mode=0o700,exist_ok=False)
    firmware=Path('/usr/share/OVMF/OVMF_CODE_4M.secboot.fd')
    template=Path('/usr/share/OVMF/OVMF_VARS_4M.ms.fd')
    variables=result_dir/'OVMF_VARS.fd';shutil.copyfile(template,variables)
    qmp_path=runtime/'qmp.sock';serial_path=runtime/'serial.sock'
    command=['qemu-system-x86_64','-enable-kvm','-machine','q35,smm=on','-cpu','host','-smp','4','-m','8192',
             '-global','driver=cfi.pflash01,property=secure,value=on',
             '-drive','if=pflash,format=raw,readonly=on,file='+str(firmware),
             '-drive','if=pflash,format=raw,file='+str(variables),
             '-drive','if=none,id=tails,format=qcow2,file='+str(overlay),
             '-device','qemu-xhci','-device','usb-storage,drive=tails,removable=on,bootindex=1',
             '-boot','order=c','-nic','none','-no-reboot',
             '-device','virtio-vga,xres=1280,yres=800','-display','none',
             '-serial','unix:'+str(serial_path)+',server=on,wait=on','-monitor','none',
             '-qmp','unix:'+str(qmp_path)+',server=on,wait=off']
    started=time.monotonic();console=bytearray();errors=bytearray();p=None
    try:
        p=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        os.set_blocking(p.stderr.fileno(),False)
        while not serial_path.exists():
            assert p.poll() is None and time.monotonic()-started<15
            time.sleep(.1)
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as serial:
            serial.connect(str(serial_path));serial.setblocking(False)
            limit=90 if mode=='baseline' else 35 if mode=='kernel-signature-control' else 65
            while p.poll() is None and time.monotonic()-started<limit:
                try:console.extend(serial.recv(65536));del console[:-65536]
                except BlockingIOError:pass
                data=p.stderr.read(4096)
                if data:errors.extend(data);del errors[:-8192]
                if mode.startswith('probe') and MARKER.encode() in console and (
                        (MARKER+' SecureBoot=1 SetupMode=0').encode() in console or
                        b'secure boot enabled' in console.lower()):
                    break
                time.sleep(.2)
            if mode=='kernel-signature-control' and p.poll() is None:
                def key(name):qmp(qmp_path,'send-key',{'keys':[{'type':'qcode','data':name}],'hold-time':30})
                key('c');time.sleep(1)
                for char in 'linux /live/vmlinuz':
                    key({' ':'spc','/':'slash'}.get(char,char));time.sleep(.08)
                key('ret');time.sleep(1)
            if p.poll() is None:screenshot(qmp_path,result_dir/'screen.png')
            status=qmp(qmp_path,'query-status') if p.poll() is None else {'exit':p.returncode}
    finally:
        if p is not None and p.poll() is None:
            try:qmp(qmp_path,'quit')
            except Exception:p.terminate()
            p.wait(timeout=15)
    result={'mode':mode,'image_sha256':digest(image),'firmware_sha256':digest(firmware),
            'initial_firmware_variables_sha256':digest(template),'network_devices':0,'host_disks_exposed':0,
            'test_image_writes_use_disposable_8GiB_qcow2_overlay':True,
            'elapsed_seconds':round(time.monotonic()-started,2),'qemu_status':status,
            'marker_seen':MARKER.encode() in console,
            'marker_with_secure_boot_enabled_and_setup_mode_off':(MARKER+' SecureBoot=1 SetupMode=0').encode() in console,
            'guest_kernel_reports_secure_boot_enabled':b'secure boot enabled' in console.lower(),
            'console_tail':console.decode(errors='replace'),'qemu_stderr':errors.decode(errors='replace')}
    (result_dir/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('console_tail','qemu_stderr')}))


def main():
    assert os.geteuid()!=0 and BASE.resolve()==BASE and BASE.stat().st_uid==os.getuid()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('baseline','probe','probe-observed','kernel-negative','kernel-signature-control'))
    boot(parser.parse_args().mode)


if __name__=='__main__':main()
