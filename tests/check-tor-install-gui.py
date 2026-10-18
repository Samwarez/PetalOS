#!/usr/bin/python3
"""Invisible installer dialogs with a mocked install backend; no disk writes."""
from pathlib import Path
import sys
import subprocess
from types import SimpleNamespace
from unittest.mock import patch
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk

project=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(project/'config/includes.chroot/usr/local/lib/portable'))
from tor_archives import ArchiveError
source=project/'config/includes.chroot/usr/local/bin/portable-tor-install'
scope={'__name__':'test'}
exec(compile(source.read_text(),str(source),'exec'),scope)
archive=next((project.parent/'provisioning/TorBrowser').glob('*.tar.xz'))
for scenario in ('cancel','valid','invalid'):
    messages=[];calls=[]
    def dialog_run(dialog):
        if isinstance(dialog,Gtk.FileChooserDialog):
            return Gtk.ResponseType.CANCEL if scenario=='cancel' else Gtk.ResponseType.OK
        messages.append(dialog.get_property('text'))
        return Gtk.ResponseType.OK
    def install(a,s):
        calls.append((a,s))
        if scenario=='invalid':raise ArchiveError('Signature verification failed.')
    scope['install']=install
    with patch.object(Gtk.Widget,'show_all',lambda _:None),patch.object(Gtk.Dialog,'run',dialog_run), \
         patch.object(Gtk.FileChooserDialog,'get_filename',lambda _:str(archive)), \
         patch('subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='/dev/mapper/portable_data\n')):
        result=scope['main']()
    assert result==(1 if scenario=='invalid' else 0)
    assert bool(calls)==(scenario!='cancel')
    assert bool(messages)==(scenario!='cancel')
    print('PASS: Tor installer graphical '+scenario)
