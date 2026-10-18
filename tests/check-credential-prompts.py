#!/usr/bin/python3 -B
"""Invisible GTK prompt checks; no real credentials or privileged operations."""
import contextlib
import io
from pathlib import Path
import sys
from unittest.mock import patch

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

root = Path(__file__).resolve().parents[1] / 'config/includes.chroot/usr/local'
sys.path.insert(0, str(root / 'lib/portable'))


def load(path):
    namespace = {'__name__': 'under_test'}
    exec(compile(path.read_text(), str(path), 'exec'), namespace)
    return namespace


dialog = load(root / 'bin/portable-dialog')
for mode, title, required, button in (
    ('--sudo-password', 'Authorize desktop action', 'administrator password', 'Authorize'),
    ('--data-password', 'Unlock Private Storage', 'Private passphrase', 'Unlock'),
    ('--data-password-retry', 'Unlock Private Storage', 'Incorrect Private passphrase', 'Unlock'),
    ('--system-password', 'Unlock SYSTEM Storage', 'SYSTEM passphrase', 'Unlock'),
):
    for accepted in (True, False):
        def respond(widget):
            assert widget.get_title() == title
            children = widget.get_content_area().get_children()
            labels = ' '.join(w.get_text() for w in children if isinstance(w, Gtk.Label))
            assert required in labels
            assert widget.get_widget_for_response(Gtk.ResponseType.OK).get_label() == button
            def descendants(widget):
                yield widget
                if isinstance(widget, Gtk.Container):
                    for child in widget.get_children():
                        yield from descendants(child)
            entry = next(w for w in descendants(widget.get_content_area()) if isinstance(w, Gtk.Entry))
            assert not entry.get_visibility() and entry.get_max_length() == 1024
            assert entry.get_text() == ''
            if mode == '--data-password-retry':
                assert any(isinstance(w, Gtk.Overlay) for w in children)
            entry.set_text('public-synthetic-prompt-fixture')
            return Gtk.ResponseType.OK if accepted else Gtk.ResponseType.CANCEL

        output = io.StringIO()
        with patch.object(Gtk.Widget, 'show_all', lambda _: None), \
             patch.object(Gtk.Dialog, 'run', respond), \
             patch('sys.argv', ['portable-dialog', mode]), \
             contextlib.redirect_stdout(output):
            status = dialog['main']()
        assert status == (0 if accepted else 1)
        expected = ('public-synthetic-prompt-fixture' + ('\n' if mode == '--sudo-password' else '')) if accepted else ''
        assert output.getvalue() == expected
    print('PASS credential label, action button, hidden entry, pipe format and cancellation:', mode)


def warning_animation(widget):
    overlay = next(w for w in widget.get_content_area().get_children() if isinstance(w, Gtk.Overlay))
    image = next(w for w in overlay.get_children() if isinstance(w, Gtk.Image))
    assert overlay.get_overlay_pass_through(image)
    samples = []
    loop = GLib.MainLoop()

    def observe():
        samples.append((image.get_visible(), round(image.get_opacity(), 2)))
        return True

    observe()
    observer = GLib.timeout_add(70, observe)
    GLib.timeout_add(1400, lambda: loop.quit() or False)
    loop.run()
    GLib.source_remove(observer)
    assert samples[0] == (True, 1.0)
    assert any(visible and opacity < 0.5 for visible, opacity in samples)
    assert not samples[-1][0], 'Warning graphic did not disappear'
    return Gtk.ResponseType.CANCEL


output = io.StringIO()
with patch.object(Gtk.Widget, 'show_all', lambda _: None), \
     patch.object(Gtk.Dialog, 'run', warning_animation), \
     patch('sys.argv', ['portable-dialog', '--data-password-retry']), contextlib.redirect_stdout(output):
    assert dialog['main']() == 1
assert output.getvalue() == ''
print('PASS retry warning pulses, expires, passes pointer events through and emits no credential on cancel')


class Delegated(Exception):
    pass


vpn = load(root / 'bin/portable-vpn-profiles')
calls = []


def delegate(path, arguments):
    calls.append((path, arguments))
    raise Delegated()


with patch('sys.argv', ['portable-vpn-profiles', '--askpass']), patch('os.execv', delegate):
    try:
        vpn['main']()
    except Delegated:
        pass
    else:
        raise AssertionError('VPN askpass did not delegate')
assert calls == [('/usr/local/bin/portable-dialog', ['/usr/local/bin/portable-dialog', '--sudo-password'])]
print('PASS VPN authentication uses the shared administrator prompt')
