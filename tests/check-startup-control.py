#!/usr/bin/env python3
"""Real-child success, failure and cooperative cancellation for startup UI."""
from pathlib import Path
import os,sys,tempfile,threading,time
source=Path(__file__).resolve().parents[1]/'config/includes.chroot/usr/local/bin/portable-desktop'
namespace={'__name__':'fixture'}
exec(compile(source.read_text(),str(source),'exec'),namespace)
runner=namespace['run_action']
assert runner([sys.executable,'-I','-c','pass'],dict(os.environ),threading.Event())==0
assert runner([sys.executable,'-I','-c','raise SystemExit(9)'],dict(os.environ),threading.Event())==9
with tempfile.TemporaryDirectory(prefix='petalos-startup-control-') as d:
    marker=Path(d)/'cleanup'
    code='''import pathlib,signal,sys,time
def stop(*_):
 pathlib.Path(sys.argv[1]).write_text('cleaned');raise SystemExit(130)
signal.signal(signal.SIGTERM,stop)
time.sleep(60)
'''
    event=threading.Event();timer=threading.Timer(.5,event.set);timer.start()
    try:
        start=time.monotonic()
        result=runner([sys.executable,'-I','-c',code,str(marker)],dict(os.environ),event)
        assert result==130 and marker.read_text()=='cleaned' and time.monotonic()-start<5
    finally:timer.join()
print('PASS startup success/failure and cancellation wait for child cleanup')
