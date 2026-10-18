"""Delegate only explicitly selected regular files, opened as Petal."""
import array
import os
from pathlib import Path
import socket
import stat
import subprocess
import tempfile
from urllib.parse import unquote, urlsplit

# Descriptor transfer keeps the authorized inode pinned across renames. Root
# never opens a caller's selected path with its own filesystem permissions.
READER = '''import array,os,socket,stat,sys
channel=socket.socket(fileno=int(sys.argv[1]))
if len(sys.argv)>3 and sys.argv[3]=='walk':
 parts=sys.argv[2].split('/')
 assert parts[0]=='' and '..' not in parts
 folder=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
 try:
  for component in parts[1:-1]:
   assert component
   child=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=folder)
   os.close(folder);folder=child
  fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=folder)
 finally:os.close(folder)
else:fd=os.open(sys.argv[2],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
try:
 assert stat.S_ISREG(os.fstat(fd).st_mode)
 channel.sendmsg([b'F'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[fd]))])
finally:os.close(fd);channel.close()
'''


def opened_as_petal(path, *, walk=False):
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    parent.settimeout(15)
    process = None
    received = []
    try:
        process = subprocess.Popen(['/usr/bin/setpriv', '--reuid=1000', '--regid=1000',
            '--clear-groups', '--inh-caps=-all', '--bounding-set=-all', '--ambient-caps=-all',
            '--no-new-privs', '/usr/bin/python3', '-I', '-c', READER, str(child.fileno()), str(path),
            *(['walk'] if walk else [])],
            pass_fds=(child.fileno(),), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={'PATH':'/usr/bin:/bin','LC_ALL':'C.UTF-8'}, close_fds=True)
        child.close()
        data, controls, flags, _ = parent.recvmsg(1, socket.CMSG_SPACE(array.array('i').itemsize), socket.MSG_CMSG_CLOEXEC)
        for level, kind, payload in controls:
            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                values = array.array('i');values.frombytes(payload[:len(payload) - len(payload) % values.itemsize])
                received.extend(values)
        assert data == b'F' and not flags & socket.MSG_CTRUNC and len(received) == 1
        assert process.wait(timeout=5) == 0
        fd = received[0]
        assert stat.S_ISREG(os.fstat(fd).st_mode)
        received.clear()
        return fd
    except Exception:
        raise RuntimeError('The selected regular file could not be opened.') from None
    finally:
        for fd in received:os.close(fd)
        parent.close();child.close()
        if process is not None and process.poll() is None:
            process.kill();process.wait(timeout=5)


def delegate(arguments, app_name):
    """Return argv, read-only binds, pinned fds. Own-folder files stay editable."""
    rewritten, binds, descriptors = [], [], []
    own = Path('/mnt/private/Documents') / app_name
    try:
        for value in arguments:
            from_amule = value.startswith('petalos-amule-media:')
            if from_amule:
                assert app_name == 'parole'
                import compartments as c
                from media_bridge import relative_item
                assert c.worker_alive(c.read_record('amule'))
                storage = c.read_record('amule')['storage']
                relative = unquote(value.split(':', 1)[1])
                # Validate again in the receiving worker, not just the broker.
                relative = relative_item('/mnt/' + storage + '/Downloads/amule/' + relative, storage)
                if storage == 'private':
                    c.private_ready()
                    value = str(c.PRIVATE / 'Downloads/amule' / relative)
                else:
                    c.ram_ready()
                    value = str(Path('/home/Petal/Downloads/amule') / relative)
            parsed = urlsplit(value)
            if parsed.scheme == 'file':
                assert parsed.netloc in ('', 'localhost') and not parsed.query and not parsed.fragment
                value = unquote(parsed.path)
            elif parsed.scheme:
                raise ValueError('Offline applications accept local items only.')
            path = Path(value)
            if not path.is_absolute():
                rewritten.append(value)
                continue
            if path.is_relative_to(own) and '..' not in path.parts:
                rewritten.append(value)
                continue
            ram = Path('/home/Petal/Documents') / app_name
            if path.is_relative_to(ram) and '..' not in path.parts:
                rewritten.append(str(Path('/mnt/ram/Documents') / app_name / path.relative_to(ram)))
                continue
            if path.is_relative_to(Path('/mnt/ram/Documents') / app_name) and '..' not in path.parts:
                rewritten.append(value)
                continue
            fd = opened_as_petal(path, walk=from_amule)
            descriptors.append(fd)
            if not os.fstat(fd).st_mode & stat.S_IROTH and app_name != 'parole':
                # A mode-0600 selection cannot be reopened by another role UID.
                # Take a bounded RAM snapshot rather than changing its ACLs.
                from compartments import BASE, protected
                folder = protected(BASE / ('offline-' + app_name) / 'opened')
                assert os.fstat(fd).st_size <= 64 * 1024**2
                copied, name = tempfile.mkstemp(prefix='selected-', dir=folder)
                try:
                    total = 0
                    while True:
                        block = os.read(fd, 1024**2)
                        if not block:break
                        total += len(block)
                        assert total <= 64 * 1024**2
                        view = memoryview(block)
                        while view:
                            written = os.write(copied, view)
                            assert written > 0
                            view = view[written:]
                    os.fchmod(copied, 0o444)
                except Exception:
                    Path(name).unlink(missing_ok=True)
                    raise
                finally:os.close(copied)
                os.close(fd)
                descriptors.pop()
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW)
                descriptors.append(fd)
            # A safe basename is presentation only, never a host mount path.
            import re
            suffix = path.suffix if re.fullmatch(r'\.[A-Za-z0-9]{1,16}', path.suffix) else '.dat'
            destination = '/run/petalos-opened/item-' + str(len(descriptors)) + suffix
            binds.append((Path('/proc/self/fd') / str(fd), destination, False))
            rewritten.append(destination)
        return rewritten, binds, descriptors
    except Exception:
        for fd in descriptors:os.close(fd)
        raise
