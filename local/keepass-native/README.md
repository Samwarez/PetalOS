# KeePassXC save and legacy-import repairs

This downstream build uses Debian trixie's `keepassxc 2.7.10+dfsg1-1`
source and Debian patches. It retains the full Debian feature set and disables
update checks, as the normal offline wrapper already does.

The phase 1.5 audit reproduced a failed buffered write on a full tmpfs:
`keepassxc-cli mkdir` returned success and replaced an existing readable database
with an empty file. The new patch checks `QSaveFile::flush()` before committing
the atomic replacement, and cancels the replacement if the flush fails. It does
not disable atomic saves or add access outside the application's sandbox.

`legacy-reader-uaf.patch` backports upstream commit
[`6a534f38c61295d60b0e937739a12511e76dbfeb`](https://github.com/keepassxreboot/keepassxc/commit/6a534f38c61295d60b0e937739a12511e76dbfeb)
for [CVE-2026-69150](https://security-tracker.debian.org/tracker/CVE-2026-69150).
Deleted legacy metadata entries are removed from both pointer lookup tables.
The accompanying regression imports the upstream public KDB fixture and checks
that every retained pointer belongs to a live entry. The builder runs the full
legacy-reader test suite; `--verify-regression` additionally tests without the
security patch, requires that regression to fail, reapplies the patch and
rebuilds and retests the deliverable executables.

Build as an ordinary user in Debian trixie:

```
python3 local/keepass-native/build.py /path/to/keepassxc_2.7.10+dfsg1.orig.tar.xz /path/to/keepassxc_2.7.10+dfsg1-1.debian.tar.xz
```

Use the Debian build dependencies plus CMake, Qt 5 development tools and a C++
compiler. The builder pins both public archive hashes, applies Debian's patch
series and `atomic-flush.patch`, and generates ignored binaries and provenance
under `config/includes.chroot/usr/local/share/portable/native-keepassxc/`.
The image hook checks hashes and the installed Debian package version, then
installs the executables behind the existing graphical wrapper. Source changes
or Debian package updates require a fresh build and regression test.

Regression: `tests/phase15-20261018/full-storage-detail.py` uses a disposable
2 MiB tmpfs with the actual KeePassXC role and AppArmor profile. On ENOSPC the
update must fail, the original database must remain byte-identical and readable,
and retrying after freeing space must persist the requested change. Run through
`tests/phase15-repairs/run.py` to preserve the original audit evidence.

The two fixes do not establish coverage of every KeePassXC save mode,
power-loss scenario or upstream security issue. Debian security updates still
require review and a rebuild; a downstream executable must not mask them.
