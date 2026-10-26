# Phase 2: supplied wallpapers and boot graphics

Prepared on **2026-10-23** against Git base
`543cf7ef2dd49eb0903fddc757fff2cff774502f`, with earlier uncommitted work
preserved. No full OS build, live-system update, physical-card write, commit or
push was performed. The last complete OS release remains
`20261019-211301-083244`. Initial source/work snapshot:
`snapshots/before-phase2-branding-20261023-200603.tar.gz`, verified with its
SHA-256 sidecar; the preceding source backup was also verified.

## Wallpaper library

All eight supplied PNG wallpapers are immutable build seeds under
`/usr/share/backgrounds/petalos-defaults/`. During SYSTEM state preparation,
missing images are copied into **`/mnt/system-state/Wallpapers/`**, available
in the file manager as **System Settings → Wallpapers**. Existing entries are
preserved. Writes use a pinned directory, private temporary files, synchronization
and non-overwriting publication; failures clean the current temporary file.

`/usr/share/backgrounds/petalos-wallpapers` points to this persistent library.
The separate `petalos/` directory retains the immutable lock-screen image.
The default
selection is **`04-petal-drift.png`** there, with the immutable seed as a display
fallback if the persistent image is unavailable. Existing saved wallpaper,
solid-color and gradient settings take precedence. The initial per-monitor XFCE
selection points into the persistent folder, so Desktop Settings starts its
folder chooser there. The corresponding upstream XFCE 4.20.1 settings code was
inspected: it derives that folder from the selected image's parent.

This is selective SYSTEM persistence; it does not open Private, persist home,
or grant applications access to additional stores. Public graphics were copied
unchanged from the supplied directories. [Asset checksums](../../config/includes.chroot/usr/share/portable/branding/assets.json)
cover all **72 supplied PNGs** (eight wallpapers and 64 boot/menu images).

## Boot sequence

| Stage | Artwork | Timing and transition |
| --- | --- | --- |
| GRUB | Pixel Tux background | Pink normal and highlighted menu text; native graphics mode when available. |
| Startup | 20 `startup` frames | 200 ms/frame, one four-second sequence before the SYSTEM prompt. |
| SYSTEM prompt | Six `password/idle` frames | 250 ms/frame, looping; masked input and Caps Lock indication. |
| Rejected passphrase | Six `password/fail` frames | 250 ms/frame, once; retry prompt after 1.5 seconds. Three attempts remain the limit. |
| Accepted passphrase | Six `password/success` frames | 250 ms/frame, looping until the next phase; finishes one cycle even if loading advances quickly. |
| RAM loading | Six frames in each RAMLoad group | 250 ms/frame. RAMLoad1 for the first 30 seconds, RAMLoad2 for the next 30, RAMLoad3 afterwards. |
| Desktop preparation | Six `Wait` frames | 250 ms/frame until handoff; a native Wayland window continues Wait while the desktop starts. |
| Handled boot failure | Supplied crying-character picture | Beside the latest bounded log lines; Space dismisses the graphical error and returns to the boot console. |

RAM loading is **not delayed** to finish the 30/60-second stages. Later groups
appear only if copying is still running. Plymouth uses a 20 Hz refresh clock
with four/five refresh intervals per frame; scheduling and slow hardware can
affect wall-clock precision. There is no claimed progress percentage.

The trusted desktop client starts the temporary Wait window before XFCE. It
closes after the panel, desktop and wallpaper renderer are seen on two checks,
with a 60-second upper bound and Escape dismissal. It is a presentation window,
not a locker or authentication surface. LightDM must release Plymouth's DRM
ownership before Labwc starts; the Wayland window bridges that handoff.
Shutdown/reboot uses Wait with the appropriate caption, rather than a startup
message.

## Failure and boot-chain behavior

