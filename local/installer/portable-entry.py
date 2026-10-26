"""Entry point shared by the portable launcher and its tool wrappers."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent.parent
runtime = ROOT / 'runtime'
sys.path[:] = [str(ROOT / 'app'), str(runtime / 'usr/lib/python3.13'),
               str(runtime / 'usr/lib/python3.13/lib-dynload'), str(runtime / 'usr/lib/python3/dist-packages')]
from petal_installer import InstallerError, __version__
from petal_installer import portable
portable.configure(ROOT)
# Loader cache filenames are absolute. A sealed in-memory cache makes them
# relocatable without writing files beside the app or changing host settings.
import fcntl
PIXBUF_FD = os.memfd_create('petalos-pixbuf-loaders', os.MFD_ALLOW_SEALING)
cache = (ROOT / 'app/pixbuf-loaders.cache.in').read_text()
escaped = str(ROOT).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
os.write(PIXBUF_FD, cache.replace('@PETAL_ROOT@', escaped).encode())
os.lseek(PIXBUF_FD, 0, os.SEEK_SET)
fcntl.fcntl(PIXBUF_FD, fcntl.F_ADD_SEALS, fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
os.set_inheritable(PIXBUF_FD, True)
os.environ['GDK_PIXBUF_MODULE_FILE'] = '/proc/self/fd/' + str(PIXBUF_FD)


def main():
    if os.geteuid() == 0:
        raise InstallerError('Start Bloom as your normal user; it asks for administrator authorization when needed.')
    if sys.argv[1:2] == ['--portable-check']:
        import json
        value = portable.verify(ROOT)
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk
        gi.require_version('GdkPixbuf', '2.0')
        from gi.repository import GdkPixbuf
        png = ROOT / 'app/petal_installer/assets/petal-emblem.png'
        svg = next((runtime / 'usr/share/icons/Adwaita').rglob('folder-symbolic.svg'))
        assert GdkPixbuf.Pixbuf.new_from_file(str(png)).get_width() > 0
        assert GdkPixbuf.Pixbuf.new_from_file(str(svg)).get_width() > 0
        print(json.dumps({'name': 'Bloom', 'version': __version__, 'portable': True, 'verified_files': len(value['files']),
                          'gtk': [Gtk.get_major_version(), Gtk.get_minor_version()], 'python': sys.version.split()[0],
                          'png': True, 'svg': True}))
        return 0
    if sys.argv[1:2] == ['--portable-tool']:
        if len(sys.argv) < 3:raise InstallerError('Missing portable tool.')
        os.execve(portable.tool_command([sys.argv[2], *sys.argv[3:]])[0],
                  portable.tool_command([sys.argv[2], *sys.argv[3:]]), portable.tool_environment())
    from petal_installer.cli import main as cli
    return cli(sys.argv[1:] or ['gui'])


if __name__ == '__main__':
    try:raise SystemExit(main())
    except InstallerError as error:
        print(str(error), file=sys.stderr);raise SystemExit(1)
