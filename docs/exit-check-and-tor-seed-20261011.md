# Exit-IP semantics and persistent Tor seed — 2026-10-11

Sam observed public exit IPv4 152.89.162.5 through the dedicated test VPN;
the previous checker warned only because it hardcoded 152.89.162.7.
The checker now accepts any global IPv4 observed through a proxy-disabled,
bounded HTTPS request bound to wg0 after the live VPN guard succeeds. It
records only address, interface and timestamp in RAM. Failure clears the
old record. Status labels this as a historical observation, never current
connection authorization. No subnet or country restriction is imposed.

The guard now also requires a regular, non-symlink root-owned mode-600
runtime config, exactly one configured peer matching the live interface,
and a positive handshake for that peer after successful active HTTPS.
No private key is emitted. Firewall configuration was not changed.

No non-VPN guest request or firewall exception was introduced. A separately
obtained host baseline could be an informational comparison, but a changed
IP or country alone cannot establish tunnel use. Geolocation is approximate,
and VPN server location need not differ from the underlying access location.
No host public-IP or geolocation request was made for this feature.

Validation: 22 diskless mocked QEMU assertions, all 26 isolated live-guest
WireGuard/nftables assertions, and six exit-check assertions passed. Exit
cases include .5 and .7, non-public/malformed replies, guard refusal and
timeout with stale-record clearing. The live fixture used source scripts in
guest RAM on the prior ISO; it does not establish deployment in a new release.

Sam selected the existing Tor 15.0.24 archive and detached signature from
Downloads. They were reverified with the official Tor Developers signing
identity EF6E286DDA85EA2A4BA7DE684E2C6E8793298290. A public-only signing keyring
is staged in build inputs. The signed archive/signature are cached outside
build inputs at `/home/sam/portable-live/provisioning/TorBrowser` for repeatable
offline seeding. No browsing profile or personal file is seeded.

`tests/provision-tor-root.py` reused the checked encrypted DATA transaction
from VPN provisioning. After Sam shut down QEMU, `tests/prepare-tor-test.py`
preserved the previous disk and created/provisioned a new clone:

`testing/sessions/20261011-184902-563580/encrypted-boot-20261011-203001-332009.img`

Only encrypted DATA was opened. Exactly one signed archive/signature pair
was installed at Private/Applications/TorBrowser, hashes/signature rechecked,
and all host mounts/mappings closed. Source profiles and the system unlock
key were not accessed. The prior disk preserves the working VPN/profile state.
The VM was relaunched as Sam, without an ISO, for Tor testing.

The staged Tor wrapper requires that signature and the baked public keyring
before fresh RAM extraction. Three signature-gate tests passed: valid,
invalid and missing signatures, using the real signed archive and a stub
browser that makes no network requests. Browser working/profile paths remain
in RAM. Startup auto-connect and update behavior were not changed or retested.

A fresh isolated live-build was launched containing these changes and the
previously staged desktop defaults. Build/deployment and actual Tor operation
are pending. The already running release still has the earlier exit checker
and Tor wrapper. No physical-card changes were made.

Reference documentation: https://support.maxmind.com/knowledge-base/articles/maxmind-geolocation-accuracy
and https://support.torproject.org/tor-browser/getting-started/verifying-tor-browser/.

Sam reports that the provisioned browser opens the Connect to Tor screen.
This verifies launch, not Tor connectivity; the manual Connect/check test is pending.
Inspection of the signed 15.0.24 archive, Browser/omni.ja modules/TorConnect.sys.mjs
lines 943–950, confirms quickstart also requires
extensions.torlauncher.prompt_at_startup=false. Its fallback is true.
The existing quickstart preference alone therefore does not enable a fresh
profile to connect automatically. No additional preference was changed in
the running VM or the in-progress build.

Sam subsequently confirmed that clicking Connect succeeds and
https://check.torproject.org/ reports use of Tor. This is a user-reported
functional browser/Tor connection test with the existing encrypted-boot
release and provisioned signed archive. It does not verify the staged
launcher signature gate in the guest, fresh-profile auto-connect, or
comprehensive leak resistance. The updated isolated release is still building.

