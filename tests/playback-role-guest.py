#!/usr/bin/python3 -I
"""Measure synthetic audio in the real offline Parole role; no media/mic/network."""
import json
import os
from pathlib import Path
import subprocess
import sys

assert os.geteuid() == 0
sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c

app = 'offline-parole'
assert not c.worker_alive(c.read_record(app)), 'Close Parole before this test.'
c.roles(); c.home(app); c.storage_setup(app)
processes, modules = [], []
code = '''import gi,json,os,socket,subprocess,time
from pathlib import Path
gi.require_version('Gst','1.0')
from gi.repository import Gst
Gst.init(None)
sources=subprocess.check_output(['pactl','list','short','sources'],text=True)
checks={'real_role_uid':os.getuid()==955,'no_groups':not os.getgroups(),
 'no_caps':next(l for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('CapEff:')).split()[1]=='0000000000000000',
 'only_playback_monitor':[l.split()[1] for l in sources.splitlines()]==['playback.monitor']}
for family,name in [(socket.AF_INET,'ipv4_denied'),(socket.AF_INET6,'ipv6_denied')]:
 try:s=socket.socket(family);s.close();checks[name]=False
 except PermissionError:checks[name]=True
p=Gst.parse_launch('audiotestsrc wave=silence samplesperbuffer=480 num-buffers=600 ! audio/x-raw,format=S16LE,rate=48000,channels=2 ! pulsesink sync=true')
started=time.monotonic()
try:
 p.set_state(Gst.State.PLAYING)
 message=p.get_bus().timed_pop_filtered(12*Gst.SECOND,Gst.MessageType.EOS|Gst.MessageType.ERROR)
 elapsed=time.monotonic()-started
 checks['completed_without_error']=message is not None and message.type==Gst.MessageType.EOS
 checks['real_time_playback']=5.5<=elapsed<=8.5
 clock=p.get_clock()
 checks['pulse_clock']=clock is not None and clock.get_name()=='GstPulseSinkClock'
 print(json.dumps({'checks':checks,'six_second_playback_elapsed':round(elapsed,3)}))
 assert all(checks.values())
finally:p.set_state(Gst.State.NULL)
'''
try:
    server = c.playback(app, processes, modules)
    result = subprocess.run(c.sandbox(app, ['/usr/bin/aa-exec', '-p', 'petalos_offline_parole', '--',
        '/usr/bin/python3', '-I', '-c', code], environment={'PULSE_SERVER': server}),
        capture_output=True, text=True, timeout=18)
    if result.returncode:
        raise RuntimeError('Parole-role playback check failed; raw output suppressed')
    report = json.loads(result.stdout)
    print(json.dumps(report, sort_keys=True))
    assert all(report['checks'].values())
finally:
    for process in processes:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()
    for module in reversed(modules):
        assert module.isdigit()
        c.desktop_audio(['unload-module', module])
