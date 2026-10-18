"""Strict WireGuard profiles. Never log payloads or exception source values."""
from pathlib import Path
import base64
import ipaddress
import os
import re
import stat
import tempfile

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
NETWORK = Path('/mnt/system-state/Network')


class ProfileError(Exception):
    pass


def checked_name(name):
    if not NAME.fullmatch(name) or name == 'legacy':
        raise ProfileError('Use a profile name containing letters, numbers, hyphens or underscores.')
    return name


def safe_directory(path):
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ProfileError('Profile directories must not be symbolic links.')


def read_profile(path, protected=True):
    if protected:
        safe_directory(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16384:
            raise ProfileError('The profile must be a regular file smaller than 16 KiB.')
        if protected and info.st_mode & 0o077:
            raise ProfileError('Restrict the profile permissions to 600 before connecting.')
        content = source.read(16385)
    try:
        return parse(content.decode('utf-8'))
    except UnicodeError:
        raise ProfileError('The profile must be UTF-8 text.') from None


def parse(text):
    sections = {}
    section = None
    allowed = {'Interface': {'PrivateKey', 'Address', 'DNS', 'MTU'},
               'Peer': {'PublicKey', 'PresharedKey', 'AllowedIPs', 'Endpoint', 'PersistentKeepalive'}}
    if len(text.encode('utf-8')) > 16384:
        raise ProfileError('The profile is too large.')
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        if line.startswith('['):
            if line not in ('[Interface]', '[Peer]') or line[1:-1] in sections:
                raise ProfileError('Exactly one Interface and one Peer section are required.')
            section = line[1:-1]
            sections[section] = {}
            continue
        if section is None or '=' not in line:
            raise ProfileError('The profile contains an invalid configuration line.')
        key, value = (part.strip() for part in line.split('=', 1))
        if key not in allowed[section] or key in sections[section] or not value:
            raise ProfileError('The profile contains duplicate or unsupported fields. Executable hooks are not allowed.')
        sections[section][key] = value
    if set(sections) != {'Interface', 'Peer'}:
        raise ProfileError('Exactly one Interface and one Peer section are required.')
    interface, peer = sections['Interface'], sections['Peer']
    if not {'PrivateKey', 'Address', 'DNS'} <= interface.keys() or not {'PublicKey', 'AllowedIPs', 'Endpoint'} <= peer.keys():
        raise ProfileError('The profile needs keys, addresses, DNS servers, full-tunnel routes and an endpoint.')
    for value in (interface['PrivateKey'], peer['PublicKey'], peer.get('PresharedKey')):
        if value is None:
            continue
        try:
            if len(base64.b64decode(value, validate=True)) != 32:
                raise ValueError()
        except ValueError:
            raise ProfileError('A WireGuard key is invalid.') from None
    try:
        addresses = [str(ipaddress.ip_interface(v.strip())) for v in interface['Address'].split(',')]
        dns = [ipaddress.ip_address(v.strip()) for v in interface['DNS'].split(',')]
        routes = {str(ipaddress.ip_network(v.strip(), strict=True)) for v in peer['AllowedIPs'].split(',')}
        endpoint = re.fullmatch(r'(\[[0-9a-fA-F:]+\]|[0-9.]+):(\d{1,5})', peer['Endpoint'])
        if not endpoint:
            raise ProfileError('Use a numeric endpoint IP address. Hostname lookup outside the VPN is disabled.')
        host = ipaddress.ip_address(endpoint[1].strip('[]'))
        port = int(endpoint[2])
        if not 1 <= port <= 65535 or host.is_unspecified or host.is_multicast or host.is_loopback or host.is_link_local:
            raise ValueError()
        if not 1 <= len(dns) <= 8 or any(v.is_unspecified or v.is_multicast or v.is_loopback or v.is_link_local for v in dns):
            raise ValueError()
        if routes != {'0.0.0.0/0', '::/0'} or not 1 <= len(addresses) <= 4:
            raise ValueError()
        if 'MTU' in interface and not 1280 <= int(interface['MTU']) <= 9000:
            raise ValueError()
        if 'PersistentKeepalive' in peer and not 0 <= int(peer['PersistentKeepalive']) <= 65535:
            raise ValueError()
    except ValueError:
        raise ProfileError('An address, DNS server, port, route or numeric setting is invalid. Both full-tunnel routes are required.') from None
    interface['Address'] = ', '.join(addresses)
    interface['DNS'] = ', '.join(map(str, dns))
    peer['AllowedIPs'] = '0.0.0.0/0, ::/0'
    peer['Endpoint'] = f'[{host}]:{port}' if host.version == 6 else f'{host}:{port}'
    # glibc resolv.conf uses at most three servers, in the provider's order.
    return {'interface': interface, 'peer': peer, 'host': str(host), 'port': port, 'version': host.version, 'dns': list(map(str, dns[:3]))}


def serialize(profile, runtime=False):
    interface = dict(profile['interface'])
    if runtime:
        interface.pop('DNS')
        interface['FwMark'] = '51820'
    return '\n'.join(['[Interface]', *(f'{k} = {v}' for k, v in interface.items()),
                      '[Peer]', *(f'{k} = {v}' for k, v in profile['peer'].items()), ''])


def atomic_write(path, text, owner=None):
    safe_directory(path.parent)
    fd, temporary = tempfile.mkstemp(prefix='.profile-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
            if owner is not None:
                os.fchown(output.fileno(), owner, owner)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def select(name=None, network=NETWORK):
    if network == NETWORK:
        from system_state import require
        require()
    safe_directory(network)
    if name is None:
        marker = network / 'selected-profile'
        if marker.exists() or marker.is_symlink():
            if marker.is_symlink() or not marker.is_file() or marker.stat().st_size > 65:
                raise ProfileError('The saved profile selection is invalid.')
            name = marker.read_text().strip()
        else:
            return 'legacy', read_profile(network / 'wg0.conf')
    checked_name(name)
    return name, read_profile(network / 'Profiles' / f'{name}.conf')


def endpoint_transaction(profile=None):
    lines = ['flush set inet portable_vpn endpoints4', 'flush set inet portable_vpn endpoints6']
    if profile:
        lines.append(f"add element inet portable_vpn endpoints{profile['version']} {{ {profile['host']} . {profile['port']} }}")
    return '\n'.join(lines) + '\n'
