#!/usr/bin/env python3
"""Boot the SSH module in a diskless, offline VM; retain only bounded RAM logs."""
from pathlib import Path
import gzip
import json
import os
import shutil
import subprocess
import tempfile
import threading

PROJECT = Path(__file__).resolve().parents[1]
RUNTIME = Path(f'/run/user/{os.getuid()}')
state = json.loads((RUNTIME / 'petalos-encrypted-test.json').read_text())
build = Path(state['release']) / 'build'
source = sorted(Path(state['image']).parent.glob('ssh-*/module'))[-1]
if os.geteuid() == 0:
    raise RuntimeError('QEMU must run as the normal user.')
with tempfile.TemporaryDirectory(prefix='petalos-ssh-check-', dir='/dev/shm') as temp:
    work = Path(temp)
    unpacked = work / 'unpacked'
    subprocess.run(['unmkinitramfs', str(build / 'binary/live/initrd.img'), str(unpacked)],
                   check=True, stdout=subprocess.DEVNULL)
    orders = list(unpacked.rglob('scripts/init-bottom/ORDER'))
    if len(orders) != 1: raise RuntimeError('Unexpected initrd ordering.')
    overlay = work / 'overlay'
    payload = overlay / 'ssh-module'
    shutil.copytree(source, payload, symlinks=True)
    for package in (PROJECT.parent / 'testing/ssh-packages').glob('*.deb'):
        shutil.copyfile(package, payload / 'usr/share/petalos-qemu-ssh/packages' / package.name)
    hook = payload / 'usr/lib/live/config/9999-petalos-qemu-ssh'
    text = (PROJECT / 'tests/qemu-ssh/9999-petalos-qemu-ssh').read_text()
    begin = text.index('test "$(/usr/sbin/blkid')
    end = text.index('# Prevent package')
    text = text[:begin] + '''install -d -m 700 /run/petalos-qemu-ssh
install -d -m 755 /run/sshd
''' + text[end:]
    text = text.replace('rm /usr/sbin/policy-rc.d', '''rm /usr/sbin/policy-rc.d
ssh-keygen -q -t ed25519 -N '' -f /run/petalos-qemu-ssh/ssh_host_ed25519_key
echo "SSH_TEST_HOST_KEY=$(cat /run/petalos-qemu-ssh/ssh_host_ed25519_key.pub)" >/dev/ttyS0''')
    text = text.replace('set -eu', 'set -eux\nexec >/dev/ttyS0 2>&1')
    hook.write_text(text); hook.chmod(0o755)
    units = payload / 'etc/systemd/system'
    (units / 'petalos-ssh-check.service').write_text('''[Unit]
After=live-config.service petalos-qemu-ssh.service petalos-qemu-vsock.service
Wants=petalos-qemu-ssh.service petalos-qemu-vsock.service
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/petalos-ssh-check
StandardOutput=tty
StandardError=tty
TTYPath=/dev/ttyS0
''')
    wants = units / 'multi-user.target.wants'; wants.mkdir(exist_ok=True)
    (wants / 'petalos-ssh-check.service').symlink_to('../petalos-ssh-check.service')
    check = payload / 'usr/local/sbin/petalos-ssh-check'; check.parent.mkdir(parents=True)
    check.write_text('''#!/bin/sh
sleep 1
systemctl --no-pager --full status petalos-qemu-ssh.service petalos-qemu-vsock.service
journalctl --no-pager -n 15 -u petalos-qemu-vsock.service -u petalos-qemu-ssh.service
ss --vsock -l
if ! systemctl is-active petalos-qemu-ssh.service petalos-qemu-vsock.service; then
systemctl --no-pager --full status petalos-qemu-ssh.service petalos-qemu-vsock.service
tail -50 /run/petalos-qemu-ssh/install.log
echo SSH_TEST_FAILURE
exit 1
fi
echo SSH_TEST_READY
'''); check.chmod(0o755)
    scripts = overlay / 'scripts/init-bottom'; scripts.mkdir(parents=True)
    (scripts / 'ORDER').write_text(orders[0].read_text()+'\n/scripts/init-bottom/petalos-ssh-check "$@"\n')
    script = scripts / 'petalos-ssh-check'
    script.write_text('#!/bin/sh\nset -eu\ncp -a /ssh-module/. "$rootmnt/"\n')
    script.chmod(0o755)
    payload.chmod(0o755)
    for directory in payload.rglob('*'):
        if directory.is_dir() and not directory.is_symlink():directory.chmod(0o755)
    archive = subprocess.check_output(['bash', '-c', 'find . -print0 | cpio --null -o -H newc --quiet'], cwd=overlay)
    initrd = work / 'initrd.img'
    with initrd.open('wb') as f:
        with (build / 'binary/live/initrd.img').open('rb') as original: shutil.copyfileobj(original, f)
        f.write(gzip.compress(archive))
    log = RUNTIME / 'petalos-ssh-verification.log'
    cmd = ['qemu-system-x86_64','-accel','kvm','-cpu','host','-m','8192','-smp','2',
           '-kernel',str(build/'binary/live/vmlinuz'),'-initrd',str(initrd),'-append',
           'boot=live components toram swap=false petalos_qemu_ssh=1 console=ttyS0 systemd.unit=multi-user.target systemd.mask=serial-getty@ttyS0.service',
           '-drive',f"file={build/'live-image-amd64.hybrid.iso'},format=raw,media=cdrom,readonly=on",
           '-nic','none','-device','vhost-vsock-pci,guest-cid=43','-nographic','-no-reboot']
    process = subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    timer = threading.Timer(180,process.kill); timer.start()
    passed = False
    print('Testing SSH package installation/startup in a diskless offline VM.',flush=True)
    try:
        with log.open('w+b') as out:
            for line in process.stdout:
                out.write(line);out.flush()
                if out.tell()>1024*1024:
                    out.seek(-1024*1024,os.SEEK_END);tail=out.read();out.seek(0);out.truncate();out.write(tail)
                if line.startswith(b'SSH_TEST_HOST_KEY='):
                    fields=line.decode().strip().split('=',1)[1].split()
                    known=RUNTIME/'petalos-ssh-test-known-hosts'
                    known.write_text('petalos-ssh-test '+' '.join(fields[:2])+'\n');known.chmod(0o600)
                if line.strip()==b'SSH_TEST_READY':
                    result=subprocess.run(['ssh','-F','/dev/null','-T','-i',state['ssh']['key'],
                        '-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
                        '-o','HostKeyAlias=petalos-ssh-test','-o','UserKnownHostsFile='+str(known),
                        '-o','ProxyCommand=socat - VSOCK-CONNECT:43:22','user@vm',
                        'printf "stdout-ok\\n"; printf "stderr-ok\\n" >&2; exit 7'],capture_output=True,timeout=15)
                    print(json.dumps({'stdout':result.stdout.decode(),'stderr':result.stderr.decode(),'exit_code':result.returncode}),flush=True)
                    assert result.returncode==7 and result.stdout==b'stdout-ok\n' and result.stderr==b'stderr-ok\n'
                    passed = True
                    print('SSH_TEST_PASS',flush=True);break
                if line.strip()==b'SSH_TEST_FAILURE':
                    raise RuntimeError('SSH service startup failed; inspect bounded RAM log.')
    finally:
        timer.cancel()
        if process.poll() is None:process.terminate()
        process.wait()
    if not passed:raise RuntimeError('SSH boot test did not complete; inspect bounded RAM log.')
