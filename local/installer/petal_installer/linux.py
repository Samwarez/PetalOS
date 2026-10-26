"""Read-only Linux discovery. No block device is opened for writing here."""
from pathlib import Path
import hashlib
import json
import platform
import subprocess

from . import InstallerError
from .releases import require
from .portable import tool_command, tool_environment

# Set only by the verified worker bootstrap. Its supervisor stays in the
# original host mount namespace while the worker uses its private runtime.
HOST_MOUNTINFO = None


def host_mounts():
    if HOST_MOUNTINFO is None:return set()
    try:
        rows = HOST_MOUNTINFO.read_text().splitlines()
        require(bool(rows), 'Could not establish the host mount state.')
        mounted = set()
        for row in rows:
            fields = row.split()
            require(len(fields) >= 10 and '-' in fields and len(fields[2].split(':')) == 2
                    and all(part.isdecimal() for part in fields[2].split(':')),
                    'Could not establish the host mount state.')
            mounted.add(fields[2])
        return mounted
    except OSError:
        raise InstallerError('Could not establish the host mount state; the operation stopped.') from None


def host_mounted(record):
    mounted = host_mounts()
    return any(node.get('maj:min') in mounted for node in walk(record))


def command(args, *, timeout=30, payload=None, allowed=(0,), pass_fds=()):
    try:
        result = subprocess.run(tool_command(args), input=payload, capture_output=True, timeout=timeout,
                                env=tool_environment(), pass_fds=pass_fds)
    except (OSError, subprocess.TimeoutExpired):
        raise InstallerError('Required Linux tool is unavailable or timed out.') from None
    if (result.returncode == 2 and payload is not None and args[:2] == ['/usr/sbin/cryptsetup', 'open']
            and b'No key available with this passphrase.' in result.stderr.splitlines()):
        raise InstallerError('The passphrase was not accepted.')
    require(result.returncode in allowed, 'Linux tool failed (' + Path(args[0]).name + '); raw output suppressed.')
    return result.stdout


def walk(record):
    yield record
    for child in record.get('children', []):
        yield from walk(child)


def describe(record, sysroot=Path('/sys/class/block')):
    nodes = list(walk(record))
    reasons = []
    if record.get('type') != 'disk':
        reasons.append('Not a whole disk.')
    if record.get('ro'):
        reasons.append('Read-only drive.')
    if int(record.get('size') or 0) <= 0:
        reasons.append('No media or usable capacity reported.')
    if not record.get('rm') and record.get('tran') != 'usb':
        reasons.append('Not identified as removable media or a USB drive.')
    if any(any(p for p in (node.get('mountpoints') or [])) for node in nodes):
        reasons.append('Drive or one of its volumes is mounted.')
    if host_mounted(record):
        reasons.append('Drive or one of its volumes is mounted by another host application.')
    if any(node.get('type') not in {'disk', 'part'} for node in nodes):
        reasons.append('Drive has an active mapping or another unsupported child.')
    for node in nodes:
        holders = sysroot / Path(node['path']).name / 'holders'
        if not holders.is_dir():
            reasons.append('Could not establish drive holder state.')
        elif any(holders.iterdir()):
            reasons.append('Drive has active holders.')
    identity = {key: record.get(key) for key in ('path', 'maj:min', 'size', 'serial', 'model', 'tran')}
    for key in ('path', 'maj:min', 'size'):
        require(identity[key] is not None, 'Incomplete drive identity.')
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    partitions = [{'path': n['path'], 'type': n.get('type'), 'fstype': n.get('fstype'),
                   'label': n.get('label'), 'partlabel': n.get('partlabel'),
                   'size': int(n['size']), 'uuid': n.get('uuid')} for n in nodes[1:]]
    return {'path': record['path'], 'model': (record.get('model') or 'Unknown drive').strip(),
            'bytes': int(record['size']), 'transport': record.get('tran'),
            'eligible': not reasons, 'blocked_reasons': sorted(set(reasons)),
            'identity': fingerprint, 'partitions': partitions}


def devices():
    require(platform.system() == 'Linux', 'Disk discovery currently requires Linux.')
    fields = 'PATH,TYPE,SIZE,RM,RO,MODEL,SERIAL,TRAN,MAJ:MIN,MOUNTPOINTS,FSTYPE,LABEL,PARTLABEL,UUID'
    try:
        data = json.loads(command(['/usr/bin/lsblk', '--json', '--bytes', '--tree', '--output', fields]))
        return [describe(record) for record in data['blockdevices'] if record['type'] == 'disk']
    except (KeyError, ValueError, TypeError):
        raise InstallerError('Could not parse Linux disk inventory.') from None


def choose(path):
    matches = [disk for disk in devices() if disk['path'] == str(path)]
    require(len(matches) == 1, 'Select an exact whole-disk path from the devices command.')
    require(matches[0]['eligible'], 'Drive is unavailable: ' + ' '.join(matches[0]['blocked_reasons']))
    return matches[0]


def raw_disk(path):
    fields = 'PATH,TYPE,SIZE,RM,RO,MODEL,SERIAL,TRAN,MAJ:MIN,MOUNTPOINTS,FSTYPE,LABEL,PARTLABEL,UUID'
    data = json.loads(command(['/usr/bin/lsblk', '--json', '--bytes', '--tree', '--output', fields, str(path)]))
    require(len(data.get('blockdevices', [])) == 1, 'Drive inventory is ambiguous.')
    record = data['blockdevices'][0]
    require(record['type'] == 'disk' and record['path'] == str(path), 'Expected an exact whole-disk path.')
    require(not host_mounted(record), 'Another host application mounted the selected drive; the operation stopped.')
    return record


def benchmark():
    """Synthetic RAM cipher measurements, not storage or passphrase timings."""
    result = {}
    for bits in (256, 512):
        raw = command(['/usr/sbin/cryptsetup', 'benchmark', '--cipher', 'aes-xts-plain64',
                       '--key-size', str(bits)], timeout=90)
        result[str(bits)] = raw.decode('utf-8', errors='replace').strip()
    return {'cipher': 'aes-xts-plain64', 'measurements': result,
            'scope': 'Synthetic RAM cipher throughput on this host; not SD throughput or boot time.'}
