# Native Wayland acceptance, 2026-10-13

Work remains in source and QEMU RAM on the preserved disk. No rebuild or
physical-card update has occurred. Original backups and initial code snapshots
were verified before this work; the pre-Wayland snapshot checksum passed again.

Accepted visually by Sam: responsive XFCE desktop, no flickering, wallpaper;
native Tor/Transmission/Pan/aMule windows; Tor websites and Tor confirmation.
Transmission's persisted open-dialog directory now resets to its own Private
download folder on launch, in the guest and source defaults.

Automated checks passed:

- Restricted Wayland protocol visibility, lease revocation and headless compositor
  survival; real-role GTK3 and GTK4 native windows with UID/mount/network/AppArmor
  boundaries, no parent runtime/home/Private/X11 socket or IP access.
- Browser Unix SOCKS path: direct IPv4/IPv6 denied, Tor HTTPS response confirmed
  without retaining IP/body; graphical browser uses explicit Unix SOCKS preferences.
- Download applications: own Private folders writable, unrelated folders hidden.
- Network-role firewall drops off-tunnel/loopback canaries; WireGuard's marked
  outer traffic reaches the existing endpoint whitelist. Roles cannot set SO_MARK.
- SAB management checks actual established server-socket UID 945 before forwarding
  requests; viewer peer must be UID 947. Real backend/viewer HTTP passes, a public
  substitute server is rejected. No new firewall exception.
- Synthetic Tor cache test: unchanged content reuses a generation; changed content
  selects a new one without modifying the old tree; every copy verifies before
  use and failed verification rejects even an existing cached generation.
- Thirteen offline-role fixtures: real UID, no groups/caps, no_new_privs, writable own
  Documents folder, parent home/runtime and unrelated Private areas hidden,
  IPv4/IPv6 sockets denied. Public probe files removed after each check.

Ten graphical offline applications reached native windows: LazPaint, Geany,
gThumb, KeePassXC, LibreOffice, Atril, Parole, Ristretto, Mousepad and Quod Libet.
Responsiveness/file-dialog acceptance is pending. Separate
`Private/Documents/<app>` folders are the current assumption, pending Sam's
preference; no existing personal files were moved or copied. Homes stay in RAM.
Public KeePassXC/VLC update-disabled defaults are seeded into fresh role homes.

VLC 3.0.24 cannot open its Qt interface without X11. Its launch now refuses with
a graphical explanation. Media defaults now use native Parole (video) and Quod Libet (audio); no Xwayland fallback,
unstable package or custom VLC build. See [upstream source](https://github.com/videolan/vlc/blob/3.0.24/modules/gui/qt/qt.cpp#L405-L415).

Native locking now follows [the Private-storage design](private-lock-20261013.md):
manual/idle locking closes DATA, and the SYSTEM passphrase unlocks the screen
without reopening Private. Selective SYSTEM settings remain available with
its full OS mount view read-only. Petal password login is
disabled; SYSTEM, administrator and Private credentials are independent.
Scoped sudo, invalid-password, extra-argument, application-role and installed
PAM negative checks passed again with the new verifier. A production monitor
configured for 600 seconds triggered storage closure and the native lock screen.
An accelerated real-event download-mode test passed from an open baseline.
Suspend testing caused unexpected power-off and is disabled in staged defaults;
cold boot remains pending. Keyboard SysRq remains disabled.

During live integration, Codex incorrectly sent SIGUSR1 to reload Labwc; this
terminated the test desktop. Sam confirmed no personal work was in progress.
LightDM restart restored native XFCE, panel, desktop and idle helper, without
Xwayland. Labwc's installed manual specifies SIGHUP or `--reconfigure` instead.
Do not repeat SIGUSR1. Wallpaper's old temporary binary was missing on restart;
signed trixie swaybg is now installed in guest RAM and the normal source helper
and global autostart are staged. One renderer runs; visual confirmation pending.
Wallpaper helper now refuses duplicate instances with a session-owned lease.
A subsequent normal LightDM restart automatically restored exactly one normal
wallpaper helper/renderer and one idle monitor, with native XFCE and no Xwayland.
Labwc's supported `--reconfigure` command succeeded without ending the session.

VPN transition fixture passed disconnect, repeated disconnect, missing-profile
failure/rollback, reconnection and switching to the same usable profile. Active
gates refused disconnected state and accepted restored state. During the bounded
window, header-only counters observed 205 WireGuard transport packets and no
unexpected physical IP egress, including off-tunnel public UDP/DNS/time canaries
from root, desktop and network roles. This is one measured QEMU window, not a
general proof of no leaks. Native network application relaunch completed; HTTPS
over IPv6 passed from the actual network-role UID 940 without capabilities. The
later wallpaper restart closed GUI apps again; no personal work was in progress.

Also outstanding: remaining panel/status acceptance; concurrent-created
0600 download permissions; Tor cache live-update acceptance; continuously forking
cleanup failure; switching between two independently usable profiles with native applications;
cold boot/persistence/admin setup; monitor hotplug and hardware acceptance.
The unrestricted Wayland clipboard is not isolated. These tests do not establish
anonymity, absence of forensic traces or Tails-equivalent security.

Cleanup fixture passed: disposable VLC role parent/child processes ignoring
SIGTERM were stopped, its RAM home removed, and a hostile home symlink did not
modify a public target outside that home. A continuously forking adversary has
not been tested; the implementation refuses cleanup if role processes remain.

Vim now runs in a native XFCE terminal under its own role, without the desktop
terminal server or session bus. The local HTML viewer uses an offline Firefox
role with update/telemetry defaults disabled. Both reached native windows with
public mode-0600 selected-file fixtures. The arbitrary offline-command fallback
has been removed. Thirteen role-boundary fixtures passed, including both new roles.

Explicitly selected outside files open read-only through descriptors opened as
Petal, not root. Public checks passed for missing neighbor exposure, denied root-only
items, symlink/nonregular rejection and inode pinning across rename. Mode-0600
items use a bounded (64 MiB) RAM snapshot, without changing original permissions.
Larger restricted items need the app's own Private folder. Save edits into that
folder. Snapshot directories are removed by role cleanup/storage locking.

Source selects native XFCE/Wayland as the next image's default session. This is
not a rebuilt-boot acceptance claim. Media MIME queries select the installed
Parole and Quod Libet desktop files. Graphical lock/download launchers and source
helper-group entries are prepared; the existing saved panel is not overwritten.

The separate SYSTEM store, boot/default-account corrections and memory
zeroing verification are recorded in [system-state storage](system-state.md) and
[memory protection](memory-protection.md). Six QEMU VPN profiles migrated with
originals preserved; connection and the active gate passed while Private stayed
closed. Ordinary offline confinement hides both SYSTEM mounts.

Authenticated temporary SSH root maintenance lease is host exec session 7608.
Remove `/tmp/petalos-public-maintenance.py` and `/run/petalos-root-maintenance.py`
and close that lease at completion/pause. Never put credentials in host tools.
