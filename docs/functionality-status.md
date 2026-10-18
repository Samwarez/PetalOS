> Historical checkpoint from October 12. Several storage and authentication details below have since changed. For the current storage layout, see [storage-layout.md](storage-layout.md); for current QEMU results, see [stability-pass-20261015.md](stability-pass-20261015.md).

# Functionality status — deployed release and current test VM

The combined batch is deployed from release 20261012-134354-535797; its
completed release and encrypted test-disk updates are recorded below.
The current QEMU clone also has test-only pinned SSH management. Real-provider
IPv4 and IPv6 now work using selected Stockholm profile `sto63-adb`, including
the built-in IPv6 checker and disconnect/reconnect verification. Zurich IPv6
fails with two keys; Stockholm works with the same key/IPv6 assignment as the
new Zurich profile, pointing to the Zurich endpoint/server path. No physical
microSD changes were made. Earlier staging and verification notes are retained
below; later dated results supersede their pending deployment/test statements.

## Working in the existing release

Encrypted boot and automatic Private unlock, selective desktop settings
save/restore, fresh panel defaults and helper group, actual-provider IPv4 VPN
and clock synchronization, provider-independent IPv4 exit reporting, signed
Tor archive launch, and fresh-session Tor auto-connect were user-tested.
Prior working encrypted clones remain preserved.

## Included functionality

- Encrypted WireGuard profiles and graphical Add/Connect/Switch/Disconnect,
  with transactional endpoint sets, profile DNS and saved selection. See
  vpn-profiles.md. Numeric endpoints are the deliberate policy; hostname
  resolution and VPN port-forwarding automation are out of scope.
- Graphical progress/authentication/errors for Private, Tor, Exit IP, Save
  Settings and SAB start/stop. These helper desktop entries use
  portable-desktop and Terminal=false. Backend output is discarded rather
  than shown or logged. Transmission, Pan and aMule also have graphical
  preparation/error paths, retaining encrypted state, file associations and
  the aMule lifetime lock. File arguments cannot override state paths via flags.
- Private recovery uses a GTK password prompt as the desktop user, with
  accepted response bytes passed only through process pipes into cryptsetup.
  Cancelled/failed dialogs never invoke cryptsetup. The normal system-volume
  key path is retained, with passphrase fallback if it fails. No data unlock
  key is copied into the live image or browser/persistence inputs.
- Manual Tor archive installation with detached-signature verification
  against the baked public keyring. A verified copy is stored under
  Private/Applications/TorBrowser/Versions; selection is replaced atomically
  after verifying the installed pair. Earlier versions and the legacy archive
  remain. Installation changes the next fresh RAM session, not a running
  browser. Profile/history files never enter this store.
- Tor's RAM distribution receives DisableAppUpdate=true in its policies.json,
  merged with existing policies. The signed 15.0.24 Policies.sys.mjs contains
  the supported handler. Actual browser policy activation still needs
  about:policies verification in the rebuilt VM. This policy controls browser
  application updates; extension update behavior was not changed.
- Optional IPv6 exit check uses api6.ipify.org, explicitly bound to wg0 with
  proxies disabled and bounded timeouts, after the current VPN guard passes.
  Its separate RAM result is historical display data, not authorization. IPv4
  remains usable if this optional check fails. Check VPN IPv6 and Install Tor
  Archive are added to fresh panel helper defaults.
- SAB wrapper now execs the backend directly, making it the service process.
  Two real start/stop cycles completed without service timeouts in the fixture.

## Completed verification

- 44 networking checks in a diskless guest passed using current source in a
  RAM overlay: real simulated-provider WireGuard, two peers/endpoints/ports,
  switch failure/recovery, IPv4 and IPv6 HTTPS through both profiles, blocked
  transport and missing-route recovery, disconnect/repeat disconnect, direct
  traffic rejection, and unchanged disconnected firewall. The direct IPv6
  fixture has uplink addresses, routes and static neighbours, so it does not
  rely solely on an absent physical IPv6 path. No external NIC is attached.
