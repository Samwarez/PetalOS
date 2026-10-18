# Fresh-build stability pass, 2026-10-15

Candidate: `20261015-193931-862289`, preserved encrypted QEMU clone
`encrypted-boot-20261015-200928-585694.img`. The physical card is unchanged.
This is functional/integration coverage, not a release certification.

## Completed

- All four release artifact hashes and sizes independently match the manifest.
- All 14 cold-boot checks passed with Private closed, native Wayland desktop,
  wallpaper and idle monitor running, no Xwayland or swap, SYSTEM state mounted.
- Release audit passed: no VLC, enforcing app profiles, selected settings and
  preference validation, firewall drop policies. No failed system services.
- All 11 shutdown authorization checks passed, including negative checks for
  remote/app roles and privileged operations. Actual desktop shutdown was
  confirmed on the ThinkPad using the same source fix before this build.
- Nine selected-file handoff checks passed, including pinned inode, read-only
  access, hidden neighbors, original permissions, rejected symlink and FIFO.
- All 17 app roles passed RAM-content checks with Private genuinely closed.
- All 12 offline roles mapped native windows, remained alive during a short
  observation, and stopped cleanly: LazPaint, Geany, gThumb, KeePassXC,
  LibreOffice, Atril, Parole, Ristretto, Mousepad, Quod Libet, local HTML, Vim.
  These are startup smoke checks, not complete app-function testing.
- A disconnected VPN correctly blocked a network-app readiness check. Saved
  VPN connected successfully, clock synchronization completed, a fresh network
  readiness check passed, and all three firewall drop policies remained.

- Transmission, Pan, aMule, SAB backend/viewer, Tor and browser all reached
  ready state and stayed alive. Sam confirms all four download app interfaces
  responsive with no blank/black windows.
- HTTPS through the browser's Unix SOCKS proxy verified the Tor Project TLS
  certificate, returned HTTP 200, and confirmed `IsTor=true`; no exit IP logged.

- Private passphrase unlock succeeded. All 17 roles passed paired RAM/Private
  writable-folder, distinct-storage and bookmark checks. Download boundary
  tests passed for four clients; all 12 offline roles passed Private folder tests.
- Native Parole played generated VP8/Vorbis WebM from Private. The aMule preview
  helper replaced existing playback successfully; the selected inode stayed
  read-only, original permissions were preserved and the player remained in its
  separate offline network namespace. Sam confirms video and timer work. The
  generated audio track was silent: audible output is not established by this.
- All synthetic storage/sleep-controller failure tests passed on source code.
- Fresh IPv4 and IPv6 HTTPS bound to wg0 both passed. Bounded journal review
  found no core-dump events, storage I/O errors, layer-shell notification errors
  or Parole X-output errors. Other component errors still need classification.

## In progress / remaining

- Actual Tor browser-tab interaction and real configured downloads.
- Actual aMule GUI preview selection, audible media output and seeking.
- Reconnect/failure transitions and a final desktop shutdown/reboot check.
- Longer-running downloads, provider port forwards/Kad, and configured Usenet
  transfers remain separate coverage. Phase 2 visuals are deferred.

## Follow-up findings and fixes (source + current guest RAM)

The desktop notification unit timed out because it waited for a D-Bus name
on the user manager's bus while the desktop uses a separate session bus.
Direct D-Bus activation of the two notification service names works on the
requesting desktop bus; sandbox service masks and activation restrictions
remain unchanged. Desktop API activation/restart works, user failed-unit
count is zero. The temporary Type=simple experiment was removed.

The installed alsa-utils device rule repeats `alsa_restore_go` and has two
jumps to a missing `alsa_restore_std` label. A narrowly conditional build
hook creates an /etc override only for this exact affected rule. The runtime
override passed `udevadm verify` alongside the storage visibility rule.

The cleanup test fixture incorrectly used production gThumb's UID950 as a
disposable UID. The harness now checks that UID61000 is unused by app roles,
accounts and processes before use. The corrected stubborn-parent/child and
symlink-safe cleanup test passed. This harness fix is outside the OS image.

