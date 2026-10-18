# Combined release regression, 2026-10-14

The preserved QEMU clone of release `20261014-173056-037830` passed all
14 cold-boot checks, graphical administrator authentication, separate Private
unlock and lock, four download-role folder-boundary probes, 13 offline-role
probes, and the native Wayland boundary test. User confirmed Transmission, Pan,
aMule and Tor Browser were usable, including Tor website access.

VPN disconnect, repeated disconnect, invalid-profile failure, reconnect and
same-profile switching passed. The bounded physical-interface observation saw
95 WireGuard frames and no unexpected IP egress. This is a functional test,
not a general anonymity guarantee. Selected sto63-adb provided successful IPv6
HTTPS checks through wg0 against api6.ipify.org and ipv6.icanhazip.com; api64
was unreachable in one diagnostic probe.

Two fixes remain to be included in a corrected release:

- The live AppArmor service omitted offline-app profiles. It now loads all 22
  production profile files. Builder validation rejects omitted profiles; a
  negative offline-HTML omission test passed. The QEMU-only Wayland probe
  profile is loaded explicitly by the test, outside the production list.
- App-private D-Bus sessions could activate XFCE Notify Daemon, which cannot
  display layer-shell surfaces on restricted compositor connections. Their
  bus policy now denies calls to the two notification service names. Four-role
  active probes proved denial, a usable private bus and no notification service
  activation. Desktop notification capabilities remained available. All four
  launchers returned success after applying the policy.

The fixes were applied only to source and the guest RAM overlay. The original
ISO remains unchanged. No physical microSD was modified. Final manual storage
lock closed/unmounted Private while SYSTEM settings remained ready. The root
maintenance session and helpers were removed; the VM remains running with
Private closed.
