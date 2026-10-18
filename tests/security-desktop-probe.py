#!/usr/bin/python3
"""Public local-document fixtures and default handlers; no personal files."""
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    assert os.getuid() == 1000
    assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
    result = {}
    environment = {**os.environ, 'DISPLAY': ':0', 'XAUTHORITY': '/home/Petal/.Xauthority', 'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/user/1000/bus'}
    for mime, wanted in [('x-scheme-handler/http', 'portable-tor.desktop'), ('x-scheme-handler/https', 'portable-tor.desktop'), ('application/pdf', 'atril.desktop'), ('image/png', 'org.gnome.gThumb.desktop'), ('video/mp4', 'org.xfce.Parole.desktop'), ('audio/mpeg', 'io.github.quodlibet.QuodLibet.desktop'), ('text/html', 'firefox-esr.desktop')]:
        query = subprocess.run(['xdg-mime', 'query', 'default', mime], capture_output=True, text=True, timeout=5, env=environment)
        result[mime + '_correct'] = query.stdout.strip() == wanted
    for app in ('atril', 'parole', 'ristretto', 'mousepad', 'quodlibet'):
        probe = subprocess.run(['/usr/bin/' + app, '--version'], capture_output=True, timeout=15, env=environment)
        result[app + '_offline_startup'] = probe.returncode == 0
        result[app + '_wrapper_present'] = 'portable-offline' in Path('/usr/bin/' + app).read_text()
    for name in ('x-www-browser', 'gnome-www-browser'):
        result[name + '_guarded'] = Path('/usr/bin/' + name).resolve() == Path('/usr/local/bin/portable-web-browser')
    probe = '''import socket,json,os
from pathlib import Path
r={'enforced':Path('/proc/self/attr/current').read_text().strip()=='petalos_offline (enforce)',
   'system_bus_hidden':not Path('/run/dbus/system_bus_socket').exists(),
   'private_session_bus':os.environ.get('DBUS_SESSION_BUS_ADDRESS','')!='unix:path=/run/user/1000/bus'}
try:socket.socket(socket.AF_INET,socket.SOCK_STREAM);r['network_denied']=False
except PermissionError:r['network_denied']=True
print(json.dumps(r));assert all(r.values())
'''
    query = subprocess.run(['/usr/local/bin/portable-offline', '/usr/bin/dbus-run-session', '--', '/usr/bin/python3', '-c', probe], capture_output=True, timeout=15, env=environment)
    result['private_bus_preserves_isolation'] = query.returncode == 0 and all(json.loads(query.stdout).values())
    with tempfile.TemporaryDirectory(prefix='public-html-audit-', dir='/home/Petal/.cache') as directory:
        path = Path(directory)
        (path / 'profile').mkdir()
        (path / 'public.html').write_text('<html><body><h1>Public offline rendering test</h1></body></html>')
        query = subprocess.run(['/usr/local/bin/portable-offline', '/usr/lib/firefox-esr/firefox-esr', '--headless', '--no-remote', '--profile', str(path / 'profile'), '--screenshot', str(path / 'public.png'), (path / 'public.html').as_uri()], capture_output=True, timeout=40, env=environment)
        result['offline_html_rendered'] = query.returncode == 0 and (path / 'public.png').is_file() and (path / 'public.png').stat().st_size > 1000
    print(json.dumps(result, sort_keys=True))
    assert all(result.values())


if __name__ == '__main__':
    main()
