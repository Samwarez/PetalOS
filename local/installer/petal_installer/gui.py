"""GTK overlay: unscrolled task pages, reviewed core operations, private IPC."""
from pathlib import Path
import threading

from . import InstallerError
from .cli import dispatch, human, parser
from .plans import ENCRYPTION, WIPE_METHODS
from .presentation import local_build_message, release_choices, variant_title
from .encryption import SHARED_EXPLANATION, PORTABILITY_EXPLANATION
from .passwords import MINIMUM_CHARACTERS, strength

ASSETS = Path(__file__).with_name('assets')


def password_meter(Gtk, entry, role):
    """A local, advisory gauge; entry contents never leave this process."""
    meter = Gtk.ProgressBar(show_text=True)
    meter.set_name('bloom-strength-' + role)
    meter.set_tooltip_text('Local estimate of common words and patterns, not a security guarantee. '
                          'Use unique, randomly chosen words or characters. Estimates use up to '
                          '128 ASCII characters; other text may not have an estimate.')
    def changed(*_):
        result = strength(entry.get_text(), role)
        meter.set_fraction(result['score'] / 4)
        meter.set_text(result['text'])
        style = meter.get_style_context()
        for score in range(5):style.remove_class('strength-' + str(score))
        style.add_class('strength-' + str(result['score']))
    entry.connect('changed', changed);changed()
    return meter


