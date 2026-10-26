# Combined-build QEMU acceptance — 2026-10-19

The bounded VM acceptance pass passed for release `20261019-211301-083244`,
product source revision `bfd9dd9efd4294a8c0f3703181b419f4cab64e36`.
No new release-blocking regression was confirmed. Hardware acceptance remains
pending. This establishes the outcomes below, without proving system security
or anonymity.

The fresh disposable VM is `testing/audit/20261019-220338-142131` outside Git.
It uses new, distinct SYSTEM/administrator/Private test credentials, independent
LUKS2 volumes, fresh SSH identities, and only the dedicated audit VPN profile.
The previous audit disk remains preserved and powered off. Production files and
security policies were not changed during this pass. Physical media were not
written. The new guest was shut down normally after testing; its image is unused
and has no attached loop mapping.

The guest booted the verified release payloads plus its public test SSH module,
generation `454373df5891d9db5dd46eec`, using KVM/QEMU 10.0.13, q35, eight CPUs,
16 GiB RAM and stock OVMF Secure Boot trust. The kernel is
`6.12.113+deb13-amd64`. [Metadata](metadata.json), [all invocations](summary.json)
and the [build manifest record](../phase15-repairs/combined-build-result.json)
identify the reviewed artifacts. Credentials, images, keys, databases and raw
screenshots/audio are excluded from this report and version control.

## Verified outcomes

