# PetalOS Phase 1.5 independent audit — 18 October 2026

**Assessment:** this build is a useful development baseline, but is not ready for an unqualified phase-one release sign-off. The main barriers are confirmed file/save failures, recovery with an incorrect clock, interrupted-update consistency, and unresolved boot-chain authentication coverage. Several installed dependencies also have unresolved Debian-tracked vulnerabilities. No repair has been applied as part of this audit. S-01 remains an explicitly unconfirmed attack path; S-02 and the functional findings below have separate evidence.

This was one bounded review of the actual source, release artifacts and separately provisioned QEMU guest. Previous reports and tests were used to locate components and select hypotheses, not as proof. Successful tests below do not establish anonymity, absence of forensic traces, resistance to every exploit, or Tails-equivalent security.

## 1. Identity, preservation and method

| Item | Reviewed identity |
|---|---|
| Project | `/home/sam/portable-live/build` |
| Revision | No Git repository exists. The SHA-256 of the initial public source manifest is `c4bd6cecb7e09fe73019cb629dba694651df4518e26b5f5eec9c8da9a5d448ad`. |
| Release | `20261017-215844-546957`, freshly verified against its manifest |
| Guest | Fresh disposable audit image `testing/audit/20261017-221958-817753/audit.img`; 16 GiB virtual disk, 16 GiB RAM, eight vCPUs |
| Kernel | `6.12.113+deb13-amd64`; Debian source version `6.12.113-1` |
| Root SquashFS SHA-256 | `50634c957ee1dece48d179407f57cf5071acc289ec76a83253073d81a485b17a` |
| Initrd SHA-256 | `2625d4f7a1c7ec10a0ec156e10c62df7874e595beacde15354dfc496cbd90247` |
| Kernel SHA-256 | `4336c75fc1a6a58e7bda66cbe9f4042f88064e7abc93faaea9e2aceb19459561` |
| ISO SHA-256 | `55668a8c92e1653d0d73a8b3311e96559b9fb8b5a2ac958f2c496afb909a10b2` |

[Identity and backup checks](identity.json), [release verification](release-verification.json), [initial source manifest](source-manifest.json), [public snapshot](public-source-before-audit.tar.gz).

AGENTS.md and PETALOS-HANDOFF.md were read. Twenty existing public code snapshots with adjacent checksums were verified; a separate initial public snapshot was preserved. This is not a claim that every historical encrypted data backup has been restored and tested. All 265 current configuration inputs compared equal to the release's staged configuration; 99 selected installed production helpers compared equal to current source. [Build comparison](source-build-comparison.json), [runtime comparison](source-runtime-comparison.json).

Only the disposable VM, new audit fixtures, and this report/evidence directory were changed. Production source, authentication policy, real credentials, personal images, physical SD cards, host disks/firmware and host security settings were outside the mutation scope. Tests used three distinct disposable credentials held outside build inputs and reports. Administrative commands authenticated normally; no passwordless administration exception was added.

Evidence files contain bounded public results. The large dependency candidate list is a triage input, **not a count of exploitable vulnerabilities**. Deliberately failed tests and corrected harness mistakes are identified below rather than counted as product failures.

## 2. Architecture actually reviewed

- **Build:** Debian trixie live-build configuration, numbered chroot/binary hooks, and `tests/rebuild-release.py`. Each release uses a separate build directory and may reuse public package archives. The coordinator rejects obvious secret-bearing inputs, validates RAM boot flags, verifies selected installed files, and writes artifact hashes. This is an integrity record, not a signed release trust chain or reproducible-build proof.
- **Boot:** signed EFI shim/GRUB and Debian kernel, external initrd and GRUB configuration on the boot filesystem. `portable-unlock` opens encrypted SYSTEM in initramfs. Live-boot copies selected filesystem images to RAM and constructs a SquashFS/overlay root. Secure Boot and kernel lockdown were enabled in QEMU.
- **Persistence:** SYSTEM's full mounted view is root-only and read-only; selected state directories are exposed through writable binds. VPN profiles, signed public Tor archives, desktop settings and an approved application-preference subset live there. Root/home/logs/caches remain volatile. Private is a separate LUKS2 filesystem, closed at boot, with its own credential and explicitly delegated per-app directories.
- **Authentication:** Petal's password login is locked. SYSTEM authenticates boot/screen unlock, the administrator credential authorizes privileged maintenance, and Private alone opens Private. The administrator hash is restored from encrypted SYSTEM into the live session. The fresh audit image has no legacy automatic DATA key.
- **Network:** a default-drop nftables policy precedes NetworkManager. Literal VPN endpoint addresses/ports are allowlisted; WireGuard configuration is prepared in RAM. Network roles use the VPN; external DNS and chrony use the permitted tunnel. Launch decisions call current checks rather than trusting a cached success report.
- **Desktop:** **labwc 0.8.3**, with wlroots 0.18.2, supplies the Wayland compositor/window management; XFCE supplies the panel, settings, desktop components and file manager. Native wallpaper and custom window-appearance controls bridge XFCE's incomplete Wayland support. XWayland-related packages exist, but ordinary reviewed application launches use native Wayland and receive no host X11 socket.
- **Applications:** fixed root broker, distinct application UIDs, bubblewrap mount/PID/IPC boundaries, no effective capabilities and `no_new_privs`. Offline roles and the Tor browser have separate network namespaces. Security-context Wayland listeners exclude privileged compositor protocols. Main applications have AppArmor profiles; some private-session D-Bus/GVFS/accessibility helpers are unconfined by AppArmor but retain their application UID and namespace boundaries. Do not describe the entire process tree as AppArmor-confined.
- **Bridges:** selected-file delegation, a read-only media handoff, restricted Tor control/SOCKS sockets, SABnzbd's authenticated local administration bridge, and a playback-only audio bridge. Sandboxed applications do not receive the desktop's unrestricted system/session buses or microphone interface.
- **Local builds:** patched native Parole and Conky binaries are hash-pinned by build hooks. The custom aMule Kad candidate is separate and **not installed in this release**. The installed aMule matches the Debian package's executable.

