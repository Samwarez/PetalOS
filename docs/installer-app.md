# Bloom installer app

The app starts with a portable Python CLI/core and an optional Linux GTK overlay.
Both use the same parser, validation and operations. Windows/macOS adapters are
future work. Source and usage: [local/installer](../local/installer/README.md).

Bloom 0.4.0 has a [portable Linux amd64 edition](portable-installer.md):
extract its folder and run the GUI/CLI without installing the Debian package.
It bundles Python/GTK/tools and uses the host's administrator authorization with
a build-pinned temporary backend. The installed backend remains the `.deb` path.

## Release choices

Choose a GitHub release **version**, then a **variant** from its catalog.
Arbitrary names and a local-AI-agent flag support the requested choices without
hard-coded product names. Downloads stream to temporary directories, validate
lengths and SHA-256, and publish only after verification. Asset paths, metadata
limits, pagination and HTTPS redirects are checked. Authentication is not
forwarded to redirected asset hosts. Private repositories use `GH_TOKEN`.

The initial trust boundary is GitHub HTTPS plus catalog checksums. Use trusted
releases or reviewed local builds. Independent release signing, publisher-key
distribution and rotation remain future work; checksums and PE signature presence
do not authenticate the publisher. No release was published by this work.

## Modes and implementation status

| Mode | Intended behavior | Current implementation |
| --- | --- | --- |
| Fresh install | Erase the drive; independently encrypt OS, SYSTEM settings and Private. OS/settings share one SYSTEM passphrase; Private/admin credentials are separate. | Real guarded Linux executor, reviewed plan confirmation, separate password entry and production Argon2id; packaged GUI administrator backend. UEFI x86_64 boot support. |
| Update | Replace OS contents and BOOT selectors, keeping settings and Private closed and unchanged. | Real OS-only execution and generation activation/retention; entire settings/Private ciphertext partitions compare byte-for-byte before/after the actual installer update. |
| Wipe | Remove LUKS keyslots first if selected, then random-fill/read back the logical drive. | Real device key removal and verified random fill, with separate completion reports. Disposable virtual USB tests cover interruption after key removal and a successful retry. |
| SYSTEM settings | Open only settings with its passphrase, browse or explicitly import assets. | CLI and GUI authenticated list/import/explicit replace operations. Full mount stays read-only; only the selected settings view can be writable. |
| Recovery | Check the shared SYSTEM passphrase against both independent headers, keeping Private closed. | CLI and GUI paired verifier with drive/volume checks. No automatic header restoration, passphrase rotation or legacy migration. |

Install/update/wipe default to **plans**. Execution requires administrator rights
and explicit confirmation of the recomputed plan. The installed GUI uses a
root-owned installed backend and an exact polkit action; the portable edition
stages a verified root-owned temporary backend. Both use bounded private-pipe requests and
cancellation/cleanup. It never constructs shell commands or persists passwords.
The backend pins source file descriptors, catalog hashes, selected variants and
target identity; it rechecks mappings/mounts during writes. Stop/close requests
cancel through the pipe; the window waits for cleanup.

Build the installable package with `python3 -B local/installer/build-package.py`.
Output: `../installer-dist/bloom-installer_0.4.0_all.deb` and checksum. No host
package installation or physical-card write was performed during development.
The [storage record](split-storage-20261024.md) distinguishes earlier focused
storage/boot verification from complete-image/hardware acceptance.

## Installer acceptance — 2026-10-24

The [saved installer report](installer-engine-vm-results-20261024.json) records a
successful complete run on newly created virtual USB media, using the packaged
core with real removable/USB classification and target guards. Fresh install
uses actual Argon2id/LUKS2/ext4 and independent formats for all three volumes.
The actual installer update keeps settings/Private unopened; host-side SHA-256
of every ciphertext byte in both partitions is identical before and after.

Tests also interrupt immediately after one volume's keyslots are removed, then
retry and verify a complete random overwrite/readback of the separate small
wipe disk. Firmware boots the installed signed shim/GRUB/kernel with Secure Boot
and exactly one SYSTEM prompt. OS and settings open, OS is read-only, Private
stays closed. Synthetic rootfs payloads and a no-secret VM-only post-install
initramfs probe stop this test before desktop boot. It is not a clean rebuilt OS
or hardware acceptance. The earlier full-live-OS test is recorded separately.

