# PetalOS

## Install PetalOS with Bloom

[Bloom](https://github.com/Samwarez/Bloom) is the portable graphical installer for PetalOS. Download it from [Bloom releases](https://github.com/Samwarez/Bloom/releases), extract the complete Linux amd64 folder, and run `./bloom` as your normal desktop user. Drive operations ask for administrator authorization.

In Bloom, select `Samwarez/PetalOS`, choose a published version and build, download it, then review the exact target drive before installation. [PetalOS releases](https://github.com/Samwarez/PetalOS/releases) supply the catalog and verified OS payloads that Bloom lists and downloads. An ISO alone is not a Bloom download bundle. See the [Bloom instructions](https://github.com/Samwarez/Bloom#readme) for protection tiers, requirements and usage.

PetalOS is a Debian trixie live system with an XFCE desktop on the labwc
Wayland compositor. The OS runs from RAM, with selectively persistent encrypted
SYSTEM settings and a separately unlocked Private store. Network applications
use a guarded WireGuard connection; Tor Browser and offline applications have
additional isolation.

This is a development baseline, not a security-certified release. The
[Phase 1.5 audit](docs/audit-phase15-20261018/REPORT.md) records outstanding
security, functional and recovery issues. Those findings have not been repaired
by the version-control import.

## Repository layout

- `config/`: live-build settings, package lists, hooks, policies, desktop assets,
  runtime helpers and system documentation installed in the image.
- `local/parole-native/` and `local/conky-native/`: maintained source patches and
  checksum-pinned build scripts for the native desktop integrations.
- `tests/`: build coordination, isolated regression fixtures, QEMU management,
  and guarded installation/update tools. Read each tool's scope before running
  it: some require a disposable guest and some can write explicitly selected media.
- `docs/`: architecture, workflows, historical acceptance records and the audit.
  Dated documents describe the state tested then; they are not current guarantees.
- `scripts/`: repository-maintenance checks.
- `auto/.gitkeep`: preserves the empty directory expected by the build coordinator.

**The custom aMule Kad candidate is abandoned and unsupported.** The supported
image uses Debian's aMule package. `local/amule-kad/` and its associated diagnostic
tests remain only as historical reference; do not build or install that candidate
as part of a supported PetalOS release. See its [status](local/amule-kad/README.md).

## Building from source

Use an amd64 Debian trixie build environment with live-build, squashfs-tools,
Python 3, patch and the normal compiler/development tools. Root privileges are
needed by live-build; invoke the coordinator as an ordinary user with sudo
available, not as root. For a clean clone, first regenerate both native artifacts:

1. Install the trixie build dependencies for Parole and Conky in a dedicated
   build environment. With matching trixie source-package indexes enabled,
   `apt-get build-dep parole conky` supplies the distro's development dependencies.
   Also provide `cmake`, `pkgconf`, `intltool`, `xfce4-dev-tools`, and the GStreamer
   GTK development components. See each native component's README and builder.
2. Obtain the exact public source archives linked in those READMEs, outside the
   checkout. Each script verifies its pinned SHA-256 before extracting it.

   ```sh
   python3 -B local/parole-native/build.py /path/to/parole_4.18.2.orig.tar.bz2
   python3 -B local/conky-native/build.py /path/to/conky_1.22.1.orig.tar.gz
   ```

   These create ignored executable/checksum/provenance files under
   `config/includes.chroot/usr/local/share/portable/native-{parole,conky}/`.
   Image hooks require exact base-package versions and verify those artifacts.
   A Debian package change needs a reviewed patch/build update; do not bypass
   the version checks. Generated native executables are not in Git.
3. Run:

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
