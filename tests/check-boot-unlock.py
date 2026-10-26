#!/usr/bin/python3
"""Failure-path shell fixtures; no real devices, passphrases or mount operations."""
from pathlib import Path
import json
import os
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
script=(ROOT/'config/includes.chroot/etc/initramfs-tools/scripts/init-premount/portable-unlock').read_text()
with tempfile.TemporaryDirectory(prefix='petalos-public-unlock-') as temporary:
    root=Path(temporary);commands=root/'bin';commands.mkdir();device=root/'fake-device';device.touch()
    (root/'cmdline').write_text('boot=live live-media=/dev/mapper/portable_system')
    (root/'functions').write_text('panic() { echo panic >>"$FIXTURE/events"; }\n')
    for name in ('modprobe','udevadm','sleep','petalos-splash'):
        p=commands/name;p.write_text('#!/bin/sh\necho "'+name+' $*" >>"$FIXTURE/events"\n');p.chmod(0o755)
    (commands/'plymouth').write_text('''#!/bin/sh
case "$1" in
 --ping) [ "$FIXTURE_GRAPHICS" = yes ];;
 ask-for-password) echo ask >>"$FIXTURE/events"; printf fixture;;
 *) exit 1;;
esac
''');(commands/'plymouth').chmod(0o755)
    (commands/'cryptsetup').write_text('''#!/usr/bin/python3
import os,json,sys
from pathlib import Path
p=Path(os.environ['FIXTURE'])
if '--key-file' in sys.argv:sys.stdin.buffer.read()
with (p/'events').open('a') as f:f.write('cryptsetup\\n')
results=json.loads((p/'responses').read_text());result=results.pop(0)
(p/'responses').write_text(json.dumps(results));raise SystemExit(result)
''');(commands/'cryptsetup').chmod(0o755)
    rewritten=script.replace('/proc/cmdline',str(root/'cmdline')).replace('/scripts/functions',str(root/'functions')).replace('/dev/disk/by-label/PORTABLE_SYSTEM',str(device)).replace('/bin/petalos-splash',str(commands/'petalos-splash'))
    (root/'unlock').write_text(rewritten)
    def run(responses,graphics=True):
        (root/'events').write_text('');(root/'responses').write_text(json.dumps(responses))
        result=subprocess.run(['/bin/sh',str(root/'unlock')],env={'PATH':str(commands)+':/usr/bin:/bin','FIXTURE':str(root),'FIXTURE_GRAPHICS':'yes' if graphics else 'no'},capture_output=True,timeout=5)
        return result.returncode,(root/'events').read_text().splitlines()
    status,events=run([2,0]);assert status==0 and events.count('ask')==2 and 'petalos-splash fail' in events and events[-1]=='petalos-splash success'
    status,events=run([2,2,2]);assert status==1 and events.count('cryptsetup')==3 and events[-1]=='panic' and 'petalos-splash success' not in events
    status,events=run([4]);assert status==1 and events.count('cryptsetup')==1 and 'petalos-splash fail' not in events and events[-1]=='panic'
    status,events=run([2,0],graphics=False);assert status==0 and 'ask' not in events and not any(e.startswith('sleep ') for e in events)
    device.unlink();status,events=run([]);assert status==1 and events.count('sleep 1')==30 and 'cryptsetup' not in events and events[-1]=='panic'
    # Layout 2 uses one prompt for the paired native helper. These shell tests
    # complement its compiled transaction tests and the actual encrypted VM.
    ids=['11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222','33333333-3333-4333-8333-333333333333']
    volumes=root/'by-uuid';volumes.mkdir()
    for ident in ids:(volumes/ident).touch()
    pair=commands/'pair'
    pair.write_text((commands/'cryptsetup').read_text().replace("if '--key-file' in sys.argv:","if '--stdin' in sys.argv:").replace("f.write('cryptsetup\\n')","f.write('pair\\n')"));pair.chmod(0o755)
    ask=commands/'askpass';ask.write_text('#!/bin/sh\necho text-ask >>"$FIXTURE/events"\nprintf fixture\n');ask.chmod(0o755)
    (root/'unlock').write_text(rewritten.replace('/dev/disk/by-uuid/',str(volumes)+'/').replace('/bin/portable-unlock-pair',str(pair)).replace('/lib/cryptsetup/askpass',str(ask)))
    line='boot=live live-media=/dev/mapper/portable_os petalos.layout=2 '+ ' '.join(k+'='+v for k,v in zip(['petalos.os','petalos.system','petalos.private'],ids))
    (root/'cmdline').write_text(line)
    status,events=run([0]);assert status==0 and events.count('ask')==1 and events.count('pair')==1
    status,events=run([2,0]);assert status==0 and events.count('ask')==2 and events.count('pair')==2
    status,events=run([3]);assert status==1 and events.count('ask')==1 and events[-1]=='panic'
    status,events=run([0],graphics=False);assert status==0 and events.count('text-ask')==1 and events.count('pair')==1
    for invalid in (line+' petalos.os='+ids[0],line.replace('petalos.private='+ids[2],''),line.replace(ids[1],ids[0]),line.replace(ids[2],'bad')):
        (root/'cmdline').write_text(invalid);status,events=run([])
        assert status==1 and events[-1]=='panic' and 'pair' not in events and 'ask' not in events
print('PASS wrong/correct retry, three-attempt refusal, non-password error, text fallback and absent-volume timeout')
print('PASS split one-prompt graphical/text handoff, wrong-password retry, mismatched-pair refusal and malformed/duplicate identity rejection')
