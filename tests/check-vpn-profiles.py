#!/usr/bin/python3
"""Profile validation/storage tests using only generated, disposable credentials."""
from pathlib import Path
import base64
import importlib.util
import os
import tempfile

project = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('profiles', project / 'config/includes.chroot/usr/local/lib/portable/vpn_profiles.py')
profiles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profiles)
key = base64.b64encode(os.urandom(32)).decode()
text = f'''[Interface]
PrivateKey = {key}
Address = 10.77.0.2/32, fd77::2/128
DNS = 10.77.0.1, 198.51.100.10, fd77::1, 2001:db8::1
[Peer]
PublicKey = {key}
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = 152.89.162.4:9929
'''
profile = profiles.parse(text)
assert profile['dns'] == ['10.77.0.1', '198.51.100.10', 'fd77::1']
runtime = profiles.serialize(profile, runtime=True)
assert 'DNS =' not in runtime and 'FwMark = 51820' in runtime
assert profiles.parse(profiles.serialize(profile))['peer'] == profile['peer']
print('PASS: profile round trip, provider DNS order and fixed runtime routing mark')
v6 = profiles.parse(text.replace('152.89.162.4:9929', '[2001:db8::4]:9930'))
assert 'endpoints6 { 2001:db8::4 . 9930 }' in profiles.endpoint_transaction(v6)
assert 'endpoints4 { 152.89.162.4 . 9929 }' in profiles.endpoint_transaction(profile)
assert 'add element' not in profiles.endpoint_transaction()
print('PASS: IPv4/IPv6 endpoint transactions and empty disconnected allowances')
invalid = {
    'hostname endpoint': text.replace('152.89.162.4', 'vpn.example.org'),
    'invalid port': text.replace(':9929', ':0'),
    'missing full tunnel': text.replace('0.0.0.0/0', '10.0.0.0/8'),
    'extra route': text.replace('::/0', '::/0, 10.0.0.0/8'),
    'hook': text.replace('Address =', 'PreUp = touch /tmp/pwned\nAddress ='),
    'routing override': text.replace('Address =', 'Table = off\nAddress ='),
    'duplicate key': text.replace('Address =', f'PrivateKey = {key}\nAddress ='),
    'extra peer': text + '[Peer]\n',
    'bad key': text.replace(key, 'invalid'),
    'DNS injection': text.replace('10.77.0.1,', '10.77.0.1; touch /tmp/pwned,'),
    'multicast DNS': text.replace('10.77.0.1,', '224.0.0.1,'),
    'endpoint injection': text.replace(':9929', ':9929; accept'),
    'loopback endpoint': text.replace('152.89.162.4', '127.0.0.1'),
    'oversized profile': text + '#' * 16385,
}
for label, value in invalid.items():
    try:
        profiles.parse(value)
    except profiles.ProfileError as error:
        assert key not in str(error)
        print('PASS: rejects ' + label)
    else:
        raise AssertionError(label)
for name in ['../outside', 'bad/name', 'space name', '-leading', 'legacy']:
    try:
        profiles.checked_name(name)
    except profiles.ProfileError:
        pass
    else:
        raise AssertionError('unsafe name')
print('PASS: profile names cannot traverse paths or collide with legacy fallback')
with tempfile.TemporaryDirectory(prefix='petalos-profiles-', dir='/dev/shm') as tmp:
    network = Path(tmp) / 'Network'
    directory = network / 'Profiles'
    directory.mkdir(parents=True)
    profiles.atomic_write(directory / 'first.conf', text)
    profiles.atomic_write(network / 'selected-profile', 'first\n')
    assert profiles.select(network=network)[0] == 'first'
    file = directory / 'first.conf'
    assert file.stat().st_mode & 0o777 == 0o600
    file.chmod(0o644)
    try:
        profiles.read_profile(file)
    except profiles.ProfileError:
        pass
    else:
        raise AssertionError('unsafe permissions')
    file.chmod(0o600)
    (directory / 'link.conf').symlink_to(file)
    try:
        profiles.read_profile(directory / 'link.conf')
    except OSError:
        pass
    else:
        raise AssertionError('symlink accepted')
    (network / 'selected-profile').unlink()
    profiles.atomic_write(network / 'wg0.conf', text)
    assert profiles.select(network=network)[0] == 'legacy'
print('PASS: encrypted selection, restrictive permissions, symlink rejection and legacy fallback')
