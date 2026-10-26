# Separate encrypted OS and SYSTEM settings — layout 2

Sam explicitly requested this layout on 2026-10-24 and authorized fresh
disposable VM validation. Existing physical media and prior VM images are
preserved. No physical migration, header retirement or card write occurred.

## Storage and authentication

| Partition | LUKS label | Open mapping | Filesystem | Credential and role |
| --- | --- | --- | --- | --- |
| 1 | — | — | BIOS boot region | Reserved for a supported BIOS boot installation. |
| 2 | — | — | FAT32 `PORT_BOOT` | Public firmware/kernel/initramfs/boot selectors. |
| 3 | `PORTABLE_OS` | `portable_os` | ext4 `LIVE_OS` | SYSTEM passphrase; independent OS encryption key. Read-only at boot, copied to RAM, then mapping closed. |
| 4 | `PORTABLE_SYSTEM` | `portable_system` | ext4 `LIVE_SYSTEM` | Same SYSTEM passphrase; independently generated settings encryption key. Selected persistent settings and root-only administrator credential. |
| 5 | `PORTABLE_DATA` | `portable_data` | ext4 `LIVE_DATA` | Separate Private passphrase and independent encryption key. Closed at boot and after screen unlock. |

Administrator authentication is separate from both SYSTEM and Private. Its
protected hash stays in `.petalos-auth` on the settings partition. Selected
preferences/profiles/wallpapers remain under `.petalos-state`; the full settings
mount remains read-only with a selected writable view. OS contains neither
directory and never contains an automatic Private unlock key.

LUKS format runs separately for each role, without copying headers or supplying
a reused volume key. A shared passphrase wraps different OS/settings keys; it
does not make their master keys identical. The VM compares actual transient
volume-key bytes internally and reports only a boolean result.

## Boot and screen unlock

Boot entries identify the layout and all three canonical public LUKS UUIDs:

```text
live-media=/dev/mapper/portable_os petalos.layout=2
petalos.os=OS_UUID petalos.system=SETTINGS_UUID petalos.private=PRIVATE_UUID
```

The shared installer contract validates distinct IDs and emits these arguments.
The initramfs rejects missing, duplicate, malformed or aliased identities. The
static native helper accepts different sibling block partitions and refuses
pre-existing mappings. One Plymouth/text prompt sends its bounded passphrase
over a pipe; the helper retains it briefly in locked, non-dumpable RAM and sends
it through anonymous pipes to two cryptsetup processes. It opens OS read-only,
opens settings independently and clears its buffer. Failure at the settings
step rolls back the OS mapping rather than leaving a half-open pair.

`private_storage` pins all three UUIDs/device identities on one physical parent.
After verified RAM boot and settings setup it closes the OS mapping. Screen
authentication verifies only the settings header; it never reopens OS or Private.
Private uses its separate existing controller and passphrase. The legacy
initramfs branch still supports earlier combined-layout boot entries.

## Updates and recovery

Layout-2 updates must run outside the installation being replaced. Unlock only
OS, verify/stage a complete generation, read it back, switch BOOT selectors, then
retire known prior OS payloads according to production/test retention. SYSTEM
settings and Private stay closed; neither their headers nor filesystems are
touched. The generation helper now recognizes both legacy and split boot flags.

The CLI recovery verifier tests one SYSTEM passphrase against both independent
headers without opening either mapping or Private. Offline settings maintenance
opens settings alone, defaults to read-only, and uses a constrained writable
view only for explicit imports. VPN validation and PNG imports preserve existing
files; pending theme/override packs are inactive.

OS/settings need separate header recovery copies. Restoring an old header can
restore retired password slots. A future passphrase-change operation must add
and verify the new passphrase on both headers before retiring either old slot;
the current verifier does not perform that transaction or silently repair a
mismatch. No physical header/key retirement is authorized by these source tools.

Legacy combined-layout cards require an explicit backed-up migration. The new
installer refuses to treat repartitioning or a layout-1 bundle as a layout-2
update. Existing card-specific legacy provisioning/updater scripts retain their
identity pins and were not invoked.

## Verification

Saved results: [63 focused VM checks](split-storage-vm-results-20261024.json),
[full live-OS boot](split-storage-fullboot-results-20261024.json). The latter
records five provisioning and 16 real live-OS checks, with one SYSTEM prompt.
Its first host parser missed journald-prefixed successful records; the corrected
parser recovered the unique success records from both bounded transcripts and
verified their prompt counts. This harness correction and scope are retained in
the report rather than represented as a clean first-run controller exit.
The final local import implementation additionally pins source/destination
directory descriptors against symlink/rename redirection; its no-overwrite,
traversal and import unit checks were rerun after the VM pass. That local file-I/O
hardening does not change the on-volume storage/boot protocol tested in the VM.

