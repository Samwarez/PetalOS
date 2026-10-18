#!/usr/bin/python3 -I
"""Bounded ThinkPad soak using disposable content and production app sandboxes.

No sleep, lock, shutdown, profile switching, firewall edits or user-file scans.
Reports stay in RAM. Never records subprocess stderr or personal file contents.
"""
from pathlib import Path
import hashlib
import json
import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c

WORK = Path('/run/petalos-away-tests')
REPORT = WORK / 'report.json'
state = {'phase': 'starting', 'tests': {}, 'apps': {}, 'samples': [], 'started': time.time()}
workers = []
created_apps = []
initial_apps = set()
stopping = False


def save(phase=None):
    if phase:
        state['phase'] = phase
    temporary = REPORT.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, sort_keys=True))
    temporary.chmod(0o600)
    os.replace(temporary, REPORT)


def sample():
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    temperatures = []
    for p in Path('/sys/class/hwmon').glob('hwmon*/temp*_input'):
        try:
            value = int(p.read_text().strip())
            if 0 < value < 150000:
                temperatures.append(value)
        except (OSError, ValueError):
            pass
    return {'elapsed': round(time.monotonic() - start),
            'available_mib': int(memory['MemAvailable'].split()[0]) // 1024,
            'maximum_temperature_c': max(temperatures, default=0) / 1000,
            'load1': os.getloadavg()[0],
            'Private_open': c.private_available()}


def fixture(name, timeout=120):
    save('fixture:' + name)
    try:
        result = subprocess.run(['/usr/bin/python3', '-I', str(WORK / name)],
                                capture_output=True, timeout=timeout)
        # Fixtures in this fixed manifest print only generated/public data.
        output = result.stdout.decode(errors='replace')[-24000:]
        state['tests'][name] = {'exit': result.returncode, 'public_output': output}
    except subprocess.TimeoutExpired:
        state['tests'][name] = {'timeout': True}
    save()


def atomic_saves():
    """Exercise anonymous temporary-file commit under each actual profile."""
    report = {}
    code = '''from pathlib import Path
import ctypes,json,os,secrets
folder=Path.home()/'Documents'
p=folder/('petalos-atomic-fixture-'+secrets.token_hex(10))
fd=os.open(folder,os.O_TMPFILE|os.O_RDWR,0o600)
try:
 libc=ctypes.CDLL(None,use_errno=True)
 result=libc.linkat(-100,('/proc/self/fd/'+str(fd)).encode(),-100,str(p).encode(),0x400)
 print(json.dumps({'linked':result==0,'errno':ctypes.get_errno() if result else 0}))
finally:os.close(fd);p.unlink(missing_ok=True)
'''
    for app in c.OFFLINE:
        c.home(app); c.storage_setup(app)
        command = ['/usr/bin/aa-exec', '-p', 'petalos_' + app.replace('-', '_'), '--',
                   '/usr/bin/python3', '-I', '-c', code]
        result = subprocess.run(c.sandbox(app, command), capture_output=True, timeout=15)
        try:
            report[app] = json.loads(result.stdout)
        except (ValueError, TypeError):
            report[app] = {'fixture_exit': result.returncode}
    state['tests']['atomic-file-commit'] = report
    save()


def start_app(app, arguments=()):
    if c.worker_alive(c.read_record(app)):
        state['apps'][app] = {'skipped_existing': True}
        save()
        return
    save('launch:' + app)
    command = ['/usr/local/sbin/portable-compartment', 'launch', app, *arguments]
    try:
        result = subprocess.run(command, capture_output=True, timeout=210 if app in ('tor', 'browser') else 110)
        record = c.read_record(app)
        ready = result.returncode == 0 and c.worker_alive(record) and record.get('phase') == 'ready'
        state['apps'][app] = {'exit': result.returncode, 'ready': ready}
        if c.worker_alive(record):
            created_apps.append((app, record.get('token')))
    except subprocess.TimeoutExpired:
        record = c.read_record(app)
        state['apps'][app] = {'timeout': True}
        if c.worker_alive(record):
            created_apps.append((app, record.get('token')))
    # Tor and SAB launchers also create their GUI companions. Account for
    # those without ever retiring an application that predated this pass.
    for companion in {'tor': ('browser',), 'sabnzbd': ('sab-viewer',)}.get(app, ()):
        record = c.read_record(companion)
        if companion not in initial_apps and c.worker_alive(record) and not any(a == companion for a, _ in created_apps):
            created_apps.append((companion, record.get('token')))
    save()


