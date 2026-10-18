#!/usr/bin/python3 -I
"""Six-minute checksum integrity exercise over two private 256 MiB RAM buffers."""
from pathlib import Path
import json
import os
import signal
import subprocess
import time

assert os.geteuid() == 0
assert Path('/sys/class/dmi/id/product_name').read_text().strip() == '21CQCTO1WW'
root = Path('/run/petalos-away-tests')
code = '''import hashlib,json,resource,time
resource.setrlimit(resource.RLIMIT_AS,(640*1024**2,640*1024**2))
block=bytes(range(256))*4096
data=bytearray(block*256)
expected=hashlib.sha256(data).digest()
started=time.monotonic();passes=0
while time.monotonic()-started<360:
 if hashlib.sha256(data).digest()!=expected:raise RuntimeError('public RAM pattern changed')
 passes+=1
print(json.dumps({'bytes':len(data),'checksum_passes':passes,'elapsed':round(time.monotonic()-started,2)}),flush=True)
'''
children = []
paused = False
report = {'workers': [], 'thermal_pauses': 0}
start = time.monotonic()
try:
    for _ in range(2):
        children.append(subprocess.Popen([
            '/usr/bin/setpriv', '--reuid=61002', '--regid=61002', '--clear-groups',
            '--bounding-set=-all', '--inh-caps=-all', '--ambient-caps=-all', '--no-new-privs',
            '--', '/usr/bin/nice', '-n', '15', '/usr/bin/python3', '-I', '-c', code],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL))
    while any(p.poll() is None for p in children) and time.monotonic() - start < 420:
        temps = []
        for p in Path('/sys/class/hwmon').glob('hwmon*/temp*_input'):
            try:
                value = int(p.read_text())
                if 0 < value < 150000:
                    temps.append(value)
            except (OSError, ValueError):
                pass
        available = next(line for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
        if int(available.split()[1]) < 8 * 1024**2:
            report['stopped_for_memory_pressure'] = True
            break
        hot = max(temps, default=0)
        if hot >= 80000 and not paused:
            for p in children:
                if p.poll() is None:
                    os.kill(p.pid, signal.SIGSTOP)
            paused = True; report['thermal_pauses'] += 1
        elif hot <= 70000 and paused:
            for p in children:
                if p.poll() is None:
                    os.kill(p.pid, signal.SIGCONT)
            paused = False
        time.sleep(2)
    for p in children:
        if p.poll() is not None:
            output = p.stdout.read(1024)
            try:
                result = json.loads(output)
            except ValueError:
                result = {}
            result['exit'] = p.returncode
            report['workers'].append(result)
finally:
    for p in children:
        if p.poll() is None:
            if paused:
                os.kill(p.pid, signal.SIGCONT)
            p.terminate()
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            p.kill(); p.wait()
        p.stdout.close()
    report['elapsed'] = round(time.monotonic() - start, 2)
    report['all_checksums_passed'] = len(report['workers']) == 2 and all(w.get('exit') == 0 and w.get('checksum_passes', 0) > 0 for w in report['workers'])
    (root / 'memory-integrity.json').write_text(json.dumps(report))
