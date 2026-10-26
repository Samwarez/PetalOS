"""Measure synthetic playback at the guest output monitor; never open a microphone."""
from array import array
import json
import math
import os
import subprocess
import sys
assert os.geteuid() == 0
sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
from desktop_session import environment
assert c.worker_alive(c.read_record('offline-parole'))
command = ['setpriv', '--reuid=1000', '--regid=1000', '--clear-groups', '--',
           'parec', '--device=@DEFAULT_MONITOR@', '--raw', '--format=s16le', '--rate=48000', '--channels=2']
p = subprocess.Popen(command, env=environment(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
try:
    output, errors = p.communicate(timeout=2)
except subprocess.TimeoutExpired:
    p.terminate();output, errors = p.communicate(timeout=5)
samples = array('h');samples.frombytes(output[:len(output)//2*2])
rms = math.sqrt(sum(x*x for x in samples)/len(samples)) if samples else 0
checks = {'guest_output_samples_received': len(samples) >= 48000,
          'synthetic_tone_reached_output': rms > 4}
print(json.dumps({'checks': checks, 'samples': len(samples), 'rms': round(rms, 2),
                  'capture_source': 'guest output monitor only; raw PCM not saved'}))
assert all(checks.values())