def create_window(repository, *, dispatcher=dispatch, autoload=True):
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango
    except (ImportError, ValueError):
        raise InstallerError('The GUI needs python3-gi and gir1.2-gtk-3.0. The CLI is available without them.') from None
    if not Gtk.init_check()[0]:
        raise InstallerError('No graphical display is available. Run gui from your Linux desktop; the CLI works here.')
    # These are this process's GTK settings, never desktop configuration writes.
    appearance = Gtk.Settings.get_default()
    appearance.set_property('gtk-application-prefer-dark-theme', False)
    appearance.set_property('gtk-theme-name', 'Adwaita')
    style = Gtk.CssProvider();style.load_from_path(str(ASSETS / 'pink.css'))
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    window = Gtk.Window(title='Bloom');window.set_default_size(920, 620)
    window.set_wmclass('bloom', 'Bloom')
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10);root.set_border_width(12);window.add(root)

    def label(text, css=None):
        widget = Gtk.Label(label=text, xalign=0);widget.set_line_wrap(True);widget.set_max_width_chars(85)
        widget.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        if css:widget.get_style_context().add_class(css)
        return widget

    banner = Gtk.Box(spacing=14)
    emblem = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ASSETS / 'petal-emblem.png'), 48, 48, True)
    banner.pack_start(Gtk.Image.new_from_pixbuf(emblem), False, False, 0);window.set_icon(emblem)
    headings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
    headings.add(label('Bloom', 'brand'))
    headings.add(label('A fresh start for PetalOS. Choose your build, drive and protection.', 'subtitle'))
    banner.pack_start(headings, True, True, 0);root.pack_start(banner, False, False, 0)
    tabs = Gtk.Notebook();tabs.set_name('petal-pages');root.pack_start(tabs, True, True, 0)
    rules = [];job = {'busy': False, 'cancel': None, 'closed': False};auth = {'token': None}
    review = {'plan': None, 'bundle': None};chosen = {'directory': None}
    results = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
    results.set_left_margin(12);results.set_right_margin(12)
    spinner = Gtk.Spinner();progressbar = Gtk.ProgressBar(show_text=True)
    status = label('Checking available releases…', 'subtitle')

    def policy(widget, allowed=lambda: True):
        rules.append((widget, allowed));return widget

    def sync():
        if job['closed']:return
        for widget, allowed in rules:widget.set_sensitive(not job['busy'] and bool(allowed()))

    def invalidate(*_):
        review['plan'] = None;sync()

    def set_result(text):results.get_buffer().set_text(text)

    def invoke(words=None, completed=None, failed=None, privileged_job=None, show_result=False):
        if job['busy']:return
        job['busy'] = True;spinner.start();sync();status.set_text('Working…')
        progressbar.set_fraction(0);progressbar.set_text('Working')
        if show_result:tabs.set_current_page(2)
        token = auth['token']
        def finish(value, error):
            if job['closed']:return False
            job['busy'] = False;job['cancel'] = None;spinner.stop()
            status.set_text('Stopped. See the message on this page.' if error else 'Done.')
            progressbar.set_fraction(0 if error else 1);progressbar.set_text('Stopped' if error else 'Complete')
            if show_result:set_result(error or human(value))
            if error and not failed:
                set_result(error);tabs.set_current_page(2)
            callback = failed if error else completed
            # Apply the result before enabling inputs. A callback may start
            # the next job (version -> builds); its busy state wins below.
            if callback:callback(error if error else value)
            sync()
            return False
        def progress(event):
            if job['closed']:return False
            title = event.get('stage', 'Working').replace('-', ' ').capitalize();status.set_text(title)
            if event.get('total'):
                fraction = min(1, event['bytes'] / event['total']);progressbar.set_fraction(fraction)
                progressbar.set_text(str(round(fraction * 100)) + '%')
            else:progressbar.pulse();progressbar.set_text(title)
            return False
        def work():
            try:
                if privileged_job:
                    from .bridge import privileged
                    request, credentials = privileged_job
                    value = privileged(request, credentials, lambda event: GLib.idle_add(progress, event), job['cancel'])
                else:
                    args = parser().parse_args(['--repo', repository, *words])
                    value = dispatcher(args, lambda event: GLib.idle_add(progress, event), github_token=token)
                GLib.idle_add(finish, value, None)
            except InstallerError as error:GLib.idle_add(finish, None, str(error))
            except BaseException:GLib.idle_add(finish, None, 'Operation stopped. No raw diagnostic data was displayed.')
        threading.Thread(target=work, daemon=True).start()

    def page(title):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10);box.set_border_width(12)
        tabs.append_page(box, Gtk.Label(label=title));return box

    def field(box, title, widget):
        row = Gtk.Box(spacing=12);heading = label(title);heading.set_size_request(145, -1)
        row.pack_start(heading, False, False, 0);row.pack_start(widget, True, True, 0)
        box.pack_start(row, False, False, 0);return widget

    def button(box, title, callback, primary=False, allowed=lambda: True):
        widget = Gtk.Button(label=title)
        if primary:widget.get_style_context().add_class('suggested-action')
        widget.connect('clicked', callback);box.pack_start(widget, False, False, 0);return policy(widget, allowed)

    def error_dialog(text):
        dialog = Gtk.MessageDialog(transient_for=window, modal=True, message_type=Gtk.MessageType.ERROR,
                                   buttons=Gtk.ButtonsType.OK, text=text)
        dialog.run();dialog.destroy()

    build = page('1 · Choose build')
    build.add(label('Where is your PetalOS build?', 'section'))
    source = Gtk.ComboBoxText();source.append('online', 'Download from GitHub');source.append('local', 'Use an already downloaded build')
    source.set_active_id('online');field(build, 'Build source', policy(source))
    online = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9);build.pack_start(online, False, False, 0)
    release_message = label('Checking GitHub for published releases…', 'preview');release_message.set_name('petal-release-message');online.add(release_message)
    versions = Gtk.ComboBoxText();versions.set_name('petal-version');field(online, 'Release version', versions)
    variants = Gtk.ComboBoxText();variants.set_name('petal-variant');field(online, 'Build', variants)
    policy(versions, lambda: versions.get_model().iter_n_children(None) > 0)
    policy(variants, lambda: variants.get_model().iter_n_children(None) > 0)
    include_pre = policy(Gtk.CheckButton(label='Show prerelease versions'));online.add(include_pre)
    downloads = (Path.home() / 'Downloads' / 'PetalOS').resolve()
    cache = {'parent': downloads}
    def version_changed(_):
        variants.remove_all();selected(None, 'No build selected.')
        if not versions.get_active_id():return
        release_message.set_text('Loading builds for ' + versions.get_active_id() + '…')
        def filled(record):
            for variant in record['variants']:variants.append(variant['id'], variant_title(variant))
            variants.set_active(0);release_message.set_text('Choose a build, then download it below.')
        invoke(['variants', '--version', versions.get_active_id()], filled,
               lambda error: release_message.set_text('Could not load builds. ' + error))
    versions.connect('changed', version_changed);variants.connect('changed', lambda _: selected(None, 'No build selected.'))
    def refreshed(records):
        choices, message = release_choices(records);release_message.set_text(message)
        for record in choices:versions.append(record['version'], record['version'])
        if choices:versions.set_active(0)
        else:status.set_text('No installer-ready releases are available yet.')
    def refresh(*_):
        if job['busy']:return
        versions.remove_all();variants.remove_all();release_message.set_text('Checking GitHub for published releases…')
        invoke(['releases'] + (['--prereleases'] if include_pre.get_active() else []), refreshed,
               lambda error: release_message.set_text('Could not load releases. ' + error + ' For a private repository, use GitHub access below.'))
    buttons = Gtk.Box(spacing=8);online.add(buttons)
    button(buttons, 'Refresh releases', refresh)
    def github_access(_):
        dialog = Gtk.Dialog(title='GitHub access', transient_for=window, modal=True)
        dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Use token', Gtk.ResponseType.OK)
        content = dialog.get_content_area();content.set_border_width(16);content.set_spacing(10)
        content.add(label('For a private repository, enter a GitHub token with read access to its contents. It stays in this app session and is not saved.'))
        entry = Gtk.Entry(visibility=False);entry.set_input_purpose(Gtk.InputPurpose.PASSWORD);content.add(entry)
        content.show_all();answer = dialog.run();token = entry.get_text();entry.set_text('');dialog.destroy()
        if answer == Gtk.ResponseType.OK:auth['token'] = token or None;refresh()
    button(buttons, 'GitHub access…', github_access)
    include_pre.connect('toggled', refresh)
    def change_location(_):
        dialog = Gtk.FileChooserDialog(title='Save downloaded builds in…', transient_for=window, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Choose folder', Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:cache['parent'] = Path(dialog.get_filename()).resolve()
        dialog.destroy()
    button(buttons, 'Save location…', change_location)
    def selected(directory, description):
        chosen['directory'] = directory;invalidate();selection.set_text(description)
    def downloaded(record):
        selected(record['directory'], 'Ready: ' + record['version'] + ' · ' + variants.get_active_text())
        tabs.set_current_page(1)
    def download(_):
        version, variant = versions.get_active_id(), variants.get_active_id()
        if not version or not variant:return
        try:cache['parent'].mkdir(parents=True, exist_ok=True)
        except OSError:
            release_message.set_text('Cannot create the download folder. Choose another Save location.');return
        target = cache['parent'] / ('petalos-' + version.replace('/', '_') + '-' + variant)
        # Reusing a previous completed download verifies it instead of overwriting.
        if target.exists():
            invoke(['verify', str(target)], lambda value: selected(str(target), 'Ready: ' + value['version'] + ' · ' + value['variant']),
                   lambda error: release_message.set_text(error));return
        invoke(['download', '--version', version, '--variant', variant, '--destination', str(target)], downloaded,
               lambda error: release_message.set_text(error), show_result=True)
    button(online, 'Download selected build', download, True,
           lambda: bool(versions.get_active_id() and variants.get_active_id()))
    local = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10);build.pack_start(local, False, False, 0)
    local.add(label('Select the folder downloaded by Bloom. It contains the build information and OS files; an ISO alone is not supported.', 'preview'))
    local_folder = Gtk.FileChooserButton(title='Choose a downloaded PetalOS build folder', action=Gtk.FileChooserAction.SELECT_FOLDER)
    field(local, 'Downloaded build', policy(local_folder));local_folder.connect('selection-changed', lambda _: selected(None, 'Check the selected folder before using it.'))
    local_message = label('Choose a folder, then check its build files.', 'subtitle');local.add(local_message)
    def verify_local(_):
        directory = local_folder.get_filename()
        if not directory:return
        message = local_build_message(directory)
        if message:local_message.set_text(message);return
        local_message.set_text('Checking build files…')
        def verified(record):
            text = 'Ready: ' + record['version'] + ' · ' + record['variant']
            selected(directory, text);local_message.set_text(text);tabs.set_current_page(1)
        invoke(['verify', directory], verified, local_message.set_text)
    button(local, 'Check and use this build', verify_local, True, lambda: bool(local_folder.get_filename()))
    selection = label('No build selected.', 'subtitle');build.add(selection)
    def source_changed(*_):
        selected(None, 'No build selected.')
        online.set_visible(source.get_active_id() == 'online');local.set_visible(source.get_active_id() == 'local')
    source.connect('changed', source_changed)

    drive = page('2 · Choose drive')
    drive.add(label('What would you like to do?', 'section'))
    disks = Gtk.ComboBoxText();field(drive, 'Target drive', policy(disks));disks.connect('changed', invalidate)
    drive_message = label('Refresh to find idle USB drives and cards.', 'subtitle');drive.add(drive_message)
    def fill_disks(records):
        disks.remove_all()
        for disk in records:
            if disk['eligible']:disks.append(disk['path'], disk['model'] + ' · ' + str(round(disk['bytes'] / 1024**3, 1)) + ' GiB · ' + disk['path'])
        disks.set_active(0);drive_message.set_text('Choose the exact drive to manage.' if disks.get_active_id() else 'No idle USB drive or card found. Connect one, then refresh.')
    button(drive, 'Refresh drives', lambda _: invoke(['devices'], fill_disks, drive_message.set_text))
    modes = Gtk.ComboBoxText();modes.set_name('petal-operation')
    for ident, text in [('install', 'Fresh install'), ('update', 'Update existing PetalOS'), ('wipe', 'Wipe drive'), ('system-store', 'Manage SYSTEM settings')]:modes.append(ident, text)
    modes.set_active_id('install');field(drive, 'Operation', policy(modes))
    operation_message = label('', 'preview');drive.add(operation_message)
    install_options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8);install_options.set_name('petal-install-options');drive.add(install_options)
    install_preferences = {'encryption': 'balanced', 'erase_mode': 'random'}
    install_summary = label('Balanced — Recommended · overwrite and verify old data first.', 'subtitle');install_options.add(install_summary)
    def installation_options(_):
        dialog = Gtk.Dialog(title='Bloom · Installation options', transient_for=window, modal=True)
        dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Use these options', Gtk.ResponseType.OK)
        dialog.set_default_size(700, -1)
        content = dialog.get_content_area();content.set_border_width(16);content.set_spacing(12)
        encryption = Gtk.ComboBoxText();encryption.set_name('bloom-encryption-tier')
        for ident, profile in ENCRYPTION.items():encryption.append(ident, profile['name'])
        encryption.set_active_id(install_preferences['encryption']);field(content, 'Protection tier', encryption)
        hint = label(ENCRYPTION[encryption.get_active_id()]['description'], 'subtitle');hint.set_name('bloom-encryption-description');content.add(hint)
        encryption.connect('changed', lambda _: hint.set_text(ENCRYPTION[encryption.get_active_id()]['description']))
        content.add(label(SHARED_EXPLANATION, 'subtitle'))
        content.add(label(PORTABILITY_EXPLANATION, 'subtitle'))
        overwrite = Gtk.CheckButton(label='Overwrite and verify old data first (slower)')
        overwrite.set_active(install_preferences['erase_mode'] == 'random');content.add(overwrite)
        content.add(label('Turning this off creates new stores but does not securely erase old flash contents.', 'preview'))
        content.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            install_preferences.update(encryption=encryption.get_active_id(), erase_mode='random' if overwrite.get_active() else 'quick')
            install_summary.set_text(ENCRYPTION[install_preferences['encryption']]['name'] + ' encryption · ' + ('overwrite and verify old data first.' if overwrite.get_active() else 'quick setup; old data is not securely overwritten.'))
            invalidate()
        dialog.destroy()
    button(install_options, 'Installation options…', installation_options)
    wipe_options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8);wipe_options.set_name('petal-wipe-options');drive.add(wipe_options)
    wipe = Gtk.ComboBoxText()
    for ident, text in zip(WIPE_METHODS, ['Remove encryption keys, then overwrite and verify', 'Remove encryption keys only (quick)', 'Overwrite and verify only']):wipe.append(ident, text)
    wipe.set_active_id('keys-and-random');field(wipe_options, 'Wipe method', policy(wipe))
    wipe_options.add(label('Key removal cannot revoke a saved header backup. Overwrite covers visible sectors; flash spare/remapped pages are outside host control.', 'subtitle'))
    def mode_changed(*_):
        invalidate();mode = modes.get_active_id()
        install_options.set_visible(mode == 'install');wipe_options.set_visible(mode == 'wipe')
        operation_message.set_text({'install': 'Fresh install erases the entire selected drive and creates new encrypted OS, SYSTEM and Private stores.',
            'update': 'Update replaces only the OS and boot selection. SYSTEM settings and Private stay closed and unchanged.',
            'wipe': 'Wiping permanently removes the selected keys and/or overwrites the drive.',
            'system-store': 'Open SYSTEM settings using its passphrase. Private stays closed.'}[mode])
    modes.connect('changed', mode_changed)
    wipe.connect('changed', invalidate)
    def plan(_):
        mode, disk = modes.get_active_id(), disks.get_active_id()
        if not disk:drive_message.set_text('Connect a drive, refresh and select it first.');return
        if mode == 'system-store':tabs.set_current_page(3);return
        if mode in ('install', 'update') and not chosen['directory']:
            tabs.set_current_page(0);selection.set_text('Choose and verify a build first.');return
        words = [mode, '--device', disk]
        if mode in ('install', 'update'):words += ['--bundle', chosen['directory']]
        if mode == 'install':words += ['--encryption', install_preferences['encryption'], '--erase-mode', install_preferences['erase_mode']]
        if mode == 'wipe':words += ['--method', wipe.get_active_id()]
        def reviewed(value):review.update(plan=value, bundle=chosen['directory'])
        invoke(words, reviewed, show_result=True)
    button(drive, 'Review before starting', plan, True)

    review_page = page('3 · Review & results')
    review_page.add(label('Review the drive and operation before starting.', 'section'))
    # Only long review/results text scrolls; forms are ordinary full-size pages.
    scroller = Gtk.ScrolledWindow();scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.add(results);review_page.pack_start(scroller, True, True, 0)
    def start_operation(_):
        current = review['plan']
        if not current:return
        from .engine import credentials_checked
        from .bridge import request_from_plan
        dialog = Gtk.Dialog(title='Confirm ' + current['mode'], transient_for=window, modal=True)
        dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Start ' + current['mode'], Gtk.ResponseType.OK)
        dialog.set_default_size(620, -1)
        content = dialog.get_content_area();content.set_border_width(16);content.set_spacing(6)
        target = current['target']
        content.add(label(target['model'] + ' · ' + str(round(target['bytes'] / 1024**3, 1)) + ' GiB\n' + target['path'], 'section'))
        content.add(label('This erases the selected drive.' if current['mode'] in ('install', 'wipe') else 'Only OS contents and boot selection will change.'))
        roles = ('system', 'private', 'administrator') if current['mode'] == 'install' else ('system',) if current['mode'] == 'update' else ()
        entries = {};confirmations = {}
        for role in roles:
            title = {'system': 'SYSTEM passphrase', 'private': 'Private passphrase', 'administrator': 'PetalOS admin password'}[role]
            entry = Gtk.Entry(visibility=False);entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
            entry.set_name('bloom-password-' + role)
            entries[role] = entry
            if current['mode'] == 'install':
                group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                entry.set_placeholder_text('At least ' + str(MINIMUM_CHARACTERS[role]) + ' characters')
                group.pack_start(entry, False, False, 0)
                group.pack_start(password_meter(Gtk, entry, role), False, False, 0)
                field(content, title, group)
                other = Gtk.Entry(visibility=False);other.set_input_purpose(Gtk.InputPurpose.PASSWORD);confirmations[role] = field(content, 'Confirm', other)
            else:field(content, title, entry)
        if current['mode'] == 'install':
            content.add(label('SYSTEM unlocks OS and settings together. Private and administrator passphrases must each be different. '
                             'Minimums: SYSTEM and admin 15 characters; Private 24. '
                             'Strength estimates run locally and are guidance, not a guarantee.', 'subtitle'))
        typed = field(content, 'Type ERASE', Gtk.Entry()) if current['mode'] in ('install', 'wipe') else None
        content.add(label('Linux administrator authorization is requested separately. Passwords are not saved.', 'subtitle'))
        content.show_all();values = None
        while dialog.run() == Gtk.ResponseType.OK:
            try:
                if typed and typed.get_text() != 'ERASE':raise InstallerError('Type ERASE to confirm this drive.')
                values = {role: entry.get_text() for role, entry in entries.items()}
                if any(values[role] != entry.get_text() for role, entry in confirmations.items()):raise InstallerError('Password confirmation did not match.')
                credentials_checked(values, current['mode'], encryption=current.get('encryption', {}).get('id', 'balanced'));break
            except InstallerError as error:values = None;error_dialog(str(error))
        for entry in [*entries.values(), *confirmations.values()]:entry.set_text('')
        dialog.destroy()
        if values is None:return
        request = request_from_plan(current, review['bundle']);invalidate();job['cancel'] = threading.Event()
        invoke(privileged_job=(request, values), show_result=True)
    button(review_page, 'Start reviewed operation…', start_operation, True, lambda: review['plan'] is not None)

    settings = page('SYSTEM settings')
    settings.add(label('Prepare your next boot.', 'section'))
    settings.add(label('Select a drive on Choose drive. Open SYSTEM to view or preload settings; Private stays closed.', 'preview'))
    settings_kind = Gtk.ComboBoxText()
    for ident, title in [('vpn', 'WireGuard VPN profile'), ('wallpaper', 'PNG wallpaper'), ('theme', 'Theme palette (inactive)'), ('override', 'Desktop overrides (inactive)')]:settings_kind.append(ident, title)
    settings_kind.set_active_id('vpn');field(settings, 'Import type', policy(settings_kind))
    settings_source = Gtk.FileChooserButton(title='Choose a file to preload', action=Gtk.FileChooserAction.OPEN);field(settings, 'Source file', policy(settings_source))
    settings_name = Gtk.Entry();settings_name.set_placeholder_text('For example: home');field(settings, 'Stored name', policy(settings_name))
    replace_existing = policy(Gtk.CheckButton(label='Replace this exact stored name if it exists'));settings.add(replace_existing)
    def settings_action(action):
        disk = disks.get_active_id()
        if not disk:error_dialog('Choose a drive on Choose drive first.');return
        if action == 'import' and (not settings_source.get_filename() or not settings_name.get_text()):error_dialog('Choose a source file and stored name.');return
        def ready(value):
            dialog = Gtk.Dialog(title='Unlock SYSTEM settings', transient_for=window, modal=True)
            dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Unlock', Gtk.ResponseType.OK)
            body = dialog.get_content_area();body.set_border_width(16);body.set_spacing(10)
            body.add(label(value['target']['model'] + '\n' + value['target']['path'], 'section'))
            password = Gtk.Entry(visibility=False);password.set_input_purpose(Gtk.InputPurpose.PASSWORD);field(body, 'SYSTEM passphrase', password)
            if action == 'import':body.add(label('Import ' + settings_name.get_text() + (' · replacing that name if present.' if replace_existing.get_active() else ' · existing files are preserved.')))
            body.show_all();response = dialog.run();secret = password.get_text();password.set_text('');dialog.destroy()
            if response != Gtk.ResponseType.OK:return
            if action == 'browse':
                from .native_store_gui import edit_store
                credentials = {'system': secret}
                secret = None
                job['busy'] = True;spinner.start();sync()
                try:
                    saved = edit_store(Gtk, GLib, window, value, credentials,
                                       session_created=lambda session: job.update(cancel=session.cancel))
                    status.set_text('SYSTEM changes saved and locked.' if saved else 'SYSTEM locked; unsaved changes discarded.')
                except InstallerError as error:error_dialog(str(error))
                finally:job['busy'] = False;job['cancel'] = None;spinner.stop();sync()
                return
            request = {'mode': 'recovery' if action == 'recovery' else 'store', 'device': disk, 'plan_sha256': value['plan_sha256']}
            if action != 'recovery':request['action'] = action
            if action == 'import':request.update(kind=settings_kind.get_active_id(), source=settings_source.get_filename(), name=settings_name.get_text(), replace=replace_existing.get_active())
            job['cancel'] = threading.Event();invoke(privileged_job=(request, {'system': secret}), show_result=True)
        invoke(['system-store', '--device', disk], ready)
    button(settings, 'Import selected file…', lambda _: settings_action('import'), True)
    maintenance = Gtk.Box(spacing=8);settings.add(maintenance)
    button(maintenance, 'Browse SYSTEM folders…', lambda _: settings_action('browse'))
    button(maintenance, 'List saved settings', lambda _: settings_action('list'))
    button(maintenance, 'Check SYSTEM passphrase', lambda _: settings_action('recovery'))
    settings.add(label('Themes and overrides stay inactive until their OS loader is implemented.', 'subtitle'))
    footer = Gtk.Box(spacing=10);footer.pack_start(spinner, False, False, 0);footer.pack_start(status, True, True, 0)
    cancel = Gtk.Button(label='Stop operation');cancel.connect('clicked', lambda _: job['cancel'].set() if job['cancel'] else None)
    footer.pack_end(cancel, False, False, 0);root.pack_start(progressbar, False, False, 0);root.pack_start(footer, False, False, 0)
    def closing(*_):
        if job['busy'] and job['cancel']:
            job['cancel'].set();status.set_text('Stopping and cleaning up. Keep the drive connected.')
            return True
        return False
    def destroyed(*_):
        job['closed'] = True;auth.clear()
        if job['cancel']:job['cancel'].set()
    window.connect('delete-event', closing)
    window.connect('destroy', destroyed)
    # Choose visible panels before mapping the window. Showing every panel
    # first makes GTK permanently enlarge the initial window for hidden forms.
    root.show_all();source_changed();mode_changed();sync();window.show()
    if autoload:GLib.idle_add(lambda: (refresh(), False)[1])
    return window


def run(repository):
    window = create_window(repository)
    from gi.repository import Gtk
    window.connect('destroy', Gtk.main_quit);Gtk.main()
