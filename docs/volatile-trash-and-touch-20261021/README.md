# Volatile Trash and touch defaults — 2026-10-21

These changes are prepared for the **next build**. No full OS image, running
PetalOS session or physical card was updated. Existing uncommitted work and
backups were preserved; the initial public-source snapshot is
`snapshots/before-volatile-trash-20261021-160424.tar.gz` with its verified SHA-256
sidecar. The previous source backup checksum also passed.

Base Git revision: `543cf7ef2dd49eb0903fddc757fff2cff774502f`, branch
`fix/phase15-audit`, plus uncommitted changes. The last completed OS release
remains `20261019-211301-083244` (built revision
`bfd9dd9efd4294a8c0f3703181b419f4cab64e36`). This is component verification,
not acceptance of a newly built PetalOS image.

## Behavior prepared

- Private's normal Thunar Trash action copies files or folders completely to
  the desktop RAM Trash before deleting their originals. Ordinary RAM Trash
  continues working. Restore uses the original basename, including folders
  copied across filesystems.
- Private locking blocks new copies, stops copy workers/readers, clears all
  desktop RAM Trash content and original-path metadata, and drains late readers
  before closing Private. This intentionally also empties ordinary RAM Trash.
  Screen unlock does not reopen Private; only a successful independent Private
  unlock removes the copy barrier. Shutdown discards the RAM session.
- GIO/GVFS per-volume Trash is disabled for Private; sandbox AppArmor rules deny
  persistent `.Trash*` writes. Legacy encrypted Trash remains untouched and is
  ignored by desktop Trash. This does not delete the existing
  `desktop-settings.tar` or erase earlier persistent history.
- RAM copies are serialized, bounded by memory/free-space/complexity limits,
  and refuse symlink traversal, foreign mounts and special files. Copy failures
  preserve originals. Deletion failures retain the complete RAM copy and its
  recovery metadata. Errors do not silently switch to permanent deletion.
  Abandoned unpublished RAM staging from an interrupted helper is reclaimed on
  retry or locking. The deliberate permanent-delete action remains available.
- GTK 3/XFCE defaults become 20 logical pixels and 500 milliseconds for double
  clicks. Saved stock values migrate once; other values and subsequent user
  choices survive. These settings affect mice as well as touch.

Source: `volatile_trash.py`, `private_storage.py`, `portable-trash`, hooks
0926–0928, the persistent-Trash AppArmor abstraction, and maintained Thunar
sources under `local/thunar-native/`. Desktop settings archives already use an
allowlist; added tests explicitly verify exclusion of Trash data and metadata.

## Build and test evidence

The native component uses Debian trixie **Thunar 4.20.2-1+deb13u1**, with all
Debian source patches applied before the local change. Exact source, local
builder/patch and executable hashes and Debian hardening flags are recorded in
[native-build.json](native-build.json). Generated executables/source archives
are excluded from Git. Release preflight rejects stale local component inputs;
the image hook checks the installed package version and executable checksum.

Compilation, `make check` and staged installation passed in an isolated,
disposable Debian trixie RAM environment. This configuration exposes **zero
upstream tests** under `make check`; that result alone proves no workflow.
Compilation and GUI tests ran without network access. Public dependency setup
occurred only inside the disposable builder; no host packages or host security
settings changed.

[Native GUI results](native-GUI-workflows.json): **19 checks passed** using the
final native executable, fresh D-Bus, GVFS and Xvfb. Outcomes included actual
Thunar Trash dispatch, matching copied bytes, file/folder restore, ordinary RAM
Trash and restore, suppression of legacy persistent Trash, an insufficient-RAM
error preserving the source, actual termination of a deleted-but-open RAM Trash
reader, and effective GTK/Xfconf double-click values. This fixture uses public
fake Private storage and an adapter that bypasses boot/LUKS discovery.

[Regression results](regressions.json) record:

- Real cross-filesystem copy/metadata/restore and directory/symlink operations.
- Capacity, write/sync, changing-source, collision, unsafe ancestor, concurrency,
  special-file, complexity, interrupted-staging and lock-during-copy failures.
- Synthetic Private unlock, lock, repeated lock, fail-closed cleanup, download
  inhibition and sleep-hook paths; RAM Trash reader classification.
- Settings roundtrip, malicious archive rejection, save failures, Trash
  exclusion and one-time touch migration preserving overrides.
- Build-hook idempotence, preservation of vendor settings and refusal of a
  conflicting Private mount entry; full build-input validation.
- Parse-only checks of 22 AppArmor profiles; no host profiles loaded.

## Remaining acceptance and limits

Build a new image, verify its actual artifacts, then test normal and interrupted
Trash/restore workflows under the image's Wayland and AppArmor configuration.
Verify a real Private lock/reopen and reboot leave Trash empty, including when
locking interrupts a copy; confirm SYSTEM screen unlock leaves Private closed.
Exercise app saves/deletes with Private open and closed and ensure failures are
clear rather than hangs or silent permanent deletion.

Retest finger double taps on the **Lenovo X230 Tablet**. The pen/finger symptom
is consistent with strict double-click recognition, but distance/timing has not
been established as its sole cause. Qt-specific touch behavior was not tested.

RAM Trash is lost on lock/power loss and requires copying instead of a cheap
same-filesystem rename. Large items may be refused; deletion is not an erasure
guarantee. A failed source-deletion step can leave both a RAM copy and remaining
source entries. No guarantee of forensic RAM erasure, anonymity, or prevention
of a user deliberately copying accessible content elsewhere follows from these
tests. Old encrypted Trash needs a separately authorized cleanup if desired.

## Other storage media

The RAM-based OS and encrypted SYSTEM/Private layout are not specific to an SD
card. USB flash drives and USB hard disks can use the same design. Current
installation/update tooling deliberately validates known device identities and
has card/removable-device assumptions; adapting those guards and testing boot,
USB disconnect behavior and storage protection is required before claiming
support for another target. Internal-drive installation is untested and must
not bypass the existing host-disk protections. No alternate target was written.
