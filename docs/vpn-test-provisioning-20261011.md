# Dedicated VPN test provisioning — 2026-10-11

Sam explicitly selected `/home/sam/Desktop/zrh43-adb.conf` for the VM test.
Initial validation rejected the private-key format; no transfer was performed.
Source permissions were restricted from 664 to 600. After Sam corrected the
file and requested recheck, both key formats, full IPv4/IPv6 routes and the
currently approved fixed Zurich endpoint passed. WireGuard's own pubkey parser
accepted the private-key format, with its output discarded. No configuration,
private key or derived key was displayed or included in diagnostics.

The VM was shut down by Sam. `tests/prepare-vpn-test.py` preserved the working
encrypted disk and created a new sparse clone:

`testing/sessions/20261011-184902-563580/encrypted-boot-20261011-195331-754602.img`

`tests/provision-vpn-root.py` ran through sudo in a separate terminal using
private password prompts. It validated clone/loop/partition/mapper identities,
opened only encrypted DATA, verified its filesystem label and live-user owner,
and atomically installed the selected config at `Private/Network/wg0.conf`
with mode 600. Installed bytes were compared in memory without printing a
hash or contents. The system volume and data-unlock key were not accessed.
The source was not copied into build inputs, squashfs, initramfs or logs.
The prior encrypted disk preserves any previous profile and test data.

Syntax/config checks and an isolated non-file-device rejection check passed.
Root transfer returned successfully, all updater mounts/mappings were closed,
and runtime transfer phase became `complete`. Full failure/interruption coverage
is not claimed. No permanent sudo grant or physical-card operation occurred.

Launched the new clone as Sam with `tests/launch-encrypted-qemu.py`.
QMP confirmed the selected clone is attached, no ISO is attached and the
provisioning mapper is absent. Actual-provider connection, DNS, NTP, exit-IP
and Tor are now ready for guest testing but are not yet reported verified.

Sam subsequently reported “VPN verified and clock synchronized” from the
guest helper. The production connect path performs bounded IPv4 HTTPS
verification through wg0 before starting chrony and reports synchronized
only after chronyc waitsync succeeds. This confirms a functional dedicated
provider connection and clock synchronization by user observation; successful
HTTPS hostname resolution and NTP work within the configured tunnel/firewall
path. Explicit exit-IP comparison, Tor operation, actual-provider reconnect
and IPv6 internet access remain unverified. No comprehensive leak audit is
claimed.
