"""Validated, selective desktop persistence, separate from Private documents."""
from pathlib import Path, PurePosixPath
import tarfile

CHANNELS = ('xfce4-panel', 'xfce4-desktop', 'xsettings', 'xfwm4')

ROOTS=tuple('.config/xfce4/xfconf/xfce-perchannel-xml/'+name+'.xml'
            for name in CHANNELS)+(
    '.config/xfce4/panel','.config/gtk-3.0/settings.ini','.gtkrc-2.0',
    '.config/labwc/themerc-override')
LEGACY_ROOTS=('.config/xfce4/xfconf','.config/xfce4/panel','.config/gtk-3.0','.gtkrc-2.0',
              '.config/labwc/themerc-override')
MAX=64*1024**2
CRYSTAL='.config/crystal-dock/XFCE'
ROOTS=ROOTS+(CRYSTAL,)


def allowed(member, roots=ROOTS):
    name=str(PurePosixPath(member.name))
    if name.startswith(CRYSTAL+'/'):
        import re
        return member.isfile() and re.fullmatch(re.escape(CRYSTAL)+r'/(?:appearance|panel_[1-9][0-9]{0,2})\.conf',name) is not None
    if name==CRYSTAL or (member.isdir() and CRYSTAL.startswith(name+'/')):return True
    return any(name==root or (root in ('.config/xfce4/panel',) or roots==LEGACY_ROOTS) and name.startswith(root+'/') or
               (member.isdir() and root.startswith(name+'/')) for root in roots)


def validate_archive(source, *, legacy=False):
    import os
    assert os.fstat(source.fileno()).st_size<=MAX
    source.seek(0)
    with tarfile.open(fileobj=source,mode='r:') as archive:
        count=0;size=0
        for member in archive:
            count+=1;size+=member.size
            assert count<=4096 and size<=MAX
            path=PurePosixPath(member.name);name=str(path)
            assert not path.is_absolute() and '..' not in path.parts and (member.isfile() or member.isdir())
            assert allowed(member, LEGACY_ROOTS if legacy else ROOTS)
    source.seek(0)


def restore(source,home):
    validate_archive(source,legacy=True)
    with tarfile.open(fileobj=source,mode='r:') as archive:
        archive.extractall(home,members=[m for m in archive if allowed(m)],filter='data')
    migrate_touch_defaults(home)
    migrate_crystal_dock(home)


def migrate_crystal_dock(home):
    """Replace the legacy bottom dock once, retaining the XFCE top panel."""
    import xml.etree.ElementTree as ET
    path=Path(home)/'.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml'
    if not path.exists():return
    channel=ET.parse(path).getroot()
    assert channel.tag=='channel' and channel.get('name')=='xfce4-panel'
    marker=channel.find("property[@name='PetalOS']")
    if marker is not None and marker.find("property[@name='CrystalDockVersion']") is not None:return
    panels=channel.find("property[@name='panels']")
    if panels is not None:
        position=panels.find("property[@name='panel-2']/property[@name='position']")
        if position is not None and position.get('value','').startswith('p=10;'):
            removed={v.get('value') for v in panels.findall("property[@name='panel-2']/property[@name='plugin-ids']/value")}
            for child in list(panels):
                if (child.tag=='value' and child.get('value')=='2') or (child.tag=='property' and child.get('name')=='panel-2'):
                    panels.remove(child)
            retained={v.get('value') for v in panels.findall("property/property[@name='plugin-ids']/value")}
            plugins=channel.find("property[@name='plugins']")
            if plugins is not None:
                for child in list(plugins):
                    number=child.get('name','').removeprefix('plugin-')
                    if number in removed and number not in retained:plugins.remove(child)
    if marker is None:marker=ET.SubElement(channel,'property',name='PetalOS',type='empty')
    ET.SubElement(marker,'property',name='CrystalDockVersion',type='int',value='1')
    ET.ElementTree(channel).write(path,encoding='UTF-8',xml_declaration=True)


def migrate_touch_defaults(home):
    """One-time migration of old stock values; subsequent user choices win."""
    import configparser
    import xml.etree.ElementTree as ET
    home=Path(home)
    path=home/'.config/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml'
    if not path.exists():return
    channel=ET.parse(path).getroot()
    assert channel.tag=='channel' and channel.get('name')=='xsettings'
    petal=channel.find("property[@name='PetalOS']")
    if petal is not None and petal.find("property[@name='TouchDefaultsVersion']") is not None:return
    for name,old,new in (('DoubleClickDistance','5','20'),('DoubleClickTime','250','500')):
        prop=channel.find("property[@name='Net']/property[@name='"+name+"']")
        if prop is not None and prop.get('type')=='int' and prop.get('value')==old:prop.set('value',new)
    if petal is None:petal=ET.SubElement(channel,'property',name='PetalOS',type='empty')
    ET.SubElement(petal,'property',name='TouchDefaultsVersion',type='int',value='1')
    ET.ElementTree(channel).write(path,encoding='UTF-8',xml_declaration=True)
    gtk=home/'.config/gtk-3.0/settings.ini'
    if gtk.exists():
        settings=configparser.ConfigParser(interpolation=None);settings.optionxform=str;settings.read(gtk)
        if settings.has_section('Settings'):
            for name,old,new in (('gtk-double-click-distance','5','20'),('gtk-double-click-time','250','500')):
                if settings['Settings'].get(name)==old:settings['Settings'][name]=new
            with gtk.open('w') as output:settings.write(output)


