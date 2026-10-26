#!/usr/bin/python3
"""Portable runtime and administrator acceptance, inside a fresh networkless VM."""
from pathlib import Path
import json
import os
import subprocess
import sys
import threading
import time
import traceback

RESULTS = {}
APP = Path('/mnt/portable/app')


def check(name, condition):
    RESULTS[name] = bool(condition)
    if not condition:raise RuntimeError('Check failed: ' + name)
    print('SPLIT_PASS ' + name, flush=True)


def run(arguments, **kwargs):
    result = subprocess.run(arguments, capture_output=True, timeout=180, **kwargs)
    if result.returncode:raise RuntimeError('Portable fixture tool failed: ' + Path(arguments[0]).name)
    return result.stdout


def as_user():
    os.setgroups([]);os.setgid(1000);os.setuid(1000)


def call_worker(request=None, *, corrupt=False, traversal=False, short=False, cancel=False, host_mount=False):
    from petal_installer import portable
    value = portable.manifest(APP)
    before = set(Path('/run').glob('petalos-installer-*'))
    process = subprocess.Popen([str(APP / value.get('bootstrap', 'petal-admin'))], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    errors = []
    namespace_ready = threading.Event()
    def send():
        try:
            for index, data in enumerate(portable.chunks(APP, value)):
                if traversal and index == 0:
                    data = data.replace(b'app/backend.py', b'app/../badfile', 1)
                if corrupt and index == 1:data = bytes([data[0] ^ 1]) + data[1:]
                process.stdin.write(data)
                if short and index == 1:
                    process.stdin.close();return
            process.stdin.flush()
            if host_mount and not namespace_ready.wait(120):raise RuntimeError('Private namespace readiness timed out.')
            process.stdin.write(json.dumps({'request': request or {}, 'credentials': {}}).encode() + b'\n')
            process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError, RuntimeError) as error:
            errors.append(type(error).__name__)
            try:process.stdin.close()
            except (OSError, ValueError):pass
    writer = threading.Thread(target=send);writer.start()
    events = [];cancelled = False
    for raw in process.stdout:
        event = json.loads(raw);events.append(event)
        if host_mount and event.get('type') == 'portable-ready':
            run(['/usr/bin/mount', '-t', 'ext4', '-o', 'ro,noload,nodev,nosuid,noexec',
                 '/dev/sda', '/tmp/external-host-mount'])
            namespace_ready.set()
        if cancel and not cancelled and event.get('value', {}).get('stage') == 'random-fill':
            process.stdin.write(b'{"cancel":true}\n');process.stdin.flush();cancelled = True
    status = process.wait(timeout=30);writer.join(timeout=30)
    if not process.stdin.closed:process.stdin.close()
    diagnostic = process.stderr.read().decode(errors='replace')[-2000:]
    process.stdout.close();process.stderr.close()
    check('worker_temporary_runtime_cleaned_' + str(len(RESULTS)), before == set(Path('/run').glob('petalos-installer-*')))
    if status and not any(e.get('type') == 'error' for e in events):
        # No credentials or personal data occur in this synthetic fixture.
        print('PORTABLE_RUNTIME_ERROR ' + diagnostic.replace('\n', ' ')[:1800], flush=True)
    if status:
        print('PORTABLE_WORKER_ERROR ' + '; '.join(e.get('message', '') for e in events if e.get('type') == 'error')[:2000], flush=True)
    return status, events


