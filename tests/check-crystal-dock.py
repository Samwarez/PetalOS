#!/usr/bin/python3
"""Selective Crystal preferences and non-destructive XFCE layout migration."""
from pathlib import Path
import importlib.util,io,tarfile,tempfile,xml.etree.ElementTree as ET

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('settings',root/'config/includes.chroot/usr/local/lib/portable/desktop_settings.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
with tempfile.TemporaryDirectory(prefix='petalos-public-crystal-settings-') as temporary:
    base=Path(temporary);home=base/'home';restored=base/'restored';restored.mkdir();cfg=home/s.CRYSTAL;cfg.mkdir(parents=True)
    for name in ('appearance.conf','panel_1.conf','panel_2.conf'):(cfg/name).write_text('[General]\npublicFixture=true\n')
    (cfg/'activity.log').write_text('public excluded canary');(cfg/'unrelated.txt').write_text('public excluded canary')
    archive=base/'desktop-settings.tar';s.save(home,archive)
    with archive.open('rb') as source:s.restore(source,restored)
    assert sorted(p.name for p in (restored/s.CRYSTAL).iterdir())==['appearance.conf','panel_1.conf','panel_2.conf']
    for name in ('panel_0.conf','panel_1.conf/escape','../other.conf','history.log'):
        member=tarfile.TarInfo(s.CRYSTAL+'/'+name);assert not s.allowed(member)
    print('PASS Crystal appearance/panel roundtrip excludes unrelated files and rejects unsafe names')
    xml=home/'.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml';xml.parent.mkdir(parents=True)
    def original(position):
        return '<channel name="xfce4-panel"><property name="panels" type="array"><value type="int" value="1"/><value type="int" value="2"/><property name="panel-1"><property name="plugin-ids"><value value="13"/></property></property><property name="panel-2"><property name="position" value="'+position+'"/><property name="plugin-ids"><value value="13"/><value value="18"/></property></property></property><property name="plugins"><property name="plugin-13" value="launcher"/><property name="plugin-18" value="launcher"/></property></channel>'
    xml.write_text(original('p=10;x=0;y=0'));s.migrate_crystal_dock(home);channel=ET.parse(xml).getroot()
    assert channel.find("property[@name='panels']/property[@name='panel-1']") is not None
    assert channel.find("property[@name='panels']/property[@name='panel-2']") is None
    assert channel.find("property[@name='plugins']/property[@name='plugin-13']") is not None
    assert channel.find("property[@name='plugins']/property[@name='plugin-18']") is None
    before=xml.read_bytes();s.migrate_crystal_dock(home);assert xml.read_bytes()==before
    xml.write_text(original('p=6;x=0;y=0'));s.migrate_crystal_dock(home)
    assert ET.parse(xml).getroot().find("property[@name='panels']/property[@name='panel-2']") is not None
    print('PASS stock bottom dock migrates once; top/custom layouts and shared launcher records survive')

defaults=ET.parse(root/'config/includes.chroot/etc/skel/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml').getroot()
assert [p.get('value') for p in defaults.findall("property[@name='panels']/value")]==['1']
assert (root/'config/includes.chroot/etc/xdg/autostart/portable-crystal-dock.desktop').is_file()
print('PASS fresh defaults retain the top status panel and start Crystal Dock separately')
