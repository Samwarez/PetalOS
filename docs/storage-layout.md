# Current storage layout

This document describes the selected settings/content locations shared by both
layouts. The new [layout 2 target](split-storage-20261024.md) puts OS and SYSTEM
settings in separate encrypted partitions, with independent keys and one shared
SYSTEM boot passphrase. Private and administrator authentication remain separate.
The existing physical card retains its prior combined layout pending a separately
authorized migration; the dated cleanup observations below are historical.

| Friendly location | Path | Purpose |
| --- | --- | --- |
| Private Files | `/mnt/private` | Documents, downloads and application state that can reveal activity. Requires its own passphrase. |
| System Settings | `/mnt/system-state` | Selected settings available independently of Private. |
| Temporary Files (RAM) | `/home/Petal` | Ordinary desktop home and temporary content, discarded at shutdown. |

Private's `Documents` and `Downloads` contain per-application folders. The desktop
user can browse the category parents. Sandboxed apps receive only their assigned
folders or explicitly selected files. `AppState` is still active: download queues,
resume information and other content-related state must stay in Private, or RAM
when Private is closed. It must not be merged into the System settings whitelist.

System settings use `Desktop` for validated desktop preferences, `Network` for
VPN profiles/selection, `Applications/TorBrowser` for signature-verified browser
distribution archives, and root-managed `AppPreferences` for filtered app
preferences and aMule's server list. These are not general home-directory backups.
Browser sessions remain in RAM. Some System folders deliberately require mediated
access rather than direct desktop writes.

The `Private` and `SystemSettings` links in the RAM home are convenience aliases
for the same stores, not additional copies. The three file-manager bookmarks are
also aliases. Boot partitions and raw encrypted devices stay hidden from ordinary
volume navigation. A filesystem's `lost+found` directory is a recovery structure,
not a leftover app folder.

## Development-clone cleanup audit, October 15

The audit covered known OS-managed storage paths, source inputs and installed
helper launcher targets. Personal content was not inspected. It was not an
exhaustive classification of every file on the machine.

- Removed the empty, obsolete Private `PortableSettings` directory with `rmdir`.
  Current settings save/restore uses SYSTEM `Desktop/desktop-settings.tar`.
  The legacy archive was absent. A nonempty directory would have been preserved.
- Removed six generated Python bytecode files from source `config` inputs after
  preserving a checksum-recorded snapshot. The release coordinator already
  excludes `__pycache__` and `*.pyc` during staging.
- Private `Network` is an inactive migration remnant. Five of its six profile
  files have byte-identical System counterparts; one differs or is missing there.
  The comparison emitted only aggregate counts, never credentials or digests.
  The entire old folder was preserved to avoid losing a profile.
- Private `Applications/TorBrowser` is an inactive remnant. All four old archive
  and signature payload files have byte-identical System copies, despite different
  version-directory paths. The nonempty legacy tree was preserved as a rollback
  copy. Normal Tor startup uses only the System location.
- No remnants matching the checked public permission/dual-storage fixture names
  were found in Private Documents/Downloads at the category or app-folder level.
- All 14 installed `portable-*.desktop` helper entries checked had an existing
  executable target. No `.bak`, `.orig`, `.rej` or editor `~` leftovers were found
  in the source image-inclusion tree.

Explicit legacy-import code and sandbox deny rules for old locations remain
intentional compatibility/protection paths; they do not restore old settings at
boot or make applications depend on Private for VPN/Tor startup. Development
snapshots, prior releases, encrypted disk clones and their backups were preserved.
No full image build or physical-card write was performed for this cleanup.


The selected System Tor archive also passed detached-signature verification during
this audit. Stale VPN-manager storage wording, the Private shortcut description,
and the installed welcome-guide source were corrected for the next build. The
welcome guide now describes disabled account-password login and the separate
SYSTEM/administrator/Private credentials. These text changes are source-only;
the running VM retains its previous installed wording until updated or rebuilt.
The old functionality-status document is explicitly marked as historical and
links to this layout instead of presenting its old storage claims as current.
