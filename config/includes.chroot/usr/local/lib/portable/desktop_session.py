"""Discover the fixed trusted Petal Wayland session, without caller overrides."""
from pathlib import Path
import os
import re
import stat


def environment():
    matches = []
    for process in Path('/proc').iterdir():
        if not process.name.isdecimal():
            continue
        try:
            if process.stat().st_uid != 1000:
                continue
            if os.readlink(process / 'exe') != '/usr/bin/xfce4-session':
                continue
            with (process / 'environ').open('rb') as source:
                data = source.read(65537)
            if len(data) > 65536:
                continue
            values = dict(x.split('=', 1) for x in data.decode().split('\0') if '=' in x)
            if values.get('XDG_SESSION_TYPE') != 'wayland':
                continue
            name = values.get('WAYLAND_DISPLAY', '')
            if not re.fullmatch(r'wayland-[0-9]{1,3}', name):
                continue
            runtime = Path('/run/user/1000')
            info = runtime.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != 1000 or info.st_mode & 0o077:
                continue
            socket = (runtime / name).lstat()
            if not stat.S_ISSOCK(socket.st_mode) or socket.st_uid != 1000:
                continue
            bus = values.get('DBUS_SESSION_BUS_ADDRESS', '')
            if not bus.startswith(('unix:path=/run/user/1000/', 'unix:abstract=/tmp/dbus-', 'unix:path=/tmp/dbus-')):
                continue
            matches.append({'PATH': '/usr/sbin:/usr/bin:/sbin:/bin',
                            'HOME': '/home/Petal', 'USER': 'Petal', 'LOGNAME': 'Petal',
                            'LC_ALL': 'C.UTF-8', 'XDG_RUNTIME_DIR': str(runtime),
                            'XDG_SESSION_TYPE': 'wayland', 'WAYLAND_DISPLAY': name,
                            'DBUS_SESSION_BUS_ADDRESS': bus, 'GDK_BACKEND': 'wayland',
                            'QT_QPA_PLATFORM': 'wayland', 'MOZ_ENABLE_WAYLAND': '1'})
        except (OSError, ValueError, UnicodeError):
            continue
    if len(matches) != 1:
        raise RuntimeError('A unique native Petal desktop is required.')
    return matches[0]
