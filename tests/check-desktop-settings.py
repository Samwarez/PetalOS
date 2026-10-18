#!/usr/bin/env python3
"""Selective desktop archive roundtrip and malicious-entry rejection."""
import importlib.util
import io
from pathlib import Path
import sys
import tarfile
import tempfile
sys.dont_write_bytecode=True
source=Path(__file__).resolve().parents[1]/'config/includes.chroot/usr/local/lib/portable/desktop_settings.py'
spec=importlib.util.spec_from_file_location('settings',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with tempfile.TemporaryDirectory(prefix='petalos-public-settings-') as work:
    base=Path(work);home=base/'home';home.mkdir();target=base/'restored';target.mkdir()
    directory=home/'.config/xfce4/panel';directory.mkdir(parents=True)
    (directory/'public-fixture.txt').write_text('public-settings-fixture')
    archive=base/'desktop-settings.tar';m.save(home,archive)
    with archive.open('rb') as f:m.restore(f,target)
    assert (target/'.config/xfce4/panel/public-fixture.txt').read_text()=='public-settings-fixture'
    print('PASS selective desktop settings roundtrip')
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
print('All selective desktop settings checks passed.')
