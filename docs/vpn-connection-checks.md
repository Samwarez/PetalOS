# Automatic VPN connection checks

Connect and Switch now run the following checks automatically, with the VPN
action lock held until testing and report publication finish:

| Check | What is checked | Failure behavior |
| --- | --- | --- |
| Tunnel | Existing live guard checks all three firewall drop policies, fwmark, configured peer identity, IPv4 default route, live wg0 HTTPS reachability and a completed handshake. The public IPv4 route must also select wg0. | Reject connection and run existing rollback. |
| Public IPv4 | Bounded TLS-verified HTTPS to api.ipify.org, explicitly bound to wg0, ignoring proxy environment and curl configuration. Response must be a global IPv4 address. | Reject connection and roll back. |
| Public IPv6 | Equivalent HTTPS to api6.ipify.org, with IPv6 routing through wg0. | Warning; working IPv4 stays available. |
| VPN DNS | Resolver file matches the selected profile's protected runtime resolver file, each configured DNS server routes through wg0, and a bounded hostname lookup succeeds. | Reject connection and roll back. |
| Clock | Chrony's synchronization threshold after the existing tunnel-only sync attempt. | Warning; existing Tor readiness guard still rejects an unsynchronized clock. |

The IPv4, IPv6 and DNS probes run concurrently. There is no non-VPN public-IP
lookup, geographical expectation, external-DNS exception, insecure TLS option,
firewall relaxation or automatic Tor launch. These connectivity checks do not
prove anonymity or constitute an exhaustive DNS-leak test. The observed public
addresses need not equal the WireGuard endpoint address.

The VPN manager displays each result and public address. Reopening it shows the
last test for the current interface lifetime. Conky also displays these results,
explicitly dated as tests at connection time rather than continuous assurance.
The existing manual IP-check shortcuts remain available.

Reports are small, root-owned, desktop-readable JSON at
`/run/portable-vpn-checks.json`, verified to be on tmpfs. They contain only result
states, observed public addresses, timestamp and wg0 interface index. Disconnect,
switch teardown, failed-connect rollback and a new connect attempt clear the old
report. Readers reject unsafe files or a different/missing interface. These
reports never authorize applications: application launch guards continue to
perform fresh checks against actual networking and clock state.

No new sudo permissions were added. The internal root probe helper is invoked by
the existing authenticated VPN action. No credentials, profile contents, peer
keys or raw backend error output enter the report. Tests contact the two fixed
public-IP services through the VPN, as the manual IP-check shortcuts already do.

## October 15 acceptance

- Synthetic probe tests passed: required-check failures, optional IPv6/clock
  warnings, invalid/private address rejection, resolver mismatch, RAM-only report
  publication, and unsafe/stale-interface report rejection.
- Mocked backend flow passed: tests execute after the clock attempt; required
  failure rolls back and clears prior success; invalid profile cannot retain an
  old report; disconnect is repeatable and removes results.
- Existing profile parser/storage, manual exit-IP and credential-prompt tests
  passed. Source syntax and build-input validation passed.
- Installed five public scripts/modules atomically in the running QEMU RAM OS
  under the existing VPN lock, preserving original public scripts in a root-only
  RAM backup. No tunnel was disconnected for installation.
- The VM had no active tunnel, so the saved profile was connected through the
  actual updated backend. Connection exited successfully and automatically
  produced passing tunnel, IPv4, IPv6, DNS and clock results.
- The desktop user can read but cannot write the report. Desktop status contains
  the automatic results and both public addresses. The refreshed VPN manager
  starts successfully, and all three firewall drop policies remain intact.

Changes are in source and the live QEMU RAM OS. No full release rebuild or
physical-card write was performed. Real IPv6 failure/rollback behavior was
covered with synthetic fixtures rather than disrupting the user's live tunnel.
