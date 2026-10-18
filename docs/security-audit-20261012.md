# PetalOS security audit — 12 October 2026

The audit found two actionable gaps in the ordinary desktop workflow: a broad
passwordless polkit grant survived sudo hardening, and default URL/document
handlers bypassed the intended Tor/offline launchers. Both are corrected in
build inputs and tested in the running VM's RAM root. A new build has **not**
been made with these changes. The previously completed release
`20261012-205248-827255` still contains the old behavior.

The OS is not yet a strong boundary against a compromised application running
as Petal. Browser network permissions, unconfined download backends, shared
desktop/home access and the deliberately public administrator password leave
important gaps. Successful VPN/Tor tests do not establish Internet anonymity.

## Scope and precautions

Reviewed current build inputs, the completed release's live runtime, storage
and account metadata, exposed listeners, application launch paths, AppArmor
permissions, privileged helpers, boot design and current Debian advisories.
The installed inventory contains 1,627 binary packages. Signed kernel metadata
maps the running kernel to the actual `linux` source version `6.12.111-1`;
checking only `linux-signed-amd64` would miss kernel advisories.

Both existing backup archive checksums and the initial code snapshots passed.
A new code-only snapshot, `code-before-deep-security-20261012-213346.tar.gz`,
was preserved and verified before edits. No physical-card access, host image
attachment, personal file inspection, password-database dump, key read/export
or exploit payload was used. All canaries were public generated fixtures and
removed. The SYSTEM-key check used metadata only through the existing strict
guest-side read-only SYSTEM mount helper. Packet inspection retained only
counts, not captures, addresses or payloads. Detailed transient results are in
`/run/user/1000/petalos-security-audit` on the host, not an uploaded service.

## Prioritized findings

| Priority | Finding | Current disposition |
|---|---|---|
| High | Debian Live's polkit rule granted all actions to the active Petal desktop without authentication. | Corrected in RAM/source; awaiting a rebuilt boot. |
| High | HTTP/HTTPS links defaulted to unguarded Firefox ESR; document/media handlers included unwrapped programs. | Corrected defaults, viewer wrappers and browser alternatives in RAM/source; awaiting a rebuilt boot. |
| High | Browser policy permits direct TCP through the VPN, so code execution in the browser could bypass Tor. | Confirmed permission boundary; architectural fix remains. |
| High | Network download backends run as Petal without their own confinement and can access unlocked Private. | Existing design; per-app storage/privilege/display isolation remains. |
| High | The public Petal password also authorizes general sudo and polkit; it is not an administrator secret. | Intentional requested default retained; stronger runtime administration needs a design choice. |
| High for physical tampering | Public boot assets and external initramfs are not a fully authenticated boot chain. | Known layout limitation; hardware/Secure Boot and authenticated-image design remain. |
| Medium | Outstanding trixie advisories include aMule and file-parser libraries despite no currently available package upgrades. | Reviewed and documented; no unstable packages substituted. |
| Medium | Shared X11/audio/home access permits interference between desktop applications; offline does not mean hostile-code containment. | Existing boundary limitation; private display/home isolation remains. |
| Medium | Bluetooth defaults auto-enable controllers and are outside wired/Wi-Fi MAC randomization. | AutoEnable=false staged in RAM/source; no adapter exists in this VM to validate radio behavior. |
| Lower | Fixed network probes inherited curl configuration; some public build inputs retained root-group write bits. | Fixed probe options and tightened source permissions; critical RAM helper permissions verified. |

### Polkit authentication bypass

`/usr/share/polkit-1/rules.d/sudo_on_live.rules` returned YES for every action
from the active local Petal session. The vendor live-config component is
`1080-policykit`, which runs after `0055-petal-auth`. Thus changing sudoers
alone did not remove this separate authorization route.

Before correction, noninteractive checks against the actual desktop process
authorized privileged execution, systemd service management and storage
modification. No privileged action was executed by those checks.

The early `/etc/polkit-1/rules.d/00-petal-admin.rules` now requires AUTH_ADMIN
for Petal before later vendor grants can match; it does not retain a grant.
`1085-petal-polkit` removes the misleading generated blanket rule. With the
desktop active, all four tested sensitive actions, including system network
modification, required authentication. Sam confirmed the graphical dialog and
cancelled it; the authorization result was false. Root/system service actions
are outside the Petal-specific rule. Network and Bluetooth administration can
now request a graphical password rather than receive a blanket grant.

This corrects unintended passwordless authorization. It does not make the
public default password a defense against malicious code that knows it.

### Browser and document launch paths

The panel shortcut was Tor, but xdg HTTP/HTTPS handlers and the default Xfce
browser helper still selected Firefox ESR. PNG/JPEG also selected that browser;
PDF used Atril and media used Parole/Quod Libet outside the offline wrapper.

