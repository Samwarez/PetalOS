#!/usr/bin/env python3
"""Selective desktop archive roundtrip and malicious-entry rejection."""
import importlib.util
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest.mock
import xml.etree.ElementTree as ET
sys.dont_write_bytecode=True
source=Path(__file__).resolve().parents[1]/'config/includes.chroot/usr/local/lib/portable/desktop_settings.py'
spec=importlib.util.spec_from_file_location('settings',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with tempfile.TemporaryDirectory(prefix='petalos-public-settings-') as work:
    base=Path(work);home=base/'home';home.mkdir();target=base/'restored';target.mkdir()
    directory=home/'.config/xfce4/panel';directory.mkdir(parents=True)
    (directory/'public-fixture.txt').write_text('public-settings-fixture')
    trash=home/'.local/share/Trash'
    (trash/'files').mkdir(parents=True);(trash/'info').mkdir()
    (trash/'files/desktop-settings.tar').write_bytes(b'public disposable trash canary')
    (trash/'info/desktop-settings.tar.trashinfo').write_text('[Trash Info]\nPath=/public-fixture\n')
    archive=base/'desktop-settings.tar';m.save(home,archive)
    with archive.open('rb') as f:m.restore(f,target)
    assert (target/'.config/xfce4/panel/public-fixture.txt').read_text()=='public-settings-fixture'
    assert not (target/'.local/share/Trash').exists()
    assert (trash/'files/desktop-settings.tar').read_bytes()==b'public disposable trash canary'
    print('PASS selective desktop settings roundtrip')
    print('PASS Trash contents and deletion metadata are not saved/restored; existing Trash is untouched')
    for name,kind in [('/etc/shadow',tarfile.REGTYPE),('../escape',tarfile.REGTYPE),('.config/other/item',tarfile.REGTYPE),('.config/xfce4/panel/link',tarfile.SYMTYPE),('.config/xfce4/panel/device',tarfile.CHRTYPE)]:
        with tarfile.open(archive,'w:') as f:
            entry=tarfile.TarInfo(name);entry.type=kind
            if kind==tarfile.REGTYPE:entry.size=1;f.addfile(entry,io.BytesIO(b'P'))
            else:entry.linkname='/etc/shadow';f.addfile(entry)
        with archive.open('rb') as f:
            try:m.validate_archive(f)
            except (AssertionError,tarfile.TarError):pass
            else:raise AssertionError('Unsafe entry accepted')
    print('PASS absolute, traversal, unrelated, symlink and device entries rejected')
    with tarfile.open(archive,'w:') as f:
        for name in ('.config/gtk-3.0/settings.ini','.config/gtk-3.0/gtkfilechooser.ini',
                     '.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml',
                     '.config/xfce4/xfconf/xfce-perchannel-xml/unapproved-app.xml'):
            entry=tarfile.TarInfo(name);entry.size=1;f.addfile(entry,io.BytesIO(b'P'))
    m.sanitize(archive)
    with archive.open('rb') as f:m.validate_archive(f)
    with tarfile.open(archive) as f:
        assert set(f.getnames())=={'.config/gtk-3.0/settings.ini',
            '.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml'}
    print('PASS legacy migration drops file-chooser and unrelated app state')

    # Simulate an unavailable live daemon and a failed durable write. Neither
    # may replace a previously good archive or leave a misleading success.
    before=archive.read_bytes()
    with unittest.mock.patch.object(m,'live_xfconf',side_effect=RuntimeError('fixture bus unavailable')):
        try:m.save(home,archive,live=True)
        except RuntimeError:pass
        else:raise AssertionError('Missing session bus accepted')
    assert archive.read_bytes()==before
    with unittest.mock.patch('os.fsync',side_effect=OSError('fixture write failure')):
        try:m.save(home,archive)
        except OSError:pass
        else:raise AssertionError('Failed durable write accepted')
    assert archive.read_bytes()==before and not list(base.glob('.desktop-settings-*'))
    print('PASS daemon/write failures preserve the prior archive and clean temporary output')

from gi.repository import GLib
values={'/Net/DoubleClickTime':GLib.Variant('i',333),
        '/public-bool':GLib.Variant('b',False),
        '/public-array':GLib.Variant('av',[GLib.Variant('u',1),GLib.Variant('s','a & b')]),
        '/public-double':GLib.Variant('d',0.25)}
xml=ET.fromstring(m.channel_xml('xsettings',values))
assert xml.find("./property[@name='Net']/property").attrib['value']=='333'
assert xml.find("./property[@name='public-bool']").attrib=={'name':'public-bool','type':'bool','value':'false'}
assert [x.attrib for x in xml.find("./property[@name='public-array']")]==[
    {'type':'uint','value':'1'},{'type':'string','value':'a & b'}]
for bad in ({'/unsafe/../name':GLib.Variant('s','x')},{'/nonfinite':GLib.Variant('d',float('nan'))},
            {'/wrongtype':GLib.Variant('a{ss}',{'x':'y'})}):
    try:m.channel_xml('xsettings',bad)
    except AssertionError:pass
    else:raise AssertionError('Invalid live setting accepted')
print('PASS typed live XML preserves arrays/booleans/nesting and rejects invalid values')
print('All selective desktop settings checks passed.')

with tempfile.TemporaryDirectory(prefix='petalos-touch-migration-') as work:
    home=Path(work);xml=home/'.config/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml';xml.parent.mkdir(parents=True)
    for distance,timing,expected_distance,expected_timing in (('5','250','20','500'),('30','333','30','333')):
        xml.write_text('<channel name="xsettings" version="1.0"><property name="Net" type="empty"><property name="DoubleClickDistance" type="int" value="'+distance+'"/><property name="DoubleClickTime" type="int" value="'+timing+'"/></property></channel>')
        m.migrate_touch_defaults(home)
        root=ET.parse(xml).getroot()
        assert root.find("./property/property[@name='DoubleClickDistance']").get('value')==expected_distance
        assert root.find("./property/property[@name='DoubleClickTime']").get('value')==expected_timing
        root.find("./property/property[@name='DoubleClickDistance']").set('value','5')
        ET.ElementTree(root).write(xml)
        m.migrate_touch_defaults(home)
        assert ET.parse(xml).getroot().find("./property/property[@name='DoubleClickDistance']").get('value')=='5'
print('PASS old stock touch defaults migrate once; custom timing/distance and subsequent user overrides survive')
