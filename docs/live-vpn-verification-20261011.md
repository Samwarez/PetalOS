# Live-guest VPN verification — 2026-10-11

Ran `tests/run-vpn-live.py /home/sam/portable-live/build --scripts-from-source`
as Sam. Final run passed all 26 assertions, ending with
`LIVE_TEST_FAILURES=0`; QEMU exited successfully.

This booted the existing Debian live ISO read-only with current production
VPN scripts overlaid in guest RAM. Real WireGuard, nftables, policy routing,
encrypted test-storage mount validation and HTTPS were exercised. A guest
network namespace simulated the provider endpoint and HTTPS service. No
external NIC or writable host disk was attached. Test WireGuard, TLS and
storage keys were generated only in guest RAM and were not displayed.

Verified:

- Missing uplink fails and removes the interface/runtime VPN profile.
- Retry establishes a real handshake and successful HTTPS through wg0.
- Repeat connect refuses and preserves a usable existing connection.
- Blocked transport makes the active guard fail while direct HTTPS stays denied.
- Disconnect during blocking succeeds; a blocked reconnect rolls back fully.
- Direct HTTPS stays denied after failed connect; reconnect works after restoration.
- Missing VPN default route makes the guard fail; restoring it recovers connectivity.
- Disconnect and repeat disconnect succeed; direct HTTPS remains denied.
- Firewall remains active; its complete portable_vpn table JSON matches the initial contents.

Earlier harness runs stalled or failed because the serial login service
competed for the test console and the test chronyc wrapper was placed on
non-executable /run. Corrected both in test-only code. Individual checks
are bounded; timeout exits do not qualify as expected rejection passes.
An intermediate corrected run passed 20 checks before the final additional
blocked-connect rollback/retry and firewall comparison checks were added.

Chrony service start/stop calls are real, but its waitsync result is replaced
by a guest-only wrapper reporting unavailable synchronization. NTP, external
DNS, actual provider connectivity/exit IP, IPv6 internet connectivity, P2P,
encrypted-image boot and Secure Boot were not tested. This is a functional
simulation, not a comprehensive leak or security audit.

Prepared `tests/rebuild-release.py` and documented it in
`docs/rebuild-and-live-tests.md`. Syntax/input validation and configuration
generation passed. The active fresh build directory is:

`/home/sam/portable-live/releases/20261011-171244-905383/build`

At recording, the coordinator's phase was `awaiting-sudo-authentication`.
An open “PetalOS isolated rebuild” terminal is waiting for Sam's password;
the privileged build has not started. The previous staging attempt was
canceled before build to correct artifact permissions and is preserved.
No rebuilt ISO or test-image update is claimed. No host sudo policy,
physical microSD or production firewall rule was changed.
