# ThinkPad hardware acceptance — bounded pass completed

Core hardware workflows, suspend/resume and normal shutdown passed. SYSTEM has
29 MiB free, and the Qt sidebar fix is source/RAM-only, so this is not acceptance
of a final rebuilt image. See `summary.json` for remaining work and test limits.

Release `20261019-211301-083244`, product revision `bfd9dd9`, running
generation `5508b17fe0e494723bdf3086` on the Lenovo ThinkPad T14s.
The card update passed OS file readback and cleanup; Private was not opened.

Initial read-only checks in `initial-boot.json` confirm all 218 maintained public
runtime files, kernel 6.12.113, Secure Boot and kernel lockdown, 30 enforcing
PetalOS AppArmor profiles, RAM operation, no swap, selective SYSTEM persistence,
disabled Petal password, no legacy automatic Private key, closed Private,
default-drop firewall, and no failed system units. The pre-VPN application
readiness gate rejected access while the wireless interface was down.

The broad kernel marker scan flagged one `r8152-cfgselector` USB Ethernet adapter
reset. Inspection identified no card I/O error, GPU hang, kernel crash, or OOM;
the false broad classification is retained in the raw probe result.

SYSTEM has only **29 MiB available** after retaining the legacy OS payload and
the newly installed generation. Approximate allocated sizes: legacy live files
1,803,116,544 bytes; new generation 1,785,548,800 bytes; selected persistent
state 276,107,264 bytes. No old payload, rollback, setting, or backup was deleted.
This capacity constraint needs an explicit maintenance decision before another
OS generation can be staged; settings growth also has little headroom.

Wi-Fi/VPN recovery, actual applications/media, desktop controls, lid
suspend/resume and normal shutdown remain pending for this hardware pass.
VM results remain separate; this checkpoint is not hardware acceptance.

## Connected hardware checks

External power, Wi-Fi and VPN were confirmed from the live system. Active
tunnel-bound IPv4, IPv6, DNS and clock checks passed, both application readiness
gates accepted, and WireGuard receive/transmit counters increased. A bounded
Wi-Fi-interface observation recorded 73 WireGuard packets and no unexpected IP
packets; no packet payloads, exit addresses or MAC values were saved. This
observation is not proof of absence of all possible leaks. The active Wi-Fi MAC
was locally administered and differed from the permanent MAC reported by kernel
netlink. The first diagnostic attempt expected absent ethtool; the fixture was
adjusted to use existing netlink data, with no production package/policy change.
See `network.json`. Private remained closed.

A disposable KeePass database in RAM passed actual installed CLI creation, save,
reopen, update and group verification under its production AppArmor/bubblewrap
role. IPv4/IPv6 socket creation was denied. Selected-file handoff passed pinned
inode, read-only grant, neighbor exclusion, symlink/FIFO rejection and original
0600 owner/mode preservation. Test files were removed. See `RAM-workflows.json`.

Transmission, Pan, aMule, SAB/backend and frontend, Tor/backend and browser
reached native GUI readiness with their main application profiles enforcing.
Tor required 113.72 seconds; the other four launch transactions took 2.9–8.13
seconds. Namespace-local D-Bus/GVFS/accessibility helpers have separate labels;
this does not claim every helper is AppArmor confined. See
`application-launch.json`. SAB's actual administration bridge returned HTTP, and
the ordinary desktop UID was denied access to its administration socket; see
`SAB-bridge.json`. Real Usenet service operation remains deferred.

Parole opened a generated two-minute moving-video/quiet-tone file from RAM
Downloads through the production broker's read-only selected-file handoff.
Playback output-monitor capture received 187,400 PCM samples with nonzero RMS;
no microphone or raw saved audio was used. A separate native 1080p pipeline in
the Parole role completed all 600 frames, reporting zero drops over 21.007
seconds, with advancing timestamps and the expected audio clock; this measures
the synthetic pipeline, not all real-world codecs or speaker output. See
`media.json`. Human confirmation of video/speaker behavior and actual Tor-page
loading was requested and is still pending.

The normal desktop UID, with its initialized supplementary groups, was denied
read-only opens of the internal NVMe whole disk, the SYSTEM mapper and the full
SYSTEM mount view. No data was read from these devices. There were still no
failed system units, with approximately 26,438 MiB RAM available after startup.

Pending: visual application responsiveness, Tor-page confirmation, Private
workflows and lock/suspend/resume/shutdown on this updated hardware build. No
VPN failure transition was induced during these initial positive tests, and no
personal file/database was opened. All local test-state changes were in RAM.
The SYSTEM capacity finding above is unresolved.

