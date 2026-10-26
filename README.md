# PetalOS

PetalOS is a Debian trixie live system with an XFCE desktop on the labwc
Wayland compositor. The OS runs from RAM, with selectively persistent encrypted
SYSTEM settings and a separately unlocked Private store. Network applications
use a guarded WireGuard connection; Tor Browser and offline applications have
additional isolation.

The new [layout 2 storage target](docs/split-storage-20261024.md) separates the
encrypted OS payload from encrypted SYSTEM settings, with independent keys and
one shared SYSTEM boot passphrase. Existing physical media retains the earlier
combined layout until a separately authorized migration.

The CLI-first [Bloom installer](https://github.com/Samwarez/Bloom) supports GitHub
version/variant catalogs, fresh layout-2 installation, OS-only updates, wipe and
offline SYSTEM settings maintenance, with a soft-pink GTK overlay. Start with
`scripts/bloom --help`; commands review plans unless execution is
explicitly confirmed. The [portable Linux edition](docs/portable-installer.md)
bundles its runtime and uses a protected temporary administrator backend without
package installation; a root-owned Debian package remains available. Card
deployment requires a verified split-storage OS build and separately authorized
physical installation; no card was changed here. Build `20261026-145911-818721`
passed clean layout-2 VM verification and is prepared for publication.

Download Bloom from its [public releases](https://github.com/Samwarez/Bloom/releases).
Its [instructions](https://github.com/Samwarez/Bloom#readme) describe portable
launching and the protection tiers. PetalOS catalogs and OS payloads belong in
[PetalOS releases](https://github.com/Samwarez/PetalOS/releases), which Bloom
lists and downloads separately.

To build the current split-storage OS, verify it on newly allocated virtual
media and export a Bloom download bundle, run this as your normal desktop user
from a terminal that can authenticate sudo:

```sh
python3 -B scripts/prepare-split-release.py
```

If `tests/rebuild-release.py` has already completed a new build, pass its exact
directory with `--release ../releases/BUILD_TIMESTAMP` to verify/export it without
rebuilding. Old combined-layout builds are refused. The command preserves prior
images, changes no physical drive and does not publish automatically. See
[split-storage build and verification](docs/split-storage-20261024.md).

The checked release is `rc1-layout2-20261026-145911-818721`, base variant
(amd64, no bundled local AI agent). Publication includes its Bloom catalog,
kernel, production initramfs, rootfs, signed EFI chain and verification reports.
See [release publication](docs/release-publication.md) for the prepared command
and the limits of its clean-build acceptance.

OS changes are delivered through verified builds installed offline, never by a
live-system updater. Test media keeps at most one previous OS; production keeps
only the current OS. See [OS lifecycle and retention](docs/os-lifecycle.md).

This is a development baseline, not a security-certified release. The
[Phase 1.5 audit](docs/audit-phase15-20261018/REPORT.md) records outstanding
security, functional and recovery issues. The subsequent
[repair record](docs/phase15-repairs/README.md) distinguishes implemented and
tested fixes from remaining release gates.

## Repository layout

- `config/`: live-build settings, package lists, hooks, policies, desktop assets,
  runtime helpers and system documentation installed in the image.
- `local/parole-native/`, `local/conky-native/` and `local/keepass-native/`: maintained source patches and
  checksum-pinned build scripts for the native desktop integrations.
- `local/thunar-native/`: the maintained, version-pinned file-manager integration
  for Private-to-RAM Trash. [Build it](local/thunar-native/README.md) with the
  other native components before constructing a release.
- `local/security-backports/`: focused trixie dependency repairs and versioned
  Debian package builders, with installed-package regression evidence.
- `tests/`: build coordination, isolated regression fixtures, QEMU management,
  and guarded installation/update tools. Read each tool's scope before running
  it: some require a disposable guest and some can write explicitly selected media.
- `docs/`: architecture, workflows, historical acceptance records and the audit.
  Dated documents describe the state tested then; they are not current guarantees.
- `scripts/`: repository-maintenance checks.
- `auto/.gitkeep`: preserves the empty directory expected by the build coordinator.

**The custom aMule Kad candidate is abandoned and unsupported.** The supported
image uses Debian's aMule package with the separately maintained upstream
server-message length check. `local/amule-kad/` and its associated diagnostic
tests remain only as historical reference; do not build or install that candidate
as part of a supported PetalOS release. See its [status](local/amule-kad/README.md).

## Building from source

Use an amd64 Debian trixie build environment with live-build, squashfs-tools,
Python 3, patch and the normal compiler/development tools. Root privileges are
needed by live-build; invoke the coordinator as an ordinary user with sudo
available, not as root. For a clean clone, first regenerate the native artifacts:

1. Install the trixie build dependencies for Parole, Conky, KeePassXC and Thunar in a dedicated
   build environment. With matching trixie source-package indexes enabled,
   `apt-get build-dep parole conky keepassxc thunar` supplies the distro's development dependencies.
   Also provide `cmake`, `pkgconf`, `intltool`, `xfce4-dev-tools`, and the GStreamer
   GTK development components. See each native component's README and builder.
2. Obtain the exact public source archives linked in those READMEs, outside the
   checkout. Each script verifies its pinned SHA-256 before extracting it.

   ```sh
   python3 -B local/parole-native/build.py /path/to/parole_4.18.2.orig.tar.bz2
   python3 -B local/conky-native/build.py /path/to/conky_1.22.1.orig.tar.gz
   python3 -B local/keepass-native/build.py /path/to/keepassxc_2.7.10+dfsg1.orig.tar.xz /path/to/keepassxc_2.7.10+dfsg1-1.debian.tar.xz
   python3 -B local/thunar-native/build.py /path/to/public/thunar-source-archives
   python3 -B local/crystal-dock/build.py /path/to/v2.16.tar.gz
   python3 -B local/split-unlock/build.py
   ```

   These create ignored executable/checksum/provenance files under
   `config/includes.chroot/usr/local/share/portable/native-{parole,conky,keepassxc,thunar,crystal-dock}/`.
   Image hooks require exact base-package versions and verify those artifacts.
   A Debian package change needs a reviewed patch/build update; do not bypass
   the version checks. Generated native executables are not in Git.
   Crystal Dock additionally needs Qt 6 private headers and LayerShellQt;
   see [its builder instructions](local/crystal-dock/README.md).
3. Build and stage the four pinned Debian security backports, following
   [their instructions](local/security-backports/README.md). These need the
   exact trixie source archives and normal Debian build dependencies; generated
   packages are ignored. Installed newer Debian versions are never downgraded.
4. Run:

   ```sh
   python3 -B tests/rebuild-release.py
   ```

   The coordinator creates a new timestamped `../releases/` directory, preserving
   earlier builds. It reuses approved public package caches when available but
   creates a fresh build tree. No card or existing VM disk is updated by this
   command. See [the build workflow](docs/rebuild-and-live-tests.md).

The scripts currently assume a Linux desktop runtime directory and several
workstation-specific paths. For existing test/provisioning tools, inspect their
paths and identities before use; a fresh checkout does not include VM state,
credentials, VPN profiles, personal storage or backups. A second clean-machine
build and bit-for-bit reproducibility are not claimed by this import.

## Working safely

Read [AGENTS.md](AGENTS.md), the current source and the relevant documentation.
The local `PETALOS-HANDOFF.md`, when present, is an untracked conversation record
and may be stale. No general authorization to modify physical media follows
from having the installation scripts in this repository.

After explicit staging, inspect the actual Git index:

```sh
python3 -B scripts/check-staged-content.py
python3 -B scripts/check-staged-content.py --gitleaks /path/to/gitleaks
git diff --cached --stat
```

The second command additionally scans an isolated copy of staged blobs with
Gitleaks. Never commit credentials, real VPN profiles, password hashes, access
keys, encrypted data, LUKS headers or backups, even to this private repository.
[Version-control policy](docs/version-control.md) describes the import and
exclusions. The shipped Tor developer keyring contains public verification keys,
not development-access or decryption keys.

Third-party packages, patches and bundled assets retain their applicable
upstream licenses. This import does not assign a new blanket license.