Updated release 20261011-203223-487513 completed successfully. All four
manifest hashes were rechecked. Embedded exit checker, status, Tor launcher,
public keyring and clean XFCE panel defaults match the staged files.
The automated live VPN suite is running against embedded ISO scripts.
The next-stage coordinator prepare-release-test.py clones the current
encrypted disk and updates only boot/system from the validated new release;
DATA remains encrypted and unopened. The working disk remains selected
until a complete successful update. Guest shutdown and SYSTEM password
are required before this storage operation.

The new ISO completed all 26 automated live VPN assertions with
LIVE_TEST_FAILURES=0: actual simulated-provider WireGuard/HTTPS connection,
failed-connect rollback, blocked transport and recovery, missing route and
recovery, disconnect/repeated disconnect, direct-request rejection across
states, and unchanged kill-switch table. This remains a simulated IPv4
fixture; actual provider DNS/NTP and IPv6 are outside its coverage.

Release update completed on preserved clone encrypted-boot-20261011-212035-542748.img.
Runtime coordinator recorded complete and selected release 20261011-203223-487513.
Host loop list was empty and petal_release_system mapper absent before relaunch.
Prior VPN/Tor disk encrypted-boot-20261011-203001-332009.img remains preserved.
The first noninteractive attempt failed at sudo before opening any volumes;
its unmodified candidate is retained. The successful update ran in a GUI terminal.
Desktop verification of the revised exit checker/signature-gated Tor is pending.

Sam confirmed all requested desktop checks passed on updated clone
encrypted-boot-20261011-212035-542748.img, release 20261011-203223-487513:
encrypted boot, automatic Private unlock, restored saved panel settings,
actual-provider VPN connection and clock synchronization, revised exit-IP
check without the historical .7 comparison warning, and Tor launch/connect
with check.torproject.org confirmation. The embedded Tor launcher uses the
signature gate verified separately by valid/invalid/missing-signature tests.
Fresh-session automatic Tor connection is still unresolved; manual Connect
was part of this test. Clean defaults without a saved settings archive remain
unverified in a desktop guest. No physical microSD was updated.

Next stage: seed extensions.torlauncher.prompt_at_startup=false only once,
after fresh verified archive extraction, in the RAM-only prefs.js. The signed
15.0.24 TorConnect source requires this and quickstart for automatic bootstrap.
Do not enforce this flag in user.js: Tor can set it true following failures.
Existing profiles retain their failure/recovery flag across launcher restarts.
The Private launcher still requires an interactive cryptsetup recovery
password path; Terminal=true is retained pending a tested graphical path.

Auto-connect release 20261011-215606-115947 built successfully. Rechecked
all four artifact hashes and compared embedded portable-tor to the tested
source with the one-time fresh-profile startup-prompt seed. No QEMU process
was running before opening the preserved-clone update coordinator.
Actual fresh-session auto-connect remains pending desktop verification.
Coordinator now accepts a validated completed release directory argument
instead of requiring a code edit for each release.

Auto-connect release installed successfully on new preserved clone
encrypted-boot-20261011-222018-687613.img. Coordinator recorded complete,
selected release 20261011-215606-115947, and loop/mapper checks showed
all updater attachments closed before the desktop launch. Prior clone
encrypted-boot-20261011-212035-542748.img is preserved. Fresh boot manual
verification of automatic Tor bootstrap is pending.

Sam confirmed everything worked on release 20261011-215606-115947,
clone encrypted-boot-20261011-222018-687613.img, and Tor connected
automatically after fresh boot without clicking Connect. This completes
the requested desktop acceptance test for the one-time RAM-profile seed.
The launcher test also verifies later recovery preferences are retained;
actual Tor bootstrap failure/recovery UI remains outside the desktop test.
Graphical helper password/error paths remain the next staged priority.
No physical microSD changes were made.

Sam selected /home/sam/Downloads/got82-adb.conf as a second VPN test
profile. Multi-profile manager, dynamic endpoint/DNS support and graphical
VPN authorization/errors are staged and tested; see docs/vpn-profiles.md
for exact results and limits. Sam explicitly requested no build yet; no
new build, guest provisioning or physical-card operation was performed.
Selected payloads were validated only in memory and never copied into inputs.

Sam requested the remaining functionality work while keeping builds paused.
Graphical helpers/download launchers, manual signed Tor archive maintenance,
optional IPv6 probing and app/isolation/recovery checks are now staged;
see docs/functionality-status.md for current code/test coverage and the
remaining rebuilt-VM/real-provider/account acceptance work. No new release,
host clone provisioning or physical-card operation was performed.
