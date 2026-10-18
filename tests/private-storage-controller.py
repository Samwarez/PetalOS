#!/usr/bin/python3
"""Synthetic storage failures: never runs cryptsetup, kills tasks or powers off."""
import importlib.util
import runpy
from contextlib import contextmanager
from pathlib import Path
import sys
import tempfile
import types
from unittest.mock import patch

source = Path(__file__).resolve().parents[1] / 'config/includes.chroot/usr/local/lib/portable/private_storage.py'
spec = importlib.util.spec_from_file_location('storage_under_test', source)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)

class Shutdown(Exception):pass
class Adapter:
    def __init__(self, opened=False, fail_unlock=False, busy=False):
        self.opened=opened; self.system_open=True; self.fail_unlock=fail_unlock; self.busy=busy; self.events=[]
    def authenticate_system(self,state,password):
        self.events.append('system-auth')
        if self.fail_unlock:raise RuntimeError('synthetic rejection')
    def is_unlocked(self,state):return self.opened
    def has_active_keys(self,state):return self.opened
    def private_device_number(self,state):return 123
    def unlock(self,state,password):
        self.events.append('unlock')
        if self.fail_unlock:raise RuntimeError('synthetic rejection')
        self.opened=True
    def lock(self,state):
        self.events.append('close')
        if self.busy:raise RuntimeError('synthetic busy storage')
        self.opened=False;self.system_open=False
    def close_private(self,state):
        self.events.append("close-private")
        if self.busy:raise RuntimeError("synthetic busy storage")
        self.opened=False
    def evict(self,state):self.events.append('evict')
class Watchdog:
    def terminate(self):pass
    def wait(self,timeout):pass
@contextmanager
def operation(*args,**kwargs):yield

def shutdown():raise Shutdown()
def check(name,condition):
    assert condition,name
    print('PASS '+name)

with tempfile.TemporaryDirectory(prefix='petalos-storage-fixture-') as root:
    fake_c=types.SimpleNamespace(ram_ready=lambda:None,ROLES={},reset_ram=lambda app:None)
    with patch.dict(sys.modules,{'compartments':fake_c}), patch.object(s,'ROOT',Path(root)), patch.object(s,'operation',operation), patch.object(s,'identity',lambda:{}), patch.object(s,'power_off',shutdown), patch.object(s,'command',lambda *a,**k:None), patch.object(s,'kill_private_users',lambda *a,**k:None), patch.object(s.time,'sleep',lambda *a:None), patch.object(s.subprocess,'Popen',lambda *a,**k:Watchdog()), patch.object(Path,'write_text',lambda *a,**k:None):
        for opened in (False,True):
            a=Adapter(opened=opened,fail_unlock=True)
            with patch.object(s,'backend',lambda:a):
                check('wrong passphrase preserves '+('open' if opened else 'closed')+' state',s.unlock(b'synthetic-fixture') is False and a.opened==opened)
                check('wrong passphrase does not close an existing volume',not opened or not a.events[1:])
                check('failed Private unlock preserves first-boot SYSTEM availability',a.system_open)
        for opened in (False, True):
            for error in (s.PassphraseRejected(2), s.StorageOperationError(4)):
                a = Adapter(opened=opened)
                with patch.object(s, 'backend', lambda: a), patch.object(a, 'unlock', side_effect=error):
                    try:
                        s.unlock(b'synthetic-fixture', raise_errors=True)
                    except type(error) as raised:
                        check('typed unlock error preserves original failure', raised is error)
                    else:
                        raise AssertionError('Typed unlock error was swallowed')
                    check('typed error preserves existing volume and SYSTEM', a.opened == opened and a.system_open)
        for rejected in (False,True):
            a=Adapter(fail_unlock=rejected)
            with patch.object(s,'backend',lambda:a):
                result=s.authenticate_system(b'synthetic-fixture')
                check('SYSTEM screen authentication '+('rejects bad secret' if rejected else 'accepts valid secret'),result is not rejected)
                check('screen authentication never opens Private',not a.opened and a.events==['system-auth'])
        a=Adapter(opened=True,busy=True)
        with patch.object(s,'backend',lambda:a):
            try:s.lock()
            except Shutdown:pass
            else:raise AssertionError('busy volume must fail closed')
            check('busy volume evicts keys before shutdown',a.events==['close','evict'])
        a=Adapter()
        with patch.object(s,'backend',lambda:a):
            check('repeated closed-volume lock succeeds',s.lock() is True and not a.events)
            flag=Path(root)/'download-mode';flag.touch()
            check('download mode inhibits idle lock',s.lock(idle=True) is False and flag.exists())
            check('manual lock overrides and clears download mode',s.lock() is True and not flag.exists())
        @contextmanager
        def busy_operation(*args,**kwargs):raise BlockingIOError();yield
        with patch.object(s,'operation',busy_operation):
            try:s.lock()
            except BlockingIOError:print('PASS concurrent lock request never enters shutdown path')
            else:raise AssertionError('contention must be reported')

# Use the project path explicitly; the fixture must never invoke a real helper.
hook = Path(__file__).resolve().parents[1] / 'config/includes.chroot/usr/lib/systemd/system-sleep/portable-private-lock'
with patch.dict(sys.modules, {'private_storage': s}), patch.object(s.os, 'geteuid', lambda: 0):
    calls=[]
    with patch.object(s, 'lock', lambda: calls.append('close')), patch.object(s, 'power_off', shutdown), patch.object(sys, 'argv', [str(hook), 'pre', 'suspend']):
        runpy.run_path(str(hook), run_name='__main__')
        check('sleep hook closes storage without a desktop service', calls==['close'])
    with patch.object(s, 'lock', lambda: calls.append('unexpected')), patch.object(sys, 'argv', [str(hook), 'post', 'suspend']):
        try:runpy.run_path(str(hook), run_name='__main__')
        except SystemExit as error:check('resume never automatically unlocks Private',error.code==0 and calls==['close'])
    def blocked():raise BlockingIOError()
    with patch.object(s, 'lock', blocked), patch.object(s, 'power_off', shutdown), patch.object(s.time, 'monotonic', side_effect=[0,16]), patch.object(sys, 'argv', [str(hook), 'pre', 'suspend']):
        try:runpy.run_path(str(hook), run_name='__main__')
        except Shutdown:print('PASS unresolved concurrent unlock at sleep fails closed')
        else:raise AssertionError('sleep must not continue with an unresolved unlock')

print('All synthetic storage and sleep-hook checks passed.')
