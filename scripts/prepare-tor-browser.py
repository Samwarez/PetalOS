#!/usr/bin/python3 -B
"""Fetch and verify the pinned public Tor archive before a fresh OS build."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT/'config/includes.chroot/usr/local/share/portable/tor-browser'
KEYRING = ROOT/'config/includes.chroot/usr/local/share/portable/tor-browser-developers.keyring'


def validate(directory, manifest, keyring=KEYRING):
    source = ROOT/'config/includes.chroot/usr/local/lib/portable/tor_archives.py'
    spec = importlib.util.spec_from_file_location('tor_archives', source)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    archive = directory/manifest['archive']
    if archive.is_symlink() or not archive.is_file() or not 0 < archive.stat().st_size <= 512*1024**2:
        raise RuntimeError('The pinned Tor Browser archive is missing or invalid.')
    with archive.open('rb') as f:checksum = hashlib.file_digest(f,'sha256').hexdigest()
    if checksum != manifest['sha256']:raise RuntimeError('Pinned Tor Browser checksum mismatch.')
    module.verify(archive, Path(str(archive)+'.asc'), keyring)


def download(url, target, limit):
    # No live-system fetching: this helper runs only on the build workstation.
    with urllib.request.urlopen(url,timeout=60) as response, target.open('xb') as output:
        if response.url != url:raise RuntimeError('Unexpected Tor download redirect.')
        count = 0
        while block := response.read(1024**2):
            count += len(block)
            if count > limit:raise RuntimeError('Tor download exceeded its size limit.')
            output.write(block)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-directory',type=Path,help='Use an already downloaded, exact pinned archive/signature pair')
    args = parser.parse_args()
    if os.geteuid() == 0:raise RuntimeError('Prepare public build inputs as your normal user.')
    manifest = json.loads((ROOT/'config/tor-browser.json').read_text())
    if DESTINATION.exists():
        if json.loads((DESTINATION/'manifest.json').read_text()) == manifest:
            validate(DESTINATION,manifest);print('Verified bundled Tor Browser '+manifest['version']);return
        raise RuntimeError('A different Tor bundle already exists. Preserve it elsewhere before preparing a new version.')
    DESTINATION.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.tor-browser-',dir=DESTINATION.parent) as d:
        pending = Path(d)/'bundle';pending.mkdir()
        for name,limit in ((manifest['archive'],512*1024**2),(manifest['archive']+'.asc',1024**2)):
            if args.from_directory:
                source = args.from_directory/name
                if source.is_symlink() or not source.is_file() or source.stat().st_size > limit:
                    raise RuntimeError('Invalid public Tor input file.')
                shutil.copyfile(source,pending/name)
            else:download(manifest['source']+name,pending/name,limit)
        validate(pending,manifest)
        (pending/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        pending.rename(DESTINATION)
    print('Prepared signed Tor Browser '+manifest['version'])


if __name__ == '__main__':main()
