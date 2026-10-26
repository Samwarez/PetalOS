"""Version/variant catalogs and bounded GitHub release downloads."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from . import InstallerError, __version__

CATALOG = 'petalos-release.json'
ROLES = {'kernel', 'initrd', 'rootfs', 'shim', 'grub', 'mokmanager'}
REQUIRED = {'kernel', 'initrd', 'rootfs'}
MAX_CATALOG = 1024 * 1024
MAX_PAYLOAD = 64 * 1024**3


def require(condition, text):
    if not condition:
        raise InstallerError(text)


def file_digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def plain_file(path):
    path = Path(path)
    require(not any(p.is_symlink() for p in (path, *path.parents)),
            'Symbolic links are not accepted as release inputs.')
    require(stat.S_ISREG(path.stat().st_mode), 'Expected a regular release file.')
    return path


def payload_items(variant):
    """All downloaded assets; module keys are immutable OS squashfs names."""
    return list(variant['payloads'].items()) + [('module:' + name, item)
            for name, item in variant.get('modules', {}).items()]


def load_catalog(data):
    require(len(data) <= MAX_CATALOG, 'Release catalog is too large.')
    try:
        def unique(pairs):
            value = {}
            for key, item in pairs:
                require(key not in value, 'Duplicate catalog field.')
                value[key] = item
            return value
        catalog = json.loads(data, object_pairs_hook=unique)
        require(type(catalog) is dict and catalog.get('format') == 1,
                'Unsupported release catalog format.')
        require(isinstance(catalog['version'], str) and
                re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+_-]{0,95}', catalog['version']),
                'Invalid release version.')
        builds = catalog['variants']
        require(type(builds) is list and 1 <= len(builds) <= 32,
                'A release needs between one and 32 variants.')
        ids = set()
        for variant in builds:
            require(type(variant) is dict, 'Invalid variant record.')
            ident = variant['id']
            require(isinstance(ident, str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,47}', ident)
                    and ident not in ids, 'Invalid or duplicate variant ID.')
            ids.add(ident)
            for name, limit in [('name', 100), ('description', 2000)]:
                text = variant.get(name, '')
                require(isinstance(text, str) and len(text) <= limit and
                        not any(ord(c) < 32 and c != '\n' for c in text),
                        'Invalid variant description.')
            require(variant.get('architecture') == 'amd64' and variant.get('layout') in (1, 2),
                    'Unsupported architecture or storage layout.')
            require(type(variant.get('local_ai')) is bool, 'Variant must declare local_ai.')
            payloads = variant['payloads']
            require(type(payloads) is dict and REQUIRED <= payloads.keys() <= ROLES,
                    'Variant has unsupported or missing payload roles.')
            require(not ({'shim', 'grub', 'mokmanager'} & payloads.keys()) or
                    {'shim', 'grub', 'mokmanager'} <= payloads.keys(),
                    'The signed EFI chain must be supplied together.')
            modules = variant.get('modules', {})
            require(type(modules) is dict and len(modules) <= 32, 'Invalid OS module list.')
            require(all(isinstance(n, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*\.squashfs', n)
                        and n != 'filesystem.squashfs' for n in modules), 'Unsafe OS module name.')
            names = set()
            for _, item in payload_items(variant):
                name = item['asset']
                require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,159}', name)
                        and name not in {CATALOG, 'selection.json'} and name not in names,
                        'Unsafe or duplicate payload asset name.')
                names.add(name)
                require(type(item['bytes']) is int and 0 < item['bytes'] <= MAX_PAYLOAD,
                        'Invalid payload length.')
                require(isinstance(item['sha256'], str) and re.fullmatch(r'[a-f0-9]{64}', item['sha256']),
                        'Invalid payload checksum.')
        return catalog
    except (KeyError, TypeError, ValueError, UnicodeError):
        raise InstallerError('Malformed release catalog.') from None


def select(catalog, variant_id):
    for variant in catalog['variants']:
        if variant['id'] == variant_id:
            return variant
    raise InstallerError('That variant is not available in the selected version.')


def verify_bundle(directory):
    root = Path(directory).absolute()
    catalog = load_catalog(plain_file(root / CATALOG).read_bytes())
    selection_path = plain_file(root / 'selection.json')
    require(selection_path.stat().st_size <= 4096, 'Invalid bundle selection.')
    try:
        selection = json.loads(selection_path.read_bytes())
        require(selection['version'] == catalog['version'], 'Bundle version mismatch.')
        variant = select(catalog, selection['variant'])
    except (KeyError, ValueError, TypeError):
        raise InstallerError('Invalid bundle selection.') from None
    for _, item in payload_items(variant):
        path = plain_file(root / item['asset'])
        require(path.stat().st_size == item['bytes'] and file_digest(path) == item['sha256'],
                'A release payload failed length/checksum verification.')
    return catalog, variant


def github_url(url):
    parts = urllib.parse.urlsplit(url)
    return (parts.scheme == 'https' and not parts.username and not parts.password
            and parts.port in (None, 443) and
            (parts.hostname in {'api.github.com', 'github.com'} or
             (parts.hostname or '').endswith('.githubusercontent.com')))


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        require(github_url(url), 'Refused a release download redirect outside GitHub HTTPS.')
        redirected = super().redirect_request(request, fp, code, message, headers, url)
        if urllib.parse.urlsplit(url).hostname != 'api.github.com':
            redirected.remove_header('Authorization')
        return redirected


class GitHub:
    def __init__(self, repository='Samwarez/PetalOS', token=None):
        require(bool(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository)),
                'Use a GitHub owner/repository name.')
        self.repository = repository
        self.token = token
        self.opener = urllib.request.build_opener(SafeRedirect())

    def open(self, path, *, binary=False):
        url = 'https://api.github.com/repos/' + self.repository + path
        headers = {'User-Agent': 'PetalOS-Installer/' + __version__,
                   'Accept': 'application/octet-stream' if binary else 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2022-11-28'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        try:
            return self.opener.open(urllib.request.Request(url, headers=headers), timeout=30)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise InstallerError('GitHub release/repository not found. Private repositories need GH_TOKEN with Contents read access.') from None
            raise InstallerError('GitHub request failed (HTTP ' + str(error.code) + ').') from None
        except (OSError, urllib.error.URLError):
            raise InstallerError('Could not reach GitHub. Check the connection and try again.') from None

    def json(self, path):
        with self.open(path) as response:
            data = response.read(4 * MAX_CATALOG + 1)
        require(len(data) <= 4 * MAX_CATALOG, 'GitHub response exceeded its size limit.')
        try:
            return json.loads(data)
        except (ValueError, UnicodeError):
            raise InstallerError('GitHub returned an invalid response.') from None

    def releases(self, prereleases=False):
        records = []
        for page in range(1, 101):
            batch = self.json('/releases?per_page=100&page=' + str(page))
            require(type(batch) is list, 'Invalid GitHub releases response.')
            for release in batch:
                if not release.get('draft') and (prereleases or not release.get('prerelease')):
                    records.append({'version': release['tag_name'], 'name': release.get('name'),
                                    'prerelease': bool(release.get('prerelease')),
                                    'installer_catalog': any(a.get('name') == CATALOG for a in release.get('assets', []))})
            if len(batch) < 100:
                return records
        raise InstallerError('Release pagination limit exceeded.')

    def asset_map(self, release):
        require(type(release.get('id')) is int, 'Invalid GitHub release ID.')
        records = []
        for page in range(1, 101):
            batch = self.json('/releases/' + str(release['id']) + '/assets?per_page=100&page=' + str(page))
            require(type(batch) is list, 'Invalid GitHub asset list.')
            records.extend(batch)
            if len(batch) < 100:
                break
        else:
            raise InstallerError('Release asset pagination limit exceeded.')
        assets = {}
        for asset in records:
            require(asset['name'] not in assets, 'Duplicate GitHub release asset name.')
            assets[asset['name']] = asset
        return assets

    def catalog(self, version):
        release = self.json('/releases/tags/' + urllib.parse.quote(version, safe=''))
        require(not release.get('draft') and release.get('tag_name') == version,
                'Select a published GitHub release version.')
        assets = self.asset_map(release)
        require(CATALOG in assets, 'This version has no installer catalog yet.')
        asset = assets[CATALOG]
        require(type(asset.get('size')) is int and 0 < asset['size'] <= MAX_CATALOG,
                'Invalid release catalog length.')
        with self.asset(asset) as response:
            data = response.read(MAX_CATALOG + 1)
        require(len(data) == asset['size'], 'Release catalog download was incomplete.')
        if asset.get('digest'):
            require(asset['digest'] == 'sha256:' + hashlib.sha256(data).hexdigest(),
                    'GitHub catalog digest mismatch.')
        catalog = load_catalog(data)
        require(catalog['version'] == version, 'Catalog version does not match its GitHub release.')
        return catalog, assets, data

    def asset(self, asset):
        require(type(asset.get('id')) is int and asset['id'] > 0, 'Invalid GitHub asset ID.')
        return self.open('/releases/assets/' + str(asset['id']), binary=True)

    def download(self, version, variant_id, destination, progress=lambda event: None):
        catalog, assets, raw = self.catalog(version)
        variant = select(catalog, variant_id)
        destination = Path(destination).absolute()
        require(not destination.exists() and not destination.is_symlink(),
                'Download destination already exists; choose a new directory.')
        require(not any(p.is_symlink() for p in destination.parents),
                'Download destination parents must not be symbolic links.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix='.petalos-download-', dir=destination.parent))
        try:
            for role, item in payload_items(variant):
                require(item['asset'] in assets, 'Catalog refers to an absent GitHub asset.')
                asset = assets[item['asset']]
                require(asset['size'] == item['bytes'], 'GitHub asset size differs from the catalog.')
                if asset.get('digest'):
                    require(asset['digest'] == 'sha256:' + item['sha256'], 'GitHub payload digest mismatch.')
                checksum = hashlib.sha256()
                count = 0
                with self.asset(asset) as source, (work / item['asset']).open('xb') as target:
                    while chunk := source.read(min(1024**2, item['bytes'] - count + 1)):
                        count += len(chunk)
                        require(count <= item['bytes'], 'Download exceeded the expected payload length.')
                        target.write(chunk)
                        checksum.update(chunk)
                        progress({'stage': 'downloading', 'payload': role, 'bytes': count, 'total': item['bytes']})
                    target.flush()
                    os.fsync(target.fileno())
                require(count == item['bytes'] and checksum.hexdigest() == item['sha256'],
                        'Downloaded payload failed checksum/length verification.')
            (work / CATALOG).write_bytes(raw)
            (work / 'selection.json').write_text(json.dumps({'version': version, 'variant': variant_id}) + '\n')
            verify_bundle(work)
            require(not destination.exists(), 'Download destination appeared during download.')
            work.rename(destination)
            return {'directory': str(destination), 'version': version, 'variant': variant_id,
                    'verified': True, 'trust': 'GitHub HTTPS and catalog SHA-256; no independent release signature'}
        finally:
            if work.exists():
                shutil.rmtree(work)
