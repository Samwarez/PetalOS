# PetalOS working instructions

Read PETALOS-HANDOFF.md before changing this project. Inspect actual files: the handoff records conversation history and may lag implementation.

- Repository note (2026-10-18): PETALOS-HANDOFF.md remains local and untracked. In a fresh checkout where it is absent, read README.md, docs/version-control.md and the latest audit report instead. Sam explicitly authorized the initial source import into the PRIVATE GitHub repository Samwarez/PetalOS; this narrow authorization supersedes the no-publish instruction below for that private source upload only. It does not authorize public publication, uploading backups or credentials, or writing physical media.

- Work on the Debian live-build configuration and QEMU test environment. Do not write to, repartition, format, or update the physical microSD without a separate explicit instruction. Device names change; never rely on /dev/sdc alone.
- Verify the existing backups before making changes. Preserve an initial code snapshot. Never overwrite existing project instructions; merge these instructions if AGENTS.md already exists.
- Never display, commit, copy into build inputs, or include in diagnostics: WireGuard private keys, passwords, password databases, personal files, or the data-volume unlock key. The unlock key belongs only inside the encrypted system volume, outside filesystem.squashfs.
  Superseded historical exception authorized by Sam on 2026-10-12: the public default Petal login password may be documented and its hash included in OS build inputs. This exception does not apply to personal credentials, VPN secrets, or encryption/unlock keys. Default account creation and authentication must not depend on Private storage.
- Maintain the VPN kill switch throughout failure, disconnect, reconnect, and profile switching. Do not weaken the firewall to make a test pass. Keep external DNS and time synchronization inside the approved tunnel.
- Determine status from current system state and bounded active tests. Cached status files are presentation history, not authorization to start network applications.
- Preserve RAM-only browser sessions, ephemeral Wi-Fi/Bluetooth profiles, and selective encrypted persistence. Do not enable general root/home persistence or write the host hardware clock.
- Keep normal desktop actions free of terminal windows, but provide a working graphical password/error path before removing Terminal=true. Keep diagnostic logs bounded, in RAM, and free of secrets.
- Use the Debian trixie package set. Do not silently pull unstable packages. Local applications should retain their offline wrappers and disabled automatic update checks.
- Prefer automated QEMU verification. Never modify a mounted/running guest image; verify loop backing files and mapper identities before storage operations. Run QEMU as the normal user.
- Sam uses zsh and has no clipboard in the physical live session. Prefer scripts or short commands for live tests; administrative commands may require /usr/sbin paths.
- Implement changes in reviewable stages, test meaningful failure cases, and report exactly what was verified. Do not claim anonymity, absence of forensic traces, or Tails-equivalent security from a successful functional test.
- Do not publish this project, upload personal backups, or send messages to third parties.

- Current account policy: Petal password authentication is disabled. SYSTEM, administrator and Private passphrases have separate purposes. Only the Private passphrase may unlock Private; manual and idle locking must close its encryption mapping. Download mode may inhibit idle locking, never manual locking. Do not permanently erase encryption headers or retire physical-card key slots without separate explicit instructions.

- Screen unlock uses the SYSTEM passphrase and must leave Private closed. The existing separate Private unlock action alone accepts its own passphrase. Do not conflate desktop unlock with reopening Private. The legacy SYSTEM-held automatic DATA key must be treated as an outstanding independence gap until separately retired.

- Selective persistent VPN profiles and desktop settings now belong in the encrypted SYSTEM state area, not Private. Keep the full SYSTEM mount view read-only and expose only the selected writable areas; root/home/logs/caches remain in RAM. Freed-memory zeroing is a mitigation, never a guarantee of forensic erasure. No automatic DATA-key retirement or physical migration has been authorized.

- Sam authorized a fresh Private encryption-volume migration on a disposable QEMU clone after the read-only audit found shared SYSTEM/Private passphrases. Preserve the working image and existing backups, require a distinct new Private passphrase, and verify the encrypted mapping-to-mapping copy. This authorizes neither physical-card changes nor destruction/retirement of original images, headers, keys or backups.

- Development/test storage installs may skip unused-sector overwriting and verify allocated image extents when Sam authorizes this shortcut. Retain device-identity checks, backups, VPN protections and encryption boundaries. Label these results development-only; do not claim a full wipe or production acceptance. Limit buffered card writes with periodic flushes so interruption does not leave tens of GiB queued.

- Sam authorized a fresh, disposable phase 1.5 audit VM on 2026-10-17 with three distinct agent-accessible test-only credentials. Keep them in a mode-0600 file outside OS build inputs and reports; use them for unattended authentication only in that isolated VM. This does not authorize collecting personal passwords or weakening production authentication. Create fresh SYSTEM/Private encryption keys and SSH identities, copy no personal data, and use only the separately supplied audit VPN profile. Existing VM disks and physical media remain outside this authorization.