HTTP/HTTPS defaults and Xfce/x-www-browser/gnome-www-browser now use the guarded
Tor launcher. It accepts HTTP/HTTPS URLs as separate arguments and rejects
options, executable schemes, control characters and local-file arguments.
Tests verified exact argument forwarding without a shell. An actual xdg-open
web-link launch succeeded with the confined Tor browser present and no system
Firefox process started.

Images default to offline gThumb, PDF to offline Atril and common media types
to offline VLC. Atril, Parole, Ristretto, Mousepad and Quod Libet were added to
the existing binary-wrapper hook and explicit trixie package list. Local HTML
uses Firefox ESR through the offline wrapper. A generated local HTML document
rendered successfully in a disposable RAM profile with no network namespace
access. The default changes do not prohibit an intentional user override or
manual execution of an unconfined binary.

Parole requires Xfconf before parsing even --version. Parole/Ristretto/Mousepad
therefore get a private dbus-run-session **inside** bubblewrap. Their private
bus does not expose the host system/session bus. All five startup probes,
default handlers, browser alternatives and private-bus isolation checks passed.
This is startup/rendering evidence, not a complete feature test of each viewer.

### Tor networking is a browser convention, not an OS-enforced boundary

The browser policy's `network tcp` permits direct IPv4/IPv6 TCP as well as its
normal connection to Tor's local SOCKS socket. The VPN firewall restricts the
physical uplink, but permits applications to use wg0. A browser exploit could
therefore expose the VPN exit instead of the Tor exit.

The diagnostic used a temporary copy of the browser policy, adding only a
public Python interpreter/library execution entry to model code execution.
No extra network or Private permission was granted, and the actual browser
policy was not weakened. The probe established direct TCP to a public endpoint
through the VPN. An arbitrary public Private canary was denied, while a canary
in the intended Tor download folder was readable. The temporary policy and
files were removed, and the firewall matched its original contents. This was
not a browser exploit and does not prove a website can currently perform it.

The next fix should enforce browser-only access to a local SOCKS bridge using
separate process identities or a private network namespace. The bundled Tor
process needs its own approved tunnel access. P2P traffic should retain its
separate VPN workflow rather than be moved into Tor.

### Private storage and administrator boundary

The VM's SYSTEM and DATA are LUKS2 with AES-XTS and Argon2id passphrase slots.
Private is mode 700 and mounted nodev,nosuid,noexec,noatime. Petal cannot read
the raw SYSTEM or DATA mapper devices. The SYSTEM unlock-key directory/file
have root-only ownership, correct 700/600 permissions, no symlink and one
file link. The key remains outside filesystem.squashfs. Root login is locked,
Home is mode 700, and privileged helper code is root-owned and not writable
by Petal. Root/home remain RAM-based and no guest swap is active.

These controls protect against other unprivileged accounts and loss of locked
storage. They do not prevent Petal's own unconfined processes from reading
unlocked Private, and noexec does not prevent an interpreter from reading a
script. A public generated canary confirmed this same-account access without
reading personal data. Network backends currently lack separate profiles and
can exfiltrate such data through their otherwise permitted VPN connection.

The documented public Petal login password is deliberately retained, per
Sam's instruction. Because it is also accepted for general sudo/polkit, code
running as Petal can attempt ordinary authentication and obtain root. Clearing
the sudo timestamp prevents accidental passwordless reuse but does not change
that fact. An idle lock screen with a public password likewise provides no
meaningful access barrier to someone who has the running desktop.

A stronger design can retain the baked public login while giving runtime
administration a separate private credential, and confine network applications
to their own AppState/Downloads and a separate display/home context. A storage
lock/recovery design must also account for the SYSTEM-held auto-unlock key;
simply closing DATA while leaving that key available to root is not a strong
lock. Disk-encryption passwords remain separate and were neither inspected
nor changed. Their strength and the physical card's KDF settings were not tested.

### Outstanding advisories and exposure

Signed apt metadata was refreshed only after current VPN verification; a
dist-upgrade simulation reported no available upgrades. The audit compared
actual source versions with Debian's tracker, including the signed kernel's
Built-Using source version. Raw candidate counts include old, configuration-
specific, unimportant and unassigned issues and are **not** an exploitable-CVE
count. No claim that all packages are free of known vulnerabilities is made.

Important reviewed examples:

