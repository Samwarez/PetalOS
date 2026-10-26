#!/usr/bin/python3
"""Native GTK checks on an isolated Broadway display inside the disposable VM."""
from pathlib import Path
import atexit
import base64
import io
import os
import sys
import time
import unittest
import subprocess

root = Path(__file__).parent
sys.path.insert(0, str(root));sys.path.insert(0, str(root / 'tests'))
runtime = Path('/run/petalos-installer-gui-display');runtime.mkdir(mode=0o700, exist_ok=True)
os.environ.update(GDK_BACKEND='broadway', BROADWAY_DISPLAY=':73', XDG_RUNTIME_DIR=str(runtime),
                  GTK_THEME='Adwaita:dark', GTK_USE_PORTAL='0', GIO_USE_VFS='local', GIO_USE_VOLUME_MONITOR='unix')
server = subprocess.Popen(['/usr/bin/broadwayd', '--unixsocket=' + str(runtime / 'http.sock'), ':73'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
atexit.register(lambda: server.terminate() if server.poll() is None else None)
for _ in range(100):
    if (runtime / 'broadway74.socket').exists():break
    if server.poll() is not None:raise RuntimeError('VM-only GTK display could not start.')
    time.sleep(.1)
import test_gui
if not test_gui.DISPLAY:raise RuntimeError('Native GTK could not connect to the VM-only display.')
test_gui.Gtk.Settings.get_default().set_property('gtk-enable-animations',False)
output = io.StringIO()
result = unittest.TextTestRunner(stream=output, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(test_gui.GuiTests))
if not result.wasSuccessful() or result.skipped:
    print(output.getvalue(), flush=True);raise SystemExit(1)
try:
    import cairo
    import gi
    gi.require_foreign('cairo')
    from petal_installer.gui import create_window
    def example(args, progress, **kwargs):
        if args.command == 'releases':return [{'version':'Preview only','installer_catalog':True}]
        return {'variants':[{'name':'PetalOS','id':'base','local_ai':False}, {'name':'PetalOS with local AI','id':'agent','local_ai':True}]}
    window = create_window('example/PetalOS', dispatcher=example)
    test_gui.settle(lambda: test_gui.find(window,'petal-variant').get_model().iter_n_children(None) == 2)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, window.get_allocated_width(), window.get_allocated_height())
    window.draw(cairo.Context(surface));image = io.BytesIO();surface.write_to_png(image)
    print('GUI_PREVIEW ' + base64.b64encode(image.getvalue()).decode(), flush=True)
    window.destroy()
except (ImportError, TypeError):pass
print('GUI_TESTS_PASSED ' + str(result.testsRun), flush=True)
