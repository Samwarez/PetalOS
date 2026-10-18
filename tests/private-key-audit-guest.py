#!/usr/bin/python3 -I
"""Read-only QEMU preflight: return slots/booleans, never key material."""
import ctypes
import json
import os
from pathlib import Path
import resource
import stat
import subprocess
import sys

def check(device, slot, *, key=None, password=None):
    command = ['/usr/sbin/cryptsetup', 'open', '--type', 'luks2',
               '--test-passphrase', '--key-slot', str(slot), '--key-file',
               str(key) if key is not None else '-', str(device)]
    result = subprocess.run(command, input=password, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=45)
    if result.returncode not in (0, 2):
        raise RuntimeError('Cryptographic preflight could not be completed.')
    return result.returncode == 0

def main():
    assert os.geteuid() == 0
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    assert ctypes.CDLL('libc.so.6').prctl(4, 0, 0, 0, 0) == 0
    assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
    sys.path.insert(0, '/usr/local/lib/portable')
    from private_storage import backend, identity, operation
    from system_state import FULL, require
    with operation(shared=True):
        require()
        adapter = backend(); state = identity()
        assert not adapter.mapped('data'), 'Private must remain closed during audit.'
        adapter.verify_mapping(state, 'system')
        device = adapter.device(state, 'data')
        result = subprocess.run(['/usr/sbin/cryptsetup', 'luksDump', '--dump-json-metadata', str(device)],
                                capture_output=True, timeout=15, check=True)
        metadata = json.loads(result.stdout)
        slots = sorted(int(value) for value in metadata['keyslots'])
        assert 2 <= len(slots) <= 8 and all(0 <= value <= 31 for value in slots)
        assert not metadata.get('tokens'), 'External unlock tokens require separate review.'
        assert all(value.get('type') == 'luks2' for value in metadata['keyslots'].values())
        key = FULL/'.portable-keys/data.key'
        assert not any(path.is_symlink() for path in (key, *key.parents))
        info = key.lstat()
        assert stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
        assert stat.S_IMODE(info.st_mode) == 0o600
        matches = [slot for slot in slots if check(device, slot, key=key)]
        report = {'active_slots': slots, 'legacy_key_slots': matches,
                  'private_mapping_closed': not adapter.mapped('data')}
        assert len(matches) == 1, 'Legacy key must match exactly one slot.'
        if sys.argv[1:] == ['--verify-private']:
            from desktop_session import environment
            prompt = subprocess.run(['/usr/bin/setpriv', '--reuid=1000', '--regid=1000',
                                     '--clear-groups', '/usr/local/bin/portable-dialog', '--data-password'],
                                    env=environment(), stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=180)
            assert prompt.returncode == 0 and 0 < len(prompt.stdout) <= 512
            password = prompt.stdout
            human = [slot for slot in slots if check(device, slot, password=password)]
            report['private_passphrase_slots'] = human
            report['private_passphrase_valid'] = len(human) == 1
            report['independent_retained_slot'] = len(human) == 1 and human[0] != matches[0]
            system = adapter.device(state, 'system')
            r = subprocess.run(['/usr/sbin/cryptsetup', 'open', '--test-passphrase',
                                '--key-file', '-', str(system)], input=password,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
            assert r.returncode in (0, 2)
            report['private_phrase_also_unlocks_system'] = r.returncode == 0
            del password, prompt
        else:
            assert not sys.argv[1:]
        assert not adapter.mapped('data')
        print(json.dumps(report))

if __name__ == '__main__':
    main()