- 25 app/recovery checks in a separate diskless fixture passed: real SAB
  backend and Unix administration bridge, loopback-only listener, restart
  persistence in mapped DATA, RAM logs, offline network/bus rejection and
  dropped capabilities, permitted Home/Private writes, selective settings
  save/restore, actual disposable LUKS rejection of cancellation/wrong
  passphrase, successful recovery and mount identity/ownership. The GTK
  recovery dialog was replaced by a test-only response shim in that guest;
  its actual widgets/response handling were tested separately.
- 25 invisible GTK helper groups passed: hidden/accepted/cancelled password
  response formatting, mocked cryptsetup routing/cancellation, and success/
  failure for ten actions, immediate aMule start failure and safe file-association
  arguments. No real host sudo, storage or networking
  occurs in these GUI tests.
- Tor signature-gate tests passed with real gpgv: valid, invalid and missing
  signatures, one-time quickstart seed, retained recovery flag, prepare-only
  mode and update-policy JSON generation. A stub browser is used.
- 4 real-signature archive-maintenance groups passed: valid installation,
  failed signature preserving the old selection, retained previous version,
  symlink refusal and path-traversal refusal. Public signed software only.
- 3 invisible Tor installer GUI cases passed: cancellation, success and
  failed verification with a mocked installer.
- 12 IPv4/IPv6 exit-report cases passed, including wrong-family/private/
  malformed answers, failed guard and timeout with stale-result removal.
- SAB viewer navigation handlers passed local-only navigation, popup and
  permission rejection tests. The live bridge test exercises HTTP access
  inside the offline namespace; actual WebKit rendering is not yet tested.
- Transmission, Pan and aMule preparation tests passed with stubbed guards
  and native clients: configuration defaults, preservation of user overrides,
  failed-guard refusal and prepare-only behavior. Actual native client GUI
  rendering/downloads remain outside those tests.
- Staged inputs passed the existing obvious-secret/trixie validation; no
  rebuild was launched. This validation is not a comprehensive secrets audit.

The app fixture initially exposed a 45-second test bound shorter than the
service's 60-second stop bound, and an absent DATA label needed by restore.
The stop checks now allow 70 seconds and additionally require service
Result=success. The wrapper was changed to exec, and the corrected fixture
supplies its verified RAM-loop label. All app/recovery checks then passed.
The expanded IPv6 fixture also needed to restore its removed uplink address
after deliberate link-down; corrected networking checks all passed.

## Remaining acceptance work

When Sam authorizes a combined build, verify the embedded artifacts and
boot a preserved clone. Seed only the two selected VPN profiles with the
prepared coordinator, then test real-provider switching and selected-profile
restoration. Test actual helper windows, sudo authorization and password
cancellation; confirm Tor about:policies lists DisableAppUpdate as active,
and manually install/reboot into a signed archive while retaining the previous
version. Confirm fresh helper defaults and persisted overrides.

Real provider IPv6 Internet connectivity remains unresolved. Both selected
profiles have non-global IPv6 interface addresses, which can work only with
appropriate provider routing/NAT; this is not evidence of a local defect.
The isolated dual-stack tests do not establish provider support. The new
optional IPv6 probe will distinguish it in the next desktop test. No firewall
or routing workaround was added to force public IPv6 connectivity.

SAB's local backend is verified, but real Usenet credentials/downloads and
WebKit GUI rendering still need the user's VM/account setup. Broader native
Transmission/Pan/aMule GUI/persistence tests, optional MAC randomization and
branding remain separate work. Physical Secure Boot smoke testing and a
physical-card update still require their own explicitly authorized stage.

References:
- https://firefox-admin-docs.mozilla.org/reference/policies/disableappupdate/
- https://support.torproject.org/tor-browser/getting-started/verifying-tor-browser/
- https://www.ipify.org/ (IPv6-only API is api6.ipify.org.)

