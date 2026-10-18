#!/usr/bin/python3 -I
"""QEMU-only public GTK fixture: real UID, restricted IPC and mapped window."""
import json
import os
from pathlib import Path
import secrets
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, '/usr/local/lib/portable')
from desktop_session import environment
from wayland_context import Connection

assert os.geteuid() == 0
assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
assert 'toram' in Path('/proc/cmdline').read_text().split()
assert 'petalos_wayland_probe (enforce)' in Path('/sys/kernel/security/apparmor/profiles').read_text().splitlines()
directory = Path(tempfile.mkdtemp(prefix='petalos-native-public-', dir='/run'))
control = None
lease = None
process = None
try:
    values = environment()
    control = Connection(Path(values['XDG_RUNTIME_DIR']) / values['WAYLAND_DISPLAY'])
    control.watch_windows()
    baseline = set(control.windows)
    listener = directory / 'wayland.sock'
    lease = control.create_listener(listener, 'native-probe', secrets.token_hex(16))
    os.chown(listener, 941, 941)
    runtime = directory / 'runtime'
    runtime.mkdir(mode=0o700)
    os.chown(runtime, 941, 941)
    fixture = directory / 'probe.py'
    fixture.write_text('''import json,os,socket,sys
sys.path.insert(0,'/usr/local/lib/portable')
from wayland_context import Connection
c=Connection('/run/user/941/wayland-0')
names=set(c.globals);c.close()
forbidden={'wp_security_context_manager_v1','zwlr_screencopy_manager_v1',
 'zwlr_export_dmabuf_manager_v1','zwlr_virtual_pointer_manager_v1',
 'zwp_virtual_keyboard_manager_v1','zwlr_data_control_manager_v1',
 'zwlr_layer_shell_v1','ext_session_lock_manager_v1',
 'zwlr_foreign_toplevel_manager_v1','ext_foreign_toplevel_list_v1'}
blocked=[]
for family in (socket.AF_INET,socket.AF_INET6):
 try:s=socket.socket(family);s.close();blocked.append(False)
 except OSError:blocked.append(True)
from pathlib import Path
status=Path('/proc/self/status').read_text().splitlines()
r={'real_uid':os.getuid()==941 and os.geteuid()==941,
 'no_groups':not os.getgroups(),'no_effective_caps':'CapEff:\\t0000000000000000' in status,
 'private_hidden':not Path('/mnt/private').exists(),
 'parent_runtime_hidden':not Path('/run/user/1000').exists(),
 'parent_home_hidden':not Path('/home/Petal').exists(),
 'x11_hidden':not Path('/tmp/.X11-unix').exists() and not os.environ.get('DISPLAY'),
 'direct_network_blocked':all(blocked),'privileged_protocols_hidden':not bool(names&forbidden),
 'native_window_protocols_available':{'wl_compositor','wl_shm','wl_seat','xdg_wm_base'}<=names}
print(json.dumps(r),flush=True)
assert all(r.values())
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
app=Gtk.Application(application_id='org.petalos.IsolationProbe')
def activate(app):
 w=Gtk.ApplicationWindow(application=app,title='PetalOS public isolation test')
 w.add(Gtk.Label(label='Native Wayland boundary test'))
 w.set_default_size(360,120);w.show_all()
 GLib.timeout_add_seconds(15,lambda:app.quit() or False)
app.connect('activate',activate)
app.run([])
''')
    fixture.chmod(0o644)
    command = ['bwrap', '--die-with-parent', '--ro-bind', '/', '/',
               '--unshare-net', '--unshare-pid', '--unshare-ipc', '--proc', '/proc',
               '--dev', '/dev', '--chmod', '1777', '/dev/shm',
               '--tmpfs', '/run', '--tmpfs', '/home', '--tmpfs', '/mnt',
               '--tmpfs', '/media', '--tmpfs', '/root', '--tmpfs', '/sys',
               '--perms', '1777', '--tmpfs', '/tmp',
               '--dir', '/run/user', '--bind', str(runtime), '/run/user/941',
               '--ro-bind', str(listener), '/run/user/941/wayland-0',
               '--ro-bind', str(fixture), '/run/probe.py', '--clearenv',
               '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'HOME', '/tmp',
               '--setenv', 'XDG_RUNTIME_DIR', '/run/user/941',
               '--setenv', 'WAYLAND_DISPLAY', 'wayland-0', '--setenv', 'GDK_BACKEND', 'wayland',
               '--setenv', 'GTK_USE_PORTAL', '0',
               '--setenv', 'LC_ALL', 'C.UTF-8', '--setenv', 'LIBGL_ALWAYS_SOFTWARE', '1',
               '--', '/usr/bin/setpriv', '--reuid', '941', '--regid', '941', '--clear-groups',
               '--inh-caps=-all', '--bounding-set=-all', '--ambient-caps=-all', '--no-new-privs',
               '--', '/usr/bin/dbus-run-session', '--', '/usr/bin/aa-exec',
               '-p', 'petalos_wayland_probe', '--', '/usr/bin/python3', '/run/probe.py']
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    mapped = False
    for _ in range(100):
        control.roundtrip()
        # GTK3 uses this fixture's program name for Wayland app_id even with
        # a separately registered Gtk.Application ID.
        mapped = any(handle not in baseline and
                     (app_id == 'probe.py' or re.fullmatch(r'org\.petalos\.IsolationProbe(?:_[0-9]+_[0-9]+)?', app_id))
                     for handle, app_id in control.windows.items())
        if mapped or process.poll() is not None:
            break
        time.sleep(.1)
    output, errors = process.communicate(timeout=20)
    assert len(output) <= 4096
    if not output:
        # This fixture sees only public files and prints no credentials/data.
        print(json.dumps({'fixture_exit': process.returncode,
                          'public_fixture_error': errors[:2048].decode(errors='replace')}))
        raise RuntimeError('The public fixture returned no result.')
    try:
        # Private D-Bus accessibility services may print their public startup
        # banner after the fixture's first, flushed JSON result.
        report = json.loads(output.splitlines()[0])
    except json.JSONDecodeError:
        print(json.dumps({'public_fixture_output': output[:2048].decode(errors='replace'),
                          'public_fixture_error': errors[:2048].decode(errors='replace')}))
        raise
    report['native_window_mapped'] = mapped
    if not mapped:
        # Connection discards window titles and accepts only bounded app IDs.
        print(json.dumps({'observed_public_app_ids': sorted(set(control.windows.values()))}))
    report['fixture_exit_success'] = process.returncode == 0
    print(json.dumps(report, sort_keys=True))
    assert all(report.values())
finally:
    if lease is not None:
        os.close(lease)
    if control:
        control.close()
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill();process.wait()
    shutil.rmtree(directory)