Human confirmation received: the actual Tor page confirms Tor and Parole's
moving video was visible. The initial quiet tone was not heard. A separate
RAM WAV with alternating 440/660 Hz beeps was replayed through actual Parole;
the default output was the speakers, unmuted at the unchanged 33% volume. Sam
confirmed sound was playing. This owned test playback was stopped and its RAM
WAV removed. See `human-confirmation.json`.

## Private workflow checks

After Sam entered the Private passphrase through the normal desktop action,
the actual mapping, readiness check and hardened mount options were confirmed.
All 16 supported application roles passed creation/edit/reopen of new 0600
files in both their delegated RAM and Private folders, with desktop read/edit
access and sibling-folder exclusion. The disposable files were removed.
Installed KeePassXC CLI also passed create/save/reopen/update/readback inside
its real sandbox using Private, with IPv4/IPv6 sockets denied. See
`Private-workflows.json`. These are real filesystem/application checks; the
actual KeePass GUI save/reopen confirmation is still pending separately.

Read-only power authorization checks passed: active local desktop shutdown,
reboot and suspend are permitted; remote desktop/app identities still require
authorization; privileged inhibit overrides, system-unit/storage/system-network
modification and arbitrary polkit execution retain authorization. This did not
request a power transition. Five explicit XFCE power properties were queried
and returned unset; this does not establish the effective default lid behavior.
See `power-authorization.json`. Actual lid/suspend/resume remains pending.

The KeePassXC GUI is open for Sam to create a disposable `hardware-test.kdbx`
in its Private Documents folder and verify save/reopen. The suggested test
filename was checked absent before requesting this operation. No test used or
recorded Sam's Private, SYSTEM or administrator passphrase.

## KeePass GUI and sidebar repair

Sam confirmed the disposable Private database saves and reopens in the actual
KeePassXC GUI. The user then requested a Private shortcut in its file chooser.
The desktop GTK bookmarks and app GTK bookmarks already contained Private, but
the actual Qt widget reproduced the missing shortcut, showing only Computer
and its sandbox home.

