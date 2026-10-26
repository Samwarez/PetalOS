# OS builds, offline installation and retention

PetalOS starts each boot from the built, read-only OS image and runs its writable
root, home, caches and logs in RAM. It does not offer in-session OS/package
updates. Changes to the OS, bundled applications, dependencies and security
policies must be reviewed in source, included in a new build, verified, and
installed from outside the running PetalOS installation. Do not add a live
updater or persist packages installed into a running session.

The two persistent data areas are:

- **SYSTEM settings:** the selected configuration and credentials explicitly
  allowed by the system; the full SYSTEM mount stays read-only during normal
  operation and only the selected state areas have writable views.
- **Private:** separately encrypted user content, opened only by its own unlock
  action and closed by locking/suspend handling.

For existing layout 1 media, the encrypted SYSTEM partition also contains the
immutable bootable OS payload. The new layout 2 target gives OS its own encrypted
partition, with an independent key but the same SYSTEM passphrase. Its payload
is read-only during RAM boot; settings and Private remain separate persistent
partitions. Offline layout 2 updates leave both persistent partitions closed and
replace only OS contents and required BOOT selectors. No in-place repartitioning
of a legacy card is part of an update. See [split storage](split-storage-20261024.md).

The OS payload is not a writable application-data store. General root/home
persistence remains disabled. Read-only operation does not guarantee that a new
build or interrupted installation cannot fail; verification and recovery remain
necessary.

## Retention during offline installation

The generation helper `tests/release_generations.py` applies these modes:

| Mode | Payloads after successful installation | Boot menu |
| --- | --- | --- |
| `test` (default) | Current OS and at most one previous OS | One previous-release choice |
| `production` | Current OS only | No previous-release choice |
| `preserve` | Historical fixture behavior | For explicitly selected isolated audit fixtures only |

The host-side, identity-pinned test-card installer selects `test` explicitly.
Production mode is implemented/tested in the generation helper; this change
does not provide a new general-purpose production installer or run one.
The older cold-boot audit fixture explicitly preserves its input payloads;
it is not a supported live-update path for deployed systems.

Before staging a third OS, the installer verifies the active generation against
its manifest, removes references to the oldest rollback, and retires only known
unselected OS files. The active OS stays available until the complete replacement
has passed byte verification and the boot selectors are switched. A production
installation retires the prior active OS only after that switch. An interrupted
operation may leave extra payloads until retry completes; the retention limit is
the completed-installation state, not a reason to delete an active payload.

Cleanup is under the existing exclusive update lock. It validates generation
names, manifests, paths and file types before deleting; unknown content,
symlinks, stale selectors and corrupt active payloads stop retirement. Generated
rollback configurations are flattened so they do not accumulate older menus.
Legacy OS kernel/initrd/root-image files can be retired, while shared public
module inputs remain for subsequent builds/installation.

SYSTEM settings, administrator credentials, Private, EFI executables, encryption
headers/keys and external backups are outside this cleanup. The physical-card
installer still requires separate authorization, an idle identity-pinned device,
and verified raw BOOT/encrypted-SYSTEM backups before its first write. Low space
still stops installation if the new image and settings cannot fit even after
retiring old versions. No resize or data deletion is used to force a fit.
Keeping two large images on test media can still leave little space for growing
settings; bounded retention prevents accumulation, but does not enlarge SYSTEM.

## Verification on 2026-10-20

`python3 -B tests/check-release-generations.py` exercises ordinary disposable
directories, without opening block devices:

- Successive test releases, repeated installs and switching to production mode.
- Capacity limited to two OS payloads, requiring retirement before staging.
- Interrupted staging, selector activation, retirement and retry in both modes.
- Refusal for unknown files, symlinks, corrupt active content, empty/stale
  selectors and concurrent update attempts.
- Preservation of settings and shared-module/EFI canaries.

These are host filesystem fixtures, not a new QEMU boot or physical-card
acceptance result. No card was mounted or written for this implementation. Its
last measured SYSTEM free space remains 29 MiB until an authorized offline
installation applies retention. Existing backups and source snapshots remain.
Exact tested helper hashes and coverage are in [the test record](os-retention-tests.json).
