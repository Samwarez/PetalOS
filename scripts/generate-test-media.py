#!/usr/bin/python3 -B
"""Generate PetalOS's original CC0 picture/stereo test clip with GStreamer."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import struct
import sys


def generate(destination):
    import cairo
    import gi
    gi.require_version('Gst','1.0')
    gi.require_version('GstPbutils','1.0')
    from gi.repository import Gst, GstPbutils
    Gst.init(None)
    assert sys.byteorder == 'little'
    destination.mkdir(parents=True,exist_ok=True)
    output = destination/'hardware-test.webm'
    assert not output.exists(), 'Preserve the previous clip before generating another.'
    width,height,fps,seconds,rate = 1280,720,25,12,48000
    pipeline = Gst.parse_launch('appsrc name=picture format=time ! videoconvert ! '
        'vp8enc deadline=1 cpu-used=4 target-bitrate=1000000 keyframe-max-dist=25 ! queue ! mux. '
        'appsrc name=sound format=time ! audioconvert ! vorbisenc quality=0.4 ! queue ! mux. '
        'webmmux name=mux ! filesink name=output')
    picture,sound = pipeline.get_by_name('picture'),pipeline.get_by_name('sound')
    picture.set_property('caps',Gst.Caps.from_string(f'video/x-raw,format=BGRx,width={width},height={height},framerate={fps}/1'))
    sound.set_property('caps',Gst.Caps.from_string(f'audio/x-raw,format=S16LE,rate={rate},channels=2,layout=interleaved'))
    pipeline.get_by_name('output').set_property('location',str(output))
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24,width,height)
    context = cairo.Context(surface)
    colors = [(1,1,1),(1,1,0),(0,1,1),(0,1,0),(1,0,1),(1,0,0),(0,0,1)]
    pipeline.set_state(Gst.State.PLAYING)
    try:
        for frame in range(fps*seconds):
            t=frame/fps;section=int(t//4)
            for index,color in enumerate(colors):
                context.set_source_rgb(*color);context.rectangle(index*width/7,0,width/7+1,height);context.fill()
            context.set_source_rgb(.04,.04,.06);context.rectangle(0,0,width,180);context.fill()
            context.rectangle(0,height-100,width,100);context.fill()
            context.set_source_rgb(1,1,1);context.select_font_face('DejaVu Sans',cairo.FONT_SLANT_NORMAL,cairo.FONT_WEIGHT_BOLD)
            context.set_font_size(48);context.move_to(40,65);context.show_text('PetalOS · Picture & Stereo Test')
            cue=('LEFT speaker · 440 Hz','RIGHT speaker · 880 Hz','BOTH speakers · stereo')[section]
            context.set_font_size(36);context.move_to(40,130);context.show_text(cue)
            context.set_font_size(30);context.move_to(40,height-40)
            context.show_text(f'{t:05.2f} / 12.00 s     1280 × 720 · 25 fps     Frame {frame+1:03d}')
            x=80+(width-160)*(t%4)/4;y=360+100*math.sin(2*math.pi*t/2)
            context.set_source_rgb(0,0,0);context.arc(x,y,52,0,2*math.pi);context.fill()
            context.set_source_rgb(1,1,1);context.arc(x,y,42,0,2*math.pi);context.fill()
            surface.flush()
            video=Gst.Buffer.new_wrapped(bytes(surface.get_data()));video.pts=frame*Gst.SECOND//fps;video.duration=Gst.SECOND//fps
            assert picture.emit('push-buffer',video)==Gst.FlowReturn.OK
            pcm=bytearray()
            for sample in range(rate//fps):
                at=frame*(rate//fps)+sample;now=at/rate
                within=now%4
                ramp=min(1,within/.025,(4-within)/.025)
                # Moderate volume, short silence between cues, no microphone input.
                level=.18*max(0,ramp) if now%1<.8 else 0
                left=level*math.sin(2*math.pi*440*now) if section!=1 else 0
                right=level*math.sin(2*math.pi*880*now) if section!=0 else 0
                pcm.extend(struct.pack('<hh',int(32767*left),int(32767*right)))
            audio=Gst.Buffer.new_wrapped(bytes(pcm));audio.pts=video.pts;audio.duration=video.duration
            assert sound.emit('push-buffer',audio)==Gst.FlowReturn.OK
        picture.emit('end-of-stream');sound.emit('end-of-stream')
        message=pipeline.get_bus().timed_pop_filtered(180*Gst.SECOND,Gst.MessageType.ERROR|Gst.MessageType.EOS)
        assert message is not None and message.type==Gst.MessageType.EOS, 'Media encoding failed.'
    finally:pipeline.set_state(Gst.State.NULL)
    info=GstPbutils.Discoverer.new(20*Gst.SECOND).discover_uri(output.resolve().as_uri())
    assert info.get_result()==GstPbutils.DiscovererResult.OK
    assert len(info.get_video_streams())==len(info.get_audio_streams())==1
    assert info.get_audio_streams()[0].get_channels()==2
    assert abs(info.get_duration()/Gst.SECOND-seconds)<.2
    manifest={'file':output.name,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
              'bytes':output.stat().st_size,'duration_seconds':seconds,'width':width,'height':height,
              'frames_per_second':fps,'audio_channels':2,'sample_rate':rate,
              'cues':['0–4 s: left 440 Hz','4–8 s: right 880 Hz','8–12 s: both'],
              'license':'CC0-1.0','origin':'Original synthetic Cairo/GStreamer picture and sine-wave audio; no recorded content',
              'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (destination/'hardware-test.json').write_text(json.dumps(manifest,indent=2)+'\n')
    output.chmod(0o644);(destination/'hardware-test.json').chmod(0o644)
    print(json.dumps(manifest),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('destination',type=Path)
    generate(parser.parse_args().destination)
