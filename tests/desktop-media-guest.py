#!/usr/bin/python3 -B
"""Only fresh virtual USB/output disks; no personal data or network."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

FIXTURE = Path('/tmp/desktop-media-fixture')
# This is a running disposable guest, not an offline image customization.
# systemd tools otherwise ignore requests merely because its OS is chrooted.
os.environ['SYSTEMD_OFFLINE']='0'
os.environ['SYSTEMD_IGNORE_CHROOT']='1'
checks = {}
def check(name, value):
    assert value, name
    checks[name] = True;print('SPLIT_PASS '+name,flush=True)
def run(command, **kwargs):
    result = subprocess.run(command,capture_output=True,text=True,timeout=30,**kwargs)
    if Path(command[0]).name=='setpriv':print('USER_PROBE_LOG '+result.stderr[-5000:],flush=True)
    if result.returncode:
        print('FIXTURE_TOOL '+Path(command[0]).name+': '+result.stderr[-4000:],flush=True)
        result.check_returncode()
    return result.stdout


assert os.geteuid() == 0
check('only_disposable_usb',Path('/sys/class/block/sda/device').resolve().name.startswith('0:') or
      'usb' in str(Path('/sys/class/block/sda/device').resolve()))
properties = run(['udevadm','info','-q','property','-n','/dev/sda'])
check('usb_serial_is_fixture','PETALOS_GUI_USB_TEST' in properties)
check('fresh_usb_partition_ready',Path('/dev/sda1').exists())
Path('/run/dbus').mkdir(exist_ok=True)
Path('/run/dbus').chmod(0o755)
Path('/run/udev').chmod(0o755)
Path('/run/user').mkdir(exist_ok=True);Path('/run/user').chmod(0o755)
runtime=Path('/run/user/1000');runtime.mkdir(parents=True,exist_ok=True);os.chown(runtime,1000,1000);runtime.chmod(0o700)
Path('/home/Petal').mkdir(parents=True,exist_ok=True);os.chown('/home/Petal',1000,1000)
import pwd
try:pwd.getpwuid(1000)
except KeyError:run(['useradd','--uid','1000','--no-create-home','--home-dir','/home/Petal','Petal'])
run(['dbus-daemon','--system','--fork','--nopidfile'])
rule=Path('/etc/udev/rules.d/99-portable-storage.rules');reviewed_rule=rule.read_text()
fixture_rule=Path('/etc/udev/rules.d/98-petal-usb-test.rules')
fixture_rule.write_text('SUBSYSTEM=="block", KERNEL=="sda1", ENV{ID_BUS}:="ata"\n')
fixture_rule.chmod(0o644)
rule.write_text('SUBSYSTEM!="block", GOTO="test_old_end"\nENV{UDISKS_IGNORE}="1"\n'
    'ENV{ID_BUS}=="usb", ENV{ID_FS_USAGE}=="filesystem", ENV{ID_FS_LABEL}!="PORT_BOOT", ENV{UDISKS_IGNORE}="0", ENV{UDISKS_AUTO}="0"\n'
    'LABEL="test_old_end"\n')
preview=subprocess.run(['udevadm','test','--action=change','/sys/class/block/sda1'],capture_output=True,text=True)
print('FOREGROUND_UDEV '+json.dumps([line for line in preview.stdout.splitlines() if line.startswith(('ID_BUS=','UDISKS_'))]),flush=True)
run(['/usr/lib/systemd/systemd-udevd','--daemon'])
run(['udevadm','control','--reload-rules'])
run(['udevadm','trigger','--subsystem-match=block','--action=change','--settle'])
run(['udevadm','settle','--timeout=15'])
before=run(['udevadm','info','-q','property','-n','/dev/sda1'])
print('OLD_USB_PROPERTIES '+json.dumps([s for s in before.splitlines() if s.startswith(('ID_BUS=','ID_FS_','UDISKS_'))]),flush=True)
check('legacy_bus_rule_reproduces_hidden_ata_usb_bridge','ID_BUS=ata\n' in before and 'UDISKS_IGNORE=1\n' in before)
rule.write_text(reviewed_rule)
run(['udevadm','control','--reload-rules'])
run(['udevadm','trigger','--subsystem-match=block','--action=change'])
run(['udevadm','settle','--timeout=15'])
properties = run(['udevadm','info','-q','property','-n','/dev/sda1'])
print('USB_PROPERTIES '+json.dumps([s for s in properties.splitlines() if s.startswith(('ID_BUS=','ID_FS_','UDISKS_'))]),flush=True)
check('usb_ata_bridge_is_visible_without_automount',all(p+'\n' in properties for p in
      ('ID_BUS=ata','ID_FS_TYPE=exfat','UDISKS_IGNORE=0','UDISKS_AUTO=0')))
internal=run(['udevadm','info','-q','property','-n','/dev/vda'])
check('internal_filesystem_stays_hidden','UDISKS_IGNORE=1\n' in internal)
check('no_automatic_mount',subprocess.run(['findmnt','-n','--source','/dev/sda1'],capture_output=True).returncode==1)
run(['udisksctl','info','-b','/dev/sda1'])
probe=FIXTURE/'volume-probe.py'
probe.write_text('''import gi,json,time
from gi.repository import Gio,GLib
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
try:
 result=bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','StartServiceByName',GLib.Variant('(su)',('org.gtk.vfs.UDisks2VolumeMonitor',0)),None,Gio.DBusCallFlags.NONE,15000,None)
 print('MONITOR_ACTIVATED '+str(result.unpack()),flush=True)
except GLib.Error as e:print('MONITOR_ACTIVATION_ERROR '+str(e),flush=True)
v=Gio.VolumeMonitor.get()
until=time.monotonic()+6
while time.monotonic()<until:
 while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
 time.sleep(.02)
print(json.dumps([{'device':x.get_identifier('unix-device'),'name':x.get_name(),'automount':x.should_automount()} for x in v.get_volumes()]))
''')
probe.chmod(0o644)
output=run(['setpriv','--reuid=1000','--regid=1000','--clear-groups','dbus-run-session','--',
            'env','HOME=/home/Petal','XDG_RUNTIME_DIR=/run/user/1000','/usr/bin/python3',str(probe)])
print('GUI_VOLUMES '+output.strip(),flush=True)
volumes=json.loads(output.splitlines()[-1]);selected=[v for v in volumes if v['device']=='/dev/sda1']
print('USB_VISIBILITY '+str(selected),flush=True)
check('usb_visible_in_native_volume_monitor',len(selected)==1)
check('usb_manual_mount_only',not selected[0]['automount'])
run(['udisksctl','mount','-b','/dev/sda1','-o','ro'])
check('manual_mount_works',subprocess.run(['findmnt','-n','--source','/dev/sda1'],capture_output=True).returncode==0)
run(['udisksctl','unmount','-b','/dev/sda1'])
if (FIXTURE/'usb-only').exists():pass
elif (FIXTURE/'generate-test-media.py').exists():
    target=Path('/mnt/fixture-output');target.mkdir()
    run(['mount','/dev/vda',str(target)])
    generator=subprocess.run(['/usr/bin/python3',str(FIXTURE/'generate-test-media.py'),str(target)],capture_output=True,text=True,timeout=240)
    print('MEDIA_GENERATOR '+generator.stdout[-4000:],flush=True)
    if generator.returncode:print(generator.stderr[-4000:],flush=True)
    check('original_test_video_and_stereo_audio_generated',generator.returncode==0)
    decoded=subprocess.run(['/usr/bin/python3',str(FIXTURE/'check-test-media.py'),str(target/'hardware-test.webm')],
                           capture_output=True,text=True,timeout=240)
    print('MEDIA_DECODE '+decoded.stdout[-4000:],flush=True)
    if decoded.returncode:print(decoded.stderr[-4000:],flush=True)
    check('full_video_and_distinct_stereo_cues_decoded',decoded.returncode==0)
    run(['umount',str(target)])
else:
    clip=Path('/usr/share/petalos/test-media/hardware-test.webm')
    decoded=subprocess.run(['/usr/bin/python3',str(FIXTURE/'check-test-media.py'),str(clip)],
                           capture_output=True,text=True,timeout=180)
    print('MEDIA_DECODE '+decoded.stdout[-4000:],flush=True)
    if decoded.returncode:print(decoded.stderr[-4000:],flush=True)
    check('bundled_video_and_distinct_stereo_cues_decoded',decoded.returncode==0)
    sys.path.insert(0,'/usr/local/lib/portable')
    from offline_files import delegate
    rewritten,binds,fds=delegate([str(clip)],'parole')
    try:
        check('media_uses_existing_readonly_file_delegation',rewritten==['/run/petalos-opened/item-1.webm'] and
              len(binds)==1 and binds[0][2] is False and os.read(fds[0],4)==clip.read_bytes()[:4])
    finally:
        for fd in fds:os.close(fd)
    import tor_archives,compartments
    archive=tor_archives.current()
    check('signed_tor_available_without_system_archive',archive.parent==tor_archives.BUNDLED)
    extracted=compartments.distribution()
    executable=extracted/'Browser/TorBrowser/Tor/tor'
    check('signed_bundled_tor_extracts_into_ram',executable.is_file())
    inside='/tmp/tor-browser/Browser/TorBrowser/Tor/tor'
    version=run(['bwrap','--die-with-parent','--ro-bind','/','/','--unshare-pid','--unshare-ipc','--unshare-net',
                 '--proc','/proc','--dev','/dev','--perms','1777','--tmpfs','/tmp',
                 '--ro-bind',str(extracted),'/tmp/tor-browser','--clearenv',
                 '--setenv','LD_LIBRARY_PATH',str(Path(inside).parent),'--',
                 '/usr/bin/setpriv','--reuid=940','--regid=940','--clear-groups',
                 '--inh-caps=-all','--bounding-set=-all','--ambient-caps=-all','--no-new-privs','--',inside,'--version'])
    check('bundled_tor_binary_runs_in_readonly_unprivileged_namespace','Tor version ' in version)
print('SPLIT_RESULT '+json.dumps({'passed':True,'stage':'desktop-media','checks':checks}),flush=True)