The passphrase travels directly from Plymouth over a pipe to cryptsetup, with
no password file, shell variable, command-line argument or logging. The existing
text cryptsetup prompt remains the fallback when Plymouth is unavailable or
`nosplash` is selected. Non-passphrase cryptsetup errors fail immediately;
incorrect passphrases retry within the existing limit. SYSTEM, administrator
and Private credentials retain their separate purposes.

The initramfs panic hook shows the artwork and up to 22 bounded boot-log lines
before releasing Plymouth on Space. Selected post-initramfs failures
(live-config, AppArmor setup, temporary-content setup, administrator setup and
the display manager) have an OnFailure display handler while Plymouth is still
available. LightDM's immediate-quit failure action is replaced by that handler;
the build refuses an unexpected upstream OnFailure configuration. Log material
is displayed from RAM, not saved into persistent diagnostics.

Firmware errors, failures before the graphics stack exists, kernel panics,
broken GPUs, or failures after Plymouth has exited cannot be guaranteed this
graphical treatment. Escape retains Plymouth's underlying boot-log view. The
error display does not grant shell access or change recovery authorization.

The signed EFI executables and kernel are unchanged by this work. GRUB artwork
and fonts are included in the release manifest. The offline generation updater
verifies and stages content-addressed artwork before selecting its theme;
existing device checks, exclusive update lock, file readback and rollback
handling remain. Styling follows verified OS activation; an interrupted style
update leaves the verified OS bootable with its earlier styling. No live OS
updater was added. Identical artwork is reused across builds; obsolete small
artwork directories are not automatically deleted by OS retention.

## Verification and previews

[Regression results](regressions.json) cover wallpaper seeding, preserving custom
files, write failure/retry, symlink refusal, monitor selection, saved-image/color
overrides, all supplied checksums, the actual binary hook, offline GRUB
interruption/retry/idempotence and rollback compatibility. Boot-unlock shell
fixtures cover wrong/correct retries, three rejected attempts, other cryptsetup
errors, text fallback and a missing-volume timeout. Existing storage-controller,
settings and OS-generation tests also pass. Final build-input validation and
the installed Plymouth script parser pass.

[QEMU component results](qemu-components.json) use the previous release's kernel
and initramfs userspace with the new theme/helper/unlock script in a disposable
fixture. Networking is absent. A newly generated disposable LUKS volume accepts
the correct test passphrase after rejecting a wrong one. Startup, Idle, Fail,
Success, all three timed RAM groups, Wait and error artwork were captured and
visually inspected. RAM-copy duration is **simulated** in this fixture; this is
not a newly built PetalOS boot. The panic display is invoked explicitly; Space
quits Plymouth and returns to its caller. The full recovery shell is not tested.

The native Wayland Wait-window test uses the last release's userspace inside
isolated user/PID/mount/network namespaces and a headless Labwc compositor.
The window mapped fullscreen on `GdkWaylandDisplay`, and six distinct animation
frames were observed. It does not prove the full LightDM-to-desktop transition.

GRUB's theme also rendered in a disposable UEFI fixture. That rendering fixture
uses a standalone unsigned GRUB, so it does **not** validate the production
Secure Boot chain. The production signed executables were not replaced.

Previews: [GRUB](grub.png), [SYSTEM prompt](password-idle.png),
[wrong passphrase](password-failure.png), [RAM loading](ram3.png),
[Wait](wait.png), [error and log](error.png).

## Next acceptance

Build a fresh image and let artifact verification check the actual squashfs,
initramfs contents, menu assets and boot flags. Cold-boot a disposable encrypted
VM with saved desktop overrides and a fresh wallpaper library. Verify the real
RAM-copy transitions, LightDM/Wayland handoff, display-manager failure behavior,
wallpaper selection and persistence across reboot, and ordinary shutdown/lock.
Hardware acceptance still needs low-resolution/HiDPI displays, real Intel/AMD
graphics, any firmware-to-Plymouth gap, and the production signed GRUB menu.
No hardware acceptance or anonymity/security guarantee follows from these
component tests. The earlier RAM Trash/touch changes also await a full build.
