# Selective encrypted SYSTEM settings

Prepared in source and verified in the preserved QEMU guest, without a full
rebuild or physical-card update. The existing encrypted SYSTEM volume provides
system settings; a new partition or fourth passphrase is not needed.

The live OS stays in its RAM overlay. SYSTEM is mounted behind a root-only RAM
directory at `/run/portable-storage/system-volume`, with a read-only mount view.
A writable bind exposes only `.petalos-state` at `/mnt/system-state`:

- `Network/Profiles`: validated WireGuard profiles, mode 600.
- `Network/selected-profile`: a selection, never network authorization.
- `Desktop/desktop-settings.tar`: only approved panel/GTK/XFCE settings.

The bind's root is owned by root, group 1000, mode 750; Petal can write only
Network and Desktop. `~/SystemSettings` is the user-facing link. The independent
administrator hash remains in SYSTEM's root-only `.petalos-auth` area. Its fixed
provisioning helper may use a temporary writable mount for that credential.
No general root/home persistence, logs, caches, Wi-Fi or Bluetooth profiles are
added. Ordinary applications have neither system-settings mount exposed.

Boot prepares SYSTEM settings before the desktop. Wayland's session client
restores the validated desktop archive before starting XFCE. Private stays
closed until its own unlock action/passphrase. Manual and idle locking close
Private, while SYSTEM settings remain available. Screen unlock checks SYSTEM's
passphrase without opening Private. Existing automatic DATA keys remain an
outstanding independence gap; they have not been retired.

Verified in QEMU: six VPN profiles migrated without logging payloads, originals
retained; no old desktop archive was present; current panel/settings then saved
and restored from SYSTEM while Private was closed. Full SYSTEM mount flags are
read-only and an attempted root write there returned EROFS. Petal cannot create
an unrelated file in the state root, but can save selected desktop settings.
An offline-role fixture cannot see either SYSTEM mount or the parent home.
The corrected 640×480 native locker showed the supplied wallpaper; Sam unlocked
it with SYSTEM and Private stayed closed. Native desktop restart/autologin worked
with Petal password login disabled and restored saved settings from SYSTEM.
VPN connection from the migrated SYSTEM profiles and the active network gate
passed while Private remained closed. A rebuilt cold boot remains unverified.

The old Private-based VPN provisioning test scripts describe an earlier storage
layout; use the current GUI importer. No physical-card migration has been run.

Cold-boot test preparation (2026-10-13 local): a public configuration layer now
includes 13 approved trixie Wayland archives reused from the guest package cache.
Each archive was checked against signed APT metadata and its package identity;
104 native desktop/locker dependency paths exist in the base release or layer.
Only archive payloads and public project configuration were copied, not the
running guest filesystem or personal settings. This is a QEMU-only functional
layer, not a release build: package maintainer scripts and the installed-package
database are not updated by extracting archives. A full live-build release is
still required before hardware acceptance.

The clone updater now applies init_on_alloc=1/init_on_free=1 in the
configuration-only path as well as normal release updates. A bounded source
check covers normal/failsafe kernel lines, repeated updates and rejection of
explicit disabling or duplicate options. The obsolete default-account.hash
release-verification entry was replaced with the current storage/lock/default
session files. No DATA slots or encryption headers were changed.

The working VM was shut down gracefully after saving selected desktop settings.
The preserved-disk clone updater reported FAILED after the terminal exited.
The active image remains the original and the updater mapper is absent. The
public terminal error is requested; no cold boot attempted. Boot and
screen/Private separation acceptance are pending.

The stale unselected configuration module collision was resolved by installing
the new public layer as petalos-wayland-test.squashfs. The corrected clone update
completed successfully; mapper/loop/disk-user checks passed before launch.
The new normal-user QEMU boot is awaiting SYSTEM unlock and acceptance checks.

First layered cold boot reached the native Wayland desktop with both memory
flags set. SSH was unavailable and the administrator password was rejected.
Console sudo policy confirmed rootpw; selected SYSTEM settings were mounted.
Credential restoration preceded SYSTEM-state preparation, and the SSH hook used
a second ro,noload mount despite the active SYSTEM-state mount. Source now
prepares the verified SYSTEM view before credential restoration and the test
SSH hook reuses it. The second public layer is prepared, with storage failure
and memory-flag checks passing; actual corrected cold-boot acceptance is pending.
No administrator credential or encryption slot was reset.

Corrected v2 cold boot: all 14 automated checks passed over restored pinned SSH.
Native compositor/session/wallpaper/idle monitor are running, Xwayland is absent,
both memory-zeroing flags are present, toram/swap=false and no swap are confirmed,
selected SYSTEM state is mounted, and Private is closed and unmounted.
Administrator authentication is being checked separately with sudo /usr/bin/true;
its result is pending. No encryption slots or administrator credentials changed.

The harmless administrator authentication test returned failure after three
attempts. The v2 mount/startup change restored SSH but did not establish valid
administrator authentication; do not claim the credential issue is fixed.
A QEMU-only boot diagnostic is prepared to report configuration, credential
validation and internal active/stored comparison as booleans. Neither credential
value leaves guest memory, and the diagnostic changes no credential. Its boot
acceptance is pending; all earlier successful cold-boot checks remain recorded.

v3 diagnostic confirmed the saved administrator credential validates, while the
active root account is locked and does not match it. The early auth-failure
marker is present; SYSTEM preparation succeeded. The test layer omitted the
normal build hook's enabled portable-admin-setup.service (UnitFileState disabled).
v4 enables that existing late restoration service and retains the boolean
verification. No credential reset is needed at this stage; v4 boot is pending.

v4 cold boot passed all 14 automated checks. The administrator-setup service
is enabled and exited successfully. The diagnostic confirms SYSTEM readiness,
a configured root password, a valid saved credential, and an active credential
matching the saved one. The graphical sudo authentication test is pending;
no credential was reset or changed.

Final v4 administrator acceptance: Sam entered the existing password, and the
harmless sudo /usr/bin/true test returned exit 0. Private stayed closed afterward;
no root maintenance helper or lease was installed. The test-layer service
omission is fixed and late restoration is accepted. The early-hook failure still
needs its bounded exception traced; successful late restoration does not prove
every early boot hook succeeds. No full release build or physical-card test ran.

Exact early-hook failure resolved (2026-10-13 local): an isolated replay with
verified SYSTEM views detached failed at root locking with FileNotFoundError.
The hook used /usr/sbin/passwd, whereas the installed executable is
/usr/bin/passwd. Source and guest RAM now use the correct path. Repeating the
complete hook from detached SYSTEM views returned exit 0, prepared settings,
and restored the saved administrator credential; the active/saved comparison
and all 14 state checks passed afterward. Private remained closed. This
supersedes the earlier hypothesis that mount ordering alone caused the early
failure. The missing late service enablement was a separate test-layer issue.

Temporary maintenance helpers were removed and the authenticated SSH root
session closed. The path correction is in source and RAM, not yet in the
on-disk v4 test layer; include it in the next module/release update. No additional
full build, credential reset, encryption-slot change or physical-card write ran.
