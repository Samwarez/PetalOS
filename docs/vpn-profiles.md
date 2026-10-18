> Current automatic connection checks: [vpn-connection-checks.md](vpn-connection-checks.md). Historical staging/deployment statements below describe earlier builds; current source and live QEMU acceptance are recorded in that document.

# Encrypted VPN profiles — staged, not built

Current storage update: `~/SystemSettings` points to `/mnt/system-state`.
Only the selected state bind is writable; the full SYSTEM view is read-only.
It is prepared at boot without opening Private. Existing QEMU profiles were
migrated into this encrypted area without deleting the originals or copying
keys into build inputs. A rebuilt boot is pending. Earlier acceptance and
provisioning notes below describe historical stages; the old Private-oriented
provisioning coordinators are not the current import path. Use the GUI manager.


Profiles live in `SystemSettings/Network/Profiles/NAME.conf`, mode 600, inside a
mode-700 directory. `SystemSettings/Network/selected-profile` remembers a profile
name only; it never authorizes network applications. One live interface,
`wg0`, continues to be checked against its protected runtime configuration,
authenticated peer, route, firewall policies, handshake and bounded HTTPS
request. The legacy `SystemSettings/Network/wg0.conf` is preserved.

The panel's **VPN Profiles / Connect** shortcut opens a GTK manager with
**Add Profile**, **Connect / Switch**, and **Disconnect**. Import copies a
validated configuration into encrypted storage with restrictive permissions;
duplicate names are refused. A valid legacy configuration is copied to
`original.conf` for migration. Invalid legacy files do not prevent importing
a replacement. The manager provides graphical sudo authentication and
failure handling. Backend output is discarded, not copied into logs or
dialogs. Other helpers retain their existing terminal behavior.

Switching is serialized with connection/disconnection, tears down the old
tunnel first, replaces the narrowly permitted endpoint atomically, and
actively verifies the new tunnel. A failed switch leaves the VPN down and
the kill switch in place. The saved selection changes only after a verified
connection. The original profile file is not altered or deleted. Connected
applications may lose their current connections during a switch.

Firewall endpoint sets are empty at boot and after disconnect. Only marked
WireGuard UDP to the selected numeric address/port is allowed off-tunnel,
alongside existing DHCP. Input/output/forward drop policies remain. DNS is
taken from the selected profile; the first three provider servers are used
in resolver order. DNS and time remain subject to the tunnel firewall.
There is no public DNS exception for endpoint lookup.

This stage accepts numeric IPv4 and bracketed IPv6 endpoint syntax. Hostname
endpoints are refused with an explanation; Sam chose to keep numeric endpoints
as the policy and exclude pre-VPN hostname DNS. VPN port-forwarding automation
is also out of scope. A numeric provider endpoint is required when importing.
Profiles need one Interface and one Peer,
valid keys/addresses/DNS, and both full-tunnel routes. Executable hooks,
routing overrides, duplicate fields and unsupported fields are rejected.
IPv6 endpoint parsing/transaction syntax is covered, but actual IPv6
transport and Internet connectivity have not been verified.

Adding, editing and switching profiles will not require rebuilding once this
manager is installed. This stage still requires a future release build and
desktop verification before it is available in the normal VM image.

## Verification

- 18 parser/storage test groups passed, including malformed fields, hooks,
  endpoint injection, name traversal, permissions, symlinks and legacy fallback.
- 22 diskless mocked shell regression checks passed. The minimal fixture uses
  a profile-preparation stub; parser and real firewall transactions are tested
  separately.
- 38 live guest checks passed with current source in a RAM overlay over the
  existing release. A simulated provider exercised two different WireGuard
  peers, endpoint IPs, ports, addresses and DNS; invalid switching failed
  closed, reconnect used the last verified selection, direct HTTPS stayed
  blocked, old endpoint permission was removed, and disconnected firewall
  contents matched boot. This fixture has no external NIC or writable disk.
- 8 GTK test groups passed with invisible windows and a mocked backend:
  hidden password acceptance/cancellation, connect, failure, disconnect,
  import, import cancellation, invalid input and duplicate names.
- Desktop-entry fields/targets and staged build-input validation passed.

Sam's selected `zrh43-adb.conf` and `got82-adb.conf` payloads were validated
without displaying or writing them into build inputs. The second source
resides on a fuseblk filesystem that does not retain Unix mode changes;
imports still receive mode 600 in encrypted SYSTEM settings. No build or profile
provisioning has been run for this stage.

## Deferred deployment

After a future release build, update a preserved clone with
`tests/prepare-release-test.py RELEASE_DIRECTORY`. The prepared
`tests/prepare-profiles-test.py` coordinator can then preserve that disk and
seed only the two explicitly selected profiles into a new clone's DATA
volume. It requires guest shutdown, sudo authentication and the test DATA
password. It reuses the verified loop/mapper/mount identity transaction;
the SYSTEM unlock key is never accessed. This new provisioner is staged and
syntax-checked, but its actual storage transaction remains untested.

Desktop acceptance should verify importing another profile, connecting both
selected profiles, switching, cancellation, invalid configuration refusal,
encrypted selection restoration after reboot, and Tor/clock guards. Do not
claim comprehensive IPv6/leak coverage or physical Secure Boot testing from
the simulated IPv4 fixture. No physical microSD operations are included.
