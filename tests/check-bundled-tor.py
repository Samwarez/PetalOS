#!/usr/bin/python3 -B
"""Real public signature checks for OS-bundled Tor selection and failure cases."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import tempfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('tor_archives',ROOT/'config/includes.chroot/usr/local/lib/portable/tor_archives.py')
archives=importlib.util.module_from_spec(spec);spec.loader.exec_module(archives)
keyring=ROOT/'config/includes.chroot/usr/local/share/portable/tor-browser-developers.keyring'
cached=ROOT.parent/'provisioning/TorBrowser/verified-15.0.25'
source=next(cached.glob('tor-browser-linux-x86_64-*.tar.xz'))
real_verify=archives.verify
archives.verify=lambda a,s:real_verify(a,s,keyring)
checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name);print('PASS: '+name)
def rejected(name,call):
    try:call()
    except archives.ArchiveError:check(name,True)
    else:raise AssertionError(name)
with tempfile.TemporaryDirectory(prefix='petalos-bundled-tor-') as temporary:
    root=Path(temporary);bundle=root/'bundle';bundle.mkdir();legacy=root/'missing-system'
    archive=bundle/source.name;shutil.copyfile(source,archive)
    signature=Path(str(archive)+'.asc');signature.write_bytes(Path(str(source)+'.asc').read_bytes())
    manifest={'archive':archive.name,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
    marker=bundle/'manifest.json';marker.write_text(json.dumps(manifest))
    check('signed bundled browser works without SYSTEM archive',archives.current(legacy,bundle)==archive)
    legacy.mkdir();(legacy/'current-archive.json').write_text('invalid old selection')
    check('OS bundle takes precedence over old SYSTEM selection',archives.current(legacy,bundle)==archive)
    signature.write_text('invalid signature')
    rejected('bad bundled signature refuses startup',lambda:archives.current(legacy,bundle))
    signature.write_bytes(Path(str(source)+'.asc').read_bytes())
    with archive.open('r+b') as stream:stream.write(b'bad')
    rejected('modified bundled bytes refuse startup',lambda:archives.current(legacy,bundle))
    marker.write_text(json.dumps({'archive':'../outside','sha256':manifest['sha256']}))
    rejected('bundled manifest cannot escape its directory',lambda:archives.current(legacy,bundle))
    marker.unlink()
    rejected('incomplete bundle never falls back to SYSTEM',lambda:archives.current(legacy,bundle))
    shutil.rmtree(bundle);(legacy/'current-archive.json').unlink()
    rejected('legacy empty archive folder gives controlled error',lambda:archives.current(legacy,bundle))
    print('Verified '+str(len(checks))+' bundle checks with cached signed '+source.name+'; production 15.0.26 payload preparation remains separate.')
