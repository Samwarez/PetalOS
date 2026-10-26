#!/usr/bin/python3
"""Invisible GTK helpers and mocked recovery; no mounts, sudo or networking."""
from pathlib import Path
import contextlib
import io
import os
import secrets
import subprocess
import sys
import tempfile
from unittest.mock import patch
from types import SimpleNamespace

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

project = Path(__file__).resolve().parents[1]
root = project / 'config/includes.chroot/usr/local'


def load(path):
    namespace = {'__name__': 'under_test'}
    exec(compile(path.read_text(), str(path), 'exec'), namespace)
    return namespace


secret = secrets.token_urlsafe(24)
accept = True
messages = []


def dialog_run(self):
    if self.get_title() in ('Authorize desktop action', 'Unlock Private Storage'):
        entry = next(w for w in self.get_content_area().get_children() if isinstance(w, Gtk.Entry))
        assert not entry.get_visibility() and entry.get_max_length() == 1024
        entry.set_text(secret)
        return Gtk.ResponseType.OK if accept else Gtk.ResponseType.CANCEL
    messages.append(self.get_property('text'))
    return Gtk.ResponseType.OK


with patch.object(Gtk.Widget, 'show_all', lambda _: None), patch.object(Gtk.Dialog, 'run', dialog_run):
    dialog = load(root / 'bin/portable-dialog')
    for mode in ('--sudo-password', '--data-password'):
        for accept in (True, False):
            stdout = io.StringIO()
            with patch('sys.argv', ['portable-dialog', mode]), contextlib.redirect_stdout(stdout):
                result = dialog['main']()
            assert result == (0 if accept else 1)
            expected = secret + ('\n' if mode == '--sudo-password' else '') if accept else ''
            assert stdout.getvalue() == expected
    print('PASS: hidden password prompts, exact pipe formatting and cancellation')
    helper = load(root / 'sbin/portable-unlock-passphrase')
    for cancelled, crypto_result in ((True, 0), (False, 0), (False, 2)):
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            assert secret not in ' '.join(command)
            assert kwargs.get('stderr') == subprocess.DEVNULL
            if command[0] == '/usr/sbin/runuser':
                return SimpleNamespace(returncode=int(cancelled), stdout=secret.encode() if not cancelled else b'')
            assert command[0] == '/usr/sbin/cryptsetup' and kwargs['input'] == secret.encode()
            return SimpleNamespace(returncode=crypto_result)
        with patch('os.geteuid', return_value=0), patch.dict(os.environ, {'SUDO_USER':'testuser'}), \
             patch('pwd.getpwnam'), patch('sys.argv', ['portable-unlock-passphrase']), patch('subprocess.run', run):
            assert helper['main']() == (1 if cancelled else crypto_result)
        assert len(calls) == (1 if cancelled else 2)
    print('PASS: cancelled recovery never invokes cryptsetup; wrong key fails, accepted key travels only in stdin')
    desktop = load(root / 'bin/portable-desktop')
    # Exercise the UI's result handling here; the cancellable process runner
    # has separate real-child and guest sudo/broker regression tests.
    desktop['run_action'] = lambda command, env, event: subprocess.run(command, env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    for action in desktop['ACTIONS']:
        for success in (True, False):
            with tempfile.TemporaryDirectory(prefix='petalos-desktop-', dir='/dev/shm') as temporary:
                calls, launches = [], []
                def run(command, **kwargs):
                    calls.append(command)
                    assert kwargs['stdin'] == kwargs['stdout'] == kwargs['stderr'] == subprocess.DEVNULL
                    assert kwargs['env']['SUDO_ASKPASS'] == '/usr/local/bin/portable-askpass'
                    return SimpleNamespace(returncode=0 if success else 1)
                def launch(command, **kwargs):
                    launches.append(command)
                    assert kwargs['stdin'] == kwargs['stdout'] == kwargs['stderr'] == subprocess.DEVNULL
                    return SimpleNamespace(poll=lambda:None)
                messages.clear()
                with patch('sys.argv', ['portable-desktop', action]), patch('subprocess.run', run), \
                     patch('subprocess.Popen', launch), patch.object(Path, 'home', return_value=Path(temporary)):
                    result = desktop['main']()
                assert (result == 0) == success
                if not success:
                    assert messages == [desktop['ERRORS'][action]] and not launches
                elif action == 'private':
                    assert len(launches) == 1
                elif action in ('tor','sab-open','transmission','pan','amule'):
                    assert not launches
                    assert calls == [desktop['ACTIONS'][action][1]]
                if action in ('exit-ip','exit-ipv6'):
                    assert calls == [desktop['ACTIONS'][action][1]]
                print('PASS: graphical ' + action + (' success' if success else ' failure'))
    calls=[];launches=[]
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0)
    def launch(command, **kwargs):
        launches.append(command)
        return SimpleNamespace(poll=lambda:None)
    calls=[];launches=[]
    with patch('sys.argv',['portable-desktop','transmission','--config-dir','/tmp']),patch('subprocess.run',run):
        assert desktop['main']()==1
    assert not calls
    print('PASS: file-association arguments cannot override state paths')
    with patch('sys.argv',['portable-desktop','transmission','magnet:disposable-test']),patch('subprocess.run',run),patch('subprocess.Popen',launch):
        assert desktop['main']()==0
    assert calls[-1][-1]=='magnet:disposable-test'
    print('PASS: magnet file-association argument reaches the validating broker')
    for target in ('--profile', 'javascript:alert(1)', 'file:///tmp/test.html', 'https://example.org/\n--profile'):
        calls.clear(); launches.clear()
        with patch('sys.argv',['portable-desktop','tor',target]),patch('subprocess.run',run),patch('subprocess.Popen',launch):
            assert desktop['main']()==1
        assert not calls and not launches
    print('PASS: Tor URL handler rejects options, executable schemes and local-file arguments')
    target='https://example.org/a?text=%22quoted%22&value=$(public-test)'
    calls.clear(); launches.clear()
    with patch('sys.argv',['portable-desktop','tor',target]),patch('subprocess.run',run),patch('subprocess.Popen',launch):
        assert desktop['main']()==0
    assert calls==[[*desktop['ACTIONS']['tor'][1],target]]
    assert not launches
    print('PASS: guarded Tor URL is passed as one argument without a shell')
