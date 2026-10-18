# Proposed build and QEMU helper (not installed)

The current tool session has NoNewPrivs=1. Both `sudo -n -l` and
`sudo -n true` fail before authorization; sudo also reports /etc/sudo.conf
owned by uid 65534. These observations do not establish Sam's ordinary
host sudo policy. A sudoers change cannot overcome NoNewPrivs. No sudoers
or host permissions were changed.

Prefer a disposable build VM: run live-build as root inside that VM and
QEMU as Sam on the host. User-controlled live-build hooks execute code as
root, so granting host `sudo lb build` or a wrapper around a writable build
tree is effectively general host-root authorization.

If host image maintenance is still needed, propose a root-owned helper
with an exact operation enum, no shell command argument:

- `inspect-test`: report only image identity, loop backing path, mapper
  identities and mount/busy state; never keys, profiles or personal data.
- `stage-test-release RELEASE_ID`: accept a verified release manifest
  containing exactly kernel, initrd and squashfs. Enforce regular files,
  no symlinks/path traversal, size/hash checks and immutable root-owned
  staging before privileged use. Reject secret-like files at ingestion.
- `update-test RELEASE_ID`: operate only on one root-owned registered test
  image beneath /var/lib/petalos-tests, never an arbitrary path or device.
  Acquire a root-owned lock shared with the rootless launch coordinator.
  Refuse a running guest, existing loop attachment, mapper or mount.
  Verify regular-file inode/device identity, loop backing file, partition
  parentage and cryptsetup mapping before each operation. Mount only test
  boot/system partitions; do not open the data partition or copy data keys.
  Ensure cleanup on failures. No repartition/format operation.

QEMU launch and diskless regression tests require no privileged helper.
The launch coordinator must reserve the same test-image lease before
opening the image; root helper must never invoke QEMU as root. Image copies
for QEMU must be owned by Sam and kept outside build inputs.

The helper must reject all block-device input, physical disk discovery by
label alone, physical-card writes, arbitrary mount/cryptsetup/losetup args,
arbitrary executable paths and environment overrides. It should use fixed
absolute executables and a sanitized environment, bounded RAM logs, and
root-owned configuration/state. Test credentials must enter privately,
never through command-line arguments or logs.

Before installation, implement and review the helper, including symlink,
TOCTOU, running-guest, wrong-loop, wrong-mapper and interruption tests.
Only then consider a sudoers entry for that single root-owned executable.
No broad sudo grants for lb, bash, mount, cryptsetup, losetup or QEMU.
This document proposes a design; it grants no privileges and implements
no host storage operation.
