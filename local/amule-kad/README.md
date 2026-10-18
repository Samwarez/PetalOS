# aMule Kad diagnostic candidate

**Status: abandoned; not part of the supported PetalOS build.** The supported
image uses Debian trixie's aMule package, without this custom candidate. The
patch, builder and associated tests are retained only as diagnostic history.
The trial did not resolve the observed Kad issue; no candidate binary should
be staged into a release or installed by the normal build process. Commands
and trial results below describe the historical experiment, not build steps
for supported releases.

This corrects operator precedence in `CPrefs::GetMyConnectOptions` in Debian
trixie's `1:2.3.3-3.2`. Each conditional must produce its bit before the bitwise
OR combines them. Otherwise, requested+supported becomes 2 instead of 3;
required and callback combinations are also wrong.

The correction is confirmed by compiling the actual source function and checking
all 512 input combinations. The original function fails 131. This is a real
protocol-advertisement bug; it is **not yet established as the cause of the
observed Kad firewall failures**.

`build.py` checks both source archive hashes, applies every Debian patch without
fuzz, then applies `connect-options.patch`. The Debian default disabling update
checks is retained. It builds only the GUI executable, retains Boost.Asio, UPnP,
GeoIP and translations, and does not replace the installed CLI tools. Development
packages can be extracted from trixie into a temporary `--sysroot`; host package
installation and root privileges are unnecessary. `--resume` reuses a prepared
tree only if the patch and corrected source hashes match its preparation record.

Example:

```
python3 -B tests/check-amule-connect-options.py /path/amule_2.3.3.orig.tar.xz
python3 -B local/amule-kad/build.py /path/amule_2.3.3.orig.tar.xz \
  /path/amule_2.3.3-3.2.debian.tar.xz /new/output/directory --sysroot /temporary/sysroot
```

Artifacts include an executable, separate public debug symbols, checksums and
provenance. They are diagnostic candidates outside live-build inputs. No OS hook
installs this candidate automatically. VM testing must preserve the original
executable, stop aMule gracefully, install atomically into guest RAM, and retain
the existing launcher, application UID, namespaces, AppArmor and VPN firewall.
Write bounded numeric results into a root-only RAM report before cleanup, so
an unrelated shutdown/cleanup failure cannot discard the test observations.

Source archives:
https://deb.debian.org/debian/pool/main/a/amule/amule_2.3.3.orig.tar.xz
https://deb.debian.org/debian/pool/main/a/amule/amule_2.3.3-3.2.debian.tar.xz

`tests/amule-kad-state-guest.py` reads only selected numeric Kad test fields
identified by matching public ELF/DWARF metadata. It refuses a binary hash
mismatch and never outputs keys, client IDs, IP addresses, filenames or memory
dumps. Its results are diagnostic, never a launch authorization or proof of
anonymity.

The public debug layout is generated without accessing guest data:

```
python3 -B local/amule-kad/layout.py /output/amule /output/amule.debug > candidate-layout.json
```

`tests/amule-kad-trial-guest.py` runs only from a root-owned 0700 RAM directory,
checks both executable identities, requires Private closed, and uses the normal
broker. It saves the baseline and a snapshot every 30 seconds, then restores the
original executable even if graceful application shutdown exceeds its limit.
It never weakens network rules or disables aMule's filters or bans.

Trial result (2026-10-16): source regression PASS for all 512 combinations;
live return tracing confirmed value 3 twice. At 180 seconds, TCP had four replies
and zero successful callbacks; UDP had two completed failures. The bitmask bug
is corrected, but this correction alone does not resolve the observed Kad issue.
All seven numeric snapshots were preserved before successful rollback; original
executable and normal broker restart verified. VPN gate, firewall drop policies,
Private-closed state and removal of temporary probes all passed. AppArmor remained
`petalos_amule (enforce)`, effective capabilities zero, NoNewPrivs enabled.
