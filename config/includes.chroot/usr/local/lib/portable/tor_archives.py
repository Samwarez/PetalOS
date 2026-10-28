"""Manual signed-archive installation; no browser profile is persisted."""
from pathlib import Path
import datetime
import json
import os
import re
import shutil
import subprocess
import tempfile

ROOT = Path('/mnt/system-state/Applications/TorBrowser')
BUNDLED = Path('/usr/local/share/portable/tor-browser')
KEYRING = Path('/usr/local/share/portable/tor-browser-developers.keyring')
ARCHIVE = re.compile(r'tor-browser-linux-x86_64-[0-9]+(?:\.[0-9]+)+(?:\.tar\.xz|\.tar\.gz)\Z')


class ArchiveError(Exception):
    pass


def safe(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ArchiveError('Tor archive paths must not be symbolic links.')


def verify(archive, signature, keyring=KEYRING):
    for path, limit in ((archive, 512 * 1024**2), (signature, 1024**2), (keyring, 1024**2)):
        safe(path)
        if not path.is_file() or not 0 < path.stat().st_size <= limit:
            raise ArchiveError('The archive, signature or signing key is missing or invalid.')
    if not ARCHIVE.fullmatch(archive.name):
        raise ArchiveError('Choose a Tor Browser Linux x86_64 distribution archive.')
    result = subprocess.run(['/usr/bin/gpgv', '--keyring', str(keyring), str(signature), str(archive)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    if result.returncode:
        raise ArchiveError('Tor Browser signature verification failed. The selected archive was not installed.')


def bundled(root=BUNDLED):
    """The reviewed OS supplies its default browser; never trust an unsigned copy."""
    safe(root)
    marker = root / 'manifest.json'
    safe(marker)
    if not marker.is_file() or marker.stat().st_size > 4096:
        raise ArchiveError('The bundled Tor Browser manifest is missing or invalid.')
    try:
        record = json.loads(marker.read_text())
        name, checksum = record['archive'], record['sha256']
        if not ARCHIVE.fullmatch(name) or not re.fullmatch('[a-f0-9]{64}', checksum):raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise ArchiveError('The bundled Tor Browser manifest is invalid.') from None
    archive = root / name
    safe(archive)
    import hashlib
    if not archive.is_file() or not 0 < archive.stat().st_size <= 512*1024**2:
        raise ArchiveError('The bundled Tor Browser archive is missing or invalid.')
    with archive.open('rb') as contents:actual = hashlib.file_digest(contents, 'sha256').hexdigest()
    if actual != checksum:raise ArchiveError('The bundled Tor Browser checksum failed.')
    verify(archive, Path(str(archive)+'.asc'))
    return archive


def current(root=ROOT, bundle=BUNDLED):
    # Bundled applications follow the reviewed OS release. Legacy releases
    # without a bundle retain their separately installed archive workflow.
    if bundle.exists() or bundle.is_symlink():return bundled(bundle)
    safe(root)
    marker = root / 'current-archive.json'
    if marker.exists() or marker.is_symlink():
        safe(marker)
        if not marker.is_file() or marker.stat().st_size > 1024:
            raise ArchiveError('The selected Tor archive record is invalid.')
        record = json.loads(marker.read_text())
        version, name = record['version'], record['archive']
        if not re.fullmatch(r'\d{8}-\d{6}-\d+', version) or not ARCHIVE.fullmatch(name):
            raise ArchiveError('The selected Tor archive record is invalid.')
        archive = root / 'Versions' / version / name
    else:
        archives = [p for p in root.glob('tor-browser-linux-x86_64-*.tar.*') if ARCHIVE.fullmatch(p.name)]
        if len(archives) != 1:
            raise ArchiveError('Install a signed Tor archive in SystemSettings/Applications/TorBrowser using Install Tor Archive.')
        archive = archives[0]
    safe(archive)
    return archive


def install(archive, signature, root=ROOT, keyring=KEYRING):
    # Sources may use a symlinked Downloads folder; follow only directory links.
    if archive.is_symlink() or signature.is_symlink():
        raise ArchiveError('Choose regular archive and signature files.')
    archive, signature = archive.resolve(strict=True), signature.resolve(strict=True)
    verify(archive, signature, keyring)
    safe(root)
    versions = root / 'Versions'
    safe(versions)
    versions.mkdir(parents=True, mode=0o700, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    destination = versions / stamp
    destination.mkdir(mode=0o700)
    # Keep prior installations and the old pointer until the copied pair verifies.
    for source, target in ((archive, destination / archive.name),
                           (signature, destination / (archive.name + '.asc'))):
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as output, source.open('rb') as input_file:
            shutil.copyfileobj(input_file, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
    verify(destination / archive.name, destination / (archive.name + '.asc'), keyring)
    fd, temporary = tempfile.mkstemp(prefix='.current-', dir=root)
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump({'version': stamp, 'archive': archive.name}, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, root / 'current-archive.json')
        for directory in (destination, versions, root):
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return destination / archive.name


def main():
    import sys
    try:
        archive = current()
        verify(archive, Path(str(archive) + '.asc'))
        print(archive)
    except Exception:
        print('No valid signed Tor archive is selected.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
