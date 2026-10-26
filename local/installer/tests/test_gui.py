"""Native GTK regressions: run in a Linux desktop; safely skip without a display.

Uses in-memory release responses and never invokes a disk operation or backend.
"""
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, GLib
    DISPLAY = Gtk.init_check()[0]
except (ImportError, ValueError):DISPLAY = False
from petal_installer import InstallerError
from petal_installer.gui import create_window


def descendants(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():yield from descendants(child)


def find(window, name):return next(w for w in descendants(window) if w.get_name() == name)


def settle(condition):
    end = time.monotonic() + 3
    while time.monotonic() < end:
        for _ in range(12):
            if not Gtk.events_pending():break
            Gtk.main_iteration_do(False)
        if condition():return
        time.sleep(.01)
    raise AssertionError('GUI did not reach its expected state')


def contrast(a, b):
    def luminance(c):
        values = [getattr(c, name) for name in ('red', 'green', 'blue')]
        values = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in values]
        return sum(v*w for v,w in zip(values,(.2126,.7152,.0722)))
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light+.05)/(dark+.05)


@unittest.skipUnless(DISPLAY, 'Native GTK checks need a graphical display')
class GuiTests(unittest.TestCase):
    def setUp(self):self.windows = [];self.calls = []

    def tearDown(self):
        for window in self.windows:window.destroy()
        for _ in range(30):
            if not Gtk.events_pending():break
            Gtk.main_iteration_do(False)

    def window(self, releases=None, failure=None):
        Gtk.Settings.get_default().set_property('gtk-theme-name', 'Adwaita-dark')
        def fake(args, progress, *, github_token=None):
            self.calls.append(args.command)
            if failure:raise InstallerError(failure)
            if args.command == 'releases':return releases or []
            if args.command == 'variants':return {'variants': [{'id':'base','name':'Base','local_ai':False}, {'id':'agent','name':'Agent','local_ai':True}]}
            raise AssertionError('GUI test must not invoke disk or download operations')
        window = create_window('example/PetalOS', dispatcher=fake)
        self.windows.append(window);return window

    def test_empty_release_state_is_explicit_and_not_an_empty_active_dropdown(self):
        window = self.window();message = find(window, 'petal-release-message')
        settle(lambda: 'No releases are published' in message.get_text())
        self.assertFalse(find(window, 'petal-version').get_sensitive())
        self.assertFalse(find(window, 'petal-variant').get_sensitive())

    def test_versions_and_build_choices_load_automatically(self):
        window = self.window([{'version':'test-version','installer_catalog':True}])
        variants = find(window, 'petal-variant')
        settle(lambda: variants.get_model().iter_n_children(None) == 2 and variants.get_sensitive())
        self.assertEqual(self.calls, ['releases','variants'])
        self.assertEqual(find(window,'petal-version').get_active_id(), 'test-version')
        self.assertEqual(variants.get_model()[1][0], 'Agent · local AI agent')

    def test_network_failure_stays_visible_on_the_build_page(self):
        window = self.window(failure='Could not reach GitHub.')
        settle(lambda: 'Could not reach GitHub' in find(window,'petal-release-message').get_text())
        self.assertEqual(find(window,'petal-pages').get_current_page(), 0)

    def test_forms_are_not_scrolled_and_irrelevant_options_are_hidden(self):
        window = self.window();settle(lambda: 'No releases are published' in find(window,'petal-release-message').get_text())
        notebook = find(window,'petal-pages')
        self.assertEqual(notebook.get_n_pages(), 4)
        for i in (0,1,3):
            self.assertFalse(any(isinstance(w,Gtk.ScrolledWindow) for w in descendants(notebook.get_nth_page(i))))
        mode = find(window,'petal-operation');mode.set_active_id('wipe')
        self.assertFalse(find(window,'petal-install-options').get_visible())
        self.assertTrue(find(window,'petal-wipe-options').get_visible())
        self.assertLessEqual(window.get_preferred_height_for_width(920)[0], 720)
        self.assertLessEqual(window.get_size()[1], 720)
        self.assertLessEqual(window.get_allocated_height(), 768)

    def test_dropdown_and_disabled_colours_remain_readable_on_dark_desktop(self):
        window = self.window();settle(lambda: 'No releases are published' in find(window,'petal-release-message').get_text())
        self.assertEqual(Gtk.Settings.get_default().get_property('gtk-theme-name'),'Adwaita')
        menu = Gtk.Menu();item = Gtk.MenuItem(label='Readable build');menu.append(item);menu.show_all();self.windows.append(menu)
        context = menu.get_style_context();bg = context.get_background_color(Gtk.StateFlags.NORMAL)
        fg = item.get_child().get_style_context().get_color(Gtk.StateFlags.NORMAL)
        self.assertGreaterEqual(bg.alpha,.99);self.assertGreaterEqual(contrast(fg,bg),4.5)
        button = Gtk.Button(label='Unavailable build');button.set_sensitive(False)
        context = button.get_style_context()
        fg = context.get_color(Gtk.StateFlags.INSENSITIVE);bg = context.get_background_color(Gtk.StateFlags.INSENSITIVE)
        self.assertGreaterEqual(contrast(fg,bg),4.5)

    def test_bloom_protection_choices_and_options_fit_without_scrolling(self):
        window = self.window();settle(lambda: 'No releases are published' in find(window, 'petal-release-message').get_text())
        self.assertEqual(window.get_title(), 'Bloom')
        failures = []
        def inspect():
            dialog = next(w for w in Gtk.Window.list_toplevels() if isinstance(w, Gtk.Dialog) and w.get_title() == 'Bloom · Installation options')
            try:
                combo = find(dialog, 'bloom-encryption-tier')
                self.assertEqual(combo.get_model().iter_n_children(None), 3)
                self.assertEqual(combo.get_active_id(), 'balanced')
                for ident, text in [('fast', '32–64 MiB'), ('balanced', '256–512 MiB'), ('paranoid', '1–2 GiB')]:
                    combo.set_active_id(ident)
                    self.assertIn(text, find(dialog, 'bloom-encryption-description').get_text())
                self.assertFalse(any(isinstance(w, Gtk.ScrolledWindow) for w in descendants(dialog)))
                self.assertLessEqual(dialog.get_preferred_height_for_width(700)[0], 700)
            except BaseException as error:failures.append(error)
            finally:dialog.response(Gtk.ResponseType.CANCEL)
            return False
        GLib.idle_add(inspect)
        next(w for w in descendants(window) if isinstance(w, Gtk.Button) and w.get_label() == 'Installation options…').clicked()
        if failures:raise failures[0]


if __name__ == '__main__':unittest.main()
