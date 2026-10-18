# Private legacy-key retirement review

Scope: read-only audit and a disposable QEMU clone test, preserving the working
image and existing backups. No physical-card update or destruction of original
keys/headers is authorized by this stage.

The existing encrypted SYSTEM-held automatic DATA key is an independence gap:
SYSTEM access may permit opening Private against the current DATA header.
The audit must use the key only at its existing encrypted SYSTEM path, never
print/hash/copy its contents, and return only slot numbers and pass/fail results.
No full LUKS metadata, salts or encrypted key material belong in the report.

Before any clone slot change, prove the human Private passphrase matches a
remaining slot distinct from the automatic key; require at least two active
slots, verify raw device/mapper/loop identities, and ensure DATA is closed.
The working image must be shut down and detached before making a disposable
regular-file clone. Refuse physical block devices or unregistered paths. Do not
remove a slot simply because it has a familiar number. The target slot must
have been proven to accept the actual legacy key, while another proven slot
accepts the human passphrase.

A successful slot-removal test is limited to the modified header. Removing a
slot does not change the volume encryption key: old headers/backups may still
unlock the same ciphertext with the old key. Keeping initial backups is
necessary for recovery and also preserves their old access paths. Do not call
this forensic key erasure or complete revocation. For stronger independence of
future ciphertext, review fresh-volume migration or volume-key reencryption;
that is a separate storage operation, not part of this test.

The clone test should verify: the automatic key works before the change and
fails after it; the Private passphrase works before and after; the last remaining
slot cannot be removed by the helper; a wrong passphrase changes nothing; the
original working image remains unchanged. No extra plaintext key/header backup
is created. A retained encrypted full-disk original supplies rollback.

Sources: cryptsetup's upstream FAQ and luksKillSlot manual:
https://gitlab.com/cryptsetup/cryptsetup/-/blob/main/FAQ.md
https://www.man7.org/linux/man-pages/man8/cryptsetup-luksKillSlot.8.html

Audit and clone acceptance are pending. Real key slots have not been changed.

Read-only QEMU audit completed: DATA has slots 0 and 1. The existing legacy
SYSTEM-held key matches slot 1; the human Private passphrase matches slot 0.
The human Private passphrase ALSO unlocks SYSTEM. No key/credential payload was
logged and Private stayed closed. This makes slot removal alone insufficient
for the requested passphrase separation.

Sam selected fresh Private-volume migration on a disposable clone. The helper
will create a new LUKS2 volume key, require a new Private phrase distinct from
SYSTEM, old Private and the saved administrator credential, and copy the full
filesystem directly between encrypted mappings. It will compare the complete
copied plaintext internally and report only pass/fail, retain the original
ciphertext disk unchanged, and remove the obsolete automatic-key file only from
the clone's encrypted SYSTEM. Logical deletion is not a forensic-erasure claim.
The new header must have one Argon2id slot; old automatic key and SYSTEM phrase
must fail against it. An old-header/old-key mapping of the NEW ciphertext must
also fail to reproduce the correct first block. No extra real header/key file
is created. Backups and the source disk still retain access to their OLD data.

A disposable RAM-only synthetic encryption test passed: slot removal rejects
the legacy key against the current header but the retained old header still
accepts it; fresh-key ciphertext cannot be read with that old header/key, while
the correct new key reads the public fixture marker. Synthetic files/mappings
were removed. Image guards rejected device paths, symlinks, wrong sizes and
wrong owners. Actual fresh-clone migration and boot acceptance remain pending.

The first real clone attempt stopped with CalledProcessError after its copy
message. Cleanup closed all migration mappings, and the working image remained
selected. No candidate boot ran. The initial report did not identify the failed
tool. A verification-only continuation is prepared: it reopens the existing
fresh clone DATA read-only, requires complete mapped-plaintext checksum equality,
and never formats or rewrites DATA. It releases both DATA mappings before the
old-header challenge and emits bounded tool/exit/error categories on failure.
This continuation and final clone acceptance are pending. Retained original
images/backups remain unchanged and still preserve their old access paths.

Verification-only continuation completed and selected the fresh clone. Completion
required complete filesystem checksum equality, new-passphrase acceptance,
old-key/SYSTEM-passphrase rejection, old-header/new-ciphertext mismatch, a single
Argon2id slot, logical removal of the obsolete key from cloned SYSTEM, clean
unmount/mapper/loop cleanup, and an unchanged source-image checksum. No original
or backup was retired. The old-header test now releases both DATA mappings
before challenging the new ciphertext; the first run's exact tool failure was
not captured and is not claimed as diagnosed.

The fresh clone booted using SYSTEM only. All 14 automated cold-boot checks
passed, including Private remaining closed/unmounted, mounted SYSTEM settings,
Wayland/wallpaper/idle, zeroing flags, no Xwayland and no swap. Administrator
configuration and active/saved credential comparison also pass. New Private GUI
unlock and subsequent lock acceptance are pending.

Live fresh-clone acceptance completed: the distinct new Private passphrase was
accepted through the separate graphical unlock (exit 0), with Private mounted
rw,nosuid,nodev,noexec,noatime. Scoped manual Private lock then returned exit 0,
closed its mapping, and unmounted it while selected SYSTEM settings stayed
available. All 14 cold-boot/state checks passed again; administrator active/saved
credential comparison remains valid. No maintenance helper or privileged lease
remains active. The initial GUI test prompt expired during coordination; the
fresh direct SSH attempt with a 200-second host timeout succeeded.

The fresh clone now has independent Private encryption and an accepted separate
unlock path. Existing originals/backups still contain the old ciphertext and
its old access paths. They have not been erased or migrated. The physical card
has not changed. No anonymity, total memory erasure, forensic nonrecoverability
or Tails-equivalent security is claimed from this functional acceptance.
