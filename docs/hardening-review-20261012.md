# Live-system hardening review — 2026-10-12

This review covers the actual encrypted QEMU guest and corresponding build
inputs. Existing project/encrypted backup checksums passed; initial code
snapshots passed and a fresh code-only snapshot was preserved before edits.
No build, physical-card update or host storage attachment was performed.
The guest remains connected to `sto63-adb` with working IPv4 and IPv6.

## Changes staged and tested in guest RAM

- NetworkManager previously preserved connected-interface MAC addresses.
  `95-portable-privacy.conf` now defaults Ethernet and Wi-Fi to a new random
  MAC on each connection activation, randomized connection identity, DHCPv4
  client identity based on the current MAC, and DHCPv6 link-layer DUID/IAID
  based on that MAC. Hostname advertising, LLMNR and mDNS defaults are off.
  The WireGuard connection is not matched by these device-specific sections.
  Wi-Fi scan randomization is enabled generally; Debian's driver-specific
  scan exceptions remain for compatibility. Explicit profile overrides still
  override defaults. No Wi-Fi credentials/profiles are made persistent.
- Background system Tor, Avahi/mDNS, CUPS and printer discovery are stopped
  and masked. Tor Browser uses its separate signed RAM executable and guard.
  Printing/discovery services therefore require deliberate re-enabling if
  later wanted. Default OpenSSH service/socket are masked; the QEMU-only
  loopback/vsock SSH service is retained and is not baked into the image.
- Kernel pointers are hidden, unprivileged kernel logs/process tracing/BPF
  are restricted, and ICMP redirects/source routing are disabled. Existing
  user namespaces, bubblewrap, WireGuard marking/routing, IPv6 and reverse
  path filtering are retained. The change does not replace the firewall.
- Process crash dumps are discarded, with hard core limits for future PAM
  sessions/services. The kernel pipe also discards crashes from already
  running sessions with older limits. No password or key is involved.
- Journald explicitly uses volatile RAM storage, 64 MiB runtime maximum,
  8 MiB files/eight files, one-day retention and rate limiting; forwarding
  to syslog, console and wall is off. Its drop-in sorts after Debian's vendor
  `syslog.conf`, which otherwise overrides an earlier numbered drop-in.

These guest changes are in RAM and disappear on reboot. Build inputs contain
the defaults for the next authorized build. Profiles/selected Stockholm
selection remain in their existing encrypted persistence. No new build has
been started.

## Verification actually performed

- The actual VM wired interface got distinct, locally administered unicast
  MAC addresses on two consecutive NetworkManager connection activations.
  A bounded DHCP capture checked six outbound packets: no hostname/FQDN
  option, and client ID matched the randomized BOOTP MAC. Only booleans were
  retained; no raw packets or hostname/identifier values were logged.
  `tests/hardening-mac-guest.py` reproduces this and refuses non-QEMU guests
  or an active wg0. The nftables ruleset matched exactly before/after.
- The first packet test caught textual `false` being ignored for the global
  hostname ternary default in NetworkManager 1.52.1. Changing it to numeric
  `0` made the real packet test pass. This is fixed in both RAM and source.
- A disposable sibling process's ptrace attach was denied. A disposable
  root process deliberately aborted with its core limit raised and produced
  no core file. No real application/process or personal data was targeted.
- The actual offline wrapper refused an external TCP connection, hid the
  system bus and ran with zero effective capabilities. User namespaces still
  work. This is not proof of isolation against hostile X11/audio IPC.
- Background service listeners disappeared; only the test loopback SSH TCP
  listener remained. All targeted service/socket units are masked. The
  firewall stayed intact during stopping services and cycling the uplink.
- After cycling MACs, the normal VPN reconnect restored IPv4, IPv6 and
  synchronized time; both actual exit helpers passed. Signed Tor preparation
  succeeded, produced its RAM browser copy, and its distribution policy file
  has DisableAppUpdate=true. Browser UI policy activation is not verified by
  reading that file alone.
- Root/home upper storage is tmpfs-backed overlay, Private retains
  nodev/nosuid/noexec/noatime, and no swap device is active. Journals occupy
  about 24 MiB; the effective merged configuration has volatile storage and
  forwarding off. Build-input/trixie/obvious-secret validation and hook/Python
  syntax checks passed. Booted rebuilt-artifact checks are deferred until
  the next authorized build.

Physical Wi-Fi MAC behavior, vendor scan exceptions and DHCPv6 are not tested
by this Ethernet-only VM. Defaults do not guarantee every adapter supports
randomization, and changing a MAC can require a new DHCP lease or network
authentication. MAC randomization only changes link-layer identifiers;
it does not change persistent VPN/P2P/account identities.

## Highest-priority remaining work

1. Administration policy: `sudo -n -l` confirms `(ALL) NOPASSWD: ALL` for the
   live user. Replace general passwordless root with a separately provisioned
   admin-password path and narrowly audited permissions for normal helpers.
   This needs boot/session credential provisioning and GUI/SSH/recovery tests;
   no password, password database or hash belongs in build inputs. The current
   policy was not silently changed while remote management depends on it.
2. AppArmor: the kernel module is enabled but there are no loaded profiles.
   The vendor service explicitly skips `/run/live/overlay/work`; stock Tor
   Browser profiles attach to torbrowser-launcher's directory, not our custom
   portable-tor RAM path. Develop and test appropriate overlay/custom-path
   policies rather than treating an installed package as active confinement.
3. Actual browser about:policies activation, manual signed Tor archive
   install/rollback/fresh-session acceptance, real SAB Usenet setup/download,
   and any native-app GUI/persistence acceptance not already completed.
4. Physical Wi-Fi/Bluetooth/MAC and Secure Boot smoke tests, then a separately
   authorized card update. Branding remains optional product work.

## Primary references

- https://manpages.debian.org/trixie/network-manager/NetworkManager.conf.5.en.html
- https://networkmanager.pages.freedesktop.org/NetworkManager/NetworkManager/NetworkManager.conf.html
- https://raw.githubusercontent.com/NetworkManager/NetworkManager/main/examples/nm-conf.d/30-anon.conf
- https://www.kernel.org/doc/html/latest/admin-guide/sysctl/kernel.html
- https://www.freedesktop.org/software/systemd/man/252/journald.conf.html
- https://gitlab.com/apparmor/apparmor/-/work_items/604
- https://bugs.debian.org/995367

## AppArmor implementation follow-up

The AppArmor gap above now has tested source policies for the portable Tor
Browser, bundled Tor, offline applications and SAB's isolated viewer. They
are enforcing in the current guest's RAM root; see [AppArmor evidence](apparmor.md).
A new image boot is still pending, and download backends/system daemons are
not covered by this stage. The account design was separately revised to an
OS-baked public default per Sam's instruction; see [default account](default-account.md).
