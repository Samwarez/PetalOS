# Combined-build QEMU acceptance, 2026-10-16

Release: `20261016-210826-820502`.
Test disk: `encrypted-boot-20261016-213255-727082.img`.
Prior working disk preserved; no physical card changes.

## Verified

- Completed build coordinator published its verified manifest; all four expected
  artifacts exist with matching sizes. Built public inputs and boot flags passed
  the coordinator's artifact comparison.
- All 14 cold-boot checks passed: native desktop, wallpaper, idle monitor,
  SYSTEM state available, Private closed/unmounted, no swap or Xwayland,
  RAM boot and allocation/free zeroing flags.
- Ten current guest files match this release, including compartments, numeric
  aMule preferences, VPN checks/backend, prompts, storage visibility rules,
  session startup, bookmarks and patched Conky.
- Read-only release audit passed: VLC absent, all app profiles enforcing,
  root-only whitelisted preference storage, strict desktop archive, and firewall
  input/output/forward drop policies. The audit fixture now recognizes the
  deliberately preserved root-only `AppPreferences/Backups` directory; no
  production configuration was changed for this fixture correction.
- All 11 shutdown authorization checks passed, including remote-user/app-role
  denials and continued authentication for unrelated privileged operations.
- All 17 application roles passed RAM content canaries with Private closed;
  SYSTEM and the desktop home were hidden inside their application namespaces.
- Real offline Parole-role synthetic audio took 6.028 seconds for six seconds
  of PCM using GstPulseSinkClock. Actual UID955, no groups/capabilities,
  playback-monitor-only audio source, direct IPv4/IPv6 denied. Test processes
  and desktop audio modules were removed afterward.
- Saved VPN connected; fresh automatic tunnel, IPv4, IPv6, DNS and clock checks
  all passed. No cached report was used to authorize a network app.

## Current testing

All 11 VPN transition checks passed: repeated disconnect, blocked disconnected
launch gate, invalid-profile failure without a tunnel, reconnect and same-profile
switch. Bounded physical-interface observation counted 194 WireGuard packets and
no unexpected IP egress. Private-folder acceptance passed for all 17 roles. All 12 offline boundary
probes, four download-role probes and selected-file handoff checks passed.
All 17 RAM canaries were verified and removed; Private probes removed their own
canaries. Main network-app workers are ready; visual smoke confirmation remains.

## Known limits

Kad is a low-priority known issue accepted by Sam for this development cycle,
not a release blocker. Experimental aMule correction remains outside this image.
Slight choppiness with the known-good 1080p video still needs hardware follow-up;
the playback-clock defect itself passed automated and earlier audible/visual
acceptance. Configured Usenet transfers remain untested. These functional checks
do not establish anonymity or absence of forensic traces.

## Post-build follow-up

Sam requested automatic retry feedback for a wrong Private passphrase. This is
implemented and tested in source plus guest RAM, not in this completed artifact.
See `private-lock-20261013.md`. The initial unlock failures in this acceptance
run were explained by Sam entering the wrong credential; the correct Private
passphrase unlocked normally before this follow-up. No underlying unlock defect
was inferred from those attempts.

Tor and browser reached ready state in the new build. The actual browser-UID
Unix SOCKS boundary test verified TLS, HTTP 200 and `IsTor=true`; direct IPv4/IPv6
sockets were denied. The temporary test profile was unloaded/removed afterward.
Main download workers reached ready with Private storage. SAB viewer had exited
normally (stopped, no error); it was reopened successfully. Awaiting Sam's final
visual responsiveness and browser-page confirmation.
