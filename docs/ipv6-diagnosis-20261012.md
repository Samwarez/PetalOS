# Live VPN IPv6 diagnosis — 2026-10-12

Current result: real-provider IPv6 works after selecting Stockholm profile
`sto63-adb`. The built-in IPv6 exit checker and independent Cloudflare HTTPS
both pass. Zurich still fails with the same client key and IPv6 assignment,
which strongly localizes the failure to the Zurich endpoint/server path.

Diagnosed the booted encrypted QEMU test clone directly through pinned SSH,
after Sam connected the real Zurich WireGuard profile. Sam confirmed IPv6
is enabled in the OVPN account. The second Gothenburg profile is knowingly
invalid and cannot serve as a provider comparison.

Verified observations:

- IPv4 HTTPS through wg0 succeeds and the active VPN guard passes.
- IPv6 is enabled globally and on wg0. The assigned /128, default route in
  table 51820, policy rules, firewall mark, and peer AllowedIPs include the
  expected IPv6 configuration. Route lookups select wg0 and its assigned
  source address, including a lookup explicitly constrained to wg0.
- Original host, stored encrypted, and runtime profile Address, AllowedIPs
  and numeric Endpoint fields match after canonical IPv6 formatting. No
  keys or complete configuration payloads were displayed or logged.
- Bounded IPv6 HTTPS attempts to Cloudflare, Google, and ipify time out
  before TCP connects. IPv6 ICMP probes to Cloudflare and Google also get
  no reply. A UDP DNS probe to Cloudflare's IPv6 resolver, explicitly bound
  to wg0, times out. No DNS/firewall exception was added.
- A bounded AF_PACKET capture on wg0 sees four 80-byte outbound TCP SYNs
  to a fixed Cloudflare IPv6 destination and no inbound IPv6 replies.
  A simultaneous capture on the physical guest interface sees outbound
  encrypted WireGuard datagrams of the corresponding size to the selected
  numeric provider endpoint. Only protocol/header counts were retained;
  no application payload, encrypted packet dump, or key was retained.
- Reconnecting the selected profile through the normal serialized switch
  path restores verified IPv4 and synchronized time, but IPv6 still fails.
- The kill switch's input/output/forward policies remain drop throughout.
  Existing routing/firewall configuration and MTU were not changed as a
  speculative workaround. IPv6 was not disabled and a failed check was
  not relabeled as successful.

These observations point to the provider profile's IPv6 assignment or the
provider server/return path. They do not conclusively distinguish those
causes or prove a provider-wide outage. A normal packet-size MTU failure is
unlikely because the missing exchange consists of small TCP SYN packets.
Prior diskless dual-stack tests verified the guest stack against a simulated
provider; those do not verify the actual provider allocation.

Requested a freshly downloaded Zurich configuration using the existing
provider key slot, or another known-valid existing profile, with only its
host file path supplied in chat. This allows validation/import and a live
test without rebuilding, restarting QEMU, consuming a new key slot, or
weakening the kill switch. IPv6 remained unresolved pending that comparison.

## Fresh-key Zurich comparison

Sam supplied `/home/sam/Desktop/zrh43-alt.conf`, generated with a new key.
The profile passed the strict parser. Its host-file mode was restricted to
600, and its canonical payload was transferred through pinned SSH stdin
directly into encrypted `Private/Network/Profiles/zrh43-alt.conf`, using
exclusive creation, mode 600 and fsync. Existing profiles were preserved;
no profile payload or key was copied into project/build inputs or diagnostics.

The normal serialized switch connected the new profile, verified IPv4 and
synchronized the clock. Its client key and assigned addresses differ from
the original; server key, numeric endpoint and DNS are unchanged. The live
IPv6 address and route use the new assignment. IPv4 HTTPS succeeds, but
IPv6 HTTPS to ipify and independent Cloudflare still times out before TCP
connects. The kill switch retains its existing output rules and drop policy.

The stale-original-key explanation is therefore less likely. This still
does not distinguish a Zurich IPv6 server/return-path issue from a broader
provider/account issue. Requested a known-valid profile for a different
provider server/location; the fake Gothenburg profile cannot serve this
comparison. At that stage `zrh43-alt` was selected and functional for IPv4. No rebuild
or VM shutdown was needed. IPv6 was not fixed by the fresh Zurich profile.

## Stockholm comparison and working selection

Sam supplied `/mnt/xhome/Sam/Downloads/sto63-adb.conf`. It passed the strict
parser and was imported through SSH stdin into encrypted Private with
exclusive creation, mode 600 and fsync. Existing profiles were preserved.
The normal serialized switch verified IPv4 and synchronized the clock.

Stockholm uses the same client private key and same assigned IPv6 address
as the new Zurich profile, with a different endpoint/server key. Equality
was checked in memory and only boolean results emitted. IPv6 HTTPS to ipify
now returns a public IPv6 address, the actual `portable-check-exit-ip --ipv6`
helper succeeds and updates its RAM status record, and independent Cloudflare
HTTPS returns HTTP 200. This rules out a general guest IPv6 or account/key
failure for this tested key. It strongly implicates the Zurich endpoint's
IPv6 server/return path; no provider-wide outage is established.

The disconnected state retained all three drop policies and empty endpoint
allowances, removed wg0, and a bounded direct IPv6 HTTPS probe failed. That
probe alone is not a comprehensive IPv6 leak audit. The saved selection
`sto63-adb` was used for reconnect, which restored verified IPv4, synchronized
time and another successful built-in IPv6 exit check. The VM is left connected
to Stockholm. No firewall, routing implementation, MTU,
OS rebuild or VM restart was needed for the working profile.

Provider references:

- https://support.ovpn.com/hc/en-us/articles/46236295057427-Does-OVPN-support-IPv6
- https://www.ovpn.com/en/guides/wireguard/ubuntu-wg-cli

The general provider status page lists Zurich operational, but its fetched
update time was 2026-10-09 and it does not separately report this subscriber's
WireGuard IPv6 path. It is not evidence that this particular path works.
