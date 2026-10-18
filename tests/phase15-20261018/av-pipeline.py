#!/usr/bin/python3 -I
"""Synthetic 1080p native Wayland video + silent audio in the Parole role.

Uses the already-running Parole role's playback-only Pulse bridge, not a
microphone or user media. A distinct restricted display listener is temporary.
"""
from pathlib import Path
import json
import os
import secrets
import subprocess
import sys
import time

sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
from desktop_session import environment
from wayland_context import Connection

assert os.geteuid() == 0
assert c.worker_alive(c.read_record('offline-parole'))
values = environment()
control = Connection(Path(values['XDG_RUNTIME_DIR']) / values['WAYLAND_DISPLAY'])
path = Path('/run/petalos-phase15') / ('av-' + secrets.token_hex(8) + '.sock')
lease = process = None
probe = '''import gi,json,os,socket,time
gi.require_version('Gtk','3.0');gi.require_version('Gst','1.0')
from gi.repository import GLib
GLib.set_prgname('petalos-av-fixture')
from gi.repository import Gtk,Gst,GLib,Gio
Gst.init(None)
app=Gtk.Application(application_id='org.petalos.AVFixture',flags=Gio.ApplicationFlags.NON_UNIQUE)
app.register(None)
window=Gtk.ApplicationWindow(application=app);window.set_title('PetalOS synthetic A/V load test');window.set_default_size(960,540)
pipeline=Gst.parse_launch('videotestsrc num-buffers=600 pattern=smpte ! video/x-raw,width=1920,height=1080,framerate=30/1 ! videoconvert ! queue ! gtksink name=video sync=true audiotestsrc wave=silence samplesperbuffer=480 num-buffers=2000 ! audio/x-raw,format=S16LE,rate=48000,channels=2 ! pulsesink sync=true')
sink=pipeline.get_by_name('video');window.add(sink.get_property('widget'));window.show_all()
began=time.monotonic();done=False;positions=[];result={}
def tick():
 global done
 message=pipeline.get_bus().pop_filtered(Gst.MessageType.EOS|Gst.MessageType.ERROR)
 ok,pos=pipeline.query_position(Gst.Format.TIME)
 if ok:positions.append(round(pos/Gst.SECOND,3))
 if message is not None or time.monotonic()-began>30:
  stats=sink.get_property('stats')
  result.update(completed=message is not None and message.type==Gst.MessageType.EOS,
   elapsed=round(time.monotonic()-began,3),positions=positions,
   rendered=stats.get_value('rendered'),dropped=stats.get_value('dropped'),
   clock=pipeline.get_clock().get_name() if pipeline.get_clock() else None,
   real_role_uid=os.getuid()==955)
  done=True;Gtk.main_quit();return False
 return True
try:
 pipeline.set_state(Gst.State.PLAYING);GLib.timeout_add(1000,tick);Gtk.main()
finally:pipeline.set_state(Gst.State.NULL);window.destroy()
print(json.dumps(result),flush=True)
'''
try:
    control.watch_windows(); baseline = set(control.windows)
    lease = control.create_listener(path, 'public-av-fixture', secrets.token_hex(16))
    os.chown(path, 955, 955)
    command = c.sandbox('offline-parole', ['/usr/bin/aa-exec', '-p', 'petalos_offline_parole',
        '--', '/usr/bin/python3', '-I', '-c', probe], wayland={'path': path},
        environment={'PULSE_SERVER': 'unix:/run/user/955/pulse/native'})
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    mapped = False
    observed = set()
    deadline = time.monotonic() + 40
    while process.poll() is None and time.monotonic() < deadline:
        control.roundtrip()
        observed.update(app_id for handle, app_id in control.windows.items() if handle not in baseline)
        mapped = mapped or any(handle not in baseline and
            app_id in ('org.petalos.AVFixture', 'petalos-av-fixture', 'python3') for handle, app_id in control.windows.items())
        time.sleep(.25)
    output, errors = process.communicate(timeout=3)
    if process.returncode or not output:
        diagnostic = {'fixture_exit': process.returncode,
                      'synthetic_fixture_stderr': errors[-1600:].decode(errors='replace')}
        (path.parent / 'av-load-result.json').write_text(json.dumps(diagnostic))
    assert process.returncode == 0 and len(output) < 8192, 'A/V fixture failed; raw output suppressed.'
    report = json.loads(output.splitlines()[0])
    report['native_window_mapped'] = mapped
    report['synthetic_window_app_ids'] = sorted(observed)
    report['clock_tracks_real_time'] = 19 <= report['elapsed'] <= 25
    report['position_does_not_race'] = all(b >= a for a, b in zip(report['positions'], report['positions'][1:])) and max(report['positions'], default=0) <= report['elapsed'] + 1
    (path.parent / 'av-load-result.json').write_text(json.dumps(report))
    print(json.dumps(report, sort_keys=True))
    assert report['completed'] and mapped and report['clock_tracks_real_time'] and report['position_does_not_race']
finally:
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()
    if lease is not None:
        os.close(lease)
    control.close(); path.unlink(missing_ok=True)
