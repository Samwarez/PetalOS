# Thunar: volatile Private Trash

The supported trixie base is **4.20.2-1+deb13u1**. Apply all patches from
Debian's source archive first, then `volatile-trash.patch`; append `ram-trash.c`
to the existing GIO extensions compilation unit. The source archive hashes
are pinned in `build.py`. This preserves the Debian security patches.

The ordinary Trash action sends Private files to the unprivileged
`portable-trash` helper, which copies into the desktop's RAM Trash. GIO/GVFS
per-volume persistent Trash is disabled for Private. Private copy errors do not
fall back to a permanent-delete prompt. Files can still be deliberately deleted
permanently through the separate normal user action.

Trash uses opaque collision-safe storage keys and standard `.trashinfo` original
paths. Thunar's target collection and recursive transfer both use validated
original basenames when moving files/folders out of Trash. This avoids exposing
storage keys as restored filenames. Metadata cannot select a destination parent.

Build in a dedicated Debian trixie amd64 environment, **not a live PetalOS
session**. Install the build dependencies described by the exact Debian `.dsc`
in that builder, then compile as an ordinary user:

```sh
python3 -B local/thunar-native/build.py /path/to/public/thunar-source-archives
```

Required archives (obtain from Debian's public Thunar package pool):

- `thunar_4.20.2.orig.tar.bz2`
- `thunar_4.20.2-1+deb13u1.debian.tar.xz`

The script stages only the executable, checksum and provenance under the ignored
`config/includes.chroot/usr/local/share/portable/native-thunar/` directory.
`make check` completes, but the pinned source/configuration exposes **zero
upstream tests** there; it is not functional evidence. Maintained copy/error
tests and the isolated native Thunar/GVFS workflow supply separate evidence.
The hook checks the exact installed base-package version; release preflight
rejects a binary/provenance pair built from older local patch inputs.

See [test evidence and limits](../../docs/volatile-trash-and-touch-20261021/README.md).
The source is GPL-2.0-or-later; the image retains Debian's Thunar copyright and
licensing files. Bit-for-bit reproducibility is not claimed.
