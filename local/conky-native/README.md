# Conky click-through status surface

Debian trixie's Conky 1.22.1-1 creates a transparent Wayland bottom-layer
surface with the default input region. That region covers the entire surface,
including transparent pixels. On a 640×480 desktop the 600-pixel-wide status
surface overlaps desktop icons and intercepts their mouse input. Box selection
started outside the surface and keyboard activation still work. Stopping Conky
restored direct icon activation in the QEMU acceptance test.

The patch sets an empty Wayland input region before the first surface commit.
Conky remains visible, but all pointer input passes to the surface underneath.
PetalOS uses Conky only as a display; interactive Lua mouse hooks are intentionally
unavailable on this Wayland surface. X11 behavior is unchanged.

Source: https://deb.debian.org/debian/pool/main/c/conky/conky_1.22.1.orig.tar.gz

`build.py` checks the source checksum, applies the patch without fuzz, builds
with the standard trixie Conky features, and stages a stripped executable plus
checksum/provenance. Documentation, extras and tests are omitted from this local
build. Use trixie development dependencies and ordinary-user privileges. The
image hook checks the exact base package version and binary checksum before
installation. No runtime library search path is embedded.
