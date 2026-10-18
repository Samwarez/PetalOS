"""Minimal security-context-v1 client; no display pixels or input interception.

Trusted session-side code creates a restricted listener. Applications receive
only that listener path, never the unrestricted compositor socket. Integration
with the production application broker remains gated by QEMU acceptance.
"""
import array
import os
from pathlib import Path
import re
import socket
import struct


class WaylandError(Exception):
    pass


def integer(value):
    return struct.pack('=I', value)


def string(value):
    data = value.encode('utf-8') + b'\0'
    if len(data) > 1024 or '\0' in value:
        raise WaylandError('Invalid protocol string.')
    return integer(len(data)) + data + bytes((-len(data)) % 4)


class Connection:
    def __init__(self, path):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.settimeout(5)
        self.pending = b''
        self.globals = {}
        self.handlers = {}
        self.windows = {}
        self.next_id = 3
        try:
            self.socket.connect(str(path))
            self.send(1, 1, integer(2))  # wl_display.get_registry
            self.roundtrip()
        except BaseException:
            self.socket.close()
            raise

    def close(self):
        self.socket.close()

    def allocate(self):
        identifier = self.next_id
        self.next_id += 1
        return identifier

    def send(self, object_id, opcode, payload=b'', fds=()):
        size = len(payload) + 8
        if size > 65532 or size % 4:
            raise WaylandError('Invalid protocol message.')
        message = struct.pack('=II', object_id, (size << 16) | opcode) + payload
        if fds:
            count = self.socket.sendmsg([message], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', fds))])
            if count <= 0:
                raise WaylandError('Descriptor transfer failed.')
            self.socket.sendall(message[count:])
        else:
            self.socket.sendall(message)

    def roundtrip(self):
        callback = self.allocate()
        self.send(1, 0, integer(callback))  # wl_display.sync
        budget = 1024 * 1024
        while budget > 0:
            if len(self.pending) < 8:
                data = self.socket.recv(8192)
                if not data:
                    raise WaylandError('Compositor disconnected.')
                self.pending += data
                budget -= len(data)
                continue
            object_id, word = struct.unpack('=II', self.pending[:8])
            size, opcode = word >> 16, word & 65535
            if size < 8 or size > 65532 or size % 4:
                raise WaylandError('Invalid compositor message.')
            if len(self.pending) < size:
                data = self.socket.recv(8192)
                if not data:
                    raise WaylandError('Compositor disconnected.')
                self.pending += data
                budget -= len(data)
                continue
            payload, self.pending = self.pending[8:size], self.pending[size:]
            if object_id == 1 and opcode == 0:
                raise WaylandError('Compositor rejected the requested operation.')
            if object_id == callback and opcode == 0:
                return
            if object_id == 2 and opcode == 0:
                if len(payload) < 12:
                    raise WaylandError('Invalid registry entry.')
                name, length = struct.unpack('=II', payload[:8])
                end = 8 + length
                offset = 8 + ((length + 3) & ~3)
                if not 1 < length <= 256 or len(payload) != offset + 4 or payload[end-1] != 0:
                    raise WaylandError('Invalid registry entry.')
                interface = payload[8:end-1].decode('ascii')
                version = struct.unpack('=I', payload[offset:offset+4])[0]
                self.globals[interface] = (name, version)
            elif object_id == 2 and opcode == 1 and len(payload) == 4:
                removed = struct.unpack('=I', payload)[0]
                self.globals = {key: value for key, value in self.globals.items() if value[0] != removed}
            elif object_id in self.handlers:
                self.handlers[object_id](opcode, payload)
        raise WaylandError('Compositor response exceeded the diagnostic limit.')

    def watch_windows(self):
        """Trusted broker only: observe mapped handles/app IDs, discard titles."""
        protocol = 'zwlr_foreign_toplevel_manager_v1'
        if protocol not in self.globals:
            raise WaylandError('Native window readiness observation is unavailable.')
        name, version = self.globals[protocol]
        manager = self.allocate()

        def manager_event(opcode, payload):
            if opcode == 0 and len(payload) == 4:
                handle = struct.unpack('=I', payload)[0]
                if len(self.windows) >= 256:
                    raise WaylandError('Too many native windows.')
                self.windows[handle] = ''

                def window_event(event, data):
                    if event == 1 and len(data) >= 4:
                        length = struct.unpack('=I', data[:4])[0]
                        if not 1 <= length <= 256 or len(data) != 4 + ((length + 3) & ~3) or data[3+length] != 0:
                            raise WaylandError('Invalid native application identity.')
                        value = data[4:3+length].decode('utf-8')
                        self.windows[handle] = value if re.fullmatch(r'[A-Za-z0-9_. -]{1,255}', value) else ''
                    elif event == 6:
                        self.windows.pop(handle, None)
                        self.handlers.pop(handle, None)
                self.handlers[handle] = window_event
        self.handlers[manager] = manager_event
        self.send(2, 0, integer(name) + string(protocol) + integer(min(version, 3)) + integer(manager))
        self.roundtrip()

    def create_listener(self, path, app, instance):
        if not re.fullmatch('[a-z][a-z0-9-]{0,31}', app) or not re.fullmatch('[a-f0-9]{32}', instance):
            raise WaylandError('Invalid compartment identity.')
        protocol = 'wp_security_context_manager_v1'
        if protocol not in self.globals:
            raise WaylandError('Compositor security contexts are unavailable.')
        name, version = self.globals[protocol]
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        read_fd, keep_fd = os.pipe()
        created = False
        try:
            listener.bind(str(path));created = True
            os.chmod(path, 0o600)
            listener.listen(8)
            manager, context = self.allocate(), self.allocate()
            self.send(2, 0, integer(name) + string(protocol) + integer(1) + integer(manager))
            self.send(manager, 1, integer(context), (listener.fileno(), read_fd))
            self.send(context, 1, string('org.petalos'))
            self.send(context, 2, string('org.petalos.' + app))
            self.send(context, 3, string(instance))
            self.send(context, 4)
            self.roundtrip()
            return keep_fd
        except BaseException:
            os.close(keep_fd)
            if created:
                Path(path).unlink(missing_ok=True)
            raise
        finally:
            os.close(read_fd)
            listener.close()
