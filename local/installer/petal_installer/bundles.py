"""Create local installer bundles, and pin read-only payload descriptors."""
from pathlib import Path
import contextlib
import hashlib
import json
import os
import shutil
import stat
import tempfile
import subprocess

from .releases import CATALOG, file_digest, load_catalog, payload_items, require, verify_bundle
from .store import directory_fd, read_import
from .portable import tool_command, tool_environment


def create_bundle(destination, version, variant, name, payloads, *, modules=None, local_ai=False):
    """Caller supplies reviewed public artifacts; no credentials, uploads or scripts."""
    destination = Path(destination).absolute()
    require(not destination.exists() and not destination.is_symlink(), 'Choose a new bundle directory.')
    sources = dict(payloads)
    modules = modules or {}
    sources.update({'module:' + n: p for n, p in modules.items()})
    record = {'id': variant, 'name': name, 'description': 'Locally packaged reviewed build',
              'architecture': 'amd64', 'layout': 2, 'local_ai': local_ai, 'payloads': {}, 'modules': {}}
    for role, source in sources.items():
        source = Path(source).absolute()
        require(not any(p.is_symlink() for p in (source, *source.parents)) and source.is_file(),
                'Bundle inputs must be regular files without symlink ancestors.')
        filename = variant + '-' + (role.split(':', 1)[1] if role.startswith('module:') else
                   {'kernel': 'vmlinuz', 'initrd': 'initrd.img', 'rootfs': 'filesystem.squashfs',
                    'shim': 'shim.efi', 'grub': 'grub.efi', 'mokmanager': 'mm.efi'}.get(role, role))
        descriptor = {'asset': filename, 'bytes': source.stat().st_size, 'sha256': file_digest(source)}
        if role.startswith('module:'):
            record['modules'][role[7:]] = descriptor
        else:
            record['payloads'][role] = descriptor
    catalog = {'format': 1, 'version': version, 'variants': [record]}
    encoded = json.dumps(catalog, indent=2).encode() + b'\n'
    load_catalog(encoded)
    parentfd = directory_fd(destination.parent);os.close(parentfd)
    work = Path(tempfile.mkdtemp(prefix='.petalos-bundle-', dir=destination.parent))
    try:
        for role, descriptor in payload_items(record):
            shutil.copyfile(sources[role], work / descriptor['asset'])
        (work / CATALOG).write_bytes(encoded)
        (work / 'selection.json').write_text(json.dumps({'version': version, 'variant': variant}) + '\n')
        verify_bundle(work)
        require(not destination.exists(), 'Bundle destination appeared during packaging.')
        work.rename(destination)
        return {'directory': str(destination), 'version': version, 'variant': variant,
                'catalog_sha256': hashlib.sha256(encoded).hexdigest(), 'verified': True}
    finally:
        if work.exists():shutil.rmtree(work)


def from_build(release, destination, version, variant, name, *, local_ai=False):
    """Export a completed local live-build release without a GitHub round trip."""
    release = Path(release).absolute()
    manifest_path = release / 'manifest.json'
    require(manifest_path.is_file() and not manifest_path.is_symlink(), 'Choose a completed release with manifest.json.')
    manifest = json.loads(read_import(manifest_path, 1024**2))
    sources = {}
    for role, filename in [('kernel', 'vmlinuz'), ('initrd', 'initrd.img'), ('rootfs', 'filesystem.squashfs')]:
        relative = 'binary/live/' + filename;source = release / 'build' / relative
        expected = manifest.get(relative)
        require(type(expected) is dict and expected.get('bytes') == source.stat().st_size
                and expected.get('sha256') == file_digest(source), 'Completed release payload does not match its manifest.')
        sources[role] = source
    listing = subprocess.run(tool_command(['/usr/bin/lsinitramfs', str(sources['initrd'])]),
                             env=tool_environment(), capture_output=True, timeout=120)
    require(listing.returncode == 0 and any(name in listing.stdout.splitlines() for name in
            (b'bin/portable-unlock-pair', b'usr/bin/portable-unlock-pair')),
            'This release predates split storage. Build and verify a new layout-2 release first.')
    for role, relative in [('shim', 'usr/lib/shim/shimx64.efi.signed'),
                           ('grub', 'usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed'),
                           ('mokmanager', 'usr/lib/shim/mmx64.efi.signed')]:
        source = release / 'build/chroot' / relative
        if not source.is_file():source = Path('/') / relative
        require(source.is_file(), 'Signed EFI files are unavailable. Use bundle-create with explicit reviewed firmware assets.')
        sources[role] = source
    return create_bundle(destination, version, variant, name, sources, local_ai=local_ai)


class PinnedBundle:
    """Open every source with no-follow descriptors, verify before first write.

    Copies additionally verify their expected hashes before activation; a user
    modifying a pinned file cannot cause an unverified update to be selected.
    """
    def __init__(self, directory, catalog_sha256):
        self.stack = contextlib.ExitStack()
        self.paths = {}
        self.fds = {}
        self.hashes = {}
        self.catalog = None
        self.variant = None
        self.directory = Path(directory).absolute()
        self.expected_catalog = catalog_sha256

    def __enter__(self):
        try:
            raw = read_import(self.directory / CATALOG, 1024**2)
            require(hashlib.sha256(raw).hexdigest() == self.expected_catalog, 'Release catalog changed since review.')
            self.catalog = load_catalog(raw)
            selection = json.loads(read_import(self.directory / 'selection.json', 4096))
            require(selection['version'] == self.catalog['version'], 'Bundle version mismatch.')
            from .releases import select
            self.variant = select(self.catalog, selection['variant'])
            parent = directory_fd(self.directory);self.stack.callback(os.close, parent)
            for role, item in payload_items(self.variant):
                fd = os.open(item['asset'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                self.stack.callback(os.close, fd)
                info = os.fstat(fd)
                require(stat.S_ISREG(info.st_mode) and info.st_size == item['bytes'], 'Invalid payload file or length.')
                path = Path('/proc/self/fd') / str(fd)
                require(file_digest(path) == item['sha256'], 'Pinned payload failed verification.')
                self.paths[role] = path
                self.fds[role] = fd
                self.hashes[role] = item['sha256']
            return self
        except BaseException:
            self.stack.close();raise

    def __exit__(self, *args):
        return self.stack.__exit__(*args)
