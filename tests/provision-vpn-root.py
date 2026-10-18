#!/usr/bin/env python3
"""Copy the explicitly selected VPN file into encrypted test DATA only."""
from pathlib import Path
import base64
import json
import os
import re
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
SOURCE = Path('/home/sam/Desktop/zrh43-adb.conf')
MAPPER = Path('/dev/mapper/petal_vpn_test_data')


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def selected_payload(uid):
    if SOURCE.is_symlink() or not SOURCE.is_file():
        raise RuntimeError('Unexpected selected config identity.')
    info = SOURCE.stat()
    if info.st_uid != uid or info.st_mode & 0o077 or info.st_size > 65536:
        raise RuntimeError('Selected config owner, permissions or size rejected.')
    payload = SOURCE.read_bytes()
    sections = []; section = None; values = {}
    for line in payload.decode().splitlines():
        line = line.split('#', 1)[0].strip()
        if not line or line.startswith(';'): continue
        if re.fullmatch(r'\[(Interface|Peer)\]', line):
            section = line[1:-1]; sections.append(section); continue
        if '=' not in line or section is None:
            raise RuntimeError('Invalid config structure; contents suppressed.')
        key, value = line.split('=', 1)
        values.setdefault((section, key.strip()), []).append(value.strip())
    if sections != ['Interface', 'Peer']:
        raise RuntimeError('Expected exactly one Interface and Peer.')
    for sec, key in (('Interface', 'PrivateKey'), ('Peer', 'PublicKey')):
        value = values.get((sec, key), [])
        try: valid = len(value) == 1 and len(base64.b64decode(value[0], validate=True)) == 32
        except Exception: valid = False
        if not valid: raise RuntimeError('Invalid WireGuard key; contents suppressed.')
    endpoint = values.get(('Peer', 'Endpoint'), [])
    if len(endpoint) != 1 or endpoint[0].lower() not in {'152.89.162.4:9929', 'vpn43.prd.zurich.ovpn.com:9929'}:
        raise RuntimeError('Endpoint is incompatible with the current firewall.')
    routes = set(','.join(values.get(('Peer', 'AllowedIPs'), [])).replace(' ', '').split(','))
    if not {'0.0.0.0/0', '::/0'}.issubset(routes):
        raise RuntimeError('Both full-tunnel routes are required.')
    if subprocess.run(['/usr/bin/wg', 'pubkey'], input=values[('Interface', 'PrivateKey')][0] + '\n',
                      text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        raise RuntimeError('WireGuard rejected key format.')
    return payload


def with_private(image, uid, installer):
    image = Path(image)
    allowed = PROJECT.parent / 'testing/sessions'
    if image.is_symlink() or not image.is_file() or not image.resolve().is_relative_to(allowed.resolve()):
        raise RuntimeError('Only a regular test-clone file is allowed.')
    if not re.fullmatch(r'encrypted-boot-\d{8}-\d{6}-\d+\.img', image.name):
        raise RuntimeError('Unexpected clone filename.')
    identity = image.stat()
    if identity.st_uid != uid or identity.st_size != 16 * 1024**3:
        raise RuntimeError('Unexpected clone owner or size.')
    if any(name.startswith(('qemu-system', 'qemu-nbd')) for name in run('/usr/bin/ps', '-eo', 'comm=').splitlines()):
        raise RuntimeError('QEMU is running; transfer refused.')
    for backing in Path('/sys/block').glob('loop*/loop/backing_file'):
        if Path(backing.read_text().strip()).resolve() == image.resolve():
            raise RuntimeError('Clone already has a loop attachment.')
    if MAPPER.exists() or subprocess.run(['/usr/bin/fuser', str(image)], stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL).returncode != 1:
        raise RuntimeError('Clone or mapper is busy, or busy state is unknown.')
    loop = None; mapped = False; mounted = False
    work = Path(tempfile.mkdtemp(prefix='petalos-vpn-', dir='/run'))
    target = work / 'data'; target.mkdir()

    def loop_identity():
        now = image.stat()
        if (now.st_dev, now.st_ino, now.st_size) != (identity.st_dev, identity.st_ino, identity.st_size):
            raise RuntimeError('Clone identity changed.')
        backing = Path('/sys/class/block') / Path(loop).name / 'loop/backing_file'
        if Path(backing.read_text().strip()).resolve() != image.resolve():
            raise RuntimeError('Wrong loop backing file.')

    def data_device():
        loop_identity()
        device = Path(f'{loop}p4')
        if (Path('/sys/class/block') / device.name).resolve().parent.name != Path(loop).name:
            raise RuntimeError('Wrong data partition parent.')
        return device

    def mapper_identity():
        loop_identity()
        dev = MAPPER.stat().st_rdev
        slaves = Path(f'/sys/dev/block/{os.major(dev)}:{os.minor(dev)}/slaves')
        if [p.name for p in slaves.iterdir()] != [data_device().name]:
            raise RuntimeError('Wrong data mapper backing device.')

    def tag(device, name):
        return run('/usr/sbin/blkid', '-s', name, '-o', 'value', str(device))

    try:
        loop = run('/usr/sbin/losetup', '--find', '--show', '--partscan', str(image))
        loop_identity()
        subprocess.run(['/usr/bin/udevadm', 'settle', '--timeout=10'], check=True)
        table = json.loads(run('/usr/sbin/sfdisk', '--json', loop))['partitiontable']
        if table['label'] != 'gpt' or len(table['partitions']) != 4 or table['partitions'][2]['size'] != 8388608:
            raise RuntimeError('Unexpected test partition layout.')
        device = data_device()
        if tag(device, 'LABEL') != 'PORTABLE_DATA' or tag(device, 'TYPE') != 'crypto_LUKS':
            raise RuntimeError('Unexpected encrypted DATA partition.')
        print('Enter the QEMU test DATA-volume password at the cryptsetup prompt.', flush=True)
        subprocess.run(['/usr/sbin/cryptsetup', 'open', str(device), MAPPER.name], check=True)
        mapped = True; mapper_identity()
        if tag(MAPPER, 'LABEL') != 'PORTABLE_FILES' or tag(MAPPER, 'TYPE') != 'ext4':
            raise RuntimeError('Unexpected decrypted DATA filesystem.')
        subprocess.run(['/usr/bin/mount', '-t', 'ext4', '-o', 'nodev,nosuid,noexec,noatime',
                        str(MAPPER), str(target)], check=True)
        mounted = True
        owner = target.stat()
        if owner.st_uid != uid:
            raise RuntimeError('Unexpected live-user DATA ownership.')
        mapper_identity()
        installer(target, owner, mapper_identity)
        mapper_identity()
    finally:
        if mounted:
            mapper_identity()
            actual = Path(run('/usr/bin/findmnt', '-n', '-o', 'SOURCE', '--target', str(target)))
            if actual.stat().st_rdev != MAPPER.stat().st_rdev:
                raise RuntimeError('Cleanup mount identity mismatch; retain for inspection.')
            subprocess.run(['/usr/bin/umount', str(target)], check=True)
        if mapped or (loop and MAPPER.exists()):
            mapper_identity(); subprocess.run(['/usr/sbin/cryptsetup', 'close', MAPPER.name], check=True)
        if loop:
            loop_identity(); subprocess.run(['/usr/sbin/losetup', '--detach', loop], check=True)
        # No recursive cleanup of a potentially mounted filesystem.
        target.rmdir(); work.rmdir()
    print('Transfer complete; DATA mapping and clone loop are closed.', flush=True)


def main():
    if os.geteuid() != 0 or len(sys.argv) != 2:
        raise RuntimeError('Use the prepared coordinator through sudo.')
    uid = int(os.environ['SUDO_UID'])
    payload = selected_payload(uid)
    def install(target, owner, guard):
        network = target / 'Network'
        if network.is_symlink() or (network.exists() and not network.is_dir()):
            raise RuntimeError('Unexpected Network destination.')
        if not network.exists():
            network.mkdir(mode=0o700); os.chown(network, owner.st_uid, owner.st_gid)
        destination = network / 'wg0.conf'
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            raise RuntimeError('Unexpected VPN destination.')
        # The entire previous encrypted disk is preserved; no existing profile is lost.
        fd, filename = tempfile.mkstemp(prefix='.vpn-test-', dir=network)
        temporary = Path(filename)
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(payload); output.flush(); os.fsync(output.fileno())
            os.chown(temporary, owner.st_uid, owner.st_gid); temporary.chmod(0o600)
            if temporary.read_bytes() != payload:
                raise RuntimeError('Config copy verification failed; contents suppressed.')
            guard()
            os.replace(temporary, destination)
            if destination.read_bytes() != payload or destination.stat().st_mode & 0o077:
                raise RuntimeError('Installed config verification failed; contents suppressed.')
        finally:
            if temporary.exists(): temporary.unlink()
        print('Selected VPN config installed and verified in encrypted Private/Network/wg0.conf.', flush=True)
    with_private(sys.argv[1], uid, install)


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
