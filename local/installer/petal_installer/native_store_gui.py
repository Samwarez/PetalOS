"""Small session control panel; the normal host file manager handles files."""
from . import InstallerError
from .editor_client import EditingSession, open_folder


def edit_store(Gtk, GLib, parent, plan, credentials, *, session_factory=EditingSession, opener=open_folder, session_created=None):
    dialog = Gtk.Dialog(title='Bloom · Edit SYSTEM settings', transient_for=parent, modal=True)
    dialog.set_default_size(620, -1);dialog.set_name('bloom-native-store')
    discard = dialog.add_button('Discard and lock', 1)
    save = dialog.add_button('Save changes and lock', 2)
    body = dialog.get_content_area();body.set_border_width(16);body.set_spacing(10)
    text = Gtk.Label(label='Use your file manager to add, rename or remove saved files. Changes stay in a RAM working copy until you save them in Bloom. Private stays locked.', xalign=0)
    text.set_line_wrap(True);text.set_max_width_chars(70);body.add(text)
    path = Gtk.Label(label='Preparing the editing folder…', xalign=0);path.set_selectable(True)
    path.set_line_wrap(True);path.set_max_width_chars(70);path.set_name('bloom-editor-path');body.add(path)
    opening = Gtk.Button(label='Open folder');body.add(opening)
    status = Gtk.Label(label='Administrator authorization is requested once for this session.', xalign=0)
    status.set_line_wrap(True);status.set_max_width_chars(70);status.set_name('bloom-editor-status');body.add(status)
    state = {'ready': False, 'saving': False, 'closed': False, 'destroyed': False, 'error': None, 'success': False}
    def sync():
        if state['destroyed']:return
        save.set_sensitive(state['ready'] and not state['saving'])
        discard.set_sensitive(not state['saving'])
        opening.set_sensitive(state['ready'] and not state['saving'])
    def launch(*_):
        try:opener(session.workspace)
        except InstallerError as error:status.set_text(str(error))
    def event(value):
        if state['destroyed']:return False
        kind = value.get('type')
        if kind == 'editor-ready':
            state['ready'] = True;path.set_text(str(session.workspace))
            status.set_text('Edit files in the file manager, then return here to save and lock. Finish all file copies before saving.')
            sync();launch()
        elif kind == 'editor-error':
            state['saving'] = False;status.set_text(value['value']['message']);sync()
        elif kind == 'progress':status.set_text(value['value'].get('stage', 'Working').replace('-', ' ').capitalize())
        elif kind == 'error':state['error'] = value['message'];status.set_text(value['message'])
        elif kind == 'editor-closed':
            state['closed'] = True;state['success'] = bool((value.get('value') or {}).get('saved'))
            dialog.response(Gtk.ResponseType.CLOSE)
        return False
    request = {'device': plan['target']['path'], 'plan_sha256': plan['plan_sha256']}
    try:session = session_factory(request, credentials, lambda value: GLib.idle_add(event, value))
    except BaseException:
        credentials.clear();dialog.destroy();raise
    if session_created:session_created(session)
    opening.connect('clicked', launch)
    def closing(*_):
        if not state['closed'] and not state['saving']:
            state['saving'] = True;sync()
            if state['ready']:session.send('discard')
            else:session.cancel.set()
            status.set_text('Closing SYSTEM and removing the RAM working copy…')
        return not state['closed']
    dialog.connect('delete-event', closing)
    dialog.show_all();sync();session.start()
    try:
        while not state['closed']:
            response = dialog.run()
            if state['closed']:break
            if response == 2 and state['ready'] and not state['saving']:
                state['saving'] = True;status.set_text('Validating and saving changes…');sync();session.send('save')
            elif response in (1, Gtk.ResponseType.DELETE_EVENT, Gtk.ResponseType.CANCEL):closing()
    finally:
        state['destroyed'] = True;credentials.clear()
        if not state['closed']:session.cancel.set()
        dialog.destroy()
    if state['error']:raise InstallerError(state['error'])
    return state['success']
