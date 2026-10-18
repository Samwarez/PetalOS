#!/usr/bin/python3 -I
"""Synthetic public archive fixture; never reads the user's browser/archive."""
import importlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile

sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
import tor_archives as archives
assert os.geteuid() == 0
old_payload, old_current, old_verify = c.PAYLOAD, archives.current, archives.verify
verified = []
report = {}
try:
    with tempfile.TemporaryDirectory(prefix='petalos-public-cache-', dir='/run') as directory:
        root = Path(directory)
        archive = root / 'tor-browser-linux-x86_64-1.0.tar.xz'
        Path(str(archive) + '.asc').write_text('public fixture signature')
        c.PAYLOAD = root / 'cache'
        archives.current = lambda: archive
        def verify(path, signature):
            verified.append(path.read_bytes())
        archives.verify = verify
        def write_archive(value):
            with tarfile.open(archive, 'w:xz') as output:
                data = value.encode()
                item = tarfile.TarInfo('tor-browser/Browser/public-version')
                item.size = len(data)
                output.addfile(item, io.BytesIO(data))
        write_archive('old-public-version')
        first = c.distribution()
        report['same_archive_reuses_generation'] = c.distribution() == first
        write_archive('new-public-version')
        second = c.distribution()
        report['changed_archive_gets_new_generation'] = first != second
        report['new_contents_selected'] = (second / 'Browser/public-version').read_text() == 'new-public-version'
        report['old_generation_unchanged'] = (first / 'Browser/public-version').read_text() == 'old-public-version'
        report['every_copy_verified_before_use'] = len(verified) == 3
        def reject(path, signature):
            raise archives.ArchiveError('Synthetic invalid signature')
        archives.verify = reject
        try:
            c.distribution()
            report['failed_verification_rejects_cached_generation'] = False
        except archives.ArchiveError:
            report['failed_verification_rejects_cached_generation'] = True
finally:
    c.PAYLOAD, archives.current, archives.verify = old_payload, old_current, old_verify
print(json.dumps(report, sort_keys=True))
assert all(report.values())
