# Verification — 2026-10-11

Read the handoff and both AGENTS.md files. The instruction files are identical.
Both existing backup SHA256 checks passed. The project tar archive was fully
listed successfully with contents suppressed. The encrypted personal backup
was not decrypted; plaintext readability and restore remain unverified here.
Code snapshot preserved and read back under snapshots/, with SHA256 record.
Inputs were scanned for private-key declarations and secret-file names.

Guard captures complete nft/route output, checks three drop policies,
interface, mark and IPv4 route, and requires a bounded HTTPS request bound
to wg0 with proxies disabled. This uses the existing exit-check service.
It does not validate full rule integrity, expected exit or IPv6 connectivity.
Connect/disconnect share a lock. Failed connect stops chrony and tears down
wg0, removing runtime config when the interface is absent. Failed teardown
retains config for a Disconnect retry. Chrony starts after active verification.
Firewall configuration was not changed.

Shell syntax and Python compilation passed. Diskless QEMU TCG testing passed
18 assertions using the actual production scripts and mocked network commands:
large nft output, missing firewall/drop policy/route/mark/interface,
failed reachability, failed setup cleanup, blocked-transport rollback,
retry/repeat connect, disconnect/repeat disconnect, failed teardown and retry.
The guest used the existing Debian kernel, a temporary initramfs, no attached
disk and no NIC. QEMU ran as the normal user.

These tests verify script control flow, not real WireGuard/nftables networking.
No rebuilt image, encrypted test-image update, live tunnel/leak test, IPv6
or Secure Boot test was performed. Full live-guest testing remains pending:
before-network connect, real successful connect, transport blocking,
missing route/firewall, reconnect and disconnect while checking leak denial.
The environment has NoNewPrivs=1 and no /dev/kvm. Sudo fails before policy
authorization and also reports /etc/sudo.conf ownership uid 65534.
No sudoers changes or physical-card operations were performed.
