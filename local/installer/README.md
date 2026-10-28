# Bloom 0.4.4

Bloom is a CLI-first Linux installer with a soft-pink GTK overlay. It installs new
layout-2 media, updates OS contents, wipes selected drives and manages offline
SYSTEM settings. Windows and macOS adapters are future work.

## Portable edition

The Linux amd64 edition runs from its extracted folder without installing a
Debian package. It bundles Python 3.13, GTK 3, fonts, public CA certificates and
the disk/encryption tools from checksum-verified installed trixie packages.
It does not need FUSE or unprivileged user namespaces.

```sh
tar -xzf bloom-0.4.4-linux-amd64.tar.gz
./bloom-0.4.4-linux-amd64/bloom
```

The launcher opens the GUI by default; append `--help` for the CLI or
`--portable-check` to verify all bundled files. Keep the whole extracted folder
together. Do not run it with sudo. Downloads remain in the chosen download
directory; no package, menu entry, polkit policy or service is installed.

Administrator operations use the desktop's existing `pkexec` and authorization
agent. A static native bootstrap creates a root-only `/run` directory, receives
a bounded public-code stream over a pipe and compares its SHA-256 to the digest
compiled into that bootstrap. It rejects traversal, duplicate files, unusual
modes and truncated input. Only then does it run the existing worker using the
protected runtime. A private mount namespace supplies the bundled `/usr` to
that operation; the host's `/usr` remains unchanged. Normal completion, errors
and cancellation remove the temporary runtime. Forced termination or power loss
may leave public runtime files until reboot. Passwords follow the public-code
stream through the same private pipe and are never staged as files.

Initial target: Debian 13 and compatible **amd64, merged-/usr** Linux desktops
with mount namespaces and the kernel SHA-256 hash API. Host Python, GTK and
special disk tools are not required. Desktop services, the Linux kernel and
administrator authorization still come from the host. The self-check establishes
internal consistency, not an independently authenticated publisher identity.
Older distributions and other architectures need separate acceptance.

Build locally without administrator rights or network requests:

```sh
python3 -B local/installer/build-portable.py
```

The builder reads only package-owned public runtime files, checks them against
dpkg checksums, records exact package versions and includes copyright/license
files. It excludes local host configuration, site packages, caches and personal
data. See [portable implementation and acceptance](../../docs/portable-installer.md).

## Install and launch

Build the Debian package without administrator rights:

```sh
python3 -B local/installer/build-package.py
sudo apt install ../installer-dist/bloom-installer_0.4.4_all.deb
bloom gui
```

Run from a Linux graphical session. The installed GUI asks for Linux
administrator authorization using polkit when a drive operation starts. Its
privileged backend is installed under root-owned `/usr/lib/bloom-installer`.
Passwords use masked fields and a private pipe, with cancellation and cleanup;
they are never command arguments, environment variables or saved job files.
Your host's administrator authorization is separate from the new PetalOS
administrator password.

The source CLI works without installing Python packages:

```sh
scripts/bloom --help
scripts/bloom --json devices
scripts/bloom encryption
scripts/bloom encryption --benchmark
```

The benchmark measures RAM cipher throughput on this CPU. It does not predict
SD-card throughput or another computer's unlock latency.

## Protection tiers

All three tiers use **AES-256-XTS with two 256-bit keys** and LUKS2/Argon2id.
They change the cost of unlocking and guessing passphrases, not ongoing cipher
throughput. A CPU without AES acceleration may limit disk speed in every tier.

| Tier | Intended use | Argon2id memory | Initial work target per volume |
| --- | --- | --- | --- |
| Fast — Legacy Friendly | Older computers and shorter unlock waits | 32–64 MiB | About 1 second |
| Balanced — Recommended | Default for modern computers | 256–512 MiB | About 2 seconds |
| Paranoid — Maximum Protection | High-value data and expensive offline guessing | 1–2 GiB | About 5 seconds |

