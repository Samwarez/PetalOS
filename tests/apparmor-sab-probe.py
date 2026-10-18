#!/usr/bin/python3
"""Run inside portable-offline with PORTABLE_SAB_ADMIN=1 and a ready bridge."""
import http.server
import json
from pathlib import Path
import socket
import threading
import gi

gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, WebKit2, GLib

result = {'enforcing': Path('/proc/self/attr/current').read_text().strip() == 'petalos_offline_sab (enforce)',
          'only_loopback': [name for _, name in socket.if_nameindex()] == ['lo']}
try:
    with socket.create_connection(('1.1.1.1',443),timeout=1):
        result['external_connection_denied'] = False
except OSError:
    result['external_connection_denied'] = True
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
    connection.settimeout(3)
    connection.connect('/run/user/1000/portable-sab-admin/control.sock')
    connection.sendall(b'HEAD / HTTP/1.0\r\nHost: 127.0.0.1:8080\r\n\r\n')
    result['sab_bridge_responds'] = connection.recv(4096).startswith(b'HTTP/')

class PublicPage(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        result['public_http_requested'] = True
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'<html><body>Public AppArmor test</body></html>')
    def log_message(self,*args):
        pass

server = http.server.HTTPServer(('127.0.0.1',0),PublicPage)
threading.Thread(target=server.serve_forever,daemon=True).start()
window = Gtk.Window()
view = WebKit2.WebView()
window.add(view)
result['webkit_loaded'] = False
def finished(view,event):
    if event == WebKit2.LoadEvent.FINISHED:
        result['webkit_loaded'] = True
        Gtk.main_quit()
view.connect('load-changed',finished)
view.load_uri('http://127.0.0.1:'+str(server.server_port)+'/')
window.show_all()
GLib.timeout_add_seconds(10,lambda:(Gtk.main_quit(),False)[1])
Gtk.main()
server.shutdown()
window.destroy()
print(json.dumps(result,sort_keys=True))
assert all(result.values()), 'SAB confinement acceptance failed.'
