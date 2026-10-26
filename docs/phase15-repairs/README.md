# Phase 1.5 repairs — first repair batch

Started 2026-10-19 on local branch `fix/phase15-audit`, from
`3da16c2c83924260c1e076818a0ed57e06d30cec`. The original
[audit report](../audit-phase15-20261018/REPORT.md) and its evidence remain unchanged.
Seventy-four existing snapshot checksum records were checked before edits, and
`snapshots/before-phase15-repairs-20261019-123714.tar.gz` preserves the initial
tracked source. Existing work, backups, release images and physical media are
preserved. No physical-card updater has been executed in this repair pass.

Runtime tests use the separately provisioned disposable audit VM, initially
booted from release `20261017-215844-546957`. Public repairs were first tested in
its RAM overlay, then installed as generation `db54a7f70cc1a9868caade29` in that
disposable disk. Its cold boot passed source/binary readback, content-service
ordering, RAM operation, locked Private, and restoration of the immediately
saved setting 333. **This is a tested repair layer, not a rebuilt release ISO.**
Generated executables
remain ignored; their maintained builders, patches and public provenance are
tracked inputs.

| Finding | Repair and current evidence | Remaining acceptance |
| --- | --- | --- |
| F-01 | Explicitly check buffered flush before KeePassXC atomic commit. Real CLI ENOSPC now returns failure, preserves the original database byte-for-byte and allows retry. GUI displays the space error, preserves the original, and saves/reopens the pending entry after space is freed. | Repeat representative GUI lifecycle with the final combined build. Other save modes and abrupt power loss are not covered. |
| F-02 | Validate firewall/peer/routes before attempting tunnel-only chrony; defer normal TLS reachability until afterward. A TLS-verified tunnel may still work when NTP is unavailable; Tor retains its separate clock gate. Add authenticated manual UTC correction and actionable failure text. Actual correction/reconnect works, invalid/unauthenticated inputs fail, and guest RTC is unchanged. | Final-build GUI test. A clock older than the peer's remembered handshake cannot be repaired through that unavailable tunnel automatically. |
| F-03 | Permit edits to desktop-owned files only in each offline role's own RAM documents directory. All 12 roles pass RAM/Private access tests; an actual Mousepad GUI edit persisted. | Final rebuilt image; the repair-layer cold boot and post-boot matrix passed. |
| F-04 | Dedicated RAM Documents/Downloads mount plus per-process idmapped content views. Underlying content belongs to Petal; each isolated app sees its own UID. All 12 offline and four download roles create/edit 0600 files in RAM and Private, and the desktop reads/edits them. Siblings remain hidden. AppState and app homes are not remapped. | Hardware kernel/filesystem compatibility; cold-boot ordering and the post-boot 16-role matrix passed. Active Geany/KeePassXC mapped views were removed and Private closed by the normal lock action. |
| F-05 | Bind copied torrent/NZB imports independently of Private availability. Locked-storage import checks pass with the new mounts. A real trackerless Transmission webseed download completed with Private closed; hash, size and desktop readability matched. | Repeat in the final build; SAB/Pan imports need their own end-to-end checks. |
| F-06 | Immutable complete generations, matching kernel/initrd/live-directory selection, durable staged payloads, retained old payloads and rollback configurations. Seven interruption points, retry/idempotence and interrupted-copy tests pass in directory fixtures. A version-pinned live-boot transformation copies only the selected generation into RAM. Actual FAT/ext4 exhaustion during staging preserved old selection; freeing space and retrying activated the complete generation. | QEMU updated-generation and retained-baseline boots both passed; returning to the candidate and repeating its cold-boot checks also passed. Capacity refusal before activation also passed. Sudden power loss and physical-media durability remain hardware concerns. |
| F-07 | Bounded per-role-family locks, cancellable network-app startup UI, and worker reaping on cancellation. With Tor deliberately blocked, Geany started in 1.6 s; a duplicate Tor launch failed after 3.2 s; ordinary-user cancellation completed in 4 s and left no Tor worker. GUI helper tests passed. Cancellation after a real SAB backend became ready removed a newly started backend and preserved a pre-existing one. | Final-build UI smoke; no claim of exhaustive startup-race coverage. |
| F-08 | The custom aMule/Kad candidate remains abandoned and unsupported, as requested. | Upstream dependency maintenance is separate; no revival of that candidate. |
| F-09 | Save typed live Xfconf values, validate/read back the archive, fsync and atomically replace it. Three immediate changes were captured correctly. Typed-array/boolean tests and daemon/write-failure preservation pass. | Cold boot restored 333; the retained old release also read that archive correctly. |
| S-02 | KeePassXC UAF backport: negative control fails without the fix, all 14 legacy-reader tests pass with it. Versioned trixie backports also cover aMule server-message lengths, libxml2 QName sizing, polkit cookie bounds/NUL input, and Poppler R6 password limits. Installed-package tests pass the documented focused regressions and app startup. | Combined-image verification and broader compatibility testing. Poppler's full upstream suite is not passing because Debian omits its external test documents; all 53 failed test blocks report missing files. |
| S-01 | Confirmed boot-chain gap: a properly rebuilt external initramfs executed a harmless marker while Secure Boot remained enabled. No secret was captured and no firmware or trust key changed. | Accepted limitation for the phase-one RC under Sam's Tails benchmark. The [direct Tails 7.15 comparison](tails-boot-comparison.md) confirmed the same unsigned-initramfs execution path with kernel signature enforcement active. Stronger boot authentication is optional future work. |