For every tier, new SYSTEM and administrator passwords need at least **15
characters** and Private needs at least **24 characters**. Spaces are allowed,
and no special character mix is required. Each new-password field has a live
local strength meter based on zxcvbn-c, bundled in the portable app. The meter
checks common words and predictable patterns; it sends nothing over the network
and saves no passwords or scores. Its estimate is advisory, with minimum length
shown separately. It examines up to 128 ASCII characters; other text can be used
but may show no strength estimate. There are no cracking-time guarantees.

Use unique, randomly chosen words or characters. Length requirements do not
measure entropy and cannot make predictable phrases strong. All three new
credentials remain distinct: SYSTEM, Private and administrator. Existing media
are never re-keyed automatically and retain their existing credentials.

Bloom benchmarks Argon2id using RAM before opening the target for an install.
It reserves at least half the currently available RAM, respects cgroup-v2
limits, and caps parallelism at the available CPU affinity and tier limit.
On slower CPUs it can extend the work target to twice, then four times the
initial target to preserve the memory floor. If the tier still cannot be met,
installation stops before erase. The calibrated values are fixed for formatting
all three independently keyed volumes and checked in each new header.

OS and settings unlock sequentially: one SYSTEM prompt performs two derivations.
Private unlock is separate. Calibration describes the installer computer;
another computer may take longer or lack enough RAM. Select the tier for the
oldest computer you plan to boot.

AES-256 provides a strong margin against known quantum key-search attacks;
this applies to **all tiers**. It is not a guarantee that a passphrase or entire
computer is quantum-safe or resistant to compromise. Paranoid increases offline
guessing costs; it does not promise immunity to any adversary. This release is
**passphrase-only**; hardware tokens and additional factors are deferred.
See [design and sources](../../docs/bloom-encryption.md).

```sh
bloom encryption
bloom encryption --calibrate balanced
```

Calibration changes no drive. The older `petal-installer` launcher remains a
compatibility alias; Bloom and `bloom` are the displayed app name and primary
command. PetalOS remains the operating system and release/storage format.

## Choose a build

The GUI checks GitHub on launch and loads build choices when a version is
selected. Variants may include a local AI agent; only actual published choices
are offered. The repository currently has no published releases (checked
2026-10-24), so the GUI explains that state rather than displaying blank lists.
For private repositories, GitHub access accepts a masked read token for this
app session only. The CLI still accepts GH_TOKEN from its environment.

```sh
bloom releases
bloom variants --version VERSION
bloom download --version VERSION --variant VARIANT --destination /path/to/new-bundle
bloom verify /path/to/new-bundle
```

The default repository is `Samwarez/PetalOS`; global `--repo OWNER/REPO` changes
it. Private repositories can use GUI GitHub access or CLI `GH_TOKEN`. Tokens
are never forwarded to redirected asset hosts or privileged workers. Global
`--json` returns machine-readable results; progress/errors use stderr.

For the next local card build, export a **completed new split-storage release**:

```sh
scripts/bloom bundle-from-build ../releases/COMPLETED_RELEASE --version VERSION --variant base --destination /path/to/new-bundle
```

This verifies release-manifest hashes and the paired-unlock helper in its
initramfs. The existing `20261023-211330-297439` release predates split storage
and is refused. Build and validate a new OS release before card use. The
`bundle-create --help` command supports explicit reviewed kernel/initrd/rootfs,
signed EFI files and optional read-only squashfs modules.

## GUI layout

Choose build, Choose drive, and Review & results are separate pages. Forms do
not use embedded scrolling panels; only long review/results text scrolls.
Installation options open a compact dialog. The app uses a consistent light
pink palette for menus, disabled controls and unfocused windows, even when the
desktop theme is dark; it does not modify desktop theme preferences.