def sanitize(destination):
    """One-time format migration: discard legacy file-chooser/other app state."""
    import os,tempfile
    destination=Path(destination)
    fd=os.open(destination,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as source:
        validate_archive(source,legacy=True)
        with tarfile.open(fileobj=source,mode='r:') as archive:
            if all(allowed(m) for m in archive):return
        source.seek(0)
        fd,name=tempfile.mkstemp(prefix='.desktop-sanitize-',dir=destination.parent)
        try:
            with os.fdopen(fd,'w+b') as output:
                with tarfile.open(fileobj=source,mode='r:') as old, tarfile.open(fileobj=output,mode='w:') as new:
                    for member in old:
                        if allowed(member):new.addfile(member,old.extractfile(member) if member.isfile() else None)
                validate_archive(output);output.flush();os.fsync(output.fileno())
            os.replace(name,destination)
            fd=os.open(destination.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:os.fsync(fd)
            finally:os.close(fd)
        finally:Path(name).unlink(missing_ok=True)


def channel_xml(channel, properties):
    """Serialize Xfconf's typed live values without adding unrelated channels."""
    import math
    import xml.etree.ElementTree as ET
    assert channel in CHANNELS and len(properties) <= 4096
    root = ET.Element('channel', name=channel, version='1.0')
    nodes = {'': root}
    types = {'s': 'string', 'b': 'bool', 'i': 'int', 'u': 'uint',
             'x': 'int64', 't': 'uint64', 'd': 'double'}

    def assign(node, value):
        while value.get_type_string() == 'v':
            value = value.get_variant()
        kind = value.get_type_string()
        if kind.startswith('a'):
            assert kind in ('av', 'as', 'ab', 'ai', 'au', 'ax', 'at', 'ad')
            assert value.n_children() <= 4096
            node.set('type', 'array')
            for i in range(value.n_children()):
                assign(ET.SubElement(node, 'value'), value.get_child_value(i))
        else:
            assert kind in types
            raw = value.unpack()
            if kind == 'd':
                assert math.isfinite(raw)
            node.set('type', types[kind])
            node.set('value', ('true' if raw else 'false') if kind == 'b' else str(raw))

    for path, value in sorted(properties.items()):
        assert path.startswith('/') and len(path) <= 4096
        parts = path[1:].split('/')
        assert all(part and part not in ('.', '..') for part in parts) and len(parts) <= 64
        parent = ''
        for part in parts:
            name = parent + '/' + part
            if name not in nodes:
                nodes[name] = ET.SubElement(nodes[parent], 'property', name=part, type='empty')
            parent = name
        assign(nodes[parent], value)
    data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    assert len(data) <= MAX
    return data


def live_xfconf():
    """Read the session daemon, not its delayed on-disk XML cache."""
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def call(method, parameters, reply):
        return bus.call_sync('org.xfce.Xfconf', '/org/xfce/Xfconf',
                             'org.xfce.Xfconf', method, parameters,
                             GLib.VariantType.new(reply), Gio.DBusCallFlags.NONE,
                             5000, None)

    channels = call('ListChannels', None, '(as)').unpack()[0]
    output = {}
    for channel in CHANNELS:
        if channel not in channels:
            continue
        result = call('GetAllProperties', GLib.Variant('(ss)', (channel, '')), '(a{sv})')
        values = result.get_child_value(0)
        properties = {}
        for i in range(values.n_children()):
            entry = values.get_child_value(i)
            properties[entry.get_child_value(0).get_string()] = entry.get_child_value(1)
        output['.config/xfce4/xfconf/xfce-perchannel-xml/' + channel + '.xml'] = channel_xml(channel, properties)
    assert output, 'No live desktop channels available.'
    return output


def save(home,destination, *, live=False):
    import io,os,tempfile
    home=Path(home);destination=Path(destination)
    assert not destination.is_symlink()
    snapshots = live_xfconf() if live else {}
    paths=[p for p in ROOTS if (home/p).exists() or p in snapshots]
    assert paths
    fd,name=tempfile.mkstemp(prefix='.desktop-settings-',dir=destination.parent)
    try:
        with os.fdopen(fd,'w+b') as output:
            with tarfile.open(fileobj=output,mode='w:',dereference=False) as archive:
                for p in paths:
                    if p in snapshots:
                        member=tarfile.TarInfo(p);member.size=len(snapshots[p]);member.mode=0o600
                        archive.addfile(member,io.BytesIO(snapshots[p]))
                    else:
                        archive.add(home/p,arcname=p,filter=(lambda member:member if allowed(member) else None) if p==CRYSTAL else None)
            validate_archive(output);output.flush();os.fsync(output.fileno())
            output.seek(0)
            with tarfile.open(fileobj=output,mode='r:') as archived:
                for path,data in snapshots.items():
                    assert archived.extractfile(path).read()==data
        os.replace(name,destination)
        fd=os.open(destination.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:Path(name).unlink(missing_ok=True)
