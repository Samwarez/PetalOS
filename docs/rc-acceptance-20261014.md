# Release-candidate QEMU acceptance, 2026-10-14

Release: `/home/sam/portable-live/releases/20261014-192806-258005`.
ISO size: 1,953,349,632 bytes.
SHA256: `39e0ace7a07d8d37aa0de816f200bba08ec35b2f014a66386987357e55f170e4`.
The preserved encrypted test clone boots this release with an additional
QEMU-only management module. No physical card was updated.

Verified on this candidate:

- Builder artifact/input checks passed, including absence of VLC/libVLC and
  the prohibited DATA unlock-key path. All 14 cold-boot/state checks passed
  initially and again after the final Private lock.
- Read-only RC audit passed before and after tests: enforcing app profiles,
  all three main firewall chain policies drop, restricted whitelisted SYSTEM
  preferences, strict desktop settings archive, and no VLC command or role.
- All 12 remaining offline GUI roles launched and mapped native windows.
  Transmission, Pan, aMule and Tor Browser also launched. These are startup
  checks, not exhaustive tests of every application feature.
- All 17 RAM-only folder probes passed with Private closed. After the user
  separately unlocked Private, all 17 dual-folder probes passed: writable own
  RAM and Private content, distinct storage, both bookmarks, and hidden
  SYSTEM/desktop-home views.
- Transmission normally remained running after its window closed. Sending
  SIGTERM to its actual app process allowed its normal settings flush. Eight
  supported fields were saved through the desktop user's fixed preference
  helper, then restored after restart. Deliberately changing a RAM speed
  setting while stopped was overridden by the saved SYSTEM snapshot on
  restart. The requested numeric value 123 was not observed; no claim is
  made that this particular GUI edit was saved. Pan and aMule matched their
  saved filtered fields on launch (one and five fields respectively).
- Manual Private lock succeeded with Transmission, Pan and aMule running
  against Private. All role workers stopped, the DATA mapping and mount
  disappeared, SYSTEM remained ready, and WireGuard was absent. All 17 RAM
  content canaries survived and were removed afterward.
- Saving preferences after those apps last used Private, with Private now
  closed, correctly failed. Existing SYSTEM preference bytes and modification
  times were unchanged: no fallback to stale RAM settings.
- All four notification fixtures passed, including explicit D-Bus service
  activation refusal and a usable private session bus.
- All 11 VPN transition checks passed, including repeated disconnect, invalid
  profile refusal, reconnect and same-profile switching. A bounded observation
  saw WireGuard traffic and no unexpected physical IP egress. IPv6 exit check
  also succeeded. These bounded checks do not establish anonymity.
- Signed Tor Browser 15.0.25 was installed as Petal into the candidate's
  encrypted SYSTEM public-application area. The earlier archive was retained;
  signature verification and disabled internal browser updates were checked.
  Its session profile remains in RAM. This payload is separate from the ISO.

## Isolated management feasibility

`tests/hardware-management-netns-guest.py` passed all seven checks in QEMU.
Two disposable namespaces and a virtual Ethernet pair exercised key-only SSH,
exact stdout/stderr/exit-7 capture, wrong-key rejection, unauthorized-source
blocking, no external route, distinct network namespace, and unchanged main
firewall/routes/rules both during operation and after cleanup. Ephemeral keys
were generated and destroyed inside guest RAM; none entered build inputs.

This proves the synthetic arrangement, not a completed hardware installer or
physical Ethernet/Wi-Fi compatibility. See `hardware-rc-acceptance.md` for the
ThinkPad T14s plan. Physical testing, actual wireless MAC behavior and the
physical card's independent Private encryption layout remain unverified.
Actual Usenet login/download tests remain explicitly deferred. Suspend remains
disabled. These functional checks do not prove absence of forensic traces or
Tails-equivalent security.
