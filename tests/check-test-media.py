#!/usr/bin/python3 -B
"""Decode the whole clip and measure actual video frames and stereo output."""
from pathlib import Path
import array
import json
import math
import sys
import gi
gi.require_version('Gst','1.0')
from gi.repository import Gst
Gst.init(None)


def verify(path):
    pipeline=Gst.parse_launch('uridecodebin name=source '
        'source. ! queue ! videoconvert ! fakesink name=picture sync=false signal-handoffs=true '
        'source. ! queue ! audioconvert ! audioresample ! audio/x-raw,format=F32LE,channels=2,rate=48000,layout=interleaved '
        '! appsink name=sound sync=false emit-signals=true')
    pipeline.get_by_name('source').set_property('uri',path.resolve().as_uri())
    frames=[];sums=[[0.,0.,0] for _ in range(3)]
    def picture(_sink,buffer,_pad):frames.append(buffer.pts)
    def audio(sink):
        sample=sink.emit('pull-sample');buffer=sample.get_buffer();ok,mapped=buffer.map(Gst.MapFlags.READ)
        assert ok
        try:
            values=array.array('f');values.frombytes(mapped.data)
            start=buffer.pts/Gst.SECOND
            for offset in range(0,len(values)-1,2):
                now=start+offset/2/48000;section=int(now//4)
                if section<3 and .2<now%4<3.8:
                    sums[section][0]+=values[offset]**2;sums[section][1]+=values[offset+1]**2;sums[section][2]+=1
        finally:buffer.unmap(mapped)
        return Gst.FlowReturn.OK
    pipeline.get_by_name('picture').connect('handoff',picture)
    pipeline.get_by_name('sound').connect('new-sample',audio)
    pipeline.set_state(Gst.State.PLAYING)
    try:
        message=pipeline.get_bus().timed_pop_filtered(180*Gst.SECOND,Gst.MessageType.ERROR|Gst.MessageType.EOS)
        assert message is not None and message.type==Gst.MessageType.EOS,'Full media decoding failed.'
    finally:pipeline.set_state(Gst.State.NULL)
    assert len(frames)==300 and frames[-1]>11*Gst.SECOND, 'Moving video frames are missing.'
    rms=[[math.sqrt(left/count),math.sqrt(right/count)] for left,right,count in sums]
    assert rms[0][0]>.04 and rms[0][1]<.005,'Left cue has wrong channel or no audio.'
    assert rms[1][1]>.04 and rms[1][0]<.005,'Right cue has wrong channel or no audio.'
    assert min(rms[2])>.04,'Stereo cue has no audio on one channel.'
    return {'decoded_frames':len(frames),'left_right_stereo_rms':rms,'passed':True}


if __name__=='__main__':print(json.dumps(verify(Path(sys.argv[1]))))
