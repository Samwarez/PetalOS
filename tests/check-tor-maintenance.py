#!/usr/bin/python3
"""Real signature/selection tests with public archives only; never launch Tor."""
from pathlib import Path
import importlib.util
import json
import tempfile

project = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('archives', project / 'config/includes.chroot/usr/local/lib/portable/tor_archives.py')
archives = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archives)
cache = project.parent / 'provisioning/TorBrowser'
archive = next(cache.glob('tor-browser-linux-x86_64-*.tar.xz'))
signature = Path(str(archive) + '.asc')
keyring = project / 'config/includes.chroot/usr/local/share/portable/tor-browser-developers.keyring'
with tempfile.TemporaryDirectory(prefix='petalos-tor-maintenance-', dir='/dev/shm') as temporary:
    root = Path(temporary) / 'TorBrowser'
    first = archives.install(archive, signature, root, keyring)
    assert archives.current(root) == first
    assert first.stat().st_mode & 0o777 == 0o600
    selected = (root / 'current-archive.json').read_bytes()
    invalid = Path(temporary) / 'invalid.asc'
    invalid.write_text('invalid detached signature')
    try:
        archives.install(archive, invalid, root, keyring)
    except archives.ArchiveError:
        pass
    else:
        raise AssertionError('invalid signature accepted')
    assert (root / 'current-archive.json').read_bytes() == selected
    assert archives.current(root) == first
    print('PASS: verified installation and invalid signature preserves selection')
    second = archives.install(archive, signature, root, keyring)
    assert first.exists() and second != first and archives.current(root) == second
    print('PASS: manual replacement retains previous distribution and changes selection atomically')
    link = Path(temporary) / archive.name
    link.symlink_to(archive)
    try:
        archives.install(link, signature, root, keyring)
    except archives.ArchiveError:
        pass
    else:
        raise AssertionError('symlink accepted')
    print('PASS: symbolic archive rejected')
    (root / 'current-archive.json').write_text(json.dumps({'version':'../outside','archive':archive.name}))
    try:
        archives.current(root)
    except archives.ArchiveError:
        pass
    else:
        raise AssertionError('path traversal accepted')
    print('PASS: invalid selection cannot escape version storage')
