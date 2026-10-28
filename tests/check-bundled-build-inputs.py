#!/usr/bin/python3 -B
"""Validate complete build inputs using a verified public archive specimen."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import tempfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('build',ROOT/'tests/rebuild-release.py')
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
with tempfile.TemporaryDirectory(prefix='petalos-bundled-preflight-') as temporary:
    config=Path(temporary)/'config'
    shutil.copytree(ROOT/'config',config,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc','tor-browser'))
    archive=next((ROOT.parent/'provisioning/TorBrowser/verified-15.0.25').glob('*.tar.xz'))
    bundle=config/'includes.chroot/usr/local/share/portable/tor-browser';bundle.mkdir()
    shutil.copyfile(archive,bundle/archive.name)
    shutil.copyfile(str(archive)+'.asc',bundle/(archive.name+'.asc'))
    pin=json.loads((config/'tor-browser.json').read_text())
    pin.update(version='15.0.25',archive=archive.name,sha256=build.digest(archive))
    (config/'tor-browser.json').write_text(json.dumps(pin))
    (bundle/'manifest.json').write_text(json.dumps(pin))
    build.validate_inputs(config)
    print('PASS complete build-input preflight with verified cached public 15.0.25 specimen')
    signature=bundle/(archive.name+'.asc');previous=signature.read_bytes();signature.write_text('invalid')
    try:build.validate_inputs(config)
    except Exception as error:
        assert type(error).__name__=='ArchiveError'
    else:raise AssertionError('Invalid bundle signature was accepted')
    signature.write_bytes(previous)
    print('PASS invalid public signature fails before live-build')
    media=config/'includes.chroot/usr/share/petalos/test-media/hardware-test.webm'
    with media.open('r+b') as output:output.write(b'changed')
    try:build.validate_inputs(config)
    except RuntimeError as error:assert 'test media' in str(error)
    else:raise AssertionError('Changed hardware clip was accepted')
    print('PASS changed hardware-test media fails before live-build')
    print('Production 15.0.26 download/signature acceptance requires the normal build workstation network.')
