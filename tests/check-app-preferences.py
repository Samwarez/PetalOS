#!/usr/bin/env python3
"""Synthetic configuration fixtures; no real app profiles or credentials read."""
from pathlib import Path
import configparser
import importlib.util
import json
import struct
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('prefs',Path(__file__).resolve().parents[1]/
    'config/includes.chroot/usr/local/lib/portable/app_preferences.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
result=p.filtered('transmission',json.dumps({'speed-limit-down':1234,
    'speed-limit-down-enabled':True,'download-dir':'/private/example',
    'rpc-password':'public fixture','recent-files':['public fixture'],
    'downloaded-bytes':999999,'peer-limit-global':-1}).encode())
assert result=={'speed-limit-down':1234,'speed-limit-down-enabled':True}
assert p.filtered('amule',b'[eMule]\nMaxDownload=500\nMaxUpload=20\nNick=public fixture\nTotalDownloadedBytes=99\n')=={
    'eMule/MaxDownload':500,'eMule/MaxUpload':20}
amule_fixture=b'''[eMule]
Port=4662
UDPEnable=1
Reconnect=0
MinToTray=1
DownloadCapacity=1200
Nick=public fixture
YourHostname=public fixture
IncomingDir=/private/public-fixture
SmartIdState=7
TotalDownloadedBytes=999
Ed2kServersUrl=https://example.org/personal-query
[Proxy]
ProxyPassword=public fixture
[Obfuscation]
IsCryptLayerRequested=1
CryptoKadUDPKey=1234567
[UserEvents/DownloadCompleted]
CoreCommand=public fixture
'''
amule_clean=p.filtered('amule',amule_fixture)
assert amule_clean=={'eMule/Port':4662,'eMule/UDPEnable':True,
    'eMule/Reconnect':False,'eMule/MinToTray':True,'eMule/DownloadCapacity':1200,
    'Obfuscation/IsCryptLayerRequested':True}
assert p.filtered('amule',b'[eMule]\nPort=0\nUDPPort=999999\nMinToTray=not-a-bool\n')=={}
assert p.filtered('pan',b'<preferences><int name="cache-size-megs" value="32"/><string name="last-search" value="public fixture"/></preferences>')=={'cache-size-megs':32}
assert p.filtered('offline-quodlibet',b'[player]\nvolume=0.5\nrecent-file=public fixture\n')=={'player/volume':0.5}
try:p.filtered('pan',b'<!DOCTYPE preferences [<!ENTITY x "public fixture">]><preferences/>')
except AssertionError:pass
else:raise AssertionError('XML entity accepted')
tags=b'\x03\x01\x00\x90'+struct.pack('<I',123456789)+b'\x02\x01\x00\x01\x0e\x00public fixture'
database=b'\xe0'+struct.pack('<I',1)+struct.pack('<IHI',0x01020304,4661,2)+tags
assert p.endpoints(database)==[['1.2.3.4',4661]]
for bad in (database[:-1],database+b'junk',b'\xe0'+struct.pack('<I',999999)):
    try:p.endpoints(bad)
    except AssertionError:pass
    else:raise AssertionError('Invalid server list accepted')
try:p.validate('transmission',{'version':1,'preferences':{'rpc-password':'public fixture'},'servers':[]})
except AssertionError:pass
else:raise AssertionError('Unapproved preference accepted')
with tempfile.TemporaryDirectory() as d:
    root=Path(d);(root/'plain').write_text('public fixture')
    (root/'link').symlink_to(root/'plain')
    try:p.read_bounded(root,'link',{__import__('os').getuid()})
    except OSError:pass
    else:raise AssertionError('Symlink input accepted')
    target=root/'result';p.atomic(target,b'public fixture')
    assert target.read_bytes()==b'public fixture' and target.stat().st_mode&0o777==0o600
    state=root/'payload/transmission/state';state.mkdir(parents=True)
    (state/'settings.json').write_text('{"speed-limit-down":80}')
    saved=root/'saved';saved.mkdir()
    fake=SimpleNamespace(worker_alive=lambda r:False,read_record=lambda a:{'storage':'private'},
        private_available=lambda:False,PAYLOAD=root/'payload',PRIVATE=root/'private',ROLES={'transmission':942})
    with patch.dict('sys.modules',{'compartments':fake}), patch.object(p,'SPECS',{'transmission':p.SPECS['transmission']}), \
            patch.object(p,'store',lambda:saved),patch.object(p.os,'geteuid',lambda:0):
        try:p.save_all()
        except AssertionError:pass
        else:raise AssertionError('Closed Private preferences fell back to stale RAM settings')
    assert not list(saved.iterdir())
    # Fresh RAM launch receives only reviewed settings and tag-free servers.
    snapshot=root/'snapshot.json'
    record={'version':1,'preferences':amule_clean,'servers':p.endpoints(database)}
    snapshot.write_text(json.dumps(p.validate('amule',record)))
    ram=root/'ram';state=ram/'AppState/amule';state.mkdir(parents=True)
    fake=SimpleNamespace(ROLES={'amule':944})
    real_path=Path
    def mapped_path(value):
        if str(value)=='/run/petalos-preferences.json':return snapshot
        if str(value)=='/mnt/ram':return ram
        return real_path(value)
    with patch.dict('sys.modules',{'compartments':fake}),patch.object(p.os,'getuid',lambda:944), \
            patch.dict(p.os.environ,{'PORTABLE_STATE_ROOT':'/mnt/ram'}),patch.object(p,'Path',mapped_path):
        p.apply('amule')
    restored=(state/'amule.conf').read_bytes()
    assert p.filtered('amule',restored)==amule_clean
    # The whitelist reader also accepts words, but aMule's wxConfig reader
    # requires numeric booleans. A self-roundtrip alone misses this failure.
    wx_config=configparser.ConfigParser(interpolation=None)
    wx_config.read_string(restored.decode())
    assert wx_config.getint('eMule','UDPEnable')==1
    assert wx_config.getint('eMule','Reconnect')==0
    assert wx_config.getint('Obfuscation','IsCryptLayerRequested')==1
    assert b'Nick=' not in restored and b'CryptoKadUDPKey=' not in restored
    clean_server=b'\xe0'+struct.pack('<I',1)+struct.pack('<IHI',0x01020304,4661,0)
    assert (state/'server.met').read_bytes()==clean_server
    # An existing Private/RAM server file is not overwritten by snapshot restore.
    (state/'server.met').write_bytes(database)
    with patch.dict('sys.modules',{'compartments':fake}),patch.object(p.os,'getuid',lambda:944), \
            patch.dict(p.os.environ,{'PORTABLE_STATE_ROOT':'/mnt/ram'}),patch.object(p,'Path',mapped_path):
        p.apply('amule')
    assert (state/'server.met').read_bytes()==database
print('PASS: whitelist, history exclusion, clean server list, malformed-input rejection and safe file I/O')