The initial firmware probe could not read an EFI variable even though the signed
kernel reported EFI Secure Boot/lockdown. The corrected probe reads the EFI byte
at its defined offset, with the kernel report as fallback; the entire sequence
then passed. Test artifacts moved to RAM-backed `/tmp` after the home filesystem
ran out of space. No original image was reused as a disposable target.

Local validation: 30 installer tests, the layout-2 generation interruption and
retention suite, Python parsing, GTK stylesheet parsing, package permissions,
polkit XML and extracted-package CLI startup pass. Final prewrite refusal and
package-permission additions after VM staging have dedicated local coverage;
the report records that distinction and source hashes. Exact disposable test
credentials are absent from source, reports and the extracted final package.

## Encryption and settings

New [layout 2 media](split-storage-20261024.md) separates OS and SYSTEM settings.
The physical card and earlier releases retain the legacy combined layout. The
installer refuses to call repartitioning an update; migration needs separate
authorization and verified recovery copies.

Default encryption is LUKS2, AES-256 XTS (512 total key bits), Argon2id with a
256 MiB budget and roughly two-second calibration target per header; boot verifies
OS and settings sequentially. Lower-memory derivation
and AES-128 XTS expose their tradeoffs. `encryption --benchmark` measures RAM
cipher throughput on the actual host, without disk writes or invented SD speeds.
Passphrase derivation affects unlock latency/memory; it does not accelerate file
I/O. One-prompt initramfs support is for LUKS2 passphrase slots, not OPAL/FIDO.

VPN imports use the existing strict profile validator and never select or connect
automatically. Wallpaper imports are size/dimension-bounded PNGs. Existing files
are preserved unless explicit replacement of the exact stored name is chosen.
Theme palettes and bounded desktop overrides stage **inactive** JSON descriptions; the OS has no reviewed boot pack loader yet. Arbitrary
persistent root scripts are not implied by mod support.

## Wipe wording

Keyslot removal disables current on-card password slots. A saved header or
volume key can still restore access, and an open mapping retains a usable key.
Random fill covers host-addressable sectors; SD spare/remapped pages may remain
outside host control. Report key removal and completed fill/readback separately,
without promising that a host overwrite proves physical flash erasure.

References: [cryptsetup erase](https://man7.org/linux/man-pages/man8/cryptsetup-erase.8.html),
[NIST SP 800-88r2](https://csrc.nist.gov/pubs/sp/800/88/r2/final),
[GitHub releases API](https://docs.github.com/en/rest/releases/releases).

## GUI

Soft-pink surfaces, rounded cards, plum text and rose accents use the supplied
Petal emblem, copied unchanged with provenance. The overlay offers release and
variant selection, downloads, drive selection, reviewed execution, progress,
cancellation and SYSTEM imports/recovery. Version 0.2.1 removes scrolling form panels and gives the long review/results
text its own page. Installation options use a dialog. The process uses an
explicit pink/light palette, including popup menus, disabled and backdrop states,
without changing desktop preferences.
GTK stylesheet parsing and 34 display-independent installer checks pass.
All five native GTK regressions passed on the exact packaged source in a
networkless VM with a local Broadway display. The complete rendered window is
972 × 721 pixels including decorations/shadows. See the
[GUI validation record](installer-gui-20261024.json) and
[sample layout preview](installer-gui-20261024.png); preview build names are fake. Desktop
polkit prompt acceptance remains separate. No host packages were changed.

## Next physical build

The last completed OS release `20261023-211330-297439` predates split-storage
initramfs support. Build and validate a new release, then use `bundle-from-build`
to export it locally; the exporter refuses the old release. GitHub publication
is optional for local installation. The installer reserves a BIOS partition but
currently installs only the signed UEFI x86_64 chain. No legacy BIOS boot or
physical hardware acceptance is claimed. Existing combined-layout card updates
are refused; its migration remains separately authorized work.


## Release list behaviour in 0.2.1

The connected GitHub releases API returned an empty list for Samwarez/PetalOS on
2026-10-24. No release was published as part of this change. The GUI now starts
lookup automatically, loads builds after selecting a version, and explains empty,
not-installer-ready and network/authentication error states inline. A masked
GitHub access dialog keeps an optional read token only in the GUI process and
passes it explicitly to the HTTP client; it never mutates the environment or
passes that token to the privileged worker. Clear source choices replace Bundle
folder/Local bundle labels. Current local build export requirements still apply.
