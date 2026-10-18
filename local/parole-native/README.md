# Native Parole for PetalOS

Downstream patch to Debian trixie's Parole 4.18.2-1. It embeds GStreamer's
`gtksink` in a GtkBin, builds with X11 disabled, recognizes broker-provided
read-only `fd://` selections, rewinds them on replay, and excludes descriptor
URIs from recent-file history. The launcher replaces an existing Parole session
when another file is selected, retiring the old file grant first. The sandbox still has no Internet interface and
receives only selected read-only files, not aMule's entire download tree.

Source: https://deb.debian.org/debian/pool/main/p/parole/parole_4.18.2.orig.tar.bz2

`build.py` verifies the source archive hash, applies `native-gtk.patch` without
fuzz, builds, strips and stages the executable and provenance in live-build
inputs. Run it as the ordinary user with the trixie development packages for
GTK3, GStreamer base, dbus-glib, Xfconf and libxfce4ui, plus pkgconf, intltool,
xfce4-dev-tools and the usual C build tools. No root invocation is required.

The first test build used an extracted temporary development-package sysroot;
no development packages were installed on the host or ThinkPad. The image hook
verifies the artifact checksum and exact base package version before replacing
the diverted executable. A Parole package update requires reviewing this patch
and rebuilding the artifact. No complete OS build is needed to test the player
in an existing live session.

Validation: generated VP8/WebM video plays in Parole's own Wayland window;
read-only descriptor delivery crosses the application boundary. The initial
hand-generated raw AVI lacked presentation timestamps and is not a reliable
playback fixture. Preserve the selected-file permission and namespace tests
when changing this integration. Sam also confirmed a real video opens from Thunar. The actual aMule preview
helper launched the offline player from an authenticated aMule sandbox in the
RAM test; unrelated paths, traversal and a symlink were rejected. Encoded audio,
seeking, Private-backed preview and aMule's GUI preview menu still need separate
runtime acceptance.