## Important boundaries and observations

The mapped-content tests also verified zero process capabilities, no-new-privs,
hidden host devices, hidden SYSTEM and desktop sockets, and denial of IPv4/IPv6
sockets in the offline profile. These observations establish those tested
boundaries, not a comprehensive proof of isolation. The new RAM service refuses
to mount over existing files and must start before the desktop. During live
testing, the disposable guest's original RAM folders were retained separately;
no user storage migration is performed by the production boot service. Shared content mounts use `x-gvfs-hide` to avoid duplicate desktop volume icons.

The first mapped-content lock assertion incorrectly required SYSTEM to close.
That is not the current policy: SYSTEM retains selected settings behind the
screen-authentication boundary, while Private loses its active mapping. The
incorrect-expectation result is preserved separately. The corrected test
confirmed that Private closed, both application workers and their decrypted
views disappeared, and SYSTEM retained its required read-only full view and
selected writable settings area.

The wrong-clock test observed no WireGuard handshake and zero received bytes
while the guest clock was in 2020; restoring the current time allowed reconnect.
This is consistent with [WireGuard's timestamp replay protection](https://www.wireguard.com/protocol/),
which rejects timestamps no later than the last accepted handshake. No forward
clock test is sent to the real provider, because it could leave that test key
unable to reconnect at the correct time. Manual correction writes only the
running clock, requires administrator authentication, refuses while VPN is
connected, and creates no persistent last-used timestamp or off-tunnel time
exception.

The GUI ENOSPC test also encountered KeePassXC's existing suggestion to disable
safe saves after repeated failures. That suggestion was cancelled; atomic saves
remained enabled and recovery then succeeded. It is not a recommended workaround.

## Dependency status checked against current Debian records

On 2026-10-19 the Debian tracker still identifies unresolved trixie issues in
[aMule](https://security-tracker.debian.org/tracker/CVE-2026-51105),
[libxml2](https://security-tracker.debian.org/tracker/CVE-2026-86138),
[Poppler](https://security-tracker.debian.org/tracker/CVE-2026-107705), and
[polkit](https://security-tracker.debian.org/tracker/CVE-2026-4897).
The polkit record explicitly warns that the first fix introduces another issue.
The focused trixie backports are now built, tested in the disposable RAM root,
and staged as generated inputs for the next build. No unstable packages were
used. KeePassXC's reviewed backport is documented separately in
[its build notes](../../local/keepass-native/README.md).

The other four package sets have adjacent `*-backport-provenance.json` records
with exact source, patch, package versions and SHA-256 values. The production
installation hook was exercised in the VM: it preserved the app wrapper and
firewall/sudo/polkit policies, configured all selected packages, and removed its
duplicate deb copies. Existing newer Debian packages are kept by the hook.
All 33 staged public archives were also unpacked for an exact disposable-test
credential scan (1,132 regular archive members); no test credential was found.

Poppler's original library crashed with 128- and 1,024-byte inputs against a
valid R6-encrypted public PDF. The repaired library opens and renders the
127/128/1,024-byte valid cases and cleanly rejects short and long incorrect
passwords under the actual Atril role. Polkit rejects oversized/NUL cookies
without waiting for EOF, rejects the wrong administrator credential, accepts
the correct credential at the PAM stage, and still refuses a fabricated
authorization cookie. This is not a complete graphical authorization test.
The existing privileged-action and raw-device denial probes also passed.
The installed libxml2 library round-trips a 1,000-element namespace document.

Polkit's five packaged tests passed. Poppler's packaged test invocation reports
18 passing and 53 failing; every failed block reports missing external PDF
fixtures. Debian's `override_dh_auto_test` explicitly tolerates this because
that corpus is absent from its source package. The successful package build
does **not** imply a passing full upstream suite. See
[the package notes](../../local/security-backports/README.md) and
[the missing-fixture summary](poppler-upstream-tests.json).

## Evidence and next release gate

Adjacent `*-result.json` files contain bounded, credential-redacted fixture
results. The fixtures are in [tests/phase15-repairs](../../tests/phase15-repairs);
older fixtures are reused without overwriting the original audit evidence.
The KeePassXC [build provenance](keepass-build-provenance.json) records source,
Debian archive, patch and executable hashes and the negative-control result.

Post-boot VPN fault tests kept all four download apps alive, denied tunnel/DNS
failures, recovered without reboot, and observed only permitted WireGuard and
ARP traffic on the uplink during the probes. A synthetic 1080p playback pipeline
completed 600 frames with zero reported drops and its clock tracked real time.
These bounded measurements are not a general performance guarantee.

Pending work remains before phase-one acceptance: finish final rebuilt-image checks
and the documented dependency compatibility coverage. The boot-authentication
limitation is accepted under the verified Tails benchmark; it is not marked fixed.
Hardware suspend/resume, external media, Secure Boot compatibility and power-loss
behavior must be retested on the ThinkPad after a separately authorized image
update. Per-computer key enrollment is not a requirement for the portable OS. No rebuilt ISO, card update or release-readiness claim is made here.

## Boot-authentication limitation and phase-one decision

The cold-boot marker confirmed S-01: modified external initramfs code ran with
Secure Boot enabled. The retained original initramfs booted without the marker.
Neither test collected a passphrase or changed physical firmware trust. The
PetalOS test generation contains that harmless marker and is not a production
release artifact.

Sam rejected mandatory per-computer enrollment as incompatible with portability
and subsequently specified Tails as the acceptance benchmark for this issue.
A direct test of the official Tails 7.15 USB image confirmed the same path:
modified external initramfs code executed, while a changed kernel was rejected
with **bad shim signature** using the same initial firmware trust. See the
[comparison and evidence](tails-boot-comparison.md).

Accordingly S-01 is now an **accepted phase-one limitation, not a required RC
repair**. The risk remains documented; this establishes parity only for the
specific tested boot-media modification, not general Tails-equivalent security.
Per-computer enrollment will not be required. A stronger distributor-trusted
verification chain may be considered later as an optional improvement.

The generation updater retains old payloads and now refuses insufficient free
space before staging. A 4 GiB SYSTEM volume has room for only a limited number
of these large generations. Automatic pruning is deliberately not introduced
by this repair: choosing which old release may be retired needs an explicit
retention/recovery policy.

## Source review and handoff

Eight host regression scripts passed during the repair pass: release generations,
startup control, desktop settings, desktop helpers, VPN connection flow,
credential prompts, VPN profile GUI, and download preparation. The last two
harnesses were updated to exercise the existing shared administrator dialog
and current state-root/normalized-JSON behavior; the product protections were
not relaxed to satisfy them. These host fixtures complement the runtime
evidence and do not establish end-to-end correctness on their own.

Source, maintained patches, regression fixtures and bounded evidence are saved
on the local repair branch. Generated packages/executables, encrypted VM images,
credentials and backups remain outside version control. The exact staged index
is checked with the project scanner and Gitleaks, plus a match against the three
disposable VM credentials without exposing their values. Three Gitleaks matches
were verified to be the SHA-256 of the public Poppler patch; only that exact
checksum in those three provenance files is allowlisted. Patch context whitespace
is retained byte-for-byte to preserve upstream patch identities.

The later dependency packages and startup-family cleanup were tested in the
disposable guest's RAM overlay after the generation cold-boot tests. They have
not yet been included in a new booted ISO. The current test generation retains
the harmless initramfs marker used to confirm S-01 and must not be published as
a release. The next integration step is one combined build followed by the
representative cold-boot, authentication, file, VPN, update and application
checks; physical-card installation remains separately authorized work.


## Combined-image integration, 2026-10-19

The first combined image, release `20261019-211301-083244`, completed live-build
but correctly failed the exhaustive public-file readback: installing the patched
aMule package after live-build's includes replaced `amule.desktop` with Debian's
original entry. The other 217 public inputs matched. The executable diversion
still guarded aMule, but the intended graphical startup helper was lost.

The security-package hook now preserves and restores the reviewed aMule desktop
entry around package installation. `tests/check-security-backport-launcher.py`
uses the actual staged `.deb` launcher to model dpkg replacement: the pre-fix hook
reproduces the loss, and the corrected hook preserves the exact source entry.
The regression does not install packages on the host.

The rejected candidate and original binary-stage markers are preserved under the
release's `rejected-launcher-before-repair` directory. To reuse completed package
assembly, only the exact maintained desktop entry was restored in the build
filesystem, the corrected hook copied into staged configuration, and live-build's
binary stage regenerated. This is an incremental integration rebuild; it is not
a second clean-from-scratch hook execution. `tests/rebuild-release.py` now supports
`--verify-existing RELEASE` to repeat the same complete artifact checks without
reinstalling the OS. Each verification uses a fresh temporary extraction, reports
the mismatching public path without contents, and cleans its temporary files.

The final combined image passed complete artifact verification: 218 public files,
5 generated live boot entries, reviewed security-package versions and critical
binaries, and release payload checksums. The production initramfs contains neither
diagnostic audit marker. See [the build record](combined-build-result.json). Clean
combined-image boot acceptance and physical hardware acceptance remain pending.


## Combined-image VM acceptance completed

The fresh combined-image pass on 2026-10-19 completed: see
[the VM acceptance report](../phase15-combined-vm-20261019/README.md) for tested
outcomes, preserved harness retries, the minor Thunar lock-screen aftermath
observation and remaining hardware/coverage limits. Product source was unchanged
during this pass; only test controllers, fixtures and evidence were added.
The disposable VM was shut down normally and detached. Physical hardware
acceptance remains pending; no card writes or Git push were performed.
