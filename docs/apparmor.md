# AppArmor on the live filesystem

The source configuration loads four enforcing profiles before the display
manager starts: `petalos_firefox`, `petalos_tor`, `petalos_offline`, and
`petalos_offline_sab`. Debian's existing AppArmor unit skips the live overlay;
`portable-apparmor.service` explicitly loads only these tested policies. It
uses no disk cache and does not replace the vendor unit or load untested stock
profiles. Offline and Tor launchers refuse to start if their policies are
missing. Offline launch failures also send a desktop notification.

Tor policies are adapted from Debian trixie's torbrowser-launcher policies
for `/home/*/.local/share/portable-tor/tor-browser`, covering both the current
`user` account and the staged `Petal` default. Their BSD license notice ships
in `/usr/share/doc/petalos/torbrowser-policy-copyright`. Browser subprocesses
retain confinement; bundled Tor receives its own profile. Browser user
namespaces remain enabled. The internal updater cannot execute; updates
remain external signed-archive installations.

The browser can save in `Private/Downloads/TorBrowser`, its new default
download directory. Arbitrary Private files and VPN profiles are inaccessible
to the browser under this policy. Bundled Tor can read/write its RAM state,
but cannot read Private. Offline applications retain their existing writable
home and Private access except `Private/Network`, which is excluded. Thus
editing VPN profiles with an offline editor is restricted; use the existing
profile import/manage flow. No real credentials are used by acceptance tests.

Offline AppArmor starts after bubblewrap constructs its read-only root and
isolated user/PID/network namespaces. The policy denies IPv4 and IPv6 sockets
and administrator executable entry points. It does not grant mount setup
permissions or capabilities. The SAB viewer needs TCP for its HTTP-to-Unix
bridge, so its separate profile permits IPv4 stream sockets inside the same
isolated namespace, which has only loopback and no external route. UDP and
IPv6 remain denied. The original namespace isolation and VPN firewall stay
in place.

## Verified in the existing encrypted QEMU guest, 2026-10-12

- Policies parsed and loaded in enforce mode on the actual live RAM overlay.
- Actual Firefox/browser subprocesses and bundled Tor had enforcing labels.
  Tor reached 100% bootstrap; a SOCKS request to Tor Project's API reported
  `IsTor=true`. No browsing profile was persisted.
- Offline Python had an enforcing label; IPv4/IPv6 socket creation was denied.
  RAM home and harmless Private file writes worked, root writes failed, and
  executing sudo failed.
- The live user could read a generated public fixture in Private/Network
  outside confinement, while offline apps and bundled Tor could not. Bundled
  Tor successfully verified an equivalent config inside its allowed RAM tree.
- Geany, KeePassXC, VLC and Vim version/startup probes passed. Geany's actual
  desktop process ran under the offline profile. WebKit rendered a public
  test page under confinement.
- SAB's ready Unix bridge responded inside the isolated namespace. WebKit
  fetched/rendered a public local HTTP test page there; the namespace had
  only loopback, and an external TCP connection failed.
- A missing policy failed closed. The nftables table was byte-for-byte
  identical before/after the automated fixture checks.
- systemd unit verification passed.

Run `python3 tests/verify-apparmor.py` against the running managed guest with
Private unlocked and a working VPN. It uses bounded pinned SSH calls, creates
and removes harmless fixtures, and prints booleans rather than raw application
logs or credentials. It prepares SAB through its normal launcher and stops it
only if the backend was initially inactive. Root fixture checks currently
require an authenticated sudo cache or the current test VM's legacy policy;
the new Petal sudo/boot acceptance is a separate pending check.

On 2026-10-12 a fresh
preserved encrypted clone booted with the public configuration squashfs layer;
all four profiles activated automatically, and both automated acceptance
sets passed again. Private unlocked and the saved panel restored. This verifies
the layered test image. The subsequent combined release
`20261012-205248-827255` also booted with all four policies enforcing and passed
the active AppArmor checks. This does not
confine every system daemon or download backend: Transmission, Pan, aMule and
SAB's network backend remain outside these new profiles. Shared desktop/display
IPC also remains a limitation; these checks do not establish whole-system
hostile-code containment or anonymity. The later
[security audit](security-audit-20261012.md) confirmed that the browser's TCP
permission can bypass Tor through the VPN after code execution. Its additional
offline viewer wrappers and private viewer buses are tested in RAM/source and
await a new built image; the original four policies are already baked.

Parser loading and policy syntax follow the
[Debian trixie parser manual](https://manpages.debian.org/trixie/apparmor/apparmor_parser.8.en.html)
and [policy reference](https://manpages.debian.org/trixie/apparmor/apparmor.d.5.en.html).