## 3. Priorities, severity and confidence

Security severity reflects confidentiality/integrity/privilege impact under stated attacker access. Functional severity reflects data loss, unavailable core workflows, recoverability and breadth of impact. “High” in the functional section does not imply privilege escalation. High confidence means direct reproduction or exact installed-version/source evidence; it does not imply that an exploit chain was demonstrated.

| Priority | Finding | Classification |
|---|---|---|
| 1 | F-01: full-storage KeePassXC CLI save destroys the database while reporting success | Confirmed, high functional severity; GUI scope unresolved |
| 2 | S-01: external-initrd/root trust-chain coverage | High-impact concern; attack execution not demonstrated |
| 3 | F-03/F-04/F-05: RAM editing, cross-account content ownership and locked-Private imports | Confirmed functional failures, high/medium severity |
| 4 | F-02: incorrect-clock VPN bootstrap deadlock | Confirmed, high functional severity |
| 5 | F-06: interrupted update can mix release generations | Confirmed code/regular-file failure model, high functional severity |
| 6 | S-02: unresolved installed dependency issues | Confirmed vulnerable package versions; exploit paths vary |
| 7 | F-09/F-07: stale settings snapshot and serialized uncancellable launches | Confirmed, medium functional severity |
| 8 | F-08: unintegrated aMule bitmask correction | Confirmed source defect, low priority; Kad consequence unresolved |

## 4. Confirmed security findings

### S-02 — Medium, with potentially greater impact in sensitive roles: unresolved installed dependency vulnerabilities

**Confidence:** high that the listed installed versions are marked vulnerable by Debian; application-specific exploitation was not attempted. No assertion of arbitrary code execution follows from merely matching a version.

**Affected:** installed packages below; [package inventory](packages.json), [Debian-version comparison](dependency-candidates.json), [APT state](package-state-result.json). The selected package lists/build release determine installation; these defects are in upstream or Debian-packaged code, not demonstrated PetalOS sandbox escapes.

