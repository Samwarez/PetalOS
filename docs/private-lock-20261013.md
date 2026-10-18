# Private storage lock checkpoint — 2026-10-13

Source and the preserved QEMU guest RAM have been updated. No rebuild, physical
card write or destructive key-slot change was performed.

Ctrl+Alt+L closes Private applications, disconnects the VPN, unmounts Private
and closes its DATA encryption mapping before showing the native lock screen.
The screen uses Sam's PetalOS wallpaper and accepts the SYSTEM passphrase.
Screen unlock leaves Private closed. The existing separate Private shortcut
accepts its own passphrase. Selective SYSTEM settings remain available through
[the read-only OS / writable selected-state design](system-state.md).

Idle locking uses the same operation after ten minutes. Ctrl+Alt+D toggles
RAM-only download mode, inhibiting idle locking while keeping Private mounted.
Manual lock and the before-sleep lock override download mode and clear it.
Download mode resets on boot. Unlocking Private uses the existing shortcut.

Verified in QEMU: the Private passphrase preflight for the storage shortcut; absent DATA and SYSTEM
mappings, absent Private mount, launch-denial fence, absent VPN interface and
running native locker after manual lock; DATA mounted, SYSTEM still closed and
locker exited after the earlier combined Private/screen unlock. Sam confirmed
wallpaper. That combined authentication was superseded by the subsequent
clarification: screen authentication is SYSTEM-only, with Private staying locked.
Synthetic and live checks now cover that corrected separation: Sam confirmed
SYSTEM screen unlock and Private remained closed.
Download-mode toggle, idle-lock exit 76 without closing Private, and toggle-off
passed. One idle monitor was started; the supported Labwc shortcut reload passed.
The configured 600-second production idle monitor triggered volume closure and
native locking. An accelerated real-event test then verified download-mode
inhibition from an explicitly open baseline. Actual suspend testing powered off
QEMU unexpectedly; do not count suspend/resume as accepted. The bounded host
wakeup observer lost its monitor connection. Guest RAM diagnostics were lost,
so the cause is not established. Investigate before hardware suspend acceptance.
A rebuilt boot remains unverified.

Synthetic controller checks cover rejected passphrases in open/closed states,
busy storage evicting keys before emergency shutdown, repeated locking, manual
lock overriding download mode, and contention never triggering shutdown.
These tests substitute storage and power-off operations; they do not prove
real blocked-I/O emergency behavior or complete RAM erasure.

A root-owned adapter separates LUKS operations from desktop actions. Storage
identities are pinned in root-only RAM and checked against raw device numbers,
labels, UUIDs and mapper backing identities. No caller device path is accepted.
Normal closure uses neither lazy unmount nor deferred cryptsetup close. Failure
attempts active-key suspension and forced power-off; a separate watchdog bounds
the lock attempt. Plaintext already copied into RAM or another file cannot be
proven erased. The old automatic DATA key slot remains pending explicit retirement.

Permanent destruction of encryption headers/slots has only been considered,
not implemented or run. It cannot guarantee unrecoverability in the presence of
header/key backups, storage remapping or RAM remnants. A kernel panic alone does
not erase memory. Physical storage destruction requires separate instructions.

The original automatic DATA key remains a security gap for compelled SYSTEM
unlock if someone can read the encrypted SYSTEM volume with that passphrase.
Retire that path before claiming independent protection. Old headers/backups
may retain it; deleting the key file alone does not establish independence.
No physical-card slots, headers or key files were changed.

The earlier blank-screen failure is fixed for the observed 640×480 mode: the
inherited 100-pixel margins and 380-pixel entry forced a lock surface wider
than the compositor configured. Protocol error metadata confirmed the mismatch;
no keyboard events were logged. Compact margins/entry now fit, and Sam confirmed
wallpaper and SYSTEM unlock. An abandoned locker kept the compositor locked;
LightDM restart recovered the test desktop while Private remained closed.

## Private passphrase retry feedback, 2026-10-16

Source and current QEMU RAM now reopen the Private prompt after an explicit LUKS
passphrase rejection. The dialog says `Incorrect Private passphrase`, starts with
an empty hidden field, and briefly pulses a standard warning graphic over the
entry. The graphic passes pointer events through and disappears after 1.1s.
Cancel stops retries and emits no credential. No global Wayland overlay protocol
or new sandbox privilege is used.

Cryptsetup exit 2 also covers permissions, so retries require both that code and
the exact C-locale `No key available with this passphrase.` result from a
password-bearing `cryptsetup open`. Other permission/device/memory/busy errors
stop with a generic storage error. Raw stderr and credentials are never logged.
Existing storage callers keep their Boolean API; the graphical helper opts into
typed failures after the original rollback/preserve-open-state handling.

Synthetic tests cover repeated rejection then acceptance, cancellation, all
storage failure categories, and original mapping/SYSTEM preservation. Existing
storage/sleep tests pass. A real read-only LUKS test rejected a synthetic invalid
phrase while preserving the open Private mapping. Invisible GTK tests on the
actual Wayland desktop verify labels, empty hidden entry, bounded graphic pulse,
expiry, pointer passthrough and no output on cancel. A four-second visual preview
was displayed and cancelled automatically; no real passphrase was needed.

This follow-up is not in release `20261016-210826-820502`; its three production
files need inclusion in a future authorized build. Initial source snapshot:
`snapshots/before-private-retry-1792196939311872525.tar.gz`. Original guest public
code is preserved in root-only RAM `/run/petalos-private-retry-before.tar.gz`.
No encryption keys, headers, account policies or physical card were changed.

The [Debian trixie cryptsetup manual](https://manpages.debian.org/trixie/cryptsetup-bin/cryptsetup.8.en.html#RETURN_CODES) documents the shared permission/bad-passphrase exit code; the retry classifier also requires the specific rejection message.
