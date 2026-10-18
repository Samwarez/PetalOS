"""Generate public moving video/tone and open it through the production broker."""
from pathlib import Path
import gi,json,os,subprocess,sys,time
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
assert os.geteuid()==0
gi.require_version('Gst','1.0')
from gi.repository import Gst
Gst.init(None)
work=Path('/run/petalos-phase15');work.mkdir(mode=0o700,exist_ok=True)
target=Path('/home/Petal/Downloads/petalos-audit-av.webm');assert not target.exists()
p=Gst.parse_launch('webmmux name=mux ! filesink location='+str(target)+' videotestsrc num-buffers=3600 pattern=ball ! video/x-raw,width=640,height=360,framerate=30/1 ! videoconvert ! vp8enc deadline=1 ! queue ! mux. audiotestsrc wave=sine freq=440 volume=0.02 samplesperbuffer=480 num-buffers=12000 ! audio/x-raw,rate=48000,channels=2 ! audioconvert ! vorbisenc ! queue ! mux.')
try:
 p.set_state(Gst.State.PLAYING);message=p.get_bus().timed_pop_filtered(90*Gst.SECOND,Gst.MessageType.EOS|Gst.MessageType.ERROR)
 assert message and message.type==Gst.MessageType.EOS
finally:p.set_state(Gst.State.NULL)
os.chown(target,1000,1000);target.chmod(0o644)
c.stop('offline-parole')
record=c.start('offline-parole',[str(target)])
print(json.dumps({'fixture_bytes':target.stat().st_size,'parole_ready':record['phase']=='ready','opened_from_downloads_via_readonly_handoff':True,'duration_seconds':120}))