| Component/version | Concrete precondition and practical impact | Smallest repair and regression |
|---|---|---|
| aMule `1:2.3.3-3.2` | A malicious contacted eD2k server supplies the affected server-message packet; Debian describes a remotely induced denial of service. A VPN does not make the remote server trustworthy. [CVE-2026-51105](https://security-tracker.debian.org/tracker/CVE-2026-51105). | Backport the reviewed upstream packet-length fix into the trixie package or obtain a maintained trixie security update. Test malformed server messages, ordinary server connection and downloads under the existing sandbox. |
| KeePassXC `2.7.10+dfsg1-1` | Importing a crafted, unlockable legacy `.kdb` database can reach a controlled use-after-free and crash. Its role may also contain legitimate password databases, so offline network isolation does not remove the sensitive in-process exposure. [CVE-2026-69150](https://security-tracker.debian.org/tracker/CVE-2026-69150). | Backport the importer lifetime fix; until then consider an explicit legacy-import restriction. Test the crafted importer regression and ordinary KDBX open/save. Disabling all database import would be broader and less usable than necessary. |
| libxml2 `2.12.7+dfsg+really2.9.14-2.1+deb13u3` | The installed library is listed as affected by an integer/heap overflow in qualified-name dictionary handling. Exact reachability through each installed XML consumer remains unvalidated. [CVE-2026-86138](https://security-tracker.debian.org/tracker/CVE-2026-86138). | Review/backport the upstream fix through trixie packaging; run its upstream regression and representative document/settings parsing. No blanket claim that every XML document is exploitable. |
| Poppler `25.03.0-5+deb13u4` | A consumer passes an attacker-controlled password longer than 127 bytes while opening an AESV3/R6 PDF. Stack corruption is the reported result. Atril's complete trigger path was not exercised. [CVE-2026-107705](https://security-tracker.debian.org/tracker/CVE-2026-107705). | Bound/fix the affected password handling through a reviewed package patch; test long-password failure and ordinary encrypted PDFs in Atril. |
| polkit `126-2` — **Low availability risk** | A local caller supplies unbounded input to the agent helper; upstream reports memory exhaustion. This audit did not demonstrate privilege escalation or sandbox escape. [CVE-2026-4897](https://security-tracker.debian.org/tracker/CVE-2026-4897). | Apply a reviewed bounded-input fix including its follow-up corrections; do not blindly select the first upstream fix, whose tracker notes a later regression. Test normal administrator dialogs and bounded oversized input. |

Selected applicability checks also reduce several raw hits: NetworkManager uses its internal DHCP implementation rather than the affected external-dhclient path; the configured sudo policy does not use the flagged date/time authorization features; `fs.protected_hardlinks=1` blocks the prerequisite cited by one loader attack; this is x86-64, not the affected Power8 string routine; systemd-homed, systemd-oomd and nscd were inactive in the final runtime check. These exclusions concern those specific prerequisites, not every CVE in the same package.

No newer installed-package upgrades were offered after a signed APT refresh through the VPN. That does **not** mean all installed packages are free of known vulnerabilities. Debian backports were accounted for using source-package versions and Debian version comparison rather than comparing upstream version strings. [Debian explanation of security backports](https://www.debian.org/security/faq.en.html).

The raw inventory produced 2,147 candidate records across installed sources, including unimportant, undetermined and feature-dependent entries. It is deliberately not reproduced as 2,147 findings. Kernel, FFmpeg, CUPS and generic library candidates require further applicability work; see the coverage limits. Moving the distro to unstable is not the proposed repair.

## 5. Confirmed functional and stability findings

### F-01 — High: a full destination can silently destroy a KeePassXC CLI database

**Confidence:** high, repeated under the production profile and in a diagnostic control without that profile. **GUI exposure is not yet confirmed.**

**Affected:** installed `/usr/bin/keepassxc-cli` from KeePassXC `2.7.10+dfsg1-1`, its Qt/file-save stack; [runtime profile](../../config/includes.chroot/etc/apparmor.d/petalos.offline-keepassxc). Upstream [AddGroup.cpp lines 59–62](https://github.com/keepassxreboot/keepassxc/blob/2.7.10/src/cli/AddGroup.cpp#L59) requests an atomic save; [Database.cpp](https://github.com/keepassxreboot/keepassxc/blob/2.7.10/src/core/Database.cpp#L325) implements that save. The exact failed-write propagation defect still needs tracing.

**Reproduction:** in a private mount namespace, mount a disposable 2 MiB tmpfs over the role's own RAM Documents directory; create and successfully reopen a synthetic database; fill remaining space to ENOSPC; run `keepassxc-cli mkdir` on that database. This did not fill the real guest root or Private filesystem. [Fixture](../../tests/phase15-20261018/full-storage-detail.py), [result](full-storage-detail-result.json), [control](full-storage-upstream-control-result.json).

**Observed:** initial database was valid and 1,838 bytes; update returned exit 0 and “Successfully added group Public group.” The database became **zero bytes**, could not reopen, and freeing space did not recover it. The control reproduced the same outcome. No real password database was used.

**Impact:** silent loss of an existing database in the tested CLI path, including a dangerous success message. An automated local assistant must not use this path for valuable databases until repaired. Ordinary non-full RAM and Private lifecycle tests both passed.

**Smallest repair:** trace and correct failed-write/flush/commit propagation in the installed KeePassXC/Qt path so an unsuccessful temporary write cannot replace the original and cannot report success. Preserve a readable original and report failure. A space precheck alone is racy and insufficient; relaxing AppArmor will not fix the reproduced control failure.

**Regression:** deterministic ENOSPC and short-write injection for both CLI and GUI, verify original database hash/readability, error indication, and a successful retry after space is freed. Also test interruption before commit and the normal atomic-save policy. Do not claim the GUI safe based solely on this CLI test.

### F-02 — High: an incorrect clock can prevent the VPN from reaching its clock-repair step

**Confidence:** high; reproduced and recovered without a reboot.

**Affected:** [portable-vpn lines 83–95](../../config/includes.chroot/usr/local/sbin/portable-vpn#L83), `portable-check-vpn`, chrony startup ordering.

**Scenario/reproduction:** disconnect normally; set only the disposable guest's system clock to 2020; connect the valid audit profile. The early HTTPS reachability/certificate check fails before chrony starts. The rollback closes the tunnel. Restore the guest clock and reconnect: success. No host clock or hardware RTC was changed. [Evidence](wrong-clock-result.json).

**Impact:** machines with a stale/dead RTC can remain unable to connect, synchronize time or start network apps even though their profile and network are valid. The firewall remained blocking; this is an availability/order defect rather than a leak.

**Smallest repair:** separate structural firewall/route/WireGuard validation from time-dependent HTTPS validation. Perform a bounded, tunnel-only clock bootstrap after the former, then the full TLS/DNS/IPv4/IPv6 readiness checks. Never fall back to off-tunnel NTP or disabled TLS verification.

**Regression:** past and future clocks, valid/invalid endpoints, unreachable time sources and interrupted synchronization. Confirm correct recovery, truthful UI state and zero nonapproved uplink traffic throughout. **Security tradeoff:** time repair must not become a general pre-VPN network exception.

### F-03 — High: all twelve offline roles reject edits to desktop-owned files in their own RAM folders

**Confidence:** high, policy matrix plus actual GUI failure.

**Affected:** `owner /mnt/ram/{,**} rwkl` in the twelve `petalos.offline-*` profiles, e.g. [Geany line 5](../../config/includes.chroot/etc/apparmor.d/petalos.offline-geany#L5); [compartments.grant](../../config/includes.chroot/usr/local/lib/portable/compartments.py#L276), per-role RAM binds.

**Scenario/reproduction:** create a regular file as Petal inside an offline application's own RAM Documents directory, then edit it as that application's distinct UID. ACL delegation permits the UID, but the AppArmor `owner` qualifier does not. All twelve tested roles could read and could not write that file. Equivalent delegated Private files were writable. [Matrix](ownership-matrix-result.json).

An actual Mousepad window opened a Petal-created file, accepted edits, and on Ctrl+S displayed a read-only/save-as warning; the original file remained unchanged. [GUI outcome](gui-editor-check-result.json). This is an intentional policy denial producing an unintended normal-workflow failure, not an application crash.

**Impact:** copying/creating files through Thunar or a terminal and then editing them in RAM is unreliable across the offline app set.

**Smallest repair:** permit writes to the exact delegated per-app RAM path independent of inode ownership, while retaining mount isolation and sibling-folder denial. Avoid granting write access to all of RAM or all of Private.

**Regression:** desktop-created, app-created, copied, renamed and atomically replaced files; actual GUI save/reopen in RAM and Private; sibling paths and unselected files must remain inaccessible. **Security risk:** a broad non-owner rule would unnecessarily increase access if a bind layout later changes.

### F-04 — Medium: new mode-0600 app files can be inaccessible to the desktop

**Confidence:** high for the access failure; the best interoperability design needs a separate decision.

**Affected:** [compartments.grant lines 294–299](../../config/includes.chroot/usr/local/lib/portable/compartments.py#L294), distinct application UIDs and default ACL inheritance.

**Reproduction:** create a mode-0600 synthetic file as an offline role in its delegated content folder, then read it as Petal. The read fails despite the directory's default named-user ACL. File mode/ACL mask restricts the inherited entry. [Evidence](offline-boundary-result.json).

**Impact:** a successfully saved/downloaded file may not be movable, previewable or openable through the desktop until permissions are refreshed. One-time recursive ACL updates at launch are not a lasting ownership contract. This is the opposite access direction from F-03.

**Smallest repair:** implement an explicit, narrow content handoff/ownership scheme that covers newly created and atomically replaced files. Evaluate a mediated file broker or mapped ownership; do not recursively make every Private file world-readable or share full home directories.

**Regression:** a real application creates mode-0600 content, then Thunar copies/moves it and a selected editor/player opens it; unrelated roles and parent directories remain denied. Include both RAM and Private and an atomic replacement after startup.

### F-05 — Medium: local torrent/NZB imports are not exposed when Private is closed

**Confidence:** high for Transmission; Pan shares the same faulty bind branch but its full import workflow was not separately exercised.

**Affected:** [compartments.import_items](../../config/includes.chroot/usr/local/lib/portable/compartments.py#L417), [sandbox imports bind](../../config/includes.chroot/usr/local/lib/portable/compartments.py#L625).

**Reproduction:** with Private closed, import a synthetic local `.torrent` through the production importer and inspect its returned path inside the actual Transmission sandbox. The bounded RAM import exists outside, but `/run/petalos-imports/...` is absent inside. That bind is created only inside the `available` (Private-open) branch. [Evidence](locked-import-result.json).

**Impact:** file-association imports fail in the intended fully functional RAM-only session. This does not invalidate the successful real webseed download with Private open.

**Smallest repair:** expose the already bounded, read-only imports directory for supported download roles regardless of Private availability, independently of Private state binds.

**Regression:** open valid torrent/NZB files through their desktop associations with Private closed/open; verify actual import/download outcome. Retain rejection of oversized files, symlinks, special files, unsupported URL schemes and injected flags.

### F-06 — High: OS updates are atomic per file, not across the bootable release

**Confidence:** high for code and isolated failure model; no physical card interruption was performed.

**Affected:** [update-card-release-root.py lines 147–163](../../tests/update-card-release-root.py#L147) and [201–206](../../tests/update-card-release-root.py#L201); kernel/initrd/root-image and GRUB update sequence.

**Reproduction:** extract the actual nested replacement function into a harmless regular-file fixture. Commit the new first payload, then fail the second source operation. The first stays new while subsequent payloads stay old. There is no generation-level rollback in the enclosing implementation. [Evidence](update-interruption-model.json).

**Impact:** power loss, removal or an I/O error can leave a mixed kernel/initrd/root release and an unbootable system. Preverified backups improve recoverability but do not make the update transactional. Current device/mapping identity checks and per-file readback are valuable and should remain.

**Smallest repair:** stage a complete versioned release, verify and durably sync it, then switch a small boot-generation selector while retaining a known-good generation. Provide a tested rollback/recovery path; account for FAT/filesystem power-loss semantics rather than assuming a rename alone is durable.

**Regression:** fault/termination after every payload and selector step on disposable images. Every resulting image must boot either the previous or new consistent release, or reach a clear recovery path. Hardware removal/power-loss validation remains necessary. **Compatibility cost:** this needs extra space and explicit module/old-release compatibility rules.

### F-07 — Medium: one slow launch blocks unrelated app actions and the progress window cannot be cancelled

**Confidence:** high for shared-lock behavior and code; a complete three-minute Tor timeout was not deliberately awaited.

**Affected:** [portable-compartment](../../config/includes.chroot/usr/local/sbin/portable-compartment#L49), [start readiness loop](../../config/includes.chroot/usr/local/lib/portable/compartments.py#L843), [portable-desktop](../../config/includes.chroot/usr/local/bin/portable-desktop#L81).

**Scenario:** Tor or another role is slow to become ready. The global broker lock is held through startup; unrelated launch/stop requests queue behind it. The GUI ignores its close event and waits for the command without an overall deadline. A bounded lock-contention test verifies unrelated requests wait and complete when the lock is released. [Evidence](broker-queue-result.json).

**Impact:** normal concurrent actions appear hung and cannot be dismissed. Repeated clicks can queue more requests. Existing `start()` has a 180-second readiness limit, but queued requests can wait longer; this report does not claim every individual startup is infinite.

**Smallest repair:** narrow locking to shared state transitions, add per-role serialization and bounded queue waits, and expose safe cancellation/error state. Cancellation must terminate and clean the corresponding worker, not merely hide the progress window.

**Regression:** delayed/failed Tor startup while an offline editor starts and another role stops; repeated clicks; cancel before/after worker creation; retry without stale grants or duplicate workers.

### F-08 — Low: the installed aMule retains the known connect-options bitmask defect

**Confidence:** high for the function defect and installed/candidate distinction; **not established as the cause of Kad's firewall status**.

**Affected:** upstream `CPrefs::GetMyConnectOptions`; [local candidate patch](../../local/amule-kad/connect-options.patch), [candidate builder](../../local/amule-kad/build.py).

The pinned upstream archive was freshly fetched and hash-verified. Compiling the actual original and patched function showed 131 failures among 512 input combinations in the original and zero in the patch. The installed executable matches the unpatched Debian package; the candidate's provenance explicitly says it is not integrated. [Function evidence](amule-bitmask-result.json), [hash-verified Debian patch review](amule-debian-patches.json). None of the six Debian patch files references the affected function.

**Impact:** incorrect advertised encryption/callback capability combinations; Kad's real inbound behavior depends on additional peer/provider conditions and was not requalified in this audit. Sam previously accepted Kad as low priority.

**Smallest repair:** if promoted later, package the tested patch with the maintained trixie aMule source and preserve existing features, update-disable policy and confinement. Do not silently substitute the diagnostic executable.

**Regression:** all 512 function combinations plus protocol capture, eD2k high-ID/download and Kad interoperability with an independently reachable peer. A corrected bitmask alone is not evidence of Kad high-ID.

### F-09 — Medium: Save Desktop Settings can report success before recent settings reach the archive

**Confidence:** high, reproduced with a real Xfconf change and reboot.

**Affected:** [portable-save-settings line 8](../../config/includes.chroot/usr/local/bin/portable-save-settings#L8), [desktop_settings.save](../../config/includes.chroot/usr/local/lib/portable/desktop_settings.py#L65), Xfconf's delayed XML persistence.

**Reproduction:** change `/Net/DoubleClickTime` through `xfconf-query`, immediately run the normal Save Desktop Settings action, then reboot. The action succeeded, but the archived XML lacked the changed property and the desktop returned to its default value 400. On repeat, the live value was 322 while the immediately saved archive still lacked it. After seven seconds the XML contained 322, and another save captured 322. [Reboot evidence](persistence-check-result.json), [timing evidence](desktop-settings-race-result.json).

**Impact:** recent supported desktop customizations can be lost despite a success notification. The archive format and restore operation can work; the snapshot was taken before the desktop daemon flushed its live state.

**Smallest repair:** export approved live Xfconf values, or request and await a verified daemon flush before archiving. Verify the saved values before success is reported. An arbitrary fixed sleep is not a robust synchronization contract.

**Regression:** change a supported setting and immediately save, including rapid consecutive changes and a busy desktop; reboot and verify the final value. Include archive-write failure and ensure the UI does not report success for an old snapshot.

## 6. Tests and observed outcomes

The evidence JSON files retain individual results. A fixture's exit 0 is not automatically a pass: several deliberately return measured false outcomes, notably the full-storage experiment.

| Area/workflow | Result and limit | Evidence |
|---|---|---|
| Artifact identity and source/runtime correspondence | Four release payload hashes verified; 265 configuration inputs and 99 runtime helpers match. | `release-verification.json`, `source-build-comparison.json`, `source-runtime-comparison.json` |
| LUKS/authentication | Correct credentials work; wrong/cross-purpose credentials fail; failed attempts leave Private closed; manual storage lock closes mapping; SYSTEM authentication does not reopen Private. | `audit-credentials-guest-result.json`, `baseline-result.json` |
| Storage policy | Fresh independent LUKS2 stores, one Argon2id slot each, no automatic DATA key; full SYSTEM read-only with selected writable state. RAM root and no swap observed. | `baseline-result.json` |
| Privileged paths | Passwordless general sudo/worker entry/invalid broker arguments denied; privileged polkit actions require authentication; Petal cannot open virtual disk/partitions/mappers for raw read or write. | `privilege-result.json` |
| Offline isolation | Tested role cannot create IPv4/IPv6 sockets, see raw disks, SYSTEM, host runtime/DBus/X11 or sibling content. Restricted Wayland registry lacks privileged capture/control protocols. | `offline-boundary-result.json` |
| App startup | Native windows/readiness for download apps, SAB/viewer and offline roles; inspect actual UIDs, capabilities, AppArmor and process state. Startup alone is not a complete app acceptance test. | `apps-start-result.json`, soak results |
| Atomic filesystem operations | Twelve offline profiles × nine selected atomic-save operations pass. This did not predict the later ENOSPC data-loss finding. | `offline-atomic-save-guest-result.json` |
| Editor GUI | Actual typing/Ctrl+S on Petal-owned RAM file produced read-only warning, unchanged original. | `gui-editor-check-result.json` |
| KeePassXC | Real CLI database create/reopen/update/readback pass in RAM and Private; full-storage loss reproduced separately. | `keepass-save-guest-result.json`, `keepass-private-result.json`, `full-storage-detail-result.json` |
| Selected file delegation | Read-only pinned source, neighbour hiding, leaf symlink/special-file rejection, rename stability and restricted 0600 handoff pass. | `offline-file-handoff-guest-result.json` |
| Transmission download | Actual GTK client completed a 1,198-byte public Debian README webseed torrent into Private; exact SHA-256 matched. Test download/settings were removed/restored. | `transmission-download-result.json` |
| Media | Actual Parole played a generated moving test video through normal selected-file delegation; successive frames changed. Separate 1080p30 native A/V pipeline under the role used GstPulseSinkClock, reached EOS in 21.034 s, rendered 589 frames and reported 6 drops. This measures integration/timing, not human-verified speaker output or a universal codec guarantee. | `media-start-result.json`, `av-pipeline-result.json` |
| Tor browser | Actual browser visibly loaded check.torproject.org successfully; actual browser network namespace rejects direct IPv4/IPv6, SOCKS path reaches Tor API; nine control-bridge authorization checks pass. | `tor-window-result.json`, `tor-netns-result.json`, `tor-control-guest-result.json` |
| SAB bridge | Actual HTTP response through correct role; wrong UID/substituted backend rejected before request bytes sent. No Usenet account supplied, so download completion untested. | `sab-bridge-guest-result.json` |
| VPN/DNS/recovery | Dedicated profile connects and current clock gate passes; tunnel loss blocks despite cached success; repeated disconnect, reconnect and same-profile switch recover; DNS failure blocks and restoration recovers without reboot. | `audit-connect-guest-result.json`, `network-failures-result.json` |
| Interrupted connection | Terminated after interface creation: failure reported, tunnel and runtime key file removed, subsequent connect succeeds. | `interrupted-connect-result.json` |
| Uplink observations | During bounded failure transitions, observed outgoing traffic was WireGuard transport, DHCP and ARP; no unexpected IP packets. This is not an all-time/global leak proof. | `network-failures-result.json` |
| Incorrect clock | Reproducible connect failure before chrony; restoring time allows reconnect. | `wrong-clock-result.json` |
| Settings and parser regressions | Nine selected existing regression suites rerun, including malicious archive entries, history exclusion, malformed VPN input and GUI/retry paths; all exit 0. Their mock/unit scope is separate from runtime outcomes. | `reviewed-regressions.json` |
| Resource exhaustion | Isolated 2 MiB ENOSPC test caused F-01; no whole-system OOM or deliberate physical-storage exhaustion. | `full-storage-detail-result.json` |
| Contention | Two unrelated launches wait behind the same broker lock and resume on release. | `broker-queue-result.json` |
| Update interruption | Actual replacement function leaves mixed generations under injected second-operation failure; regular-file model only. | `update-interruption-model.json` |
| Offline cold boot | Virtual NIC disabled before first CPU instruction; desktop and SYSTEM state ready, Private closed, offline editor usable, network app blocked. Enabling link and normal VPN connect restored network readiness without reboot. | `offline-launch.json`, `offline-boot-result.json`, `audit-connect-guest-result.json` |
| Ethernet MAC/DHCP | Two reconnects produced distinct locally administered unicast MACs; six outgoing DHCP packets had no hostname and used the randomized MAC as client ID. Firewall unchanged. Wi-Fi hardware still untested. | `hardening-mac-guest-result.json` |
| GUI idle/manual locking | Real Wayland idle notification closed Private; download mode inhibited idle only; manual lock overrode it; wrong screen password rejected; SYSTEM screen unlock left Private closed. | `lock-start-result.json`, `manual-lock-result.json`, `wrong-screen-password-result.json` |
| Reboot persistence | RAM canary absent; Private canary retained; approved numeric preference restored into an actual RAM-mode Transmission launch. Immediate desktop-settings save failed; settled/resaved snapshot tested on subsequent boot. | `persistence-check-result.json`, `persistence-app-restore-result.json`, `desktop-settings-race-result.json` |
| Shutdown/printing | Local session policy grants normal shutdown but not privileged overrides; normal XFCE session request powered QEMU off. Manual CUPS start/stop works, Unix socket only, remasked afterwards; no real printer test. | `shutdown-policy-guest-result.json`, `desktop-poweroff-result.json`, `audit-smoke-guest-result.json` |
| Dependency state | Actual installed inventory, Debian source/backport comparison, signed APT refresh over tunnel; zero offered upgrades. | `packages.json`, `tracker-source.json`, `package-state-result.json` |

Cold boot, sustained load, GUI idle/manual lock and reboot-persistence outcomes are detailed in the final verification appendix below.

## 7. Suspected issues and uncompleted validation

### S-01 — High-impact boot-chain authentication concern; dynamic validation incomplete

**Confidence:** high in the observed external-initrd layout; medium in the proposed complete attack path. **Arbitrary altered initrd code execution was not demonstrated.** Treat the attack scenario as needing validation, not a confirmed exploit.

**Affected:** [boot provisioning](../../tests/provision-audit-root.py#L174), [EFI repair](../../tests/repair-card-efi-root.py), [initramfs unlock hook](../../config/includes.chroot/etc/initramfs-tools/scripts/init-premount/portable-unlock#L16), external `grub.cfg`/`live/initrd.img`; module selection and root-image integrity are related trust-chain gaps.

**Scenario:** an attacker can alter the removable boot medium before it is booted. The reviewed configuration loads an external initrd and has no configured verification of that initrd or a signed root/module manifest. If an attacker can substitute executable initrd content, it runs before SYSTEM unlock and could capture a later passphrase or alter the live environment. The attacker need not decrypt Private merely to modify the boot partition. This is distinct from breaking LUKS cryptography.

**Attempted reproduction and result:** only on the disposable guest's virtual `PORT_BOOT`, preserve/hash the original initrd and append a harmless cpio marker. The first new script was not included in initramfs's ordered script list; a second probe targeted an existing ordered hook. Both marker checks were negative. A final check found an initramfs unpacking error in the current boot's kernel journal, so the archive concatenation method did not establish execution. Secure Boot remained enabled and the desktop booted. The original initrd was restored after each trial. [Ordered fixture](../../tests/phase15-20261018/boot-proof-ordered-stage.py), [restoration](boot-proof-restore-result.json), [kernel-journal diagnosis](boot-marker-journal-result.json).

**Required validation:** correctly unpack and repack the initrd, validate the resulting archive before boot, and repeat the harmless marker test on another disposable image. This bounded pass stopped rather than repeatedly modifying boot media until a desired result appeared. The negative marker is not evidence that external initrd authentication exists; equally, booting with trailing bytes is not proof of arbitrary code execution.

**Potential impact:** firmware reporting Secure Boot enabled is insufficient by itself to establish a trusted PetalOS session. Encryption-at-rest does not authenticate this pre-unlock code. Signed kernel enforcement remains useful but covers only part of the chain.

**Repair direction if the gap is confirmed:** define and enforce a complete authenticated boot policy, for example a signed UKI containing the kernel/initrd/command line, combined with authenticated root/module manifests or a suitable verity arrangement. Prevent bypass through an unrestricted alternate GRUB path and address rollback. Simply hashing files during installation or disabling the rescue prompt does not close the gap.

**Regression:** mutate initrd, command line, module selection and one root/module byte independently; each must be rejected before accepting secrets or executing altered content. Legitimate upgrades and recovery must still work. **Compatibility risk:** signing/key enrollment and recovery design can prevent otherwise supported machines from booting; validate the ThinkPad separately.

The remaining items below are follow-ups, **not confirmed vulnerabilities**:

1. **Resource containment:** production app workers do not have explicit per-role memory/PID/temporary-storage budgets. Separate UIDs, namespaces and AppArmor do not prevent a runaway authorized app from consuming shared RAM. The bounded load test is not a full OOM/fork-bomb test. Add measured budgets only after validating large downloads, video and office documents.
2. **Privileged bridge connection pressure:** several local bridges use thread-based request handling. Per-request limits exist, but exhaustive concurrent/slow-client resource testing was not completed. No remote code execution or bypass was demonstrated.
3. **IPv6-only physical uplink:** the approved VPN endpoint parser accepts IPv6, while physical-link neighbour discovery/router configuration deserves a dedicated IPv6-only underlay test. Working IPv6 *inside* WireGuard does not establish IPv6-only underlay support.
4. **Long-held storage operation:** nonblocking storage locks reject contention rather than racing; the UI/retry experience across concurrent authentication/lock/unlock was not exhaustively exercised. Intentional force-poweroff on failed Private closure is a separate design tradeoff below.
5. **Broader document/media libraries:** the dependency scan flags additional kernel, FFmpeg, libxml2, Poppler, CUPS and glibc records. Their entire application-feature reachability matrix was not resolved in this bounded pass. No raw count is a release severity score.
6. **Reproducibility:** source/binary hashes and provenance agree where checked, but no clean two-build reproducibility comparison was performed. The aMule resume guard hashes the patch and one corrected source file, not the entire resumed tree. Native Parole/Conky hooks install pinned prebuilt binaries; full compiler/dependency/environment provenance needs strengthening before claiming reproducibility.
7. **GUI database full-storage behavior:** F-01 is proven in CLI with the built libraries. The GUI save mode must be exercised before deciding whether it shares the same failure.

## 8. Deliberate tradeoffs and optional improvements

- **Private closure versus availability:** the lock path kills users of Private and can force poweroff if closure fails or exceeds its watchdog. This can lose unsaved work and interrupt filesystem operations. It reflects the explicit priority given to closing Private; it is not automatically a bug. Test corrupted/busy-filesystem recovery before release and explain this behavior in the manual.
- **Selected persistence is still persistence:** VPN profiles, panel launchers, preferences and server endpoint lists can identify configuration choices. A sanitized `server.met` removes tags/history but the chosen endpoints still reveal a user's configured service set. Desktop launchers can contain commands/paths intentionally chosen by the trusted desktop user. Do not market SYSTEM as containing no information about use.
- **Private is not hidden:** separate credentials and locked mappings provide separation; visible LUKS headers/partition layout do not provide plausible deniability. A compromised running root/kernel can observe subsequently entered credentials.
- **RAM-only is not forensic-proof:** swap prevention, volatile logs and `init_on_alloc=1 init_on_free=1` are useful mitigations. They do not establish resistance to cold-boot, DMA, firmware/pstore, compromised hypervisor or powered-memory acquisition.
- **Trusted desktop versus restricted apps:** Petal, compositor, file manager, panel and administrator helpers remain trusted components. Restrictions on an offline role do not apply to arbitrary software deliberately run as the desktop user or administrator.
- **Static app mounts:** an app started while Private is closed does not acquire a new Private bind merely because storage opens later. Restart/explicit regrant is required. Improve messaging before adding dynamic access grants; broad automatic access would change the security model.
- **Second-file launch behavior:** most already-running roles reject another selected item and tell the user to close the existing compartment. Parole has an explicit replacement path. This is a compatibility restriction, not a privilege flaw; safe existing-instance file handoff is an optional improvement.
- **Offline printing:** manual CUPS startup is intentionally local and session-only. Sandbox `/run` hiding means application-to-CUPS integration still needs an explicit tested design; a running service alone does not prove a sandboxed document can print. Do not enable LAN discovery as a shortcut.
- **Audit access is a module:** the audit guest has an additional pinned vsock SSH management layer; it is not an inherent property of a retail image. Remove development access/keys/modules from a production acceptance image and retest without them.
- **Error messages:** several launch failures collapse distinct causes into generic Private/VPN/confinement wording. A bounded, secret-free stage/error category would improve recovery without revealing raw application output.

## 9. Coverage limits and hardware follow-up

This pass did not test physical SD updates/removal, real disk rollback, actual ThinkPad sleep/lid/GPU recovery, Wi-Fi rfkill re-enable, wireless scanning/MAC behavior on that radio, brightness/audio hardware, USB printer output, USB/VeraCrypt modal stacking, firmware key enrollment/revocation, TPM/attestation, DMA or cold-boot memory recovery. None of the earlier hardware success reports substitutes for those checks on this exact build.

No personal databases, files, keys or backups were opened. Recovery from historical encrypted backups and retirement of older key slots/headers were not performed. The fresh audit image's independent keys do not establish that every older physical medium has the same layout.

No real Usenet server was available: Pan/SAB startup and bridge boundaries were tested, not authenticated Usenet transfers. Provider-side port forwarding and external Kad reachability were not requalified. The successful Transmission transfer was a small controlled webseed transfer, not a many-hour swarm/resume test.

The test app set was broader than the end-to-end workflows. LazPaint, LibreOffice, Atril, gThumb, Ristretto, Quod Libet and Vim received startup/policy/atomic-file checks, not every native format, plugin, export, printing and large-document operation. Real audio speaker perception was not independently confirmed by a human in this pass.

APT/installed-version review is not a complete exploit audit of 1,605 packages. Some tracker records lack enough information for applicability decisions; kernel configuration/module reachability and every media parser were not exhaustively mapped. No kernel exploit, whole-system exhaustion or unrelated network target scanning was attempted.

## 10. Proposed repair order and release gate

1. **Contain and fix demonstrated data loss (F-01)**; establish GUI scope and regression coverage before entrusting password databases to the build.
2. **Resolve the authenticated boot/recovery question (S-01)** with a correctly repacked negative test, then implement any missing enforcement before production acceptance. Do not treat the inconclusive marker test as either an exploit or a clean bill of health.
3. **Repair normal file interoperability (F-03/F-04/F-05)** with narrow delegation, then repeat real editor, database, media and download handoffs in RAM and Private.
4. **Fix settings snapshot synchronization (F-09) and time/bootstrap ordering (F-02)** and repeat negative egress/DNS tests with past/future clocks and no uplink.
5. **Make release updates recoverable as a unit (F-06)**, preserving device guards and independently verified backups.
6. **Address reachable package issues (S-02)** with reviewed trixie patches; resolve remaining dependency applicability before release acceptance. Keep package provenance and normal app compatibility checks together.
7. **Improve bounded concurrent actions/cancellation (F-07)**; retain per-role boundaries. Kad's bitmask candidate remains low priority (F-08), consistent with Sam's stated preference.
8. Run a focused post-fix regression pass and exact-build hardware acceptance, then freeze the phase-one baseline. Branding may proceed independently, but must not be used as a substitute for these gates.

No fixes, policy weakening, real credential changes or physical-media updates are authorized by this report. A later repair pass should use separate reviewable changes and recheck both security and usability for each.

## 11. Final verification appendix

- **Sustained load:** the corrected ten-minute run kept four bounded hash/memory workers alive, each with a 128 MiB working buffer, alongside all 19 application roles. All roles remained alive; minimum available RAM was 10,513 MiB. `/run` usage stayed at 9 MiB in the samples. No sampled OOM, killed-process, I/O-error, segfault or kernel-BUG messages; no failed services. Journal storage was 8 MiB. This is a moderate bounded workload, not maximum-capacity or long-duration certification. [Full samples and counts](soak-final-result.json).
- **First load harness:** an earlier worker expression temporarily made extra buffer copies and exceeded its own address-space limit. Those workers exited; the 15-minute app observation still completed, but it is not counted as a 15-minute stress pass. The corrected run above had four live workers in every sample and reaped them at completion.
- **Locking:** an actual three-second test Wayland idle notifier invoked the production idle-lock action; the normal ten-minute production timeout was not edited. Download mode inhibited that event, turning it off permitted Private closure/graphical locking, and manual locking overrode download mode. SYSTEM unlock left Private closed; an intentionally wrong GUI screen password left the locker running. The first manual-lock harness captured pipes inherited by the locker daemon and timed out waiting for EOF, although locking completed. Retesting with ordinary detached/DEVNULL streams passed. This was a harness issue, not evidence of a stuck locker.
- **Offline boot/recovery:** QMP held vCPUs paused, disabled the NIC link, then resumed boot. The full desktop and encrypted SYSTEM state became available; Private stayed closed, a native offline editor launched, and a network application was denied. Restoring the same NIC link, exercising Ethernet reconnect/MAC checks and connecting the normal audit VPN recovered without reboot. No network device, firewall exception or production policy was substituted.
- **Persistence:** the RAM canary vanished, the Private canary survived, and Transmission used the saved approved preference during an actual RAM-mode launch with Private closed. The immediate desktop save lost the changed value (F-09). Waiting for the daemon's XML write and resaving captured the setting; a second cold boot restored that value. [Final runtime evidence](final-runtime-result.json).
- **Boot authentication probe:** neither appended-cpio marker executed. The current boot's journal contains an initramfs unpacking error; both dmesg and the kernel journal retain early boot messages but lack the marker. Thus this is an inconclusive injection method, not a proven bypass and not evidence of initrd authentication. The report deliberately retains S-01 as a validation concern. The original public initrd was restored, and after poweroff a separate read-only FAT32 traversal of the virtual disk recomputed its exact release SHA-256. [Readback and cleanup](final-cleanup.json).
- **Shutdown:** normal XFCE session poweroff completed on the observed shutdown cycles. Policy queries showed local desktop permission for ordinary shutdown/suspend, while remote/sandbox identities and privileged ignore-inhibitor operations still require authentication. Hardware sleep/lid recovery was not inferred from this.
- **Other harness corrections:** an early network fixture incorrectly treated bringing a WireGuard link up as full route recovery; the corrected test uses the normal disconnect/reconnect operation before proceeding. A readiness poll attempted to inspect a root-only path as Petal and was replaced with an observable compositor check. A source-preservation comparison initially used symlink mode instead of target mode; matching the original manifest's method confirms no changes. These were not counted as OS defects.
- **Final state:** audit VM off; QMP/serial sockets and relay gone; image not in use; original initrd restored and independently read back; Private was closed before shutdown. Production files, original instructions and existing work remain unchanged. [413-file preservation check](source-preservation.json). New audit reports/tests and synthetic state in the disposable image are the only retained work products.

The bounded pass ends here. There are no pending background stress workers or planned automatic repairs.


Audit report finalized: 2026-10-18T18:10:20+00:00.