try:
    Path('/mnt/portable').mkdir()
    run(['/usr/bin/mount', '-t', 'iso9660', '-o', 'ro,nodev,nosuid', '/dev/vda', '/mnt/portable'])
    Path('/mnt').chmod(0o755)
    Path('/tmp').mkdir(exist_ok=True);Path('/tmp').chmod(0o1777)
    sys.path.insert(0, str(APP / 'app'))
    from petal_installer import linux, portable
    from petal_installer.plans import make_plan
    from petal_installer.bridge import request_from_plan
    inputs = json.loads(Path('/fixture/test-input.json').read_text())
    for directory in ('/tmp/portable-user', '/tmp/portable-user/runtime'):
        Path(directory).mkdir(mode=0o700, parents=True);os.chown(directory, 1000, 1000)
    environment = dict(os.environ, HOME='/tmp/portable-user', XDG_RUNTIME_DIR='/tmp/portable-user/runtime',
                       GDK_BACKEND='broadway', BROADWAY_DISPLAY=':73', GTK_THEME='Adwaita:dark')
    # The actual packaged Python/GTK are selected by the portable launcher.
    check('packaged_cli_has_current_version', run([str(APP / 'bloom'), '--version'], preexec_fn=as_user, env=environment).strip() == b'0.4.0')
    listing = run([str(APP / 'bloom'), '--portable-tool', '/usr/bin/lsinitramfs',
                   '/mnt/portable/public-initrd.img'], preexec_fn=as_user, env=environment)
    check('bundled_shell_tool_and_subcommands', b'portable-runtime-canary' in listing.splitlines())
    # Host minimal initrd has no GTK. Broadway and all GUI libraries come from
    # the portable tree; the display socket is accessible only inside this VM.
    server = subprocess.Popen([str(APP / 'bloom'), '--portable-tool', '/usr/bin/broadwayd',
                               '--unixsocket=/tmp/portable-user/http.sock', ':73'], preexec_fn=as_user,
                              env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        socket = Path(environment['XDG_RUNTIME_DIR']) / 'broadway74.socket'
        def display_ready():
            # GTK uses an abstract Unix socket on Linux, so no directory entry
            # exists. Inspect the kernel socket table rather than a cache file.
            return str(socket) in Path('/proc/net/unix').read_text()
        for _ in range(600):
            if display_ready():break
            if server.poll() is not None:
                print('PORTABLE_GTK_ERROR ' + server.stderr.read().decode(errors='replace')[-2000:].replace('\n', ' '), flush=True)
                raise RuntimeError('Bundled Broadway exited.')
            time.sleep(.1)
        if not display_ready():
            for process_dir in Path('/proc').glob('[0-9]*'):
                try:
                    command = (process_dir / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
                    if 'portable' in command or 'broadway' in command:
                        print('PORTABLE_GTK_ERROR process: ' + command[:800] + ' wait=' + (process_dir / 'wchan').read_text(), flush=True)
                except (OSError, ValueError):pass
            server.terminate();server.wait(timeout=10)
            print('PORTABLE_GTK_ERROR ' + server.stderr.read().decode(errors='replace')[-2000:].replace('\n', ' '), flush=True)
            print('PORTABLE_GTK_ERROR sockets: ' + ','.join(str(p) for p in Path(environment['XDG_RUNTIME_DIR']).rglob('*')), flush=True)
        check('bundled_gtk_display_started', display_ready())
        result = subprocess.run([str(APP / 'bloom'), '--portable-tool', '/usr/bin/python3',
                                 '-s', '-P', '-B', '/mnt/portable/gtk-check.py'], preexec_fn=as_user,
                                env=environment, capture_output=True, timeout=180)
        if result.returncode:print('PORTABLE_GTK_ERROR ' + (result.stdout + result.stderr).decode(errors='replace')[-3000:].replace('\n', ' '), flush=True)
        check('six_packaged_native_gtk_checks', result.returncode == 0 and b'PORTABLE_GTK_PASSED 6' in result.stdout)
    finally:
        if server.poll() is None:server.terminate();server.wait(timeout=10)
        server.stderr.close()
    check('no_installed_petalos_backend', not Path('/usr/lib/petalos-installer').exists() and not Path('/usr/lib/bloom-installer').exists())
    result = run([str(APP / 'bloom'), '--portable-check'], preexec_fn=as_user, env=environment)
    value = json.loads(result)
    check('packaged_runtime_self_check', value['portable'] and value['name'] == 'Bloom' and value['version'] == '0.4.0' and value['verified_files'] > 1000)
    # Root staging integrity: no invalid packet reaches the disk engine.
    status, events = call_worker(corrupt=True)
    check('altered_payload_refused_before_execution', status != 0 and any('differs from this application build' in e.get('message', '') for e in events))
    status, events = call_worker(traversal=True)
    check('path_traversal_refused_before_execution', status != 0 and any('redirected path' in e.get('message', '') for e in events) and not Path('/run/badfile').exists())
    status, events = call_worker(short=True)
    check('truncated_transfer_refused', status != 0 and any('ended before verification' in e.get('message', '') for e in events))
    # The only writable block device is the newly allocated disposable USB.
    run(['/usr/bin/udevadm', 'trigger', '--action=change', '--subsystem-match=block'])
    run(['/usr/bin/udevadm', 'settle', '--timeout=15'])
    disk = linux.choose('/dev/sda')
    check('fresh_disposable_usb_target', disk['transport'] == 'usb' and disk['bytes'] == 512 * 1024**2)
    # Create a read-only external mount only AFTER the worker's mount namespace
    # exists, but before it receives a job. Its supervisor still sees this mount.
    run(['/usr/sbin/mkfs.ext4', '-q', '-F', '/dev/sda'])
    Path('/tmp/external-host-mount').mkdir()
    original = run(['/usr/bin/sha256sum', '/dev/sda'])
    mounted_request = request_from_plan(make_plan('wipe', linux.choose('/dev/sda'), wipe_method='random'))
    try:
        status, events = call_worker(mounted_request, host_mount=True)
    finally:
        run(['/usr/bin/umount', '/tmp/external-host-mount'])
    check('new_external_host_mount_refused', status != 0 and any('mounted by another host application' in e.get('message', '') for e in events))
    check('external_mount_refusal_kept_disk_unchanged', original == run(['/usr/bin/sha256sum', '/dev/sda']))
    before = run(['/usr/bin/sha256sum', '/dev/sda'])
    plan = make_plan('wipe', disk, wipe_method='random');request = request_from_plan(plan)
    stale = dict(request, plan_sha256='0' * 64)
    status, events = call_worker(stale)
    check('protected_worker_rejects_stale_plan', status != 0 and any('Plan changed since confirmation' in e.get('message', '') for e in events))
    check('stale_plan_left_disposable_disk_unchanged', before == run(['/usr/bin/sha256sum', '/dev/sda']))
    status, events = call_worker(request, cancel=True)
    check('pipe_cancellation_reaches_protected_worker', status != 0 and any(e.get('value', {}).get('stage') == 'wipe-incomplete' for e in events))
    check('cancelled_worker_left_no_mappings', not any(Path('/dev/mapper').glob('petal_inst_*')))
    # A fresh plan explicitly authorizes this VM-only random wipe/readback.
    request = request_from_plan(make_plan('wipe', linux.choose('/dev/sda'), wipe_method='random'))
    status, events = call_worker(request)
    result = next((e['value'] for e in events if e.get('type') == 'result'), {})
    check('portable_random_wipe_and_full_readback', status == 0 and result.get('completed') and result.get('random_fill_verified'))
    check('successful_worker_left_no_mappings', not any(Path('/dev/mapper').glob('petal_inst_*')))
    print('SPLIT_RESULT ' + json.dumps({'passed': True, 'stage': 'portable-installer', 'checks': RESULTS}), flush=True)
except BaseException as error:
    location = traceback.extract_tb(error.__traceback__)[-1]
    print('SPLIT_RESULT ' + json.dumps({'passed': False, 'stage': 'portable-installer', 'checks': RESULTS,
        'failure_type': type(error).__name__, 'failure_source': Path(location.filename).name + ':' + str(location.lineno),
        'source_chain': [Path(frame.filename).name + ':' + str(frame.lineno) for frame in traceback.extract_tb(error.__traceback__)],
        'failure_message': str(error) if isinstance(error, RuntimeError) else 'details suppressed'}), flush=True)
finally:
    subprocess.run(['/bin/busybox', 'poweroff', '-f'])
