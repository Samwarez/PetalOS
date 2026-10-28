"""Unprivileged SYSTEM file browser backed by short, confined worker requests."""
from pathlib import Path


def browse_store(Gtk, GLib, parent, plan, password, execute):
    dialog = Gtk.Dialog(title='Bloom · SYSTEM saved settings', transient_for=parent, modal=True)
    dialog.set_default_size(760, 570);dialog.set_name('bloom-store-browser')
    close = dialog.add_button('Close and lock', Gtk.ResponseType.CLOSE)
    body = dialog.get_content_area();body.set_border_width(12);body.set_spacing(8)
    heading = Gtk.Label(label=plan['target']['model'] + ' · ' + plan['target']['path'], xalign=0);body.add(heading)
    explanation = Gtk.Label(label='Browse saved settings; Private stays locked. Other saved files are stored without activating them as OS settings.', xalign=0)
    explanation.set_line_wrap(True);explanation.set_max_width_chars(90);body.add(explanation)
    path_label = Gtk.Label(label='SYSTEM', xalign=0);path_label.set_name('bloom-store-path');body.add(path_label)
    model = Gtk.ListStore(str, str, str, str)
    tree = Gtk.TreeView(model=model);tree.set_name('bloom-store-files')
    for index, title in enumerate(('Name', 'Type', 'Size')):
        column = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=index)
        if index == 0:column.set_expand(True)
        tree.append_column(column)
    scroll = Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroll.add(tree);body.pack_start(scroll, True, True, 0)
    actions = Gtk.Box(spacing=6);body.pack_start(actions, False, False, 0)
    message = Gtk.Label(label='Opening SYSTEM…', xalign=0);message.set_line_wrap(True);message.set_max_width_chars(90)
    message.set_name('bloom-store-status');body.add(message)
    session = {'password': password, 'busy': False, 'listing': None, 'cancel': None, 'closed': False}
    password = None

    def selected():
        current, iterator = tree.get_selection().get_selected()
        return current[iterator] if iterator is not None else None

    def sync(*_):
        if session['closed']:return
        listing = session['listing'] or {};row = selected();idle = not session['busy']
        close.set_sensitive(idle);tree.set_sensitive(idle)
        up.set_sensitive(idle and bool(listing.get('path')))
        refresh.set_sensitive(idle)
        add.set_sensitive(idle and listing.get('can_add', False))
        mkdir.set_sensitive(idle and listing.get('can_mkdir', False))
        rename.set_sensitive(idle and listing.get('can_add', False) and row is not None and row[1] == 'file')
        delete.set_sensitive(idle and listing.get('can_add', False) and row is not None and row[1] in ('file', 'folder'))
        stop.set_sensitive(not idle)

    def filled(value):
        if session['closed']:return
        session['busy'] = False;session['cancel'] = None;session['listing'] = value
        model.clear();path_label.set_text('SYSTEM / ' + value['path'] if value['path'] else 'SYSTEM · saved-settings folders')
        for item in value['entries']:
            destination = item.get('path', '/'.join(filter(None, (value['path'], item['name']))))
            model.append((item['name'], item['kind'], str(item['bytes']) + ' B' if item['kind'] == 'file' else '', destination))
        message.set_text(value.get('status', 'Choose a folder.' if not value['path'] else
                         'Add or manage files here.' if value['can_add'] else 'This folder is managed by PetalOS and is browse only.'))
        sync()

    def failed(error):
        if session['closed']:return
        session['busy'] = False;session['cancel'] = None;message.set_text(error);sync()

    def request(action, **fields):
        if session['closed'] or session['busy']:return
        session['busy'] = True;message.set_text('Working…');sync()
        value = {'mode': 'store', 'device': plan['target']['path'], 'plan_sha256': plan['plan_sha256'],
                 'action': action, 'path': (session['listing'] or {}).get('path', ''), **fields}
        session['cancel'] = execute(value, {'system': session['password']}, filled, failed)

    def prompt(title, initial=''):
        question = Gtk.Dialog(title=title, transient_for=dialog, modal=True)
        question.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Use name', Gtk.ResponseType.OK)
        entry = Gtk.Entry();entry.set_text(initial);entry.set_activates_default(True)
        question.set_default_response(Gtk.ResponseType.OK)
        question.get_content_area().set_border_width(12);question.get_content_area().add(entry);question.show_all()
        answer = question.run();value = entry.get_text();question.destroy()
        return value if answer == Gtk.ResponseType.OK else None

    def confirm(text):
        question = Gtk.MessageDialog(transient_for=dialog, modal=True, message_type=Gtk.MessageType.QUESTION,
                                     buttons=Gtk.ButtonsType.YES_NO, text=text)
        answer = question.run();question.destroy();return answer == Gtk.ResponseType.YES

    def upload(*_):
        chooser = Gtk.FileChooserDialog(title='Add file to SYSTEM', transient_for=dialog, action=Gtk.FileChooserAction.OPEN)
        chooser.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Choose file', Gtk.ResponseType.OK)
        answer = chooser.run();source = chooser.get_filename();chooser.destroy()
        if answer != Gtk.ResponseType.OK or not source:return
        name = prompt('Save file as', Path(source).name)
        if name is None:return
        replace = any(row[0] == name for row in model)
        if replace and not confirm('Replace ' + name + ' in this SYSTEM folder?'):return
        request('put', source=source, name=name, replace=replace)

    def new_folder(*_):
        name = prompt('New folder')
        if name is not None:request('mkdir', name=name)

    def rename_file(*_):
        row = selected()
        if row is None:return
        old = row[0];name = prompt('Rename file', old)
        if name is not None and name != old:request('rename', name=old, new_name=name)

    def remove(*_):
        row = selected()
        if row is None:return
        name, kind = row[0], row[1]
        if confirm(('Remove empty folder ' if kind == 'folder' else 'Permanently delete ') + name + '?'):
            request('delete', name=name)

    def button(title, callback):
        widget = Gtk.Button(label=title);widget.connect('clicked', callback);actions.add(widget);return widget

    up = button('Up', lambda *_: request('browse', path=session['listing']['parent']))
    refresh = button('Refresh', lambda *_: request('browse'))
    add = button('Add file…', upload);mkdir = button('New folder…', new_folder)
    rename = button('Rename…', rename_file);delete = button('Delete…', remove)
    stop = button('Stop', lambda *_: session['cancel'].set() if session['cancel'] else None)
    tree.get_selection().connect('changed', sync)
    def activated(widget, path, column):
        row = model[path]
        if row[1] == 'folder':request('browse', path=row[3])
    tree.connect('row-activated', activated)
    dialog.connect('delete-event', lambda *_: session['busy'])
    dialog.show_all();sync()
    GLib.idle_add(lambda: (request('browse', path=''), False)[1])
    try:
        while True:
            dialog.run()
            if not session['busy']:break
            message.set_text('Stop the current operation and wait for cleanup before closing.')
    finally:
        session['password'] = None
        session['closed'] = True
        if session['cancel']:session['cancel'].set()
        session['listing'] = None;session['cancel'] = None;dialog.destroy()