| Area | Outcome and evidence |
|---|---|
| Offline boot | Desktop worked with NIC link disabled before SYSTEM unlock. Private stayed closed; network readiness was denied. Selected live generation was in tmpfs; SYSTEM credentials/settings were absent from that copied RAM medium. Content tmpfs was ready before display-manager startup. [Boot](offline-boot-verified.json), [17 smoke checks](audit-smoke-guest.json). |
| Built-file integrity | 218 public build inputs checked at runtime, with `/etc/hosts` separately validated for the exact expected live-config hostname addition. Secure Boot was enabled; kernel lockdown was active; audit markers were absent. [Cold boot](cold-reboot-integrity-verified.json), [runtime](network-and-desktop.json). |
| Credential separation | SYSTEM authenticated screen unlock and failed Private unlock. Administrator failed Private unlock. Private failed screen authentication, successfully opened its store, and was closed afterward. [Checks](credential-boundaries.json). |
| Graphical Private recovery | Normal desktop action displayed the correctly labelled Private prompt. A wrong passphrase produced an explicit retry message and red entry border. A valid retry opened Private. [Observation](Private-unlock-GUI.json). |
| VPN failure/recovery | Actual offline connect failed closed in about 87 seconds, removed wg0 and kept drop policies. Uplink restoration recovered without reboot. Automatic IPv4, IPv6, DNS, tunnel and clock checks passed. [Offline failure](combined-vm-offline-connect.json), [connection](audit-connect-guest.json), [automatic checks](network-and-desktop.json). |
| Live network faults | All four download apps survived tunnel loss, DNS failure, disconnect/reconnect and same-profile switching. Gates rejected failed states despite stale presentation reports. Missing profiles were rejected. Uplink capture saw 429 WireGuard and two ARP packets, with no unexpected IP packets. Restoring wg0 link alone did not restore readiness; normal disconnect/reconnect recovered it. Original firewall rules matched afterward. [Faults](network-failures.json). |
| Offline boundary | Actual profile/namespace denied IPv4/IPv6 sockets, raw disks, SYSTEM, desktop bus/runtime, X11 and privileged Wayland protocols. Usable Wayland protocols and delegated file save/reopen worked. [Active probes](offline-boundary.json). |
| Application launch | Transmission, Pan, aMule, SAB backend/viewer and Tor/browser reached ready native windows through the approved desktop launch interface. Main executables had their expected enforcing profiles. Namespace-local D-Bus, accessibility, GVFS and portal helpers have separate labels, including unconfined helpers; these were recorded explicitly. [Launches](application-launch-verified.json). |
| Tor workflow | Actual Tor Browser rendered `https://check.torproject.org/` over HTTPS and displayed Tor confirmation. Screenshot remained in RAM; exit address was not copied into the report. [Observation](tor-browser-visual.json). |
| Real download | A copied torrent import completed a real 1,198-byte Debian README webseed download with Private closed; bytes and SHA-256 matched the reference. [Download](combined-vm-download.json). |
| Writable content | All 16 tested roles created/edited/reopened mode-0600 files in their own RAM and Private content directories. Desktop read/edit worked; sibling role folders stayed hidden. These are file-access checks, not full feature tests for every application. [Results](content-access-after-unlock.json). |
| KeePassXC workflow | Actual GUI opened a new synthetic database in Private, saved a new group, and the installed CLI reopened that saved group. The group also survived reboot. [GUI](combined-vm-keepass-gui-check.json), [reboot](combined-vm-Private-persistence.json). |
| Storage exhaustion | On an isolated 2 MiB RAM mount under the real KeePassXC role/profile, a failed update preserved the original database byte-for-byte and readable. Freeing space allowed retry and the change persisted. [Failure/retry](combined-vm-keepass-full.json). |
| Media/audio | Native Parole displayed synthetic video opened from Downloads. A real aMule preview helper delegated a selected Private media file to Parole without modifying it. Synthetic tone reached the guest playback monitor from both RAM and Private paths. A separate native 1080p pipeline in the Parole role rendered 600 frames, zero reported drops, and completed 20 seconds of media in 21.012 seconds. [Preview](combined-vm-private-media.json), [audio](Private-media-audio.json), [clock/frame stats](av-pipeline.json). |
| SAB administration | Actual management HTTP response passed through its Unix relay under the viewer profile. Ordinary desktop UID was denied access to the management socket. Quick-start UI rendered; no Usenet credentials were supplied. [Bridge](combined-vm-sab-bridge.json). |
| Startup/cleanup | Blocked Tor startup did not block Geany; duplicate startup was bounded; ordinary-user cancellation removed its worker. SAB frontend cancellation removed a new backend and preserved an existing backend. Temporary restrictive Tor block table was removed. [Concurrency](broker-concurrency.json), [family cleanup](startup-family-cleanup.json). |
| Clock recovery | Unauthenticated and connected-tunnel correction were rejected. Invalid UTC inputs were rejected. Guest clock was set back to 2020, corrected through the real helper, and VPN reconnected. Guest RTC was not reset. This did not repeat the earlier full connection attempt while the clock remained wrong. [Clock checks](manual-clock-recovery.json). |
| Locking | Download mode inhibited idle locking. Manual lock overrode it, closed Private and removed live mapped content views. Idle action without inhibition also closed Private and established gtklock. SYSTEM unlocked the real graphical locker and left Private closed. Pink wallpaper and SYSTEM prompt were observed. [Inhibition](combined-vm-idle-inhibit.json), [manual lock](mapped-content-lock.json), [idle lock](idle-lock-verified.json). The idle action was invoked directly; the full ten-minute timer was not waited out. |
| Settings/reboot | Immediate saves captured 331/332/333 without waiting for Xfconf disk flush. Cold reboot restored 333, approved Transmission/aMule preferences and numeric server endpoint with Private still closed. Injected history/path canaries were excluded. RAM canaries, temporary media and initial trash contents were absent; Private canary and GUI-saved database survived. [Export](settings-export-verified.json), [rapid save](desktop-save-immediate.json), [restore](combined-vm-persistence-check.json), [Private content](combined-vm-Private-persistence.json). |
| Health/shutdown | Full SYSTEM mount rejected an actual root write with EROFS; desktop UID could not open raw disk/mapping/full SYSTEM view. No swap, failed system units, kernel OOM/panic/segfault marker, or active app workers remained at final check. Root/home/journal remained volatile; approximately 13.2 GiB RAM was available after cleanup. Normal XFCE shutdown powered the guest off twice. [Health](combined-vm-final-health.json), [final request](final-desktop-shutdown.json). |

The installed aMule is the supported Debian package plus the targeted security
length-check repair. The abandoned custom Kad candidate is not part of this
image. Polkit oversized/NUL input rejection, administrator PAM authentication,
fabricated-cookie denial and libxml2 namespace round-trip checks also passed
against the installed patched versions. [Dependency probes](backport-runtime-check.json).

## Functional observation

