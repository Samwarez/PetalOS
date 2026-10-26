"""Bloom's password-based storage tiers and non-destructive KDF calibration."""
from pathlib import Path
import os
import re

from .releases import require

MIB = 1024
PROFILES = {
    'fast': {
        'name': 'Fast — Legacy Friendly', 'audience': 'Older hardware',
        'memory_kib': 64 * MIB, 'minimum_memory_kib': 32 * MIB,
        'target_unlock_ms': 1000, 'parallel': 1, 'minimum_characters': 12,
        'description': 'Strong AES-256-XTS protection with a lighter Argon2id unlock cost. '
                       'Targets about 1 second per encrypted volume, using 32–64 MiB of RAM. '
                       'Best for older computers and shorter unlock waits.',
    },
    'balanced': {
        'name': 'Balanced — Recommended', 'audience': 'Default · modern computers',
        'memory_kib': 512 * MIB, 'minimum_memory_kib': 256 * MIB,
        'target_unlock_ms': 2000, 'parallel': 4, 'minimum_characters': 12,
        'description': 'AES-256-XTS with stronger Argon2id protection against passphrase guessing. '
                       'Targets about 2 seconds per encrypted volume, using 256–512 MiB of RAM. '
                       'Recommended for modern computers.',
    },
    'paranoid': {
        'name': 'Paranoid — Maximum Protection', 'audience': 'High-value data · longer unlock waits',
        'memory_kib': 2048 * MIB, 'minimum_memory_kib': 1024 * MIB,
        'target_unlock_ms': 5000, 'parallel': 4, 'minimum_characters': 32,
        'description': 'AES-256-XTS with an aggressive Argon2id memory and work budget. '
                       'Targets about 5 seconds per encrypted volume, using 1–2 GiB of RAM. '
                       'Designed to make offline guessing more expensive for well-funded attackers. '
                       'Requires long, unique, randomly chosen passphrases.',
    },
}
for _profile in PROFILES.values():
    _profile.update(format='luks2', cipher='aes-xts-plain64', key_bits=512, pbkdf='argon2id')

SHARED_EXPLANATION = (
    'All tiers use AES-256-XTS (two independent 256-bit keys). The tiers change unlock delay '
    'and resistance to passphrase guessing; they do not change ongoing AES disk speed. '
    'AES-256 offers a strong margin against known quantum key-search attacks. Weak passphrases, '
    'an unlocked computer or a compromised device can still defeat protection.'
)
PORTABILITY_EXPLANATION = (
    'CPU and RAM calibration runs on this computer before any erase. OS and SYSTEM settings '
    'are unlocked sequentially, so boot needs about twice the per-volume work. Slow CPUs may '
    'need up to four times the target delay to retain the tier’s memory protection. Stored settings '
    'may unlock more slowly elsewhere. Choose for the oldest computer you plan to use.'
)


def resources():
    values = {}
    for row in Path('/proc/meminfo').read_text().splitlines():
        key, _, rest = row.partition(':')
        if key in ('MemTotal', 'MemAvailable'):values[key] = int(rest.split()[0])
    require(set(values) == {'MemTotal', 'MemAvailable'}, 'Could not determine available memory for encryption calibration.')
    total = values['MemTotal'];available = values['MemAvailable']
    # Respect cgroup-v2 memory limits, including limits imposed by ancestors.
    base = Path('/sys/fs/cgroup');locations = {base}
    for line in Path('/proc/self/cgroup').read_text().splitlines():
        if line.startswith('0::'):
            relative = Path(line[3:].lstrip('/'))
            if '..' not in relative.parts:
                leaf = base / relative
                locations.update(p for p in (leaf, *leaf.parents) if p == base or base in p.parents)
    for location in locations:
        maximum = location / 'memory.max';current = location / 'memory.current'
        if maximum.exists():
            text = maximum.read_text().strip()
            if text != 'max':
                limit = int(text) // 1024;used = int(current.read_text()) // 1024
                total = min(total, limit);available = min(available, max(0, limit - used))
    cpus = len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else os.cpu_count() or 1
    return {'total_kib': total, 'available_kib': available, 'cpus': max(1, cpus)}


def budget(profile, hardware):
    require(profile in PROFILES, 'Unknown encryption tier.')
    policy = PROFILES[profile]
    memory = min(policy['memory_kib'], hardware['total_kib'] // 2, hardware['available_kib'] // 2)
    memory = memory // MIB * MIB
    require(memory >= policy['minimum_memory_kib'],
            policy['name'] + ' needs more free RAM for safe calibration. Choose a lighter tier or another computer.')
    return {'memory_kib': memory, 'parallel': min(policy['parallel'], max(1, hardware['cpus'])),
            'target_unlock_ms': policy['target_unlock_ms']}


def validate_calibration(profile, value):
    require(profile in PROFILES and type(value) is dict and
            set(value) == {'profile', 'memory_kib', 'parallel', 'iterations', 'target_unlock_ms'},
            'Invalid encryption calibration.')
    policy = PROFILES[profile]
    require(value['profile'] == profile and all(type(value[k]) is int for k in
            ('memory_kib', 'parallel', 'iterations', 'target_unlock_ms')),
            'Invalid encryption calibration values.')
    require(policy['minimum_memory_kib'] <= value['memory_kib'] <= policy['memory_kib']
            and 1 <= value['parallel'] <= policy['parallel']
            and 4 <= value['iterations'] <= 1000000
            and value['target_unlock_ms'] in {policy['target_unlock_ms'] * n for n in (1, 2, 4)},
            'This computer could not meet the selected encryption tier. No drive erase was started; choose a lighter tier or another computer.')
    return dict(value)


def calibrate(profile, *, hardware=None, command=None):
    if command is None:
        from .linux import command
    selected = budget(profile, resources() if hardware is None else hardware)
    for multiple in (1, 2, 4):
        target = selected['target_unlock_ms'] * multiple
        result = command(['/usr/sbin/cryptsetup', 'benchmark', '--pbkdf', 'argon2id', '--key-size', '512',
                          '--pbkdf-memory', str(selected['memory_kib']), '--pbkdf-parallel', str(selected['parallel']),
                          '--iter-time', str(target)], timeout=180).decode('utf-8')
        match = re.search(r'^argon2id\s+(\d+) iterations, (\d+) memory, (\d+) parallel threads', result, re.MULTILINE)
        require(match is not None, 'Could not read the encryption calibration; no drive erase was started.')
        iterations, memory, parallel = map(int, match.groups())
        require(memory <= selected['memory_kib'] and parallel <= selected['parallel'], 'Encryption calibration exceeded the safe hardware budget.')
        if memory < PROFILES[profile]['minimum_memory_kib'] and multiple < 4:continue
        return validate_calibration(profile, dict(profile=profile, iterations=iterations, memory_kib=memory,
            parallel=parallel, target_unlock_ms=target))


def verify_header(metadata, profile, calibration):
    calibration = validate_calibration(profile, calibration)
    segments = metadata.get('segments', {})
    require(segments and all(s.get('encryption') == 'aes-xts-plain64' for s in segments.values()),
            'The new volume cipher did not match the selected tier.')
    slots = metadata.get('keyslots', {})
    require(len(slots) == 1, 'Unexpected keyslots on a newly formatted volume.')
    for slot in slots.values():
        kdf = slot.get('kdf', {})
        require(slot.get('key_size') == 64 and kdf.get('type') == 'argon2id'
                and kdf.get('memory') == calibration['memory_kib']
                and kdf.get('cpus') == calibration['parallel']
                and kdf.get('time') == calibration['iterations'],
                'The new volume did not retain the calibrated encryption settings.')
