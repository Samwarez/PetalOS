# Isolated rebuild and live-guest tests

Run the rebuild coordinator as Sam in a terminal:

```sh
python3 -B /home/sam/portable-live/build/tests/rebuild-release.py
```

Enter the sudo password only at that terminal's sudo prompt. The coordinator
copies configuration into a new timestamped directory under
`/home/sam/portable-live/releases`, runs `lb config`, then authenticates sudo
and runs `lb build`. It preserves the existing build and ISO. No storage
device or encrypted QEMU image is opened or updated. It grants no sudo policy.
Build hooks execute as root on the host through live-build.

The coordinator checks trixie configuration and obvious secret inputs, bounds
the build log to 2 MiB in `/run/user/1000/petalos-build`, and records its phase
there. After building, it compares both VPN scripts in the squashfs with the
staged inputs, checks for the forbidden unlock-key path, and hashes the kernel,
initrd, squashfs and ISO into the release's `manifest.json`. These checks are
not a comprehensive secret or security audit.

Test a completed release, using its build directory:

```sh
python3 -B tests/run-vpn-live.py /home/sam/portable-live/releases/RELEASE/build
```

For pre-build verification against the current live OS with the current VPN
scripts copied only into the guest's RAM overlay:

```sh
python3 -B tests/run-vpn-live.py /home/sam/portable-live/build --scripts-from-source
```

QEMU runs as Sam using KVM, with a read-only ISO, no writable attached disks,
and no external NIC. A temporary initrd overlay starts the test service.
The guest creates disposable encrypted test storage and random WireGuard/TLS
keys entirely in RAM. A network namespace simulates the fixed VPN provider
endpoint and HTTPS verification service. Real WireGuard, routing, nftables,
curl and the production VPN scripts are exercised. Clock synchronization is
explicitly reported unavailable by a test-only chronyc wrapper; this suite
does not verify NTP. The client firewall is never loosened.

The serial login service is masked only in the test boot to avoid competing
for the test console. Individual checks have a 45-second timeout; timeouts
do not count as successful rejection tests. The whole guest has a watchdog.
Only test results are printed; failure diagnostics remain bounded in RAM at
`/run/user/1000/petalos-live-test/guest.log`.

Acceptance requires `LIVE_TEST_FAILURES=0`, including a successful real
handshake and HTTPS request before testing transport/route loss and recovery.
This simulated fixture does not verify an actual VPN subscription, external
DNS/NTP, IPv6 internet access, inbound P2P, encrypted-card boot or Secure Boot.
The physical microSD remains outside this workflow.

Future builds seed the three package caches with regular .deb files from
the newest completed release. No chroot, bootstrap filesystem, package
index, personal data, or build-completion markers are reused. Each release
still configures and installs a fresh system, and apt resolves current trixie
packages. The existing caches and release artifacts are preserved.