Sam authorized the next combined build on 2026-10-12. The cached-package
coordinator was launched in a separate terminal. Artifact verification and
preserved-clone deployment remain pending build completion.

Combined release 20261012-134354-535797 is building. Initial cache seeding
failed on unreadable root-owned bootstrap archives before lb config/build;
that incomplete staging directory is preserved. Cache reuse now skips
unreadable archives and falls back to older releases per cache category.
The restarted coordinator passed authentication and entered the build stage.

Combined release 20261012-134354-535797 completed successfully. All four
manifest hashes were rechecked, along with 27 embedded staged helper/config
files and desktop entries. All 44 networking and 25 app/recovery assertions
passed against the actual ISO, without source overlays. The two selected
profile payloads were revalidated without displaying them. A separate
terminal was opened for sequential preserved-clone SYSTEM update and DATA
profile provisioning. Desktop acceptance remains pending.

SYSTEM update completed on encrypted-boot-20261012-141636-015384.img.
Initial profile provisioning failed because its installer treated the shared
transaction stat_result owner argument as an integer. Host loop/mapping
checks were clear afterward; failed clone is preserved and unselected.
Corrected the transfer helper to use st_uid/st_gid, and tested its complete
installer callback with a real stat_result and synthetic RAM-only profiles.
Two mode-600 profile files and the selected marker verified. Retrying the
DATA-only transfer into a new clone requires the test DATA password again;
the built image does not need another build.

Corrected profile provisioning completed on clone
encrypted-boot-20261012-142245-778644.img, release 20261012-134354-535797.
Coordinator recorded complete; host loop list was empty and updater/data
mappers absent before relaunch. Earlier working, SYSTEM-only and failed
transfer candidates remain preserved. Desktop acceptance is now pending.

Sam reports the new desktop flow and working zrh43 profile behaved as
expected. The got82 profile was intentionally altered due to provider profile
limits and was expected to fail; do not count that refusal as a switching
defect or assert successful real-provider switching to got82. Optional IPv6
check failed on the working profile; Sam confirms provider IPv6 support.
Requested a bounded wg0-bound curl error from the guest to distinguish
resolution, routing, connection, TLS and response-validation failures.
Provider IPv6 remains unresolved; firewall unchanged.


## QEMU SSH management — 2026-10-12

Sam approved vsock SSH instead of ordinary TCP host forwarding, because the existing guest firewall drops new inbound SSH on the physical interface. The corrected preserved encrypted clone boots to the desktop. Real SSH verified separate stdout/stderr and exit code 7, rejected an unrelated key and root login, and works while WireGuard is disconnected. Host port 2222 and guest TCP port 22 bind only to loopback; no firewall exception was added. Active nftables input/output/forward policies remain drop, and the configuration hash matches production source. Dedicated host key stays outside project inputs; server key resides outside squashfs in encrypted test SYSTEM and matches its pre-provisioned host pin. See docs/qemu-ssh.md and tests/guest-ssh.py for future direct diagnostics. Provider IPv6 remains unresolved; no VPN profile or routing changes were made for SSH.


## Real-provider IPv6 diagnosis — 2026-10-12

Direct SSH diagnosis confirms correct IPv6 address/routing/AllowedIPs, matching selected profile fields, and successful IPv4 after reconnect. IPv6 HTTPS to independent providers, ICMP, and tunnel-bound UDP DNS fail. Packet header counters show small IPv6 SYNs leaving wg0 and corresponding encrypted datagrams leaving the guest, but no IPv6 replies. Sam confirmed account IPv6 enabled. Firewall drop policies were preserved; no speculative MTU/firewall/routing changes were made. A fresh profile using an existing provider key slot, or another known-valid profile, is requested to distinguish assignment and server-path failures. Actual IPv6 remains unresolved; see docs/ipv6-diagnosis-20261012.md.


## Real-provider IPv6 working — Stockholm, 2026-10-12

