# Encrypted QEMU update workflow

The tested ISO session's qcow2 overlay and original backing disk are preserved.
`tests/prepare-encrypted-qemu.py` holds the launcher lease, checks source
busy/loop state and backing identity, and converts their combined state into
a new sparse 16 GiB raw clone outside build inputs. Firmware variables are
copied for that clone. The overlay includes Sam's verified doodle/settings
changes; no personal file or archive is opened by the host coordinator.

The coordinator invokes `tests/update-encrypted-clone.py` through sudo in a
separate terminal. This is one explicitly authorized root operation, not an
installed helper or sudoers grant. Sudo and the test system-volume password
are entered privately at terminal prompts; no passwords or unlock keys are
passed as arguments, logged or copied into build inputs.

The updater rejects non-regular files, symlinks, wrong path/name/size/owner,
running QEMU, existing attachments/mappers and unknown busy state. It checks
release hashes, loop backing identity, GPT layout, partition parentage,
boot/system labels and the decrypted system mapper's exact backing partition.
It mounts only boot and system in a root-owned RAM workspace. The data
partition remains unopened. The existing encrypted-system data-unlock key
is untouched and remains within that encrypted filesystem.

GRUB paths and encrypted live-media/toram/swap=false arguments are validated.
Only kernel, initrd and squashfs are replaced, with temporary-file hash checks
and atomic rename. Bootloader files, partitioning, LUKS headers, passwords and
key slots are unchanged. Cleanup validates mount/mapper/loop identities before
unmount, close and detach; no forced cleanup occurs. Workspace cleanup uses
only empty-directory removal and preserves any remaining mount for inspection.

Syntax checks passed. Two isolated guard tests confirmed non-file device input
is rejected before storage commands and a mounted workspace is retained rather
than recursively deleted. Full helper failure/interruption coverage is not
claimed. Successful update and detachment must be observed before boot.

Runtime status is `/run/user/1000/petalos-encrypted-test.json`. The current
candidate is `encrypted-boot-20261011-191408-961940.img` within the original
test session directory. At preparation it reached the system-unlock prompt.
The prepared candidate subsequently completed its update successfully.

## Completed update and boot launch

The coordinator reached `ready-for-encrypted-boot` after the root updater
returned successfully. Release hash checks, GPT/label/mapper checks, GRUB
arguments/path validation, copied-file hash checks and cleanup all passed.
The original base disk and tested overlay remain preserved. The data
partition was never opened by the host updater.

Launched `tests/launch-encrypted-qemu.py` as Sam. QMP confirmed the running
VM has only OVMF code, copied firmware variables and the updated raw clone
attached; there is no ISO. QEMU's UID is 1000. The updater mapper is absent
and the clone has no host loop attachment. Guest system unlock, automatic
Private unlock, settings restore and RAM/swap operation still require
confirmation from the running guest; this boot launch alone does not prove
those outcomes or Secure Boot.

Sam then confirmed in the running QEMU window that the test system password
unlocked the system, the desktop appeared, Private unlocked automatically,
and the saved panel changes restored. These are user-observed functional
results from the updated clone booted without an ISO. RAM/home and swap
runtime checks remain pending. Physical Secure Boot remains untested.

Sam confirmed that `findmnt -n -o FSTYPE -T /run/live/overlay` prints
`tmpfs`, verifying that the writable root layer resides on a RAM filesystem.
The live-medium and home filesystem results and active swap check are still
pending; this single result does not establish all RAM/no-swap conditions.

Sam subsequently confirmed the remaining runtime results:

- `/run/live/medium` filesystem type is `tmpfs`.
- The home filesystem type is `overlay`.
- `/usr/sbin/swapon --show` produces no output (no active swap).

Together with the writable-layer `tmpfs` result, these confirm RAM-backed
live media and writable root/home operation with no active swap in this guest.
The encrypted-boot stage is complete: updated system unlock, automatic Private
unlock, selective settings restore and RAM/no-swap checks all passed through
user observation. Actual-provider VPN/NTP/Tor and physical Secure Boot tests
remain outstanding. The physical card is unchanged.

After successful cleanup, `tests/launch-encrypted-qemu.py` checks current
busy/loop/mapper state and starts QEMU as Sam with the new clone and copied
firmware variables, without attaching an ISO. The physical microSD is never
selected by this workflow.
