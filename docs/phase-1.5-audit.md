# Phase 1.5: disposable security and stability audit

Sam authorized preparation of a separate audit VM with agent-accessible test
credentials so later multi-hour testing can run without repeated user input.
This preparation does not constitute completion of the audit.

The VM is created from an empty sparse regular file, not a clone of the working
VM or physical card. SYSTEM, administrator and Private have distinct disposable
credentials stored in its host-side mode-0600 credentials.json, outside build
inputs. SYSTEM and Private receive independently generated LUKS2 encryption
keys. Cross-passphrase rejection is verified during provisioning. No legacy
automatic Private key is installed. Petal password login stays disabled.
The initial guest allocation is eight virtual CPUs and16GiB RAM; its disk is
a separate16GiB sparse image. These are test resources, not minimum OS specs.

Only verified public release artifacts, a signature-verified Tor archive, and
the explicitly supplied dedicated audit VPN profile are seeded. No personal
files, databases, desktop archives or old VPN profiles are copied. The audit
SSH key and host identity are new. SSH uses CID43 over vsock, with a pinned
host key and host-only relay127.0.0.1:2225; it introduces no VPN firewall hole.
The normal OS image contains neither these credentials nor audit SSH access.

Commands (all coordinators run as Sam):

```
python3 -B tests/prepare-audit-vm.py RELEASE_DIRECTORY --vpn AUDIT_PROFILE_PATH
python3 -B tests/audit-vm.py AUDIT_STATE_JSON launch
python3 -B tests/audit-vm.py AUDIT_STATE_JSON ssh 'id'
python3 -B tests/audit-vm.py AUDIT_STATE_JSON root-script PUBLIC_FIXTURE_PY
python3 -B tests/audit-vm.py AUDIT_STATE_JSON unlock-screen
```

Provisioning needs host sudo. Thereafter SYSTEM boot input and administrator
authentication can use the test-only credential file without human prompts.
The VM still exercises normal authentication; no passwordless general sudo
policy or production backdoor is added. Serial unlock data is not logged.
The host root/sudo password is never recorded or used as a VM credential.
For an explicit credential-boundary fixture, `root-credential-script` passes
the three disposable credentials to that root fixture's stdin after sudo
authentication. Ordinary `root-script` fixtures receive no such payload.
Credentials are never put in command arguments; matching output is redacted.
The screen-unlock helper requires the expected Petal locker process before
typing the disposable SYSTEM credential through host-only QMP. It does not
reopen Private. This helper must only be used for the prepared audit VM.

Planned audit coverage:

- Cold boot, reboot, unlock failure/retry, idle/manual lock, download mode,
  suspend boundaries, Private key independence and selective persistence.
- VPN failure/disconnect/reconnect/profile switching, IPv4/IPv6, DNS/time
  routing, current-state application gates, Tor-only browser egress.
- AppArmor, user/capability separation, Wayland protocol restrictions,
  selected-file handoffs and secure shared-content usability.
- App create/save/reopen operations, RAM and Private destinations, synthetic
  media playback, crash/child cleanup, repeated launch/close and sustained load.
- External-media visibility with disposable media images, printing start/stop
  boundaries, shutdown/reboot behavior and fresh-image defaults.

Tests must produce bounded, credential-free evidence and distinguish failures,
fixes, retests and untested features. Use synthetic content only. Do not attack
third parties or claim anonymity, forensic erasure or Tails-equivalent security.
Usenet transfer testing remains deferred without dedicated server credentials;
real printer and physical laptop behavior require separate hardware checks.

Known follow-up: VeraCrypt's external AppImage administrator dialog appeared
under its progress window. Bringing forward that prompt allowed a successful
mount. No general window-stacking fix has been implemented yet. Shared-content
access/ownership and the physical airplane-mode key also remain open items.


Prepared instance — 2026-10-17
------------------------------

Verified release: /home/sam/portable-live/releases/20261017-215844-546957

Active audit workspace:
/home/sam/portable-live/testing/audit/20261017-221958-817753

Its state.json selects audit.img; credentials.json contains the three separate
agent-accessible test credentials (mode0600, parent0700). Do not include that
file or either private SSH key in reports, build inputs or public snapshots.
The dedicated supplied profile is installed as audit.conf only in encrypted
SYSTEM state. Root preparation closed every host mount/mapping/loop before
launch. The old working VM and physical card were not updated or cloned.
An initial unused empty workspace221913-233643 was retained after a Downloads
parent-link validation error stopped the coordinator before provisioning.
Canonical source-path handling was corrected; target image guards stayed strict.

Readiness evidence:17 startup/hardening/manual-printing checks and10 credential
boundary checks passed. Startup checks passed again after a graceful power-off
and repeated fully automatic cold boot. Administrator authentication persisted;
actual graphical lock and SYSTEM unlock were automated successfully, leaving
Private closed. Native labwc/XFCE/panel/wallpaper processes were present; the
1280x800 desktop was visually checked. SecureBoot and kernel lockdown enabled.
The dedicated tunnel's IPv4, IPv6, DNS, clock and tunnel checks all passed, with
an independent live network/clock application gate also passing.

The initial timing probe used journal receipt times and did not establish an
entropy fault. It now uses kernel event timestamps from dmesg. A standard
virtio RNG is present; do not attribute startup improvements causally to it.
The repeat boot succeeded without a virtual Enter or human password entry.
The launcher also handles relay TIME_WAIT reuse and cleans relay process groups.

The VM is left running with VPN connected, Private closed and download mode ON
for this audit session, to prevent setup idle expiry. Production defaults are
unchanged. Disable download mode explicitly when testing idle-lock behavior;
manual lock always works. Boot/frame/QEMU diagnostics remain bounded in RAM.
Host-only runtime and QMP directory:
/run/user/1000/petalos-audit-20261017-221958-817753
Current launcher tool session58448; no held root maintenance shell.

Public summarized readiness report and SHA256:
/home/sam/portable-live/testing/artifacts/phase-1.5-readiness-20261017.json

The multi-hour audit has NOT started. SecureBoot enabled is not proof that the
external initrd/root image is authenticated; that existing physical-tampering
gap remains documented in security-audit-20261012.md and must be audited.