The focused fixture uses a completed kernel/initramfs, the current production
unlock helper/scripts and actual GPT partitions, LUKS2, dm-crypt and ext4 in a
fresh 512 MiB virtual disk. It has no NIC, host share, copied personal data or SSH
access. Test-only credentials are random and remain outside source/reports.

Two networkless boots verify:

- Three independent encryption keys; wrong SYSTEM opens neither mapping.
- A mismatched settings passphrase rolls the partially opened OS mapping back.
- Exactly one real text prompt per successful boot and read-only OS mapping.
- Production settings mount/identity and account-authentication modules.
- OS mapping closure, separate administrator authentication and Private's own
  passphrase; screen authentication does not reopen Private.
- Read-only offline settings browsing, paired recovery and explicit validated
  VPN/wallpaper imports, with all tool-created mappings closed afterwards.
- An actual OS generation update whose encrypted settings and Private
  partitions compare byte-for-byte before/after while remaining closed.
- A second boot retaining the updated generation, saved settings, administrator
  authentication, Private content and imported VPN/wallpaper.

The fixture substitutes only full-live-environment RAM preconditions and
unrelated wallpaper/Trash desktop behaviors, documented in its source. Virtual
disk discovery substitutes the removable/USB classification only; real
mount/holder/partition checks still apply. It uses small synthetic OS payloads
and deliberately fast **test-only PBKDF2**, so this is not production KDF,
complete-desktop or Secure Boot acceptance.

Native tests exercise invalid/overlong inputs, two-volume rollback and graceful
termination during activation. Installer tests exercise catalog/download
corruption and traversal, redirect authentication stripping, capacity and legacy
migration refusal, store import boundaries, real LUKS key removal and the
external-header recovery limit. Generation fault tests run for both layouts,
including interruption/retry, low capacity, selectors, retirement and locking.

Commands:

```sh
python3 -B local/split-unlock/build.py
python3 -B local/split-unlock/test.py
python3 -B tests/check-split-build-hooks.py
python3 -B -m unittest discover -s local/installer/tests -v
python3 -B tests/check-boot-unlock.py
python3 -B tests/private-storage-controller.py
python3 -B tests/check-release-generations.py
python3 -B tests/check-release-generations.py --layout2
python3 -B tests/run-split-storage-vm.py /home/sam/portable-live/releases/COMPLETED_RELEASE
python3 -B tests/run-split-fullboot-vm.py /home/sam/portable-live/releases/COMPLETED_RELEASE
```

For the clean replacement build, use the normal desktop user's terminal:

```sh
python3 -B scripts/prepare-split-release.py
```

This runs the existing clean live-build coordinator, which asks for sudo in
that terminal, then runs focused storage/update checks and a full live RAM boot
on newly allocated networkless virtual disks. It exports a verified Bloom bundle
under `../release-dist/rc1-layout2-BUILD_TIMESTAMP/base`, with checksums and
separate verification reports. It preserves existing builds and physical media.
Publication and hardware installation remain separate actions.

If the clean rebuild is already complete:

```sh
python3 -B scripts/prepare-split-release.py --release ../releases/BUILD_TIMESTAMP
```

The full-boot runner's `--clean-release` mode requires matching current build
inputs, manifest-verified kernel/initrd/rootfs/ISO, exact storage modules in the
rootfs, and the reviewed startup scripts/helper already present in the built
initramfs. It supplies no replacement production storage code or rootfs delta.
Only the isolated verification service and disposable credentials are appended
to its test initramfs. That test initramfs and VM images never enter the exported
bundle. The older delta mode remains available to test source changes against
the prior release; it does not establish clean-build acceptance.

The full-boot fixture uses the actual completed live OS plus a reviewed,
hash-checked read-only delta containing the changed source. A separate newly
allocated virtual disk holds the full rootfs in encrypted OS, separate settings
and Private. It boots through the actual live RAM-copy/account setup path,
without replacing their environmental checks. It uses direct kernel boot,
not firmware or Secure Boot; no graphical desktop acceptance is inferred. Its
test initrd includes disposable credentials and **must never be installed as a
production release**. It is not a clean live-build rebuild.

## Remaining release gates

- Clean build `20261026-145911-818721` now passes focused storage and full live
  RAM-boot verification without a production runtime overlay. Its exported Bloom
  bundle and reports are verified; publication is prepared separately. See
  [clean-build results](split-storage-clean-release-20261026/verification.json).
  Independent publisher signatures/key distribution remain future trust work.
- The installer executor, GUI privileged pipe protocol and Debian package are
  implemented; see [installer acceptance](installer-app.md). Desktop GUI/polkit
  interaction and hardware-specific capacity/performance acceptance remain.
- Verify the final rebuilt signed firmware boot chain and graphical Plymouth
  path; keep the previously recorded signed-GRUB artwork issue separate.
- Design and separately authorize the old-card migration and recovery copies.
  Preserve the current card until then.

Source snapshots were checksum/readability verified before installer and storage
edits. No host package, privilege policy, firmware or physical media changed.
