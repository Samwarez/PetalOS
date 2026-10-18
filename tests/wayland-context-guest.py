#!/usr/bin/python3 -I
"""QEMU-only, headless Wayland protocol boundary test. No user files/pixels."""
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, '/usr/local/lib/portable')
from wayland_context import Connection, WaylandError

assert os.geteuid() == 0
assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
assert 'toram' in Path('/proc/cmdline').read_text().split()
directory = Path(tempfile.mkdtemp(prefix='petalos-wayland-public-', dir='/run'))
process = None
keep = None
control = None
try:
    home, runtime = directory / 'home', directory / 'runtime'
    for path in (home, runtime):
        path.mkdir(mode=0o700);os.chown(path, 1000, 1000)
    # Parent is traversable only so the trusted test compositor can reach its
    # own home/runtime. The delegated endpoint remains separately restricted.
    directory.chmod(0o711)
    configuration = directory / 'config'
    configuration.mkdir(mode=0o755)
    (configuration / 'rc.xml').write_text('<labwc_config><keyboard><default/></keyboard></labwc_config>')
    environment = {'PATH': '/usr/bin:/bin', 'HOME': str(home), 'XDG_RUNTIME_DIR': str(runtime),
                   'XDG_CONFIG_HOME': str(home / '.config'), 'LC_ALL': 'C.UTF-8',
                   'WLR_BACKENDS': 'headless', 'WLR_HEADLESS_OUTPUTS': '1', 'WLR_RENDERER': 'pixman',
                   'WLR_XWAYLAND': '/usr/local/libexec/portable-deny-xwayland',
                   'GDK_BACKEND': 'wayland', 'QT_QPA_PLATFORM': 'wayland'}
    process = subprocess.Popen(['/usr/bin/setpriv', '--reuid', '1000', '--regid', '1000',
        '--clear-groups', '--no-new-privs', '--', '/usr/bin/labwc', '--config-dir', str(configuration)],
        env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)
    for _ in range(100):
        sockets = [p for p in runtime.glob('wayland-*') if p.is_socket()]
        if sockets:
            break
        if process.poll() is not None:
            raise RuntimeError('Headless compositor failed; raw logs suppressed.')
        time.sleep(0.05)
    else:
        raise RuntimeError('Headless compositor socket did not appear.')
    control = Connection(sockets[0])
    privileged_main = {'wp_security_context_manager_v1', 'zwlr_screencopy_manager_v1',
                       'zwp_virtual_keyboard_manager_v1', 'zwlr_layer_shell_v1'}
    assert privileged_main <= set(control.globals)
    delegated = directory / 'restricted.wayland'
    keep = control.create_listener(delegated, 'public-probe', secrets.token_hex(16))
    control.close();control = None
    # Root connects for this protocol-only probe. Context restrictions apply
    # independently of UID; real app UID/mount integration is tested separately.
    client = Connection(delegated)
    try:
        names = set(client.globals)
    finally:
        client.close()
    required = {'wl_compositor', 'wl_shm', 'wl_seat', 'xdg_wm_base'}
    forbidden = {'wp_security_context_manager_v1', 'zwlr_screencopy_manager_v1',
                 'zwlr_export_dmabuf_manager_v1', 'zwlr_virtual_pointer_manager_v1',
                 'zwp_virtual_keyboard_manager_v1', 'zwlr_data_control_manager_v1',
                 'zwlr_layer_shell_v1', 'ext_session_lock_manager_v1',
                 'zwlr_foreign_toplevel_manager_v1', 'ext_foreign_toplevel_list_v1'}
    report = {'native_window_protocols_available': required <= names,
              'privileged_protocols_hidden': not bool(forbidden & names),
              'creator_disconnect_keeps_listener': True}
    os.close(keep);keep = None
    time.sleep(0.1)
    try:
        connection = Connection(delegated)
    except (OSError, WaylandError):
        report['closing_lease_revokes_new_connections'] = True
    else:
        connection.close();report['closing_lease_revokes_new_connections'] = False
    main = Connection(sockets[0]);main.close()
    report['compositor_still_responds_after_revocation'] = process.poll() is None
    print(json.dumps(report, sort_keys=True))
    assert all(report.values())
finally:
    if control:
        control.close()
    if keep is not None:
        os.close(keep)
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill();process.wait()
    shutil.rmtree(directory)