The maintained app-home initializer now seeds Qt's separate FileDialog sidebar
with its existing Private alias (only when Private is available) and its RAM
Documents/Downloads alias. The sandbox bind mounts, AppArmor policies and
permissions are unchanged. The first partial seed was ignored because Qt needs
the sidebar width to restore these settings; that attempt is retained as an
implementation/test result, not a new security failure. The corrected seed
includes the width. Relevant upstream implementation: [Qt QFileDialog settings
restoration](https://github.com/qt/qtbase/blob/5.15/src/widgets/dialogs/qfiledialog.cpp).

The new `tests/qt-file-chooser-guest.py` exercises the actual Qt widget inside
the production KeePassXC AppArmor/bubblewrap role. With Private open, the test
passed all eight sidebar/navigation/access checks, displaying Private and
Documents. Other apps' folders and SYSTEM remained hidden; IPv4/IPv6 sockets
were denied. The actual-Private-closed variant is pending the physical lock
workflow; no mocked storage state is claimed as that test. See
`Qt-Private-sidebar.json`.

The seven-line production change was staged in guest RAM, after verifying the
original library hash and preserving its original public bytes in a root-only
RAM backup. KeePassXC was restarted after the user's completed save/reopen test.
The disposable database remains in Private. User-visible shortcut confirmation
is requested; a new image has **not** been built or written to the card for this
change. The kernel and all policy files remain those of the tested release,
but the running compartments library now differs intentionally by this patch:
SHA256 `a0e23225236a956228ff161a9e5d37e379ff2f27907f281264b015ae13e642d8`.
Source and pre-change public reports were preserved in timestamped
`before-private-chooser-*` and `hardware-reports-before-private-chooser-*`
snapshot archives with checksum sidecars.

## Selected Private media and network recovery

Sam confirmed the live Private sidebar works. Actual Parole then opened the
owned disposable Private video through the normal broker, decoded audio to the
output monitor, and preserved the synthetic source bytes. The owned test file
was removed. The media probe's strict `mode0600` field was false after startup.
Follow-up ACL review reproduced the expected content-delegation normalization:
only desktop UID1000 and role UID955 were named; owner remained1000, group
and other ACL entries granted no access, and a Geany sandbox could not see the
Parole folder. ACL masks contribute group-mode bits, so a literal0600 check
after named-ACL normalization was the wrong expectation. The raw false field
is retained in `Private-media.json`; see `Private-ACL-review.json`. No permission
or security-policy change was made for this observation.

The first tunnel-recovery fixture ran while the download apps were closed.
It demonstrated live gate denial on link loss despite the historical report,
disconnect denial, normal reconnect recovery, unchanged firewall rules, and
128WireGuard/0unexpected IP packets; it did not test app survival. That
coverage limit was reported and the pass repeated with all four apps confirmed
alive. See `tunnel-recovery.json` and `tunnel-app-recovery.json`.

With Transmission, Pan, aMule and SAB running, all remained alive through the
repeat. Fifteen synthetic underlay-bound UDP attempts across the desktop and
four download UIDs bound to Wi-Fi but their send calls were rejected. Live
readiness denied tunnel loss and disconnection despite the old report; merely
restoring link-up did not restore readiness. The normal disconnect/connect
transaction restored a passing active gate without reboot. Static firewall
rules were unchanged, with891WireGuard packets and0unexpected IP packets in
the bounded capture. Private stayed open. This checks worker survival and
network enforcement/recovery, not successful real Usenet service or every
ongoing application's transfer recovery.

A root-only, bounded600-second read-only resume observer is now staged in guest
RAM. It verified Private open before becoming ready and will collect kernel
suspend/resume events, storage/desktop state and the actual-Private-closed Qt
chooser variant after SYSTEM unlock. Its public test sources are maintained as
`tests/hardware-resume-watch-guest.py` and `tests/qt-file-chooser-guest.py`. The
arbitrary-command maintenance SSH session was closed; the finite observer
survives an ordinary SSH disconnect and accepts no commands. Physical lid test
and its result remain pending. No sleep or unlock was requested by the observer.

## Suspend/resume result and diagnostic limits

Sam reports no visible issue after lid closure, reopening and SYSTEM unlock.
The independent observer recorded one kernel suspend entry and exit,16.0seconds
of actual sleep, and a closed Private mapping before sleep and after unlock.
It saw Private close before the lid state became closed, so this evidence does
not identify whether idle/manual/before-sleep handling first closed it. The
locker was observed, SYSTEM state remained ready, all four desktop components
returned, and there were no new storage/GPU errors, swap, failed units or
firewall policy changes. Raw evidence is `suspend-resume.json`.

The observer's follow-up Qt probe was interrupted (inner exit137); its cause is
**unconfirmed**. An isolated-management-SSH application attempt also failed;
that invocation context is not assumed equivalent to the desktop. In a fresh
authenticated main-namespace diagnostic session, all home/storage/preferences/
display stages passed; the foreground closed-Private Qt fixture passed all
eight checks; the native KeePass window opened in RAM; and the approved local
desktop broker succeeded. No production policy/code change was made to obtain
those retry results. `resume-followup.json` preserves that distinction.

The diagnostic fixture now holds the existing app-family action lock around
its inactive-app check, RAM-home reset and probe. This prevents an operator's
launcher racing that test; it is not a demonstrated explanation or production
fix for the earlier interruption. A live guard check confirmed that running
KeePass is refused before reset and its existing worker stays untouched. See
`chooser-active-app-guard.json`. Syntax and whitespace checks passed.

Final health confirmed Private closed, selective SYSTEM ready, no failed units,
no swap, all30PetalOS profiles enforcing and the expected RAM sidebar library
patch. See `final-health.json`. No physical card OS update or image rebuild was
performed after the sidebar repair. Normal desktop shutdown remains pending.

## Normal shutdown and final checkpoint

Sam confirmed normal desktop shutdown works. The subsequent bounded pinned SSH
probe returned exit 255 in 5.02 seconds, confirming the management connection
was no longer accessible. The authenticated maintenance session had already
been closed. See `shutdown.json`; no further guest changes were made.

This completes the bounded hardware pass, with the interrupted diagnostic and
coverage limits retained above. Remaining work is the SYSTEM capacity decision
and building/verifying an image that includes the Qt sidebar repair. No old OS
payloads or backups were removed, and no further physical-card writes occurred.

## Follow-up retention policy

Sam selected at most one previous OS for test builds, and no previous OS for
production. OS changes must be built and installed offline, never applied by a
live-system updater. The host installer source now implements bounded retention
and passes disposable-directory failure tests; see ../os-lifecycle.md. The card
has not been mounted or changed, and its measured 29 MiB free space is unchanged.
This implementation is not a new physical installation or boot acceptance.
