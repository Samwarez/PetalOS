#!/usr/bin/python3
"""Native Thunar/GVFS workflow in an explicitly isolated RAM builder only.

The helper adapter bypasses production volume/boot discovery for this fake
Private mount. Actual copying is the maintained backend; this is not a LUKS,
AppArmor, Wayland or physical-hardware acceptance test.
"""
from pathlib import Path
import importlib.util
import json
import os
import subprocess
import sys
import time
from types import SimpleNamespace
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gio,GLib,Gtk,Gdk

assert os.getuid()==1000
mapping=Path('/proc/self/uid_map').read_text().split()
assert len(mapping)==3 and mapping[0]=='1000' and mapping[2]=='1'
assert Path('/build/volatile-trash-fixture-only').read_text()=='isolated disposable RAM builder\n'
home=Path(os.environ['HOME']);home.mkdir(mode=0o700,exist_ok=False)
source=Path('/mnt/private');assert (source/'fixture-scope').read_text()=='public disposable source only\n'
module=Path('/build/fixture-module');assert (module/'volatile_trash.py').is_file()
helper=Path('/usr/local/bin/portable-trash')
helper.write_text('''#!/usr/bin/python3 -I
import os,sys
from pathlib import Path
sys.path.insert(0,'/build/fixture-module')
import volatile_trash as m
assert len(sys.argv)==3 and sys.argv[1]=='--'
p=Path(sys.argv[2]);assert p.parent.resolve().is_relative_to(Path('/mnt/private'))
fd=os.open(p.parent,m.DIR)
try:
    (Path(os.environ['HOME'])/'helper-called').touch()
    with m.trash_directory(Path(os.environ['HOME'])) as target:
        limit=1 if (Path(os.environ['HOME'])/'force-limit').exists() else 16*1024**2
        m.move_at(fd,p.name,p,target,limit)
except m.TrashCapacityError:
    raise SystemExit(2)
except Exception as error:
    import traceback
    (Path(os.environ['HOME'])/'helper-error').write_text(traceback.format_exc())
    raise
finally:os.close(fd)
''');helper.chmod(0o755)

checks={}
Gtk.init([])
settings=Gtk.Settings.get_default()
checks['actual_GTK_distance_20']=settings.get_property('gtk-double-click-distance')==20
checks['actual_GTK_time_500']=settings.get_property('gtk-double-click-time')==500
for prop,value in (('DoubleClickDistance','20'),('DoubleClickTime','500')):
    result=subprocess.run(['xfconf-query','-c','xsettings','-p','/Net/'+prop],capture_output=True,text=True,timeout=10)
    checks['actual_Xfconf_'+prop]=result.returncode==0 and result.stdout.strip()==value

legacy=source/'.Trash-1000';(legacy/'files').mkdir(parents=True);(legacy/'info').mkdir()
(legacy/'files/desktop-settings.tar').write_bytes(b'public legacy fixture')
(legacy/'info/desktop-settings.tar.trashinfo').write_text('[Trash Info]\nPath=old-settings\nDeletionDate=2020-01-01T00:00:00\n')
item=source/'file';item.write_bytes(b'public native Thunar fixture')
checks['GIO_Private_can_delete']=Gio.File.new_for_path(str(item)).query_info('access::*',Gio.FileQueryInfoFlags.NONE,None).get_attribute_boolean('access::can-delete')
try:Gio.File.new_for_path(str(item)).trash(None)
except GLib.Error:checks['default_GIO_Private_trash_blocked']=item.exists()
else:checks['default_GIO_Private_trash_blocked']=False

def entries():
    trash=Gio.File.new_for_uri('trash:///')
    enumerator=trash.enumerate_children('standard::name,trash::orig-path',Gio.FileQueryInfoFlags.NONE,None)
    result=[]
    while info:=enumerator.next_file(None):result.append((info.get_name(),info.get_attribute_byte_string('trash::orig-path')))
    enumerator.close(None)
    return result

checks['legacy_Private_Trash_not_listed']=entries()==[]
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
def call(interface,method,parameters):
    return bus.call_sync('org.xfce.Thunar','/org/xfce/FileManager',interface,method,
                         parameters,None,Gio.DBusCallFlags.NONE,10000,None)
