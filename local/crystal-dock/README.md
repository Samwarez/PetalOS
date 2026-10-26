# Crystal Dock for PetalOS

Pinned upstream: [Crystal Dock v2.16](https://github.com/dangvd/crystal-dock/releases/tag/v2.16).
Source archive: `https://api.github.com/repos/dangvd/crystal-dock/tarball/v2.16`.
SHA-256: `920b8a36c1ee1eb5a66f85c98c44bec1b2d7f8f14e38aa2f96a0b57781091832`.
The maintained patch selects the Labwc implementation for XFCE without changing
the desktop identity inherited by launched applications. It uses guarded PetalOS
lock/session actions, disables update checks and the separate Wi-Fi manager,
adds an Adwaita icon fallback and backports the equivalent vertical mirror call
to Qt 6.8. Unsupported drop-to-Trash shows a notice directing users to Thunar's
maintained RAM Trash implementation; the dock still opens/empties RAM Trash.

Build as an ordinary user in an isolated Debian trixie amd64 environment. Build
dependencies: `build-essential cmake pkgconf extra-cmake-modules
qt6-base-private-dev qt6-wayland-dev libwayland-dev liblayershellqtinterface-dev`.
Install the runtime dependencies in `config/package-lists/crystal-dock.list.chroot`
there too, especially `layer-shell-qt` and `qt6-svg-plugins`.

```sh
python3 -B local/crystal-dock/build.py /path/to/v2.16.tar.gz
```

The executable, checksum and provenance are generated in the ignored
`config/includes.chroot/usr/local/share/portable/native-crystal-dock/` directory.
The builder runs the upstream CTest application-menu suite. The image hook
checks the checksum and exact Qt/LayerShell runtime package versions because
the dock uses private Qt APIs. Rebuild against updated trixie dependencies
rather than bypassing those checks. Release preflight rejects stale artifacts.

The upstream GPL license is included under `/usr/share/doc/crystal-dock/` in the
image. Source archives and generated executables are not committed. Bit-for-bit
reproducibility is not claimed. See the component report for runtime test scope.