Bluetooth OBEX logged missing optional Evolution contact-registry support,
and PulseAudio logged a Bluetooth D-Bus timeout. These were classified, not
fixed or silently counted as a clean log. QEMU has no emulated audio/Bluetooth
hardware in the current launcher; audible sound and physical Bluetooth need
separate hardware coverage.

User-requested file-manager navigation now offers Private Files, System
Settings and Temporary Files (RAM); raw block volumes are hidden. See
`desktop-defaults.md`. Notification, ALSA and storage-UI follow-ups are NOT
in the already-built release: they are source plus this guest's RAM only.

Desktop SYSTEM unlock returned without opening Private. All 17 controlled RAM content canaries survived the lock/unlock cycle; test canaries were then removed. User reports File System and Trash desktop icons fail to open. Both public destinations open through Thunar and the freedesktop FileManager1 ShowFolders API; desktop click behavior remains under investigation.


Conky pointer interception was confirmed by Sam: File System and Trash could be
selected by rubber band and opened with Enter, while direct clicks failed;
stopping Conky immediately restored clicking. The 600-pixel-wide transparent
Wayland surface overlaps icons on the 640×480 VM. Visibility toggling did not fix
it. A six-line patch to verified trixie Conky 1.22.1 sets an empty input region
before its first surface commit. It intentionally disables interaction with this
display-only status surface. The patched binary ran in the guest with all runtime
libraries available; a bounded Wayland trace confirmed create_region followed by
set_input_region without adding rectangles. A separate normal run remained alive.
The original guest executable is preserved under root-only /run/petalos-conky-before.
The bounded debug probe reached its file-size limit; its log was removed afterward.
The patched executable has no embedded runtime search path, a non-executable stack,
RELRO and immediate binding. Source provenance, checksum and input validation passed.

Local builder/patch, exact-version installation hook and artifact verification
mapping are staged for the next release. Only the running guest RAM was updated;
no complete OS build, test-image modification or physical-card write occurred.
The live VM now uses its advertised 1280×768 mode at scale 1. The QEMU launcher
explicitly requests 1280×800 and disables GTK zoom-to-fit (which otherwise feeds
the small initial window dimensions back into the virtual monitor). This launch
change still needs cold-boot acceptance; physical monitor configuration is untouched.
User confirmation of restored Conky plus direct icon clicks is pending.

Sam confirmed direct desktop icon clicks work with the patched Conky visible. Functional acceptance passed in the running VM. The source changes still require inclusion in a subsequent release build.


Private Documents parent permissions: Sam found the desktop could not enter it.
The parent was root:root 0700, created implicitly by app grant mkdir(parents=True).
Added pinned-descriptor, no-symlink parent setup for Documents/Downloads, restricted
to the mounted Private filesystem and expected root/Petal ownership. Only the
category parent becomes Petal:Petal 0700; child ownership/ACLs are unchanged.
Local controlled fixtures passed creation, idempotence, unchanged child inode/mode,
and symlink rejection. Pre-fix guest source matched the saved source checksum.
Updated guest RAM code and repaired both live category parents; desktop-user public
write/read/delete fixture passed, sampled existing app folder metadata unchanged.
Application UID949 cannot browse the parent in the desktop namespace. No apps were
restarted or personal files inspected. Source input validation passed. The source
fix is pending the next full build; live Private parent metadata will persist.

PortableSettings remains only as a legacy migration source and hidden sandbox path;
current desktop save/restore targets SYSTEM Desktop/desktop-settings.tar. The current
SYSTEM archive exists; the old Private archive is absent. No legacy folders or
contents were deleted.