An already-open Thunar window at Private can show a permission-denied dialog
after locking, with earlier folder-count/free-space text still visible. Mapping
closure and loss of actual content access were independently verified. This is
a low-severity UI/metadata cleanup limitation, with high confidence; locking does
not promise to erase previously displayed information from every desktop cache.
Reproduce by leaving Private open in Thunar, locking, then unlocking SYSTEM.
A future improvement could navigate or close affected windows before unmount,
provided that UI cleanup cannot delay or prevent Private closure. A regression
should check both timely mapping closure and the remaining visible metadata.
No production change was made for this observation.

## Harness corrections and preserved unsuccessful attempts

There were 44 recorded fixture invocations: 38 successful, plus six initial
unsuccessful harness invocations retained verbatim. Final acceptance uses the
verified retries, not a claim that every invocation passed:

- `combined-vm-boot.json`: byte-for-byte `/etc/hosts` comparison ignored the
  expected live-config addition. The retry validates that exact runtime change.
- `combined-vm-start-apps.json`: initial check incorrectly required every helper
  process to share the main application's AppArmor profile. Actual labels were
  inspected; the verified check requires the expected main profile and reports
  namespace-local helper labels separately.
- `content-ownership.json`: invoked before the graphical retry finished mounting
  Private. The settled-unlock retry passed all role checks.
- `combined-vm-persistence-stage.json`: synthetic server-list fixture used an
  incorrect address encoding/expectation and a documentation address, while the
  exporter permits only global numeric endpoints. Corrected fixture uses a
  global synthetic endpoint with automatic eD2k/Kad connection disabled; export
  and actual restored settings passed.
- `combined-vm-idle-lock.json`: capture pipes were inherited by the locker daemon,
  so the harness waited for unlock despite successful locking. Discarded stdio
  permits waiting for the compositor-handshake parent; the retry passed.
- `cold-reboot-integrity.json`: a Wayland socket became available before panel
  and wallpaper startup finished. A bounded check now waits for all expected
  desktop components. Full integrity/pre-VPN checks subsequently passed.

The host controller's screenshot cleanup also ran in every poll, deleting
captures before inspection. Cleanup now runs once before launch; capture names
were separated so the already-running old controller could not delete them.
Test provisioning gained a generation-layout option, and its NIC gained a stable
QMP identifier for link tests. These are test-tool changes; they do not change
the built OS, guest firewall, network routes or production confinement policy.

## Coverage limits and next gate

Ready for the separately authorized ThinkPad/card acceptance stage for this
tested scope. Required hardware checks include Secure Boot/reader reliability,
Wi-Fi/rfkill/MAC behavior, battery/brightness/volume feedback, actual suspend/lid
resume, USB media/VeraCrypt/printers, physical audio/video performance and normal
shutdown. VM success does not establish those outcomes.

Real Usenet transfers remain deferred without server credentials. Kad HighID,
inbound port-forwarding reachability, every app feature, GPU-specific rendering,
full-machine OOM, long-duration workloads, physical power interruption, a new
end-to-end physical installer/update/rollback run and migration of every legacy
Private layout were not covered here. Earlier bounded update fault tests remain
separate evidence. Shared-file handoff is read-only; writable own-folder tests
do not establish arbitrary cross-folder editing support.

S-01 remains the explicitly accepted Tails-comparable external-initramfs
authentication limitation, not a fixed finding. Freed-memory zeroing and closed
LUKS mappings do not prove the absence of recoverable RAM traces. This was one
bounded acceptance pass, not a new exhaustive security audit.

To repeat, use `tests/prepare-audit-vm.py RELEASE --vpn PROFILE --generation`,
launch through `tests/audit-vm.py STATE launch --offline`, stage public hashes
with `tests/stage-combined-vm-expectations.py STATE --offline`, and run the
individual fixtures with `tests/run-combined-vm-check.py STATE FIXTURE`.
The credential-boundary fixture uses `--label credential-boundaries` so its
boolean-only result does not collide with credential-file ignore rules.
Use `--credentials` only for fixtures expecting the disposable credential JSON
on stdin. Avoid running independent fixtures concurrently if they change the
same network, storage, clock, application or lock state. The test workspace and
its mode-0600 credentials stay outside the repository.