process=subprocess.Popen(['/out/Thunar','--daemon'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        result=bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','NameHasOwner',
                            GLib.Variant('(s)',('org.xfce.Thunar',)),None,Gio.DBusCallFlags.NONE,3000,None)
        if result.unpack()[0]:break
        assert process.poll() is None
        time.sleep(.1)
    else:raise RuntimeError('Native Thunar did not register.')
    call('org.xfce.Trash','MoveToTrash',GLib.Variant('(asss)',([str(item)],'','')))
    deadline=time.monotonic()+15
    while item.exists() and time.monotonic()<deadline:time.sleep(.1)
    copies=list((home/'.local/share/Trash/files').glob('petalos-private-*'))
    checks['Thunar_normal_trash_action_completed']=not item.exists() and len(copies)==1
    checks['Thunar_RAM_copy_matches']=len(copies)==1 and copies[0].read_bytes()==b'public native Thunar fixture'
    checks['native_copy_helper_invoked']=(home/'helper-called').exists()
    if (home/'helper-error').exists():print('PUBLIC FIXTURE ERROR:',(home/'helper-error').read_text())
    visible=entries()
    checks['actual_GVFS_lists_RAM_copy']=len(visible)==1 and visible[0][1]=='/mnt/private/file'
    if len(visible)==1:
        Gio.File.new_for_uri('trash:///'+visible[0][0]).move(Gio.File.new_for_path(str(item)),Gio.FileCopyFlags.NOFOLLOW_SYMLINKS,None,None,None)
        checks['actual_GVFS_restore_across_filesystems']=item.read_bytes()==b'public native Thunar fixture' and entries()==[]
    ram_item=home/'RAM-file';ram_item.write_bytes(b'public ordinary RAM fixture')
    call('org.xfce.Trash','MoveToTrash',GLib.Variant('(asss)',([str(ram_item)],'','')))
    deadline=time.monotonic()+15
    while ram_item.exists() and time.monotonic()<deadline:time.sleep(.1)
    visible=entries()
    checks['ordinary_RAM_Trash_still_works']=not ram_item.exists() and len(visible)==1
    if len(visible)==1:
        Gio.File.new_for_uri('trash:///'+visible[0][0]).move(Gio.File.new_for_path(str(ram_item)),Gio.FileCopyFlags.NOFOLLOW_SYMLINKS,None,None,None)
        checks['ordinary_RAM_restore_still_works']=ram_item.read_bytes()==b'public ordinary RAM fixture'
    folder=source/'folder';(folder/'sub').mkdir(parents=True);(folder/'sub/data').write_bytes(b'public directory workflow')
    call('org.xfce.Trash','MoveToTrash',GLib.Variant('(asss)',([str(folder)],'','')))
    deadline=time.monotonic()+15
    while folder.exists() and time.monotonic()<deadline:time.sleep(.1)
    visible=entries()
    checks['Private_directory_trash_completed']=not folder.exists() and len(visible)==1
    if len(visible)==1:
        restored=source/'restored';restored.mkdir()
        call('org.xfce.FileManager','MoveInto',GLib.Variant('(sassss)',('/mnt/private',['trash:///'+visible[0][0]],str(restored),'','')))
        deadline=time.monotonic()+15
        while not (restored/'folder/sub/data').exists() and time.monotonic()<deadline:time.sleep(.1)
        checks['Thunar_directory_restore_cross_filesystems']=(restored/'folder/sub/data').is_file() and (restored/'folder/sub/data').read_bytes()==b'public directory workflow'
        if not checks['Thunar_directory_restore_cross_filesystems']:
            print('PUBLIC FIXTURE RESTORED PATHS:',[str(p.relative_to(restored)) for p in restored.rglob('*')])
            window=Gdk.get_default_root_window()
            Gdk.pixbuf_get_from_window(window,0,0,window.get_width(),window.get_height()).savev('/build/gui-errors.png','png',[],[])
    checks['legacy_archive_untouched']=(legacy/'files/desktop-settings.tar').read_bytes()==b'public legacy fixture'
    (home/'force-limit').touch()
    result=subprocess.run(['/build/capacity-test'],capture_output=True,timeout=10)
    checks['native_RAM_limit_reports_NO_SPACE_and_preserves_original']=result.returncode==0 and item.read_bytes()==b'public native Thunar fixture'
finally:
    process.terminate()
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:process.kill();process.wait()

# Actual pidfd/signalling inside this PID namespace only. No storage/mount,
# password, role-record, or host-process operation is performed by the fixture.
spec=importlib.util.spec_from_file_location('storage_fixture',module/'private_storage.py')
storage=importlib.util.module_from_spec(spec);spec.loader.exec_module(storage)
storage.DESKTOP_TRASH=home/'.local/share/Trash'
sys.modules['compartments']=SimpleNamespace(ROLES={})
held=storage.DESKTOP_TRASH/'files/reader-fixture';held.write_bytes(b'public deleted RAM fixture')
reader=subprocess.Popen(['/usr/bin/python3','-I','-c',
    'import sys,time;f=open(sys.argv[1],"rb");print("ready",flush=True);time.sleep(30)',str(held)],stdout=subprocess.PIPE)
try:
    assert reader.stdout.readline()==b'ready\n'
    held.unlink()
    storage.kill_private_users(None)
    checks['deleted_RAM_Trash_reader_terminated']=reader.wait(timeout=5)==-9
finally:
    if reader.poll() is None:reader.kill();reader.wait()
print(json.dumps(checks,sort_keys=True))
assert all(checks.values())
