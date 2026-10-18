# Tor launch without administrator authentication

The desktop Tor action no longer requests general sudo authorization. Both
its preparation path and the command-line Tor wrapper use the same fixed
`portable-check-tor-ready` root helper through noninteractive sudo.

The sole passwordless rule is restricted to Petal, root as the target, the
exact installed helper path, and no arguments. Environment preservation is
explicitly disabled with NOSETENV. The no-argument restriction uses sudoers'
empty argument string syntax; see the
[Debian trixie sudoers manual](https://manpages.debian.org/trixie/sudo/sudoers.5.en.html).
General sudo, VPN changes, clock-control commands and Private recovery retain
their password requirements.

The helper uses Python isolated mode, fixed absolute child command paths,
a clean environment, root working directory, no input, suppressed child
output and bounded timeouts. It reads the existing root-only VPN transaction
lock, rejects unsafe locks and waits at most two seconds for a shared lock.
It refuses readiness during VPN changes. It does not create a lock or modify
VPN configuration, routing, DNS, firewall rules, time or credentials.

While holding the shared lock, it runs the existing live VPN guard (firewall
service/drop policies, actual peer/mark/route, tunnel-bound HTTPS request and
confirmed handshake), then queries chrony's synchronization state. It never
uses cached telemetry/status for permission to launch. The fixed network
probe is bound to wg0 and remains subject to the existing kill switch.

## Verified in the running encrypted QEMU guest

- With sudo's timestamp cleared, the helper, Tor preparation and actual
  graphical Tor launch succeeded. The launcher no longer calls sudo askpass
  for Tor; graphical success/failure regression checks passed.
- General sudo, VPN disconnect and direct chronyc commands still failed
  without a password. The helper did not grant a general sudo timestamp.
- Extra helper arguments, environment preservation and an unprivileged
  direct invocation were rejected.
- An exclusive VPN transaction lock caused refusal.
- Stopping chrony caused refusal; restoring synchronized chrony restored
  readiness.
- Disconnecting VPN caused refusal, including Tor preparation. All three
  firewall chains retained drop policies. Reconnecting the saved selected
  profile and synchronizing time restored readiness.
- Read-only checks left the nftables table byte-for-byte unchanged.

`tests/tor-readcheck-guest.py` exercises these cases as root in QEMU. It briefly
stops/restarts chrony and disconnects/reconnects VPN, preserves the kill switch,
and prints only booleans. Its administrative setup is separate from the
passwordless launch exception.

Source changes are staged for the next full build and applied to the current
VM RAM root. The already-installed test configuration layer has not been
replaced with this follow-up yet, so these particular changes would disappear
on reboot until incorporated into a new image. No physical-card update was
performed.