def stress_start(count):
    code = '''import hashlib,resource,time
resource.setrlimit(resource.RLIMIT_AS,(320*1024**2,320*1024**2))
data=bytearray(128*1024**2)
for i in range(0,len(data),4096):data[i]=i%251
chunk=memoryview(data)[:1024**2]
while True:hashlib.sha256(chunk).digest()
'''
    for _ in range(count):
        workers.append(subprocess.Popen([
            '/usr/bin/setpriv', '--reuid=61001', '--regid=61001', '--clear-groups',
            '--inh-caps=-all', '--bounding-set=-all', '--ambient-caps=-all', '--no-new-privs',
            '--', '/usr/bin/nice', '-n', '10', '/usr/bin/python3', '-I', '-c', code],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))


def stress_stop():
    for process in workers:
        if process.poll() is None:
            process.terminate()
    for process in workers:
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()
    workers.clear()


def main():
    global start
    assert os.geteuid() == 0 and sys.argv[1:] == []
    assert Path('/sys/class/dmi/id/sys_vendor').read_text().strip() == 'LENOVO'
    assert Path('/sys/class/dmi/id/product_name').read_text().strip() == '21CQCTO1WW'
    assert WORK.is_dir() and WORK.stat().st_uid == 0 and not WORK.stat().st_mode & 0o077
    c.ram_ready(); c.private_ready(); c.roles()
    initial_apps.update(app for app in c.ROLES if c.worker_alive(c.read_record(app)))
    from private_storage import directory
    assert (directory() / 'download-mode').exists()
    start = time.monotonic()
    baseline = subprocess.check_output(['/usr/sbin/nft', '-s', '-j', 'list', 'table', 'inet', 'portable_vpn'])
    state['firewall_before'] = hashlib.sha256(baseline).hexdigest()
    state['baseline'] = sample()
    save('offline-tests')
    for name in ('offline-native-boundary-guest.py', 'offline-file-handoff-guest.py',
                 'keepass-save-guest.py', 'compartment-cleanup-guest.py', 'shutdown-policy-guest.py',
                 'wayland-context-guest.py'):
        fixture(name)
    atomic_saves()
    # The audio fixture owns a temporary bridge; run before starting GUI Parole.
    fixture('playback-role-guest.py', timeout=35)
    for app in c.OFFLINE:
        if stopping or time.monotonic() - start > 12 * 60:
            break
        start_app(app)
    network_ready = False
    try:
        c.gate('transmission'); network_ready = True
    except Exception:
        pass
    state['network_gate_ready'] = network_ready
    if network_ready:
        for app in ('transmission', 'pan', 'amule', 'sabnzbd', 'sab-viewer', 'tor', 'browser'):
            if stopping or time.monotonic() - start > 12 * 60:
                break
            start_app(app)
        if c.worker_alive(c.read_record('tor')):
            fixture('tor-socks-boundary-guest.py', timeout=65)
    save('soak')
    count = min(8, max(2, (os.cpu_count() or 4) // 2))
    stress_start(count)
    deadline = min(time.monotonic() + 30 * 60, start + 45 * 60)
    paused = False
    while not stopping and time.monotonic() < deadline:
        data = sample()
        data['apps_alive'] = {app: c.worker_alive(c.read_record(app)) for app, token in created_apps}
        state['samples'].append(data)
        state['samples'] = state['samples'][-100:]
        if data['available_mib'] < 4096 or not data['Private_open']:
            state['abort_reason'] = 'resource_or_storage_boundary'; break
        if data['maximum_temperature_c'] >= 85:
            stress_stop(); paused = True; state['thermal_pause'] = True
        elif paused and data['maximum_temperature_c'] <= 70:
            stress_start(max(2, count // 2)); paused = False
        save()
        for _ in range(20):
            if stopping:
                break
            time.sleep(1)
    stress_stop()
    save('post-soak-tests')
    fixture('keepass-save-guest.py')
    fixture('offline-file-handoff-guest.py')
    current = subprocess.check_output(['/usr/sbin/nft', '-s', '-j', 'list', 'table', 'inet', 'portable_vpn'])
    state['firewall_unchanged'] = hashlib.sha256(current).hexdigest() == state['firewall_before']
    state['finished'] = time.time()


def stop(*_):
    global stopping
    stopping = True


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
try:
    main()
except BaseException as error:
    state['error_type'] = type(error).__name__
finally:
    stress_stop()
    for app, token in reversed(created_apps):
        try:
            record = c.read_record(app)
            if record.get('token') == token:
                c.stop(app)
        except Exception:
            state.setdefault('cleanup_errors', []).append(app)
    state['finished'] = time.time()
    save('complete' if 'error_type' not in state and 'abort_reason' not in state else 'stopped-with-findings')
