# Rebuilt release verification — 2026-10-11

Sam authenticated sudo in the separate rebuild terminal. The isolated
live-build run completed successfully at 18:38:43 local time. Its final
coordinator phase is `complete`.

Release directory:

`/home/sam/portable-live/releases/20261011-171244-905383`

ISO:

`build/live-image-amd64.hybrid.iso` (1884.3 MiB)

Independently recalculated SHA256 and size checks against `manifest.json`
passed for kernel, initrd, squashfs and ISO. Squashfs contents match the
current build inputs for portable-vpn, portable-check-vpn, nftables.conf and
portable-no-beep.conf. The coordinator also checked that the forbidden
data-unlock-key path was absent from squashfs. This is not a comprehensive
secret audit or a functional test of physical speaker suppression.

Ran:

```sh
python3 -B tests/run-vpn-live.py /home/sam/portable-live/releases/20261011-171244-905383/build
```

All 26 assertions passed with `LIVE_TEST_FAILURES=0`. This run used the VPN
scripts embedded in the rebuilt ISO, without the source-script overlay.
It verified real WireGuard handshake/HTTPS, no-uplink cleanup, repeated
connect, transport blocking, blocked-connect rollback, retry, missing-route
denial/recovery, disconnect and repeated disconnect. Direct HTTPS over the
simulated physical interface stayed denied. The full portable_vpn firewall
table JSON matched its initial contents at the end.

QEMU ran as Sam with the ISO attached read-only, no writable host disk and
no external NIC. All test storage and generated credentials were in guest
RAM. The temporary initrd added the test service and executable clock-test
wrapper only; it did not replace production VPN scripts. Clock waitsync
was simulated as unavailable. Chrony service start/stop calls were real.

This fixture simulates a VPN provider and HTTPS service in a guest network
namespace. It does not verify actual provider connectivity/exit IP, external
DNS or NTP, IPv6 internet access, inbound P2P or app persistence. Direct
kernel/initrd boot does not verify BIOS/UEFI bootloaders or Secure Boot.

The original build/ISO remains preserved. The physical microSD and
`testing/petal-test.img` were not updated or mounted in this stage. Next
storage stage is guarded maintenance of the encrypted QEMU test image,
followed by full boot verification; it requires separate private test-volume
authentication and storage-identity/busy-state checks.