Download from GitHub saves to Downloads/PetalOS automatically. Save location
changes that directory. Use an already downloaded build lets you select an
installer download folder, then check its version and files. The folder must
contain petalos-release.json, selection.json and its payloads. An ISO alone or
a raw live-build output directory must first be exported; they are not installer
downloads. The CLI continues using the term bundle for that complete folder.

## Review and execute

Select the exact idle whole disk returned by `devices`. Mounted, active, host
system and read-only targets are refused. Device identity, partition ownership,
mounts and encryption holders are rechecked during execution. Plans make no
writes. Appending `--execute` requires administrator rights and confirmation.

```sh
bloom install --device /dev/SELECTED --bundle /path/to/new-bundle
sudo bloom install --device /dev/SELECTED --bundle /path/to/new-bundle --execute
bloom update --device /dev/SELECTED --bundle /path/to/new-bundle
sudo bloom update --device /dev/SELECTED --bundle /path/to/new-bundle --execute
bloom wipe --device /dev/SELECTED --method keys-and-random
sudo bloom wipe --device /dev/SELECTED --method keys-and-random --execute
```

These are example placeholders, never a reason to guess a device name. In an
interactive terminal the executor displays the plan and asks for `ERASE` or
`UPDATE`, then hidden password entry. Automation must supply `--confirm` with
the exact reviewed `plan_sha256`; credentials still use hidden input. The
backend recomputes the plan before opening the target. Changed plans, bundles
or selected variants require another review.

Fresh install defaults to random overwrite/readback before creating five
partitions. `--erase-mode quick` skips old-data overwrite and must be chosen
explicitly. OS, SYSTEM settings and Private get independent LUKS2 keys. OS and
settings use one SYSTEM passphrase; Private and PetalOS administrator passwords
must each differ. Balanced encryption is AES-256-XTS with Argon2id; the app
explains the other profiles. Installed boot support is **UEFI x86_64**; the BIOS
region is reserved but no legacy BIOS loader is installed.

Update opens OS only, stages and verifies a generation, changes required BOOT
selectors, and preserves SYSTEM settings and Private closed. Production retention
keeps only the current OS after completion; `--retention test` keeps at most one
previous OS. Legacy combined-layout migration is refused.

Wipe modes are `keys-only`, `keys-and-random` and `random`. Key removal is
reported separately from random-fill/readback completion. Cancellation may
leave already-erased keys or partial writes; keep the drive connected until
cleanup finishes. Removing current keyslots cannot revoke an external header
backup or volume key. Logical overwrite cannot prove erasure of inaccessible
flash spare/remapped pages.

## SYSTEM settings and recovery

The GUI's SYSTEM settings tab lists saved assets, imports or explicitly replaces
one named asset, and verifies the shared SYSTEM passphrase against OS/settings.
Use **Browse SYSTEM folders…** to open a normal desktop file-manager window.
Bloom requests host administrator authorization and SYSTEM's passphrase once,
keeps one scoped worker/mapping open, and creates a private RAM working copy
under `/run/user/UID`. Navigation and drag-and-drop use ordinary local file
operations, without restaging the portable runtime or repeating Argon2id.

Drag files into `Files` for general saved files, `Network/Profiles` for WireGuard
profiles, `Wallpapers` for PNGs, or the pending theme/override JSON folders.
Return to Bloom and choose **Save changes and lock** to validate changes and
apply them to the card; **Discard and lock** leaves unsaved edits off the card.
Simply closing the file-manager window does not end the Bloom editing session.

The file manager runs as the desktop user, never root. Private, administrator
credentials, and managed desktop/application files are excluded from the working
copy. VPN/schema validation, active-profile deletion protection, no-link and
regular-file checks remain enforced on save. General files do not become active
OS settings. The copy is bounded to 128 MiB, 1000 entries, 12 directory levels
and 32 MiB per file. Native desktop metadata files are ignored.

