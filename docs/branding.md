# PetalOS system identity

The default kernel/static hostname and friendly computer name are `PetalOS`.
Live-config receives LIVE_HOSTNAME=PetalOS. The image supplies consistent
hostname/localhost mappings and login banners. NetworkManager's existing
no-hostname-advertising, MAC randomization, LLMNR and mDNS policies remain in
place; changing the local name does not enable network discovery.

RC 1 identifies NAME as PetalOS, PRETTY_NAME as PetalOS RC 1, and ID as
petalos in both OS-release locations. VERSION is RC 1 and VERSION_ID/BUILD_ID
are rc1; LSB identification and login/boot presentation also name PetalOS RC 1.
ID_LIKE=debian and VERSION_CODENAME=trixie retain package/API compatibility.
The ISO volume label is PETALOS_RC1, within ISO/Joliet naming limits.
These fields follow the
[OS-release specification](https://manpages.debian.org/trixie/systemd/os-release.5.en.html).

ISO application/publisher/volume names and the live-build HDD image label now
use PetalOS. A binary-stage hook brands the generated GRUB/Syslinux labels
before medium checksums are calculated. Verification against four existing
generated boot files confirmed branding changed while kernel/initrd paths
and boot arguments remained identical. Signed EFI binaries and vendor EFI
paths retain their original compatibility names.

The desktop gets a local PetalOS Guide, opened using the offline Geany wrapper.
The three upstream website shortcuts from desktop-base are hidden rather
than presenting upstream distribution links as PetalOS support. Package
copyright/license notices, Debian archive/source URLs and keys, dpkg vendor
metadata, /etc/debian_version, NTP pool names, technical references and past
test records retain accurate upstream names. Existing desktop wallpaper/art
and selectively saved personal panel settings are preserved.

Verified in the running VM: hostname PetalOS, local hostname resolution,
lsb_release distributor PetalOS, current Tor readiness and unchanged general
sudo authentication requirements. Build-input validation passed. The guest
files are currently in RAM; the installed configuration layer predates these
changes. Fresh-boot branding and produced ISO labels await the next build.
No new full build or physical-card update was performed.

## Phase 2: branding and visuals

Sam selected these improvements for the existing XFCE bottom shortcut panel:

- Larger application icons.
- A rounded, translucent, glass-like background.
- Grouped shortcut menus, including the PetalOS helpers.

Keep existing guarded application launchers and selective settings persistence.
This scope does not require true background blur, fan-out animations, icon
magnification, or replacing the dock/compositor. These are planned visual
changes for Phase 2, after the functional/stability work; do not add them to
the current combined test build.

Phase 2 started on 2026-10-23 with the supplied wallpaper library, GRUB artwork
and boot animation sequences. The implementation and component evidence are
recorded in [the phase-two boot/wallpaper report](phase2-branding-20261023/README.md).
The first wallpaper/boot change does not alter the guarded launchers or
application sandboxes. Sam subsequently selected Crystal Dock as the bottom
panel replacement. The XFCE top bar remains for the first trial; its removal
will be decided after hands-on testing. See [the Crystal Dock report](crystal-dock-20261023/README.md).

The [custom icon checklist](phase2-icon-inventory.md) inventories the completed
Phase 2 preview's launchers, startup bars, storage places and status variants;
the companion CSV/JSON retain all installed desktop-entry references. Sam wants
battery and network indicators in the **bottom Crystal Dock**. Their integration
is pending; the current preview has them disabled. The checklist also records
the blank VPN task icon and Tor's missing minimize control as integration issues.

RC1 label checks passed on 11 previously generated boot configuration files:
all non-presentation lines remained byte-for-byte equivalent, and reapplying the
branding hook did not duplicate the RC1 suffix. These are pre-build checks;
artifact verification and cold-boot checks still apply to the resulting release.
