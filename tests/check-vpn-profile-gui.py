#!/usr/bin/python3
"""GTK widget/auth flows with invisible windows and a fully mocked backend.

Requires a native desktop or test display. Never invokes sudo, mounts or networking.
"""
from pathlib import Path
import contextlib
import base64
import io
import os
import secrets
import subprocess
import sys
import tempfile

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

project = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project / 'config/includes.chroot/usr/local/lib/portable'))
import vpn_profiles
import system_state
real_ready = system_state.ready
system_state.ready = lambda: True

source = (project / 'config/includes.chroot/usr/local/bin/portable-vpn-profiles').read_text()
# Close the invisible window after a result and automatically click Connect.
source = source.replace('            return False\n\n        def worker():',
                        '            window.destroy()\n            return False\n\n        def worker():')
source = source.replace('    Gtk.main()\n', "    if not sys.argv[1:]:\n        GLib.idle_add(lambda: (perform('switch'), False)[1])\n    Gtk.main()\n")
namespace = {'__name__': 'gui_test'}
exec(compile(source, '<profile-gui-under-test>', 'exec'), namespace)
real_run = subprocess.run
real_dialog = Gtk.Dialog.run
real_show = Gtk.Widget.show_all
real_filename = Gtk.FileChooserDialog.get_filename
Gtk.Widget.show_all = lambda self: None
messages = []
secret = secrets.token_urlsafe(16)
accept = False
scenario = ''
incoming = None


def dialog_run(self):
    if self.get_title() == 'Authorize VPN action':
        entries = [w for w in self.get_content_area().get_children() if isinstance(w, Gtk.Entry)]
        assert len(entries) == 1 and not entries[0].get_visibility()
        entries[0].set_text(secret)
        return Gtk.ResponseType.OK if accept else Gtk.ResponseType.CANCEL
    if self.get_title() == 'Choose a WireGuard configuration':
        return Gtk.ResponseType.CANCEL if scenario == 'import-cancel' else Gtk.ResponseType.OK
    if self.get_title() == 'Name the profile':
        for entry in self.get_content_area().get_children():
            if isinstance(entry, Gtk.Entry):
                entry.set_text('second')
        return Gtk.ResponseType.OK
    messages.append(self.get_property('text') if isinstance(self, Gtk.MessageDialog) else self.get_title())
    return Gtk.ResponseType.OK


Gtk.Dialog.run = dialog_run
Gtk.FileChooserDialog.get_filename = lambda self: str(incoming)
try:
    for accept in (False, True):
        sys.argv = ['portable-vpn-profiles', '--askpass']
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            result = namespace['main']()
        assert result == (0 if accept else 1)
        assert captured.getvalue() == (secret + '\n' if accept else '')
    print('PASS: graphical password hidden, accepted only through stdout pipe, cancellation sends nothing')
    for scenario in ('connect', 'failure', 'disconnect', 'import', 'import-cancel', 'import-invalid', 'import-duplicate'):
        with tempfile.TemporaryDirectory(prefix='petalos-gui-', dir='/dev/shm') as temporary:
            network = Path(temporary) / 'Network'
            (network / 'Profiles').mkdir(parents=True)
            namespace['NETWORK'] = network
            namespace['read_profile'] = vpn_profiles.read_profile
            key = base64.b64encode(os.urandom(32)).decode()
            payload = f'[Interface]\nPrivateKey = {key}\nAddress = 10.0.0.2/32\nDNS = 10.0.0.1\n[Peer]\nPublicKey = {key}\nAllowedIPs = 0.0.0.0/0, ::/0\nEndpoint = 192.0.2.1:9929\n'
            vpn_profiles.atomic_write(network / 'Profiles/first.conf', payload)
            incoming = Path(temporary) / 'incoming.conf'
            incoming.write_text('invalid' if scenario == 'import-invalid' else payload)
            incoming.chmod(0o644)
            tested_source = source
            if scenario.startswith('import'):
                insertion = '    import_profile(None)\n'
                if scenario == 'import-duplicate':
                    insertion += '    import_profile(None)\n'
                tested_source = source.replace('    window.show_all()\n', '    window.show_all()\n' + insertion)
            exec(compile(tested_source, '<profile-gui-under-test>', 'exec'), namespace)
            namespace['NETWORK'] = network
            calls = []

            def run(command, **kwargs):
                assert command[0] == '/usr/bin/sudo'
                calls.append(command)
                assert kwargs.get('stdout') == subprocess.DEVNULL
                assert kwargs.get('stderr') == subprocess.DEVNULL
                if '/usr/local/sbin/portable-vpn' in command:
                    assert kwargs['env']['SUDO_ASKPASS'] == '/usr/local/bin/portable-vpn-askpass'
                return subprocess.CompletedProcess(command, 1 if scenario == 'failure' else 0)
            subprocess.run = run
            messages.clear()
            sys.argv = ['portable-vpn-profiles'] + (['disconnect'] if scenario == 'disconnect' else [])
            assert namespace['main']() == 0
            assert calls and calls[0][1] == '-A'
            imported = scenario in ('import', 'import-duplicate')
            assert calls[0][-1] == ('disconnect' if scenario == 'disconnect' else 'second' if imported else 'first')
            assert bool(messages) == (scenario in ('failure', 'import-invalid', 'import-duplicate'))
            assert (network / 'Profiles/second.conf').exists() == imported
            if imported:
                assert (network / 'Profiles/second.conf').stat().st_mode & 0o777 == 0o600
            print('PASS: graphical ' + scenario + ' with no terminal, backend output discarded')
finally:
    system_state.ready = real_ready
    subprocess.run = real_run
    Gtk.Dialog.run = real_dialog
    Gtk.Widget.show_all = real_show
    Gtk.FileChooserDialog.get_filename = real_filename
