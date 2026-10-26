# Full-build VM preview, 2026-10-23

Git base: `543cf7ef2dd49eb0903fddc757fff2cff774502f`; existing uncommitted
work preserved. Completed release: `20261023-211330-297439`. The build and
artifact verification passed. This is a preview, not full release acceptance.

A fresh disposable 16 GiB sparse VM was provisioned under
`../testing/audit/20261023-220521-839943/`, with new independent SYSTEM/Private
keys, three distinct test-only credentials and fresh SSH identities. Secrets
remain outside source/build inputs and this report. The previously authorized
audit VPN profile and signature-verified Tor archive were provisioned into
its encrypted SYSTEM state. No existing VM disks or physical media changed.

## Observed

- Actual graphical SYSTEM passphrase prompt displays the supplied animation.
  A rejected entry returned to a fresh prompt; a subsequent test-only SYSTEM
  entry booted successfully. The user reported also trying a password during
  the first attempt, so that rejection is not an isolated negative test.
- Desktop-preparation artwork displayed; native desktop handoff completed.
- Actual desktop shows `04-petal-drift.png`, Crystal Dock and the top XFCE bar.
- Pinned SSH access succeeds. Labwc, Crystal Dock, XFCE panel/desktop,
  swaybg and Conky are running; no failed systemd units were listed.
- Persistent wallpaper library has eight PNGs; the persistent alias exists;
  immutable lock-screen wallpaper remains available at its original path.
- Private mapping is closed and no swap is active after boot.

## Follow-up

The Secure Boot VM's GRUB menu showed pink console text but no Tux background.
The earlier unsigned standalone GRUB rendering fixture does not establish that
the theme works with the signed boot chain. Root cause remains unverified;
review font/theme loading under signed GRUB before declaring boot branding
accepted. No Secure Boot settings or protections were weakened.

This pass does not establish saved-dock preferences across reboot, all real app
launch/grouping/focus workflows, the full production error path, or hardware
GPU/HiDPI/touch/suspend behavior. The VM remains running for Sam's visual trial.

## Build recovery

The first full build stopped because a new persistent-library alias collided
with the existing immutable lock-image directory. The alias now uses
`/usr/share/backgrounds/petalos-wallpapers`; the lock-image path is retained.
The actual hook-prefix regression fixture and other phase-two branding checks
passed. A first resume exposed live-build's bootstrap-cache/stage-marker
mismatch; generated package stages were rebuilt from cached public archives.
Residual pre-existing configuration caused dpkg prompts whose nested PTY did
not receive outer-terminal input. A bounded host-authenticated recovery sent
keep-existing responses only to the pinned build dpkg PTY; remaining prompts
required exact comparison with reviewed build-input files. No host security
settings changed. Final hooks, compressed image and artifact readback passed.
