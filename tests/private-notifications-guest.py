#!/usr/bin/python3 -I
"""QEMU fixture: private buses cannot activate a layer-shell notification daemon."""
import json
import os
import subprocess
import sys

sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c

assert os.geteuid() == 0
assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
probe = '''import subprocess,json
checks={}
for name in ('org.freedesktop.Notifications','org.xfce.Notifyd'):
    result=subprocess.run(['dbus-send','--session','--print-reply','--dest='+name,
        '/org/freedesktop/Notifications','org.freedesktop.Notifications.GetCapabilities'],
        capture_output=True,text=True,timeout=5)
    checks[name]=result.returncode!=0 and any(error in result.stderr
        for error in ('AccessDenied','ServiceUnknown'))
    activation=subprocess.run(['dbus-send','--session','--print-reply',
        '--dest=org.freedesktop.DBus','/org/freedesktop/DBus',
        'org.freedesktop.DBus.StartServiceByName','string:'+name,'uint32:0'],
        capture_output=True,text=True,timeout=5)
    checks[name+'_activation_blocked']=activation.returncode!=0
result=subprocess.run(['dbus-send','--session','--print-reply','--dest=org.freedesktop.DBus',
    '/org/freedesktop/DBus','org.freedesktop.DBus.ListNames'],capture_output=True,text=True,timeout=5)
checks['private_bus_usable']=result.returncode==0
checks['notification_daemon_absent']='org.freedesktop.Notifications' not in result.stdout
print(json.dumps(checks));assert all(checks.values())
'''
for app in ('transmission', 'pan', 'amule', 'browser'):
    result = subprocess.run(c.sandbox(app, ['/usr/bin/dbus-run-session',
        '--config-file=/usr/local/share/portable/compartment-dbus.conf', '--',
        '/usr/bin/python3', '-c', probe]), capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, 'Private notification policy probe failed; raw output suppressed.'
    print(json.dumps({'app': app, 'checks': json.loads(result.stdout)}))
