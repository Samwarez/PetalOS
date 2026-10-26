# Crystal Dock replacement — 2026-10-23

Crystal Dock replaces the **bottom XFCE dock** in the next build. The XFCE top
bar stays for the first hands-on trial, as Sam requested; removing it and moving
its remaining controls is a later decision. No full OS build, live-system
update, physical-media write, commit or push was performed.

The source/work snapshot `snapshots/before-crystal-dock-20261023-203947.tar.gz`
was created and verified after checking the preceding source backup. Earlier
uncommitted Trash, touch, Qt sidebar, retention and branding work is preserved.
Git base: `543cf7ef2dd49eb0903fddc757fff2cff774502f`. The previous complete release
remains `20261019-211301-083244`.

## Implementation

Pinned upstream [Crystal Dock 2.16](https://github.com/dangvd/crystal-dock/releases/tag/v2.16)
is built with Debian trixie Qt 6.8 and LayerShellQt, with Debian hardening flags.
The maintained source/archive checksum, patch, builder and executable provenance
are recorded with the [builder instructions](../../local/crystal-dock/README.md).
No unstable packages or prebuilt third-party dock binaries are used. Generated
executables and public source archives stay outside Git; the upstream license
is included in the image. The build hook checks the executable and exact
Qt/LayerShell runtime versions; preflight refuses stale local artifacts.

Defaults provide a pink translucent Glass 3D dock, 56-pixel icons that zoom to
96 pixels, application menu, terminal, file manager, Tor, a Helpers group,
guarded screen lock and RAM Trash. The full legacy Adwaita icons and Qt SVG
plugins are explicit runtime dependencies. The desktop's XFCE identity is kept
for launched applications; a small dock patch selects Labwc integration for it.

The first run receives defaults from `/etc/xdg/crystal-dock/XFCE/`. Appearance
and `panel_N.conf` preferences can be saved through **Save Desktop Settings**
in selective SYSTEM persistence. Caches, activity logs, other files and whole
home directories are excluded. Existing saved archives are not edited in place.
Restoring a stock bottom-panel layout removes that known panel once and retains
the top panel, custom layouts and plugin records still used by another panel.
An explicit migration marker prevents repeating the change over later choices.

PetalOS Helpers opens a native GTK window containing the existing storage,
VPN, download-mode and preference actions. Buttons launch the same fixed
read-only desktop entries and guarded wrappers used elsewhere. Screen lock
calls `portable-lock`; the session menu calls the existing XFCE session dialog,
not raw `labwc --exit`. Authentication, VPN gates and app sandboxes are unchanged.

The dock's version-checking implementation is disabled, including when an older
configuration requests it. Its independent Wi-Fi manager is disabled so the
existing known Wi-Fi/secret-service flow remains authoritative. The top bar
continues supplying Wi-Fi and status controls during this trial. Optional
volume/battery/clock components are not enabled by default or claimed tested.
Their role must be reviewed if the top bar is removed.

The Trash icon opens/empties the existing RAM Trash. **Dropping files onto it
is intentionally unsupported** and shows a notice to use Thunar's Move to Trash.
This avoids introducing a second unsafe rename/copy path alongside the bounded
Private-to-RAM implementation. It does not silently delete or move the files.

Startup is terminal-free. A closed/crashed dock can be started from the
Applications menu; startup failures produce a notification. Healthy duplicate
starts are ignored, and native singleton enforcement remains in place. The boot
Wait curtain now includes Crystal Dock in its bounded desktop readiness check.

## Verification

[Results](results.json) contain component provenance, source hashes and outcomes.

- Compilation and the upstream CTest application-menu suite passed in a
  disposable Debian trixie RAM root. Qt's newer `QImage::flipped` call was
  replaced with the equivalent Qt 6.8 vertical-mirror call.
- A native headless Labwc session rendered the actual patched executable with
  Wayland LayerShell integration, the supplied wallpaper and themed icons.
  Clicks exercised terminal/file-manager launches, the Tor guarded launcher,
  guarded screen locking and the Helpers window. Launch endpoints were **public
  stubs**, not real applications, credentials, storage or network operations.
- The Helpers window appeared through Labwc's foreign-toplevel protocol,
  exercising incoming task tracking. Full real-app grouping/activation still
  needs image-level acceptance.
- A second instance was refused. The fixture exercises a forced dock crash and
  restart in its private PID/IPC namespace, including preservation of a changed
  preference without rebooting.
- Syscall observation showed no Internet socket creation in the tested dock
  startup/restart, even with version-check and Wi-Fi flags set in the fixture
  configuration. The namespace also had no external network. This is bounded
  evidence, not proof that every possible dock action is network-free.
- Preferences roundtrip tests exclude unrelated files. Migration tests preserve
  top/custom panels and shared plugin records. Existing desktop settings,
  Private-controller and full build-input checks pass.

The test root needed a MIME-cache generation step and complete Qt SVG/legacy
icon packages. Its GTK accessibility bridge was disabled **only in the
fixture**, whose minimal D-Bus session has no accessibility service. These are
not host or production security-policy changes. No host packages were installed.
The preview has no XFCE top bar because it is a dock-only isolated session;
the candidate configuration retains the real top bar.

Previews: [dock](dock.png), [Helpers and task tracking](helpers.png),
[after restart](restarted.png).

## Remaining acceptance

Build a fresh complete image and cold-boot the disposable encrypted VM. Verify
the actual top bar plus dock, saved-layout migration, app grouping/activation,
real guarded app launches, graphical authentication, Private lock/unlock, RAM
Trash open/empty, restart notification and saved dock preferences across reboot.
Test low-resolution/HiDPI, touch/pen, multi-monitor placement, auto-hide and
suspend/resume on hardware. New Qt dependencies require normal release package
review. No complete-release, hardware or anonymity/security acceptance is claimed
from these component tests. The card and current VM images are unchanged.
