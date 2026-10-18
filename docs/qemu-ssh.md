# QEMU SSH management

This is a test-clone feature, not a production/card feature. The existing
virtio NIC and QEMU user networking stay unchanged. The host-only listener
`127.0.0.1:2222` relays through virtio-vsock CID 42, port 22, to the guest's
loopback OpenSSH server. No nftables exception, DNS exception or WireGuard
route is added. Sam explicitly approved this alternative because ordinary
QEMU TCP forwarding would be rejected by the guest input drop policy.

`tests/prepare-ssh-test.py` preserves the current encrypted disk and firmware,
creates a fresh sparse clone, and calls the existing identity-checked updater
to add a small live-system module. Only test BOOT and SYSTEM are opened; DATA
is not opened. The original release squashfs is not replaced or repacked.
The added boot argument enables the test module. OpenSSH and its missing
dependencies are installed offline in the RAM root at boot from Debian trixie
packages. The default IP-facing SSH units and SSH generator are masked.

The dedicated host client private key is mode 600 under
`~/.local/share/petalos-qemu/ssh`, outside the project and build inputs. Only
its public key is in the test module. Authentication is public-key-only for
the live user `user`; root login, passwords, forwarding and PTYs are disabled.
Administrative commands use the guest's existing sudo policy. The server
private key is generated directly inside encrypted test SYSTEM, outside all
squashfs files, and copied into RAM at boot. Its public key is pinned on the
host during provisioning, before the first connection. No private key is
printed or added to build inputs. A per-user ACL grants Sam access to the
host `/dev/vhost-vsock` device; this ACL may need restoring after host reboot.

The launcher owns both QEMU and the loopback relay and stops the relay when
QEMU exits. It refuses SSH launches without vsock access or with port 2222
already occupied. QEMU runs as Sam. A single VM lease prevents concurrent
project VMs; CID 42 must not be assigned to another separately managed VM.

Run bounded commands from the project with:

```sh
python3 tests/guest-ssh.py --json 'id -un'
```

JSON includes stdout, stderr and the remote exit code. The script itself
returns the remote exit code; transport/time-limit failures return 255.
Do not request complete WireGuard configurations, password files, personal
files or the DATA unlock key. Diagnostics remain in RAM unless deliberately
saved as non-secret project findings.

Provisioning/desktop acceptance is in progress. The first SSH module caused
a black desktop because the coordinator's host-side umask also made public
overlay system directories mode 700. This is corrected to mode 755; host
artifacts and keys retain restrictive permissions. Diskless boot tests also
identified a missing libcbor dependency for the SSH client package; this is
now included from trixie. Failed SSH disk/firmware candidates are preserved,
and retries clone the original working disk. The launcher explicitly places
vsock at PCI slot 5, preserving NIC slot 1, VGA slot 2 and disk slot 3, and
sets disk boot priority explicitly after the initial firmware PXE fallback.

The corrected offline diskless boot test passed: real OpenSSH authentication
over vsock executed a command and captured `stdout-ok`, `stderr-ok`, and remote
exit code 7. D-Bus and both SSH management services started. This test uses
an ephemeral RAM server key and has no external NIC or guest data disk;
it does not verify reading the persistent server key from encrypted SYSTEM.
On 2026-10-12 the corrected encrypted clone
`encrypted-boot-20261012-155731-485707.img` booted to the desktop (reported by
Sam). Direct SSH checks confirmed LightDM, D-Bus, OpenSSH and the vsock relay
active; captured separate stdout/stderr with remote exit code 7; rejected an
unregistered key and root login; and confirmed password/keyboard-interactive
authentication and forwarding disabled. The server host key loaded from
encrypted SYSTEM matched the host pin established before boot. The guest
SSH listener is `127.0.0.1:22`, the host relay is `127.0.0.1:2222`, and default
SSH service/socket remain masked. SSH worked with no wg0 interface present.
The guest nftables configuration SHA256 matched production source, and the
active input/output/forward chains retained drop policies and the original
rules with empty endpoint sets; no SSH exception was added. The production
release and original working test image remain preserved. This acceptance
did not repeat the entire real-provider reconnect/switching suite.
