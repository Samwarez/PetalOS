"""Native GTK regressions: run in a Linux desktop; safely skip without a display.

Uses in-memory release responses and never invokes a disk operation or backend.
"""
from pathlib import Path
import sys
import time
import unittest
import tempfile
import threading
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, GLib
    DISPLAY = Gtk.init_check()[0]
except (ImportError, ValueError):DISPLAY = False
from petal_installer import InstallerError
from petal_installer.gui import create_window, password_meter


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
    def test_native_editor_opens_file_manager_once_and_retries_save_without_reauthorization(self):
        from petal_installer.native_store_gui import edit_store
        attempts = [];instances = [];opened = [];failures = [];stage = [0];deadline = time.monotonic() + 10
        class Session:
            def __init__(self,request,credentials,event):
                self.workspace=Path('/tmp/synthetic-editor-folder');self.cancel=threading.Event();self.event=event
                self.credentials=credentials;instances.append(self)
            def start(self):
                self.credentials.clear();self.event({'type':'editor-ready','value':{'workspace':str(self.workspace)}})
            def send(self,action):
                attempts.append(action)
                if len(attempts)==1:self.event({'type':'editor-error','value':{'message':'Synthetic validation failure.'}})
                else:self.event({'type':'editor-closed','value':{'saved':True}})
        def inspect():
            dialog=next((w for w in Gtk.Window.list_toplevels() if w.get_name()=='bloom-native-store' and w.get_visible()),None)
            if dialog is None:return True
            try:
                if time.monotonic()>deadline:raise AssertionError('Native editor test did not finish')
                save=next(w for w in descendants(dialog) if isinstance(w,Gtk.Button) and w.get_label()=='Save changes and lock')
                if not save.get_sensitive():return True
                if stage[0]==0:
                    self.assertIn('synthetic-editor-folder',find(dialog,'bloom-editor-path').get_text())
                    self.assertLessEqual(dialog.get_preferred_height_for_width(620)[0],700)
                    stage[0]=1;dialog.response(2)
                elif stage[0]==1 and find(dialog,'bloom-editor-status').get_text()=='Synthetic validation failure.':
                    next(w for w in descendants(dialog) if isinstance(w,Gtk.Button) and w.get_label()=='Open folder').clicked()
                    stage[0]=2;dialog.response(2);return False
            except BaseException as error:failures.append(error);dialog.response(1);return False
            return True
        GLib.timeout_add(30,inspect)
        credentials={'system':'synthetic-only'}
        saved=edit_store(Gtk,GLib,None,{'target':{'path':'/dev/fixture'},'plan_sha256':'fixture'},credentials,
                         session_factory=Session,opener=opened.append)
        if failures:raise failures[0]
        self.assertTrue(saved);self.assertEqual(credentials,{})
        self.assertEqual(len(instances),1);self.assertEqual(attempts,['save','save']);self.assertEqual(len(opened),2)

    def test_native_editor_reports_fatal_error_after_session_cleanup(self):
        from petal_installer.native_store_gui import edit_store
        class Session:
            workspace=Path('/tmp/synthetic-editor');cancel=threading.Event()
            def __init__(self,request,credentials,event):self.event=event
            def start(self):
                self.event({'type':'error','message':'Synthetic authorization failure.'})
                self.event({'type':'editor-closed','value':None})
        credentials={'system':'synthetic-only'}
        with self.assertRaisesRegex(InstallerError,'Synthetic authorization failure'):
            edit_store(Gtk,GLib,None,{'target':{'path':'/dev/fixture'},'plan_sha256':'fixture'},credentials,
                       session_factory=Session,opener=lambda *_:None)
        self.assertEqual(credentials,{})

    def test_system_browser_navigates_and_manages_saved_files_without_private(self):
        from petal_installer.store_gui import browse_store
        from petal_installer import store_browser
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory);(state / 'Desktop').mkdir()
            (state / 'Desktop/preferences.json').write_text('{}')
            plan = {'target': {'model': 'Synthetic card', 'path': '/dev/gui-fixture'}, 'plan_sha256': 'fixture'}
            calls = [];failures = [];stage = [0];deadline = time.monotonic() + 15
            def execute(request, credentials, completed, failed):
                self.assertEqual(set(credentials), {'system'});credentials.clear();calls.append(request)
                def finish():
                    try:
                        value = store_browser.browse(state, request['path']) if request['action'] == 'browse' else store_browser.change(state, request)
                        completed(value)
                    except BaseException as error:failed(str(error))
                    return False
                GLib.idle_add(finish);return threading.Event()
            def button(dialog, title):return next(w for w in descendants(dialog) if isinstance(w, Gtk.Button) and w.get_label() == title)
            def activate(tree, destination):
                index = next(i for i, row in enumerate(tree.get_model()) if row[3] == destination)
                tree.row_activated(Gtk.TreePath.new_from_indices([index]), tree.get_column(0))
            def inspect():
                dialog = next((w for w in Gtk.Window.list_toplevels() if w.get_name() == 'bloom-store-browser' and w.get_visible()), None)
                if dialog is None:return True
                try:
                    if time.monotonic() > deadline:raise AssertionError('SYSTEM browser did not complete its test flow')
                    tree = find(dialog, 'bloom-store-files');model = tree.get_model()
                    if not tree.get_sensitive():return True
                    path = find(dialog, 'bloom-store-path').get_text()
                    if stage[0] == 0 and 'saved-settings folders' in path:
                        self.assertFalse(button(dialog, 'Add file…').get_sensitive())
                        self.assertTrue(all('Private' not in row[0] for row in model))
                        stage[0] = 1;activate(tree, 'Files')
                    elif stage[0] == 1 and path == 'SYSTEM / Files':
                        self.assertTrue(button(dialog, 'Add file…').get_sensitive())
                        def name_folder():
                            question = next(w for w in Gtk.Window.list_toplevels() if isinstance(w, Gtk.Dialog) and w.get_title() == 'New folder')
                            next(w for w in descendants(question) if isinstance(w, Gtk.Entry)).set_text('Notes')
                            question.response(Gtk.ResponseType.OK);return False
                        stage[0] = 2;GLib.idle_add(name_folder);button(dialog, 'New folder…').clicked()
                    elif stage[0] == 2 and any(row[0] == 'Notes' for row in model):
                        self.assertTrue((state / 'Files/Notes').is_dir())
                        self.assertLessEqual(dialog.get_preferred_height_for_width(760)[0], 700)
                        stage[0] = 3;button(dialog, 'Up').clicked()
                    elif stage[0] == 3 and 'saved-settings folders' in path:
                        stage[0] = 4;activate(tree, 'Desktop')
                    elif stage[0] == 4 and path == 'SYSTEM / Desktop':
                        self.assertFalse(button(dialog, 'Add file…').get_sensitive())
                        tree.get_selection().select_path(Gtk.TreePath.new_from_indices([0]))
                        self.assertFalse(button(dialog, 'Delete…').get_sensitive())
                        stage[0] = 5;dialog.response(Gtk.ResponseType.CLOSE);return False
                except BaseException as error:
                    failures.append(error);dialog.response(Gtk.ResponseType.CLOSE);return False
                return True
            GLib.timeout_add(30, inspect)
            browse_store(Gtk, GLib, None, plan, 'synthetic-only', execute)
            if failures:raise failures[0]
            self.assertEqual(stage[0], 5)
            self.assertTrue(all(call['mode'] == 'store' for call in calls))

    def test_system_browser_failure_stays_visible_and_can_be_closed(self):
        from petal_installer.store_gui import browse_store
        plan = {'target': {'model': 'Synthetic card', 'path': '/dev/gui-fixture'}, 'plan_sha256': 'fixture'}
        def execute(request, credentials, completed, failed):
            credentials.clear();GLib.idle_add(lambda: (failed('Synthetic safe failure.'), False)[1]);return threading.Event()
        failures = [];deadline = time.monotonic() + 10
        def inspect():
            dialog = next((w for w in Gtk.Window.list_toplevels() if w.get_name() == 'bloom-store-browser' and w.get_visible()), None)
            if dialog is None:return True
            try:
                if time.monotonic() > deadline:raise AssertionError('Browser error did not become visible')
                if find(dialog, 'bloom-store-status').get_text() != 'Synthetic safe failure.':return True
                self.assertTrue(next(w for w in descendants(dialog) if isinstance(w, Gtk.Button) and w.get_label() == 'Close and lock').get_sensitive())
            except BaseException as error:failures.append(error)
            dialog.response(Gtk.ResponseType.CLOSE);return False
        GLib.timeout_add(30, inspect);browse_store(Gtk, GLib, None, plan, 'synthetic-only', execute)
        if failures:raise failures[0]

    def test_install_dialog_has_three_live_meters_and_fits_a_small_screen(self):
        record = {'path': '/dev/gui-test', 'model': 'Synthetic GUI target', 'bytes': 32 * 1024**3, 'eligible': True}
        def fake(args, progress, **kwargs):
            if args.command == 'devices':return [record]
            if args.command == 'verify':return {'version': 'gui-test', 'variant': 'base'}
            if args.command == 'install':return {'mode': 'install', 'target': record, 'encryption': {'id': 'paranoid'}}
            raise AssertionError('GUI fixture cannot perform a real operation')
        window = create_window('example/PetalOS', dispatcher=fake, autoload=False)
        self.windows.append(window)
        def click(title):
            next(w for w in descendants(window) if isinstance(w, Gtk.Button) and w.get_label() == title).clicked()
        with tempfile.TemporaryDirectory() as directory, patch('petal_installer.gui.local_build_message', return_value=None):
            chooser = next(w for w in descendants(window) if isinstance(w, Gtk.FileChooserButton))
            chooser.set_filename(directory)
            settle(lambda: bool(chooser.get_filename()))
            click('Check and use this build')
            settle(lambda: find(window, 'petal-pages').get_current_page() == 1)
            click('Refresh drives')
            settle(lambda: any(isinstance(w, Gtk.ComboBoxText) and w.get_active_id() == record['path'] for w in descendants(window)))
            click('Review before starting')
            start = next(w for w in descendants(window) if isinstance(w, Gtk.Button) and w.get_label() == 'Start reviewed operation…')
            settle(start.get_sensitive)
            failures = []
            def inspect():
                dialog = next(w for w in Gtk.Window.list_toplevels() if isinstance(w, Gtk.Dialog) and w.get_visible() and w.get_title() == 'Confirm install')
                try:
                    for role, minimum in [('system', 15), ('administrator', 15), ('private', 24)]:
                        entry = find(dialog, 'bloom-password-' + role)
                        self.assertFalse(entry.get_visibility())
                        entry.set_text('a' * minimum)
                        meter = find(dialog, 'bloom-strength-' + role)
                        self.assertIn('Very weak', meter.get_text())
                        self.assertIn('minimum met', meter.get_text())
                    self.assertLessEqual(dialog.get_preferred_height_for_width(620)[0], 700)
                except BaseException as error:failures.append(error)
                finally:dialog.response(Gtk.ResponseType.CANCEL)
                return False
            GLib.idle_add(inspect);start.clicked()
            if failures:raise failures[0]

    def test_password_meter_updates_while_typing_and_clears(self):
        from petal_installer.passwords import MINIMUM_CHARACTERS
        for role, minimum in MINIMUM_CHARACTERS.items():
            entry = Gtk.Entry(visibility=False)
            meter = password_meter(Gtk, entry, role)
            self.assertFalse(entry.get_visibility())
            self.assertIn(str(minimum), meter.get_text())
            entry.set_text('a' * minimum)
            self.assertIn('Very weak', meter.get_text())
            self.assertIn('minimum met', meter.get_text())
            weak = meter.get_fraction()
            entry.set_text('m8T!r4W#p9L$k2V%z7N@x6Q&')
            self.assertGreater(meter.get_fraction(), weak)
            entry.set_text('')
            self.assertEqual(meter.get_fraction(), 0)
            self.assertEqual(meter.get_text(), 'At least ' + str(minimum) + ' characters')
            entry.destroy();meter.destroy()

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
