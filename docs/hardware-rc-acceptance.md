# Hardware release-candidate acceptance

Run only after the exact corrected release passes preserved-clone cold-boot
regression. Sam explicitly authorized wiping the PetalOS card on 2026-10-14
(“I do not care if you wipe the card”). The identified candidate is the
255,869,321,216-byte removable device at
`/dev/disk/by-id/usb-Mass_Storage_Device_121220160204-0:0`, with PORT_BOOT,
PORTABLE_SYSTEM and PORTABLE_DATA partitions. Recheck identity, capacity and
absence of mounts immediately before any write. Authorization is for this
PetalOS card, not the other attached USB or internal disks.

Preparation now uses a separate expanded clone of the accepted fresh-Private
QEMU candidate, preserving the working image and both existing backup archives.
The hardware management layer and resulting candidate must pass QEMU before
physical installation. No physical write has yet occurred. The initial backup
archives and source snapshot checksums were reverified before preparation.

The existing physical card is not the fresh-Private QEMU clone. Its previous
storage contents are not the proposed migration source. The replacement image
inherits the tested QEMU SYSTEM, administrator and distinct Private credentials;
its new Private volume key was previously verified independently of SYSTEM.
Existing backup images retain earlier data/access paths and are not forensic
erasure targets. Image installation is not proof of flash forensic erasure.

Hardware checks after an approved update:

1. Cold boot with SYSTEM only: native desktop, wallpaper and panel, admin
   authentication, no swap, RAM writable root/home, and Private still closed.
2. RAM documents/edit/save and native app startup without Private. Signed Tor
   distribution available from SYSTEM; its browser profile stays in RAM.
3. Connect wired/Wi-Fi as available: inspect actual randomized interface MACs,
   ephemeral network-profile storage, kill-switch policies and tunnel-only DNS
   and clock. Verify IPv4/IPv6 through the selected profile as supported.
4. Separate Private unlock; each app sees only its own RAM/Private folders.
   Verify encrypted persistence and explicit filtered app/desktop preferences
   across a restart using public fixtures, not personal file listings.
5. Manual and idle Private locking close the mapping and unmount all delegated
   views; RAM content remains. SYSTEM screen unlock must not unlock Private.
   Download mode inhibits idle locking only. Suspend remains disabled.
6. Disconnect/repeat-disconnect, invalid profile, reconnect and switching must
   retain the kill switch; check bounded egress observations. No open-network
   DNS/time/IP-baseline probes are permitted.
7. Shutdown/reboot: RAM fixtures and browsing sessions gone, approved settings
   retained, physical clock not written, encrypted stores closed at shutdown.

Record observed results and actual limitations. Do not describe functional
success as anonymity, absence of forensic traces or Tails-equivalent security.
Actual Usenet provider login/download tests are deferred at Sam's request.

## Planned test machine and management link

Sam identified the separate test computer as a Lenovo ThinkPad T14s, using
Wi-Fi for Internet access, with a direct Ethernet cable to the development
host available for diagnostics. The adapter and interface identities must be
checked on the actual machine; the model name alone does not identify them.

Prepare an optional hardware-test management layer, separate from the
production image. Give it a dedicated host-side SSH key, public-key-only
authentication, pinned guest host identity, and forwarding/PTY disabled.
Private keys must stay outside public modules and build inputs.

The proposed guest Ethernet interface belongs in a dedicated network
namespace, with a static point-to-point address, no default route, no DNS or
time service, and its own drop-policy firewall permitting SSH from the host
peer only. Leave Wi-Fi, WireGuard, main routing and the main kill switch
unchanged. The diagnostic shell initially inherits the management namespace;
approved maintenance commands inspecting the main network must explicitly
enter PID 1's network namespace after administrator authorization.

The development host currently has an unused wired interface, enp2s0, and
an active wired interface, enp0s31f6. Recheck these identities and cable
carrier before configuration; preserve the active connection. This is an
inventory observation, not authorization to move or reconfigure either port.

The disposable QEMU fixture `tests/hardware-management-netns-guest.py` passed
all seven checks: key authentication and stdout/stderr/exit status, wrong-key
rejection, unauthorized-peer blocking, no external route, namespace isolation,
and unchanged main firewall/routing/rules during operation and after cleanup.
It generated ephemeral keys only in guest RAM and removed both namespaces.
An optional hardware provisioning/activation layer is now implemented under
`tests/hardware-ssh`, with preparation scripts that accept regular-file
candidates only, expand Private, and install only the public SSH module into
the live-image selection. Its end-to-end boot test is pending; synthetic
namespace success alone does not validate this layer. Physical interface
selection and connectivity have not been tested. A failed
or unavailable management link must leave the normal VPN and kill switch
intact. The authorized physical installation remains pending candidate validation.

## Physical Wi-Fi and VPN result, 2026-10-14

ThinkPad T14s booted with Secure Boot enabled after the signed EFI repair. Sam
confirmed working brightness controls and Wi-Fi password entry/connection.
The missing Wi-Fi dialog was a secret-service timeout: the systemd user keyring
was on a different session bus. Importing the trusted desktop environment,
restarting the service and starting its secrets component restored registration
and the dialog. The startup correction is in source; cold boot is still pending.

Actual wireless MAC differed from the permanent MAC and had its local bit set.
NetworkManager saved its profile into the volatile root overlay (upper filesystem
tmpfs). The VPN connect helper and independent readiness guard passed; bounded
HTTPS probes bound to wg0 returned global IPv4 and IPv6 addresses, and clock
readiness passed. Private stayed unmounted with its mapper absent. Firewall
input/output/forward drop policies were verified. Temporary root maintenance was
closed and sudo timestamps cleared. Brightness/polkit/keyring corrections remain
RAM plus source, requiring the next image before they survive reboot.

### Desktop follow-up

Sam confirmed working Conky, wallpaper selection, battery percentage, and the
new native Window Appearance controls. Conky needed native Wayland output; the
wallpaper renderer needed XFCE's GDK monitor-model settings keys rather than
connector names. The installed power plugin was added to the panel and loaded
after a panel refresh. The new appearance dialog replaces the XFWM appearance
launcher and applies Labwc title-bar colors, border width, padding and alignment.
The X11-only tweaks launcher is hidden in the next source image.

The theme override's exact file was added to selective desktop persistence;
archive round-trip and unsafe-path rejection passed. The running image still
has the previous save allowlist, so saving the new theme requires the next image
or an authenticated runtime update. Existing desktop settings save paths remain
unchanged. No build or physical-card write was performed.

Two reported administrator prompts during Private unlock remain unexplained.
Maintenance authentication rejected three attempts, so no privileged log audit
was performed and no credential or authentication policy was changed.
