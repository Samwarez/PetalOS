"""Single-authority editing session. Desktop file management stays unprivileged."""
from pathlib import Path
import json
import os
import pwd
import queue
import shutil
import stat
import subprocess
import tempfile
import threading

from . import InstallerError, portable
from .bridge import BACKEND, MAX_REQUEST
from .releases import require


def create_workspace():
    uid = os.getuid()
    require(uid > 0, 'Open SYSTEM settings as your normal desktop user.')
    runtime = Path('/run/user') / str(uid)
    require(runtime.is_dir() and not runtime.is_symlink() and runtime.stat().st_uid == uid,
            'The desktop needs its private /run/user directory for RAM editing.')
    return Path(tempfile.mkdtemp(prefix='bloom-settings-', dir=runtime))


def open_folder(path):
    """Use the host desktop opener with none of the bundled library paths."""
    path = Path(path)
    require(os.getuid() > 0 and path.is_dir() and not path.is_symlink()
            and path.stat().st_uid == os.getuid(), 'Open the editing folder as your normal desktop user.')
    environment = portable.host_environment()
    for name in ('XDG_CURRENT_DESKTOP', 'DESKTOP_SESSION', 'KDE_SESSION_VERSION', 'KDE_FULL_SESSION',
                 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME'):
        if name in os.environ:environment[name] = os.environ[name]
    environment['HOME'] = pwd.getpwuid(os.getuid()).pw_dir
    try:
        subprocess.Popen(['/usr/bin/xdg-open', str(path)], env=environment,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:raise InstallerError('Could not open the desktop file manager. Open the displayed folder manually or discard the session.') from None


class EditingSession:
    def __init__(self, request, credentials, event, *, workspace=None):
        self.workspace = Path(workspace) if workspace is not None else create_workspace()
        self.request = {**request, 'mode': 'store-editor', 'workspace': str(self.workspace)}
        self.credentials = credentials;self.event = event
        self.commands = queue.Queue();self.cancel = threading.Event();self.done = threading.Event()

    def start(self):threading.Thread(target=self.run, daemon=True).start()

    def send(self, action):
        require(action in ('save', 'discard'), 'Invalid editing-session action.')
        self.commands.put(action)

    def run(self):
        process = None;writer = None;errors = [];value = None;result = None
        try:
            if portable.root() is not None:arguments, value = portable.prepare()
            else:
                require(BACKEND.is_file() and BACKEND.stat().st_uid == 0 and not BACKEND.stat().st_mode & 0o022
                        and not any(p.is_symlink() or p.stat().st_uid != 0 or p.stat().st_mode & 0o022 for p in BACKEND.parents),
                        'Install the package or use the complete portable app for administrator actions.')
                arguments = ['/usr/bin/pkexec', str(BACKEND)]
            process = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, env=portable.host_environment())
            def write():
                try:
                    if value is not None:
                        for data in portable.chunks(portable.root(), value):
                            if self.cancel.is_set():return
                            process.stdin.write(data)
                    if self.cancel.is_set():return
                    packet = json.dumps({'request': self.request, 'credentials': self.credentials}).encode() + b'\n'
                    require(len(packet) <= MAX_REQUEST, 'Editing request exceeded its limit.')
                    process.stdin.write(packet);process.stdin.flush();packet = None;self.credentials.clear()
                    while not self.done.is_set() and not self.cancel.is_set():
                        try:action = self.commands.get(timeout=.1)
                        except queue.Empty:continue
                        process.stdin.write(json.dumps({'action': action}).encode() + b'\n');process.stdin.flush()
                except BaseException:errors.append(True)
                finally:
                    self.credentials.clear()
                    try:process.stdin.close()
                    except (OSError, ValueError):pass
            writer = threading.Thread(target=write, daemon=True);writer.start()
            for raw in process.stdout:
                require(len(raw) <= MAX_REQUEST, 'Editing response exceeded its limit.')
                event = json.loads(raw)
                if event.get('type') == 'result':result = event['value']
                elif event.get('type') == 'error':raise InstallerError(event.get('message', 'Editing stopped.'))
                else:self.event(event)
            require(process.wait() == 0 and result is not None and not errors, 'Editing authorization was cancelled or the session stopped.')
        except BaseException as error:
            message = str(error) if isinstance(error, InstallerError) else 'SYSTEM editing stopped. No credential or file contents were logged.'
            if not self.cancel.is_set() or 'cleanup' in message.lower():
                self.event({'type': 'error', 'message': message})
        finally:
            self.credentials.clear();self.done.set();self.cancel.set()
            if writer:writer.join(timeout=3)
            if process is not None:
                if process.poll() is None:
                    try:process.stdin.close()
                    except (OSError, ValueError):pass
                    try:process.wait(timeout=180)
                    except subprocess.TimeoutExpired:
                        self.event({'type': 'error', 'message': 'SYSTEM cleanup is still running. Keep the drive connected.'})
                if process.stdout:process.stdout.close()
            try:
                if process is not None and process.poll() is None:
                    raise OSError('Worker cleanup is still active.')
                if self.workspace.is_symlink():self.workspace.unlink()
                else:shutil.rmtree(self.workspace)
            except OSError:
                self.event({'type': 'error', 'message': 'The RAM working copy could not be removed. Close its file-manager window and remove it before ending the desktop session.'})
            self.event({'type': 'editor-closed', 'value': result})
