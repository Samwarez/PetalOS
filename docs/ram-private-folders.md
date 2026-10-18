# Separate RAM and Private folders

Approved option 1: the desktop home stays in the live RAM filesystem. Each
sandboxed app gets its own RAM Documents or Downloads folder, visible to Petal
under the corresponding home folder. When Private is mounted, the app also gets
its own Private content folder. GTK bookmarks label RAM as temporary and Private
as requiring unlock. No whole-home persistence, automatic content migration or
mount switching is enabled.

Apps launched with Private closed use RAM app state. Download apps launched
with Private open retain their existing encrypted app-state/queue storage and
default download destination, while their RAM folder remains available. Opening
Private does not change the mounts of an already-running app: close and reopen
the app to expose its assigned Private folder. Tor downloads default to RAM;
its profile stays in RAM. Signed public Tor archives are selected from
SYSTEM/Applications/TorBrowser instead of Private.

Only delegated content is exposed, never the desktop home or whole SYSTEM
store. The SYSTEM application directory stores a verified public distribution,
not a browsing profile. Content and activity state are never saved there.
Filtered app-preference persistence remains a separate implementation stage.

QEMU acceptance passed: all 18 content-role canaries worked with Private
closed; user confirmed Transmission, Pan, aMule, LazPaint and Tor usable.
All 18 dual-folder probes passed with Private unlocked, including distinct
storage and labelled bookmarks. The final lock closed/unmounted Private while
SYSTEM stayed ready, and all 18 public RAM canaries survived. All 14 boot-state
checks passed afterward. Symlink folder creation was rejected without changing
the target owner. VLC's existing native-only GUI restriction is unchanged;
its storage-role probe is not a GUI startup test.

A recurring notification error exposed D-Bus StartServiceByName activation,
which bypassed the previous destination-call denial. App mount namespaces now
hide both XFCE notification activation files and replace the daemon executable
with a failing stub. Explicit activation probes passed for all four network GUI
roles; fresh app launches left no sandbox notification-daemon processes.
Desktop notification capabilities remained available.

The changes are in source and guest RAM, not yet the released ISO. Only the
signed public Tor distribution was installed into the test SYSTEM store; no
content, browsing profile or Private data was copied there.
No physical microSD update is authorized.
