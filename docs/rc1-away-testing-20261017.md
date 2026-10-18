# RC 1 unattended ThinkPad testing — 2026-10-17

Sam authorized app, stability and security testing while away about an hour,
with Private unlocked, download mode on, AC power and lid open. Actual admin
password is not saved: use authenticated RAM-only maintenance connection.
No sleep/lock/shutdown during this pass. No OS/card-image updates or builds.
Disposable synthetic files may be written/deleted only in delegated content
folders; no user files, databases, VPN keys or encryption headers inspected.

Initial public source snapshot before-away-test-pass-1792277075181236889.tar.gz
verified. Hardware model 21CQCTO1WW, isolated management link intact. Selected
VPN connected via existing guarded helper, clock/current tunnel validated.

Runner /run/petalos-away-tests/hardware-away-pass-guest.py PID45200: seven
fixture groups, real app startup, 30-minute CPU/memory load, post-load fixtures.
Eight unprivileged nice10 workers, 128 MiB committed each, 320 MiB address-space
limit; pause at 85 C, restart lower load after 70 C; abort below4GiB available
or if Private becomes unavailable. Bounded report.json in RAM. Passive outbound
metadata counts in egress-counters.json, no packets/addresses/payloads logged.

Passed initial groups: 12 offline role boundaries; selected-file handoff;
real KeePass database lifecycle+network denial; stubborn child cleanup and
symlink safety; 16 local/remote power authorization checks; headless Wayland
protocol boundary; six-second real production-role audio-clock test. Network
Tor API via browser UID Unix SOCKS/TLS also passed, direct IPv4/IPv6 denied.
All 12 offline apps and network apps launched ready. Browser and SAB viewer
were started implicitly by parent launchers (cleanup must include both).

Findings fixed in source+guest RAM:

- Other 11 offline profiles had same anonymous temporary commit failure as
  KeePassXC. Added mediate_deleted flag only, preserving paths/network policy.
  New offline-atomic-save-guest.py passed nine checks for each of12roles,
  including actual RAM+Private atomic replace, no caps/groups, network denials,
  SYSTEM/desktop home/VPN profile invisibility. Baseline runner report still
  shows the BEFORE-fix failures; do not mistake that for a failed retest.
- zz-petal-preferences sudo policy source0664, installed0644; visudo-c exit1.
  Corrected source+guest to0440. Added final0992-sudo-policy-integrity hook to
  reject invalid policy/permissions during builds. Actual visudo-c now0.
  Fixed argument-free action allowed; actual extra-argument execution denied
  without admin, as is general sudo. sudo -l listing alone did not distinguish
  password-required command matches; negative test uses real no-auth execution.

Synthetic native Wayland 1080p30 A/V under CPU load: 600 rendered, zero dropped,
20s content in21.005s including poll interval; correct Pulse sink clock and
monotonic media position. Restricted actual window mapping confirmed after
fixing test program-name detection; no production rendering change needed.
User media/microphone never used. Test hardware-av-load-guest.py.

Read-only hardening metadata: SecureBoot, lockdown, both memory-zeroing flags,
no swap, core dumps discarded, Petal password disabled, all offline profiles
in enforce, full SYSTEM view read-only, legacy auto DATA key absent, raw
SYSTEM/Private mapping denied to Petal, all VPN base chain policies drop,
hibernation variants disabled. Initial sudo-file issue fixed and retested.
Signed trixie apt metadata refresh over tunnel succeeded; upgrade simulation
found zero available upgrades. No packages installed or upstream CVE absence
claimed. Some expected TTY denials and blocked ORC JIT mappings were observed;
multimedia fallback rendered without dropped frames. Did not widen policies
merely to silence those messages. No kernel crashes or storage errors observed
in current test interval at initial check.

Host synthetic regressions also passed: settings archive traversal/symlink
rejection, whitelist/history filtering, VPN profile validation and injection
rejection, post-connect probes/stale status rejection, connect/disconnect
rollback, exit IPv4/IPv6 reporting, private retry behavior, lock-ready handshake,
sleep-hook failures, memory boot flags. Ongoing load results pending.

Remaining earlier usability work: shared user-content browsing for confined
players/editors (still per-app folders), Wi-Fi airplane-key physical retest,
final volume alert replacement visual confirmation. Do not claim all issues
resolved from startup/stress tests. No rebuilt acceptance yet.

Additional bounded checks:

- Two 256 MiB synthetic memory buffers survived six minutes of repeated SHA256
  verification (1787 and 1830 passes); no thermal pause. This covers these
  buffers, not all physical memory or a hardware certification.
- Effective NetworkManager defaults and active link metadata passed nine
  checks: randomized locally administered MAC distinct from permanent MAC,
  no DHCP hostname, MAC-based DHCP identity, LLMNR/mDNS disabled. Connection
  properties inherit global defaults; blank profile-only values are not a
  privacy failure. No SSID, MAC, IP or credentials recorded in report.
- Download mode actually inhibited the idle-lock action (exit76), leaving
  Private open. No manual lock/suspend was performed while Sam was away.
- An unused X11 xiccd color daemon had crashed earlier at boot under Wayland.
  Added Hidden=true autostart override in source+RAM; next-boot verification
  remains pending. No active compositor color pipeline was changed.
- A disposable mode0600 app-owned file was unreadable to desktop Petal until
  a pinned-file ACL repair. This confirms an outstanding content-handoff
  usability gap; no global ACL watcher or wider sandbox mounts were added.

New test sources parse successfully. Sudo integrity hook passes shell syntax;
source preference policy mode is0440. Changes remain unbuilt.

Final results and cleanup
-------------------------

The 30-minute loaded soak completed normally, with all17 tracked application
roles alive at every sample, minimum23732MiB available RAM and peak69.75C.
Firewall rules matched the starting hash. Post-load KeePass lifecycle and
selected-file handoff passed. The atomic-save retest passed12roles x9checks.
No new kernel panic/oops, process segfault or storage I/O error was found in
this bounded interval. Startup/survival does not prove every GUI operation.

Passive observer counted203149 WireGuard packets and55 ARP frames, with no
unexpected outgoing IP frames in its observation interval. Its start followed
initial startup, so this is not a whole-boot capture or anonymity proof.
After closing all test apps, eleven VPN transition checks passed: repeated
safe disconnect, current gate rejection while disconnected, invalid profile
fails closed, reconnect and same-profile switch, live gate readiness after
both, and no unexpected physical IP egress. Transition observer counted215
WireGuard packets; canaries from root, Petal and app UIDs did not escape.
No firewall weakening or external DNS/time exception was introduced.

All started apps, CPU workers and metadata observers were stopped. Temporary
root-only RAM fixtures and maintenance helper files removed. Petal sudo
credentials invalidated; authenticated root SSH session60641 exited0. The
isolated host Ethernet peer remains available. Ordinary pinned SSH confirmed
Private still unlocked and download mode still enabled, matching Sam's
requested unattended state. Administrator password was never stored.

Public bounded reports saved and SHA256-checksummed at:
/home/sam/portable-live/testing/artifacts/rc1-hardware-20261017/away-test-results.json
No personal files, real databases, packet payloads or VPN secrets exported.
No build or physical boot-image update was performed. Remaining usability
items above still need implementation/testing before claiming completion.