Credential prompt audit: VPN's independent GTK askpass incorrectly requested the
system password although sudo authenticates the administrator credential. Removed
that duplicate dialog; VPN askpass now execs the shared administrator dialog.
Shared prompts explicitly distinguish administrator password, SYSTEM passphrase,
and Private passphrase; administrator acceptance button now says Authorize rather
than Unlock. SYSTEM dialog title explicitly names SYSTEM, and administrator setup
mentions the retired default rather than an active public login password. The
screen-lock UI already names SYSTEM correctly; Private helpers already select the
Private prompt. Authentication policies and backend verification are unchanged.
Source and installed live-VM scripts were updated. New invisible GTK regression
checks passed locally and under the actual Petal Wayland session: labels/buttons,
hidden bounded fields, accepted pipe formatting, no output on cancel, and VPN
forwarding to the shared administrator prompt. Synthetic input only; no real
credential was logged and no VPN reconnect was performed. Source validation and
syntax passed. Full release build pending; temporary root session closed afterward.


Automatic VPN post-connect testing is implemented in source and live QEMU RAM.
See vpn-connection-checks.md for the contract and acceptance. New shared module,
root internal helper and backend hook run under the existing action lock after
clock synchronization. GUI and Conky display per-family public IPs and statuses;
IPv6/clock failures warn, required tunnel/IPv4/DNS failures reject with rollback.
Root-owned report is RAM-only and invalidated on disconnect/switch/failure;
launch authorization never uses it. Synthetic probes, mocked connect/rollback
flow, existing profile/manual-IP/credential checks passed. Actual saved-profile
connect (previously no tunnel) automatically passed tunnel, IPv4, IPv6, DNS and
clock. Desktop report read-only, status includes both addresses, refreshed manager
alive, three firewall drop policies retained. No full build/card write. Temporary
root maintenance closed and sudo timestamp cleared after public staging cleanup.


aMule Low-ID diagnosis: selected-profile-derived client public key matches actual
wg0 public key; aMule shares the VPN network namespace. Saved app configuration
had TCP57773/UDP57451 enabled, but live sockets still used defaults TCP4662,
UDP4665/4672. Gracefully signalled the pinned aMule main process, waited for its
worker to finish, then relaunched through the normal compartment gate/broker.
Actual sockets now TCP57773, UDP57776 and UDP57451. An external host TCP handshake
to the VPN public exit on57773 succeeded. A bounded, filtered RAM-log check then
classified the latest recorded server-assigned client ID as High ID; no raw log
lines, client ID number, personal file names or private keys were emitted.
UDP ports were verified listening, not externally classified by this TCP test.

Persisted only the three approved port/UDP-enable preferences to the existing
SYSTEM whitelist record, preserving its server list and all other fields. A
root-only backup was verified inside encrypted SYSTEM AppPreferences/Backups.
RAM app state/downloads stayed in RAM; no other apps were stopped or VPN changed.
Also applied the previously tested pending selection-order fix atomically under
the VPN lock: saved profile selection now commits only after automatic tests pass.
Source and live backend match. No new build or physical-card write. Maintenance
sudo timestamp cleared and temporary root session closed afterward.

## Known-good media acceptance, 2026-10-16

Sam confirmed sustained Big Buck Bunny playback, audible sound, seeking in both
 directions and pause/resume after the FIFO audio-clock correction. Isolated
three-second PCM regression measured 0.108s with the original clock and 3.034s
with system-clock timing. The running broker matches the staged source.

Slight choppiness remains reported. A ten-second sample measured Parole at 1.81
of four guest CPU cores, with no memory/I/O pressure; guest CPU scheduling pressure
was present. QEMU used 2.21 host cores with no host CPU pressure. No actual frame
drop count was obtained. VM display/audio overhead is a hypothesis, not a finding;
repeat known-good playback on hardware before closing the performance issue.
The current audio path is a temporary guest-monitor-to-host playback relay with
no microphone/recording. No complete OS build or physical card change was made.

Sam clarified that idle/sleep was deliberately disabled for maintenance. The
absent monitor on that boot is not by itself evidence of an autostart defect;
its cause and the settings-to-native-monitor relationship were not established.