Bloom validates all changed files before starting card writes. Each file is
published atomically; a hardware/I/O failure can still interrupt a multi-file
save. Unexpected changes to card files outside the session stop the save.
Normal close, discard, client exit and EOF close the worker's mappings; the
client removes its RAM copy after worker cleanup. The host file manager retains
its usual preview, cache and Trash behavior; Bloom does not reconfigure it.

Only the settings operation opens SYSTEM; Private remains closed. CLI equivalents:

```sh
sudo bloom store --device /dev/SELECTED
sudo bloom store --device /dev/SELECTED --import /path/to/profile.conf --kind vpn --name home
sudo bloom store --device /dev/SELECTED --import /path/to/wallpaper.png --kind wallpaper --name sakura
sudo bloom recovery --device /dev/SELECTED
```

`--replace` explicitly permits atomic replacement of that exact stored name.
Import source folders may be symbolic links, including Downloads folders on
another filesystem. Bloom resolves the source folder and pins its directories
before opening the selected regular file. A symbolic link used as the selected
file itself is refused; choose its original file. Settings destinations and OS
release inputs retain their separate strict no-symlink protections.
Imports validate WireGuard profiles and PNG dimensions; they never connect VPNs
automatically. The full SYSTEM view stays read-only and imports write only the
selected settings view. Theme palettes and bounded desktop overrides are staged
**inactive** JSON; their boot loader is future work. Arbitrary persistent root
scripts are unsupported. Recovery verifies passphrases without opening mappings;
header restoration, paired password rotation and migration are not implemented.

## Release catalog and trust

Each GitHub version supplies `petalos-release.json`, a `format: 1` object with
matching `version` and a `variants` list. Each variant has `id`, `name`,
`description`, `architecture: "amd64"`, `layout: 2`, `local_ai` and `payloads`.
Required roles are `kernel`, `initrd`, `rootfs`; fresh install also requires
`shim`, `grub`, `mokmanager`. Each descriptor contains a safe `asset` filename,
positive `bytes`, and lowercase hexadecimal `sha256`. Optional `modules` maps
safe `*.squashfs` names to the same descriptor format.

Catalogs are capped at 1 MiB; payloads at 64 GiB each. Downloads do not unpack
archives or execute scripts. Bundles hold the catalog, `selection.json` and the
selected assets. HTTPS, lengths and SHA-256 are verified before publication and
again by the executor. PE signature presence is checked, but publisher identity
is not independently authenticated: **use a trusted release or reviewed local
build**. Independent release signing/key distribution remains future work.
This work does not publish GitHub releases.

## Verification

```sh
python3 -B -m unittest discover -s local/installer/tests -v
python3 -B tests/check-release-generations.py --layout2
python3 -B tests/run-installer-engine-vm.py /home/sam/portable-live/releases/COMPLETED_RELEASE
python3 -B tests/run-installer-gtk-vm.py /home/sam/portable-live/releases/COMPLETED_RELEASE
```

The acceptance harness creates new disposable USB disks, uses the installed
package core with actual target guards, real Argon2id/LUKS2/ext4, and firmware
boots through signed shim/GRUB/kernel. Its small synthetic OS tests install,
update, preservation, interrupted key removal/retry and full wipe/readback.
The VM-only post-verification boot probe stops before a desktop session.
Artifacts default to RAM-backed `/tmp/petalos-installer-tests`; reports contain
no passwords. See [implementation and acceptance](../../docs/installer-app.md).

`image-wipe` remains developer tooling for an explicitly chosen owned regular
image, never a physical block device. It refuses links, loop-bound and open
files. Existing images and the physical card are not disposable test inputs.

GUI 0.2.1 verification: 34 display-independent checks and five native GTK checks
passed. The native tests use a VM-local Broadway display, a read-only OS squashfs
and RAM overlay; no full desktop/polkit interaction or real release download is
claimed. Main forms fit a 768px-high screen including decorations in that test.
The full [GUI record](../../docs/installer-gui-20261024.json) includes scope and
fixture corrections.