Imported the two explicitly selected new profiles over pinned SSH into encrypted Private without a build or VM shutdown. Fresh-key Zurich still fails IPv6. Stockholm profile sto63-adb uses the same client key and assigned IPv6 address as fresh Zurich, and passes real IPv4/IPv6 HTTPS. The actual IPv6 exit helper succeeds and independent Cloudflare IPv6 HTTPS returns HTTP 200. Disconnect retained all drop policies and empty endpoint sets; a bounded direct IPv6 attempt failed. Reconnect used the saved Stockholm selection and restored verified VPN, synchronized clock and a successful IPv6 helper result. VM left connected to Stockholm, prior profiles preserved. This resolves the earlier real-provider IPv6 blocker for Stockholm and strongly points to the Zurich endpoint/server path as the remaining provider-specific failure. See docs/ipv6-diagnosis-20261012.md.


## Hardening staged and live-tested — 2026-10-12

MAC randomization was absent for connected interfaces; new Ethernet/Wi-Fi defaults are staged and applied in guest RAM. Real Ethernet/DHCP tests passed on two reconnects, including no advertised hostname and matching randomized client ID. Background system Tor, mDNS and printing/discovery services were stopped/masked; the QEMU test-only SSH service remains. Kernel tracing/pointer/redirect controls, discarded core dumps and bounded volatile journaling are staged and live-tested. Offline isolation, actual IPv4/IPv6 exit helpers, time synchronization and signed Tor preparation still work after uplink changes. No new build was started; live hardening disappears at reboot until baked into an authorized build. Major remaining gaps are unrestricted live-user passwordless sudo and unloaded AppArmor profiles (the vendor loader explicitly skips live overlay). See docs/hardening-review-20261012.md for evidence, physical Wi-Fi/DHCPv6 limitations and prioritized remaining work.

2026-10-12 staged AppArmor: portable Firefox/Tor and offline/SAB-viewer policies
passed live-QEMU positive and negative checks, including an actual Tor exit
confirmation. These changes remain in guest RAM and source until the next
build; fresh-boot activation is pending. See [coverage and evidence](apparmor.md).

2026-10-12 fresh boot follow-up: a preserved encrypted clone with a small public
OS configuration layer booted successfully as Petal/UID1000. Private unlocked
and Sam confirmed his saved panel restored. Password-required sudo, rejected
wrong password, boot hardening and both AppArmor acceptance sets passed. VPN
reconnected and clock synchronized. Production rebuild remains pending; this
verification used the existing completed release plus the public test layer.

2026-10-12 Tor launch follow-up: routine Tor startup now uses one narrowly
restricted, active VPN/clock check without a password prompt. General sudo
remains authenticated. Positive, disconnected-VPN, unavailable-clock and
transaction-in-progress cases passed in QEMU; actual graphical launch passed
with sudo's cache cleared. This follow-up is currently in source and guest RAM,
awaiting inclusion in the next image. See [Tor readiness](tor-readiness.md).

2026-10-12 naming stage: running VM hostname and displayed distribution are
PetalOS. Login banners/local guide and next-build ISO/boot labels are branded.
Package compatibility/upstream attribution remain accurate. Source validation,
local-name resolution and Tor readiness passed; generated boot-label fixtures
retained all boot commands. These changes await the next image for reboot
persistence. See [branding scope](branding.md).

2026-10-12 native app acceptance: Sam confirms Transmission/Pan/aMule main
windows usable. Actual Transmission completed an official Debian netinst;
all pieces verified against the fetched torrent metadata. Native preference
restarts passed for Transmission/Pan/aMule/SAB; original test preferences
restored and clients stopped. Sam confirms Tor DisableAppUpdate=true active.
Actual signed install/selection and rejected-signature preservation passed;
prior archive retained. SAB/Pan external downloads need Usenet account setup,
which Sam confirms is not configured. See [native app evidence](app-acceptance-20261012.md).
A combined rebuild was authorized and launched, with public cached packages
reused and new artifact checks. Fresh rebuilt-image verification remains next.