* aMule `1:2.3.3-3.2`: Debian reports an unfixed server-message parsing DoS,
  [CVE-2026-51105](https://security-tracker.debian.org/tracker/CVE-2026-51105).
  The upstream size check could be reviewed for a trixie source backport;
  it is not installed here. A VPN does not protect against a malicious peer/server.
* libxml2 `2.12.7+dfsg+really2.9.14-2.1+deb13u3`: outstanding integer-overflow/
  heap-overflow advisory
  [CVE-2026-86138](https://security-tracker.debian.org/tracker/CVE-2026-86138).
  Applicability depends on the consumer and input path; no exploit was attempted.
* Poppler `25.03.0-5+deb13u4`: outstanding encrypted-PDF password parsing
  [CVE-2026-107705](https://security-tracker.debian.org/tracker/CVE-2026-107705).
  The documented trigger requires an attacker-controlled long PDF password.
* NetworkManager `1.52.1-1`: outstanding private-connection file-access issue
  [CVE-2025-9615](https://security-tracker.debian.org/tracker/CVE-2025-9615).
  No NetworkManager VPN plugin packages were found; PetalOS uses its separate
  validated WireGuard manager. This is reduced exposure, not a patched daemon.
  [CVE-2026-10805](https://security-tracker.debian.org/tracker/CVE-2026-10805)
  needs an explicitly configured dhclient backend; the current backend is
  internal and that choice is now pinned in source/RAM configuration.
* The QEMU-only OpenSSH server has outstanding feature-specific records,
  including compressed-packet processing
  [CVE-2026-106585](https://security-tracker.debian.org/tracker/CVE-2026-106585).
  Compression and GSSAPI/hostbased authentication are now explicitly disabled,
  with PTYs disabled, shorter authentication limits and existing root/password/
  tunnel/forwarding prohibitions retained. Its config passed sshd validation
  and was reloaded without changing the pinned host key. Remote stdout, stderr
  and an intentional exit code 7 were captured correctly afterward. Production
  SSH remains masked; this is a trusted-host test management channel.

The selected signed Tor Browser 15.0.24 contains the security fixes described
in the [Tor Project release](https://blog.torproject.org/new-release-tor-browser-15024/).
Updates remain manual and disabled in the RAM browser; that requires a prompt
manual response to future advisories, not an assumption of permanent safety.

### Network, identifiers and physical trust

The live listener audit found only loopback Tor SOCKS/control and test SSH,
plus the kernel WireGuard UDP sockets. No failed service or X11 TCP listener
was present. A 15-second physical-facing-interface metadata probe saw 20
WireGuard packets and one ARP frame, with no other outgoing IP traffic. This
is bounded evidence, not proof that every packet or future failure is safe.
The prior built image's 44 VPN failure/profile/reconnect tests and 25 app/
recovery tests are separate evidence; no firewall rule was weakened here.

MAC randomization and hostname suppression do not erase provider account
identity, persistent WireGuard keys, P2P identity, Usenet login or traffic timing.
Tor protects correctly configured applications, not the entire OS, as the
[Tor Project explains](https://support.torproject.org/tor-browser/security/using-tb-safely/).
The simultaneous VPN/P2P and Tor workflows are distinct privacy domains;
they should not be described as universally anonymous Internet traffic.

Bluetooth's vendor AutoEnable default is true. Source/RAM now set false so
controllers should require deliberate activation. There is no controller in
QEMU: physical Bluetooth behavior, Wi-Fi scan exceptions, DHCPv6 identity and
radio leakage remain hardware tests. No Bluetooth address randomization is
claimed. The IPv6 VPN exit was already verified; IPv6-only physical uplink
neighbor discovery/transport is not verified by that result.

Public firmware boot files and an external initramfs are not fully authenticated
by merely using signed shim/GRUB/kernel packages. A physical attacker who can
alter boot assets can target the later encryption-password entry. Trusted boot
media and hardware are part of the threat model; signed UKI/verified-image and
rollback protection need a separate design. QEMU cannot protect its memory or
screen from a malicious host, and this audit did not verify physical Secure Boot.

## Verification and next stage

Reproducible audit scripts: `tests/security-audit-guest.py`,
`security-network-probe.py`, `security-boundary-probe.py`,
`security-polkit-probe.py`, `security-desktop-probe.py`, and
`security-package-audit.py`. They use metadata/public fixtures, bounded calls
and explicit QEMU checks. Existing desktop-helper positive/negative tests,
exit-IP IPv4/IPv6 fixtures, changed script syntax and build-input validation
also passed. Actual Tor Project API still reported IsTor=true after the changes;
general sudo failed after clearing its timestamp, while exact Tor readiness
remained passwordless. A generated curl configuration was ignored by the
actual exit helper, as intended.

Public source permissions were tightened without removing execute/private
bits. Bluetooth radio behavior, a fresh rebuilt boot with the new hooks,
full viewer feature acceptance and vendor vulnerability remediation remain
unverified. No new production image, encrypted disk update or card write was
performed during this audit. The VM remains usable with VPN and Tor running.

Before hardware acceptance, prioritize the Tor-only browser network boundary,
network-backend access to Private, and the runtime administrator credential
decision. Batch those changes with the staged fixes into one reviewed build,
then rerun encrypted boot and failure tests. Hardware testing can validate
device behavior; it cannot repair these software/design gaps.
