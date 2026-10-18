# Explicit application preference persistence

Use **Save App Preferences** from Utilities/the helpers launcher after closing
supported apps. This is an explicit save, not automatic app-use tracking. Launch
restores only the saved whitelist. Unchanged snapshots are not rewritten.

Current whitelist:

- Transmission: speed limits, alternative speed values and peer limits.
- aMule: transfer/connection limits, TCP/UDP ports and protocol choices,
  reconnection/server handling, file-allocation policy, interface/tray and
  statistics-display preferences, message/IP filtering and obfuscation toggles;
  plus a sanitized numeric IPv4 server list. Exact typed keys are listed in
  `app_preferences.py`; unsupported settings keep their default/Private behavior.
- Pan: cache size only. Usenet credentials, servers and activity are excluded.
- Geany: tab width, indentation type, wrapping and line-number display.
- KeePassXC: minimize-on-close and minimize-to-tray only.
- Quod Libet: volume between zero and one.

Other app-specific settings retain their baked defaults/RAM behaviour. Existing
selected XFCE/GTK desktop preferences remain handled by Save Desktop Settings.
No entire configuration directories, filenames, recent files, searches, queues,
credentials, identities or usage counters enter the app preference store.

The root exporter opens only fixed configuration paths with directory-relative
NOFOLLOW descriptors, a 1 MiB limit and expected owner checks. It validates types,
bounds and exact keys, then writes root-only SYSTEM/AppPreferences records.
Apps receive only their validated record in a read-only RAM snapshot. Restoration
runs as the app's own UID inside its mount namespace, before app startup; existing
security-forced wrapper settings still override restored convenience settings.

The aMule server.met parser discards every tag, retaining only numeric public
IPv4 addresses and ports, sorted and deduplicated. A fresh minimal list is seeded
only when no working list exists; existing Private state is not replaced. Names,
ping/failure statistics and timestamps are excluded. Format reference:
https://wiki.amule.org/wiki/Server.met_file

Do not symlink raw `server.met` or `amule.conf` into SYSTEM. aMule 2.3.3's
`ServerList.cpp` writes failure/ping statistics, last-ping data, UDP server keys
and their associated IP into the server file. `Preferences.cpp` also stores
nicknames, hostnames, paths, proxy/remote-control credentials, a persistent Kad
UDP key, executable event commands and state values alongside ordinary settings.
These fields are excluded from the SYSTEM snapshot, as are server names and
descriptions, searches, download queues and activity counters. Automatic
update checks, remote-control services and UPnP remain controlled by the wrapper.
The graph interval/capacity settings are preferences, not the collected graphs.

The canonical SYSTEM snapshot is `/mnt/system-state/AppPreferences/amule.json`,
written by **Save App Preferences** after supported apps close. Fresh sessions
receive a reconstructed tag-free `server.met` and reviewed INI keys even when
Private is locked. Raw working files remain in Private when the app starts with
Private available, otherwise RAM. Existing working server lists are preserved.
Saving is explicit; changing aMule preferences alone does not update SYSTEM.
The expanded allowlist passed synthetic save-format validation and restoration,
including identity/credential/history exclusion and existing-list preservation.
It is source-only until the next image or an authenticated runtime update.

Reviewed upstream sources:
https://github.com/amule-project/amule/blob/2.3.3/src/Preferences.cpp
https://github.com/amule-project/amule/blob/2.3.3/src/ServerList.cpp

Preference choices and explicitly configured server addresses themselves remain
persistent information. This design does not claim forensic deniability.

VLC is removed from package inputs, wrappers, production roles and policies.
Build verification rejects VLC/libVLC packages or a VLC executable in the artifact.
Parole and Quod Libet remain the native video/audio defaults. Actual Usenet
connection testing is deferred by Sam; it must not be reported as passed.

QEMU pre-build acceptance: explicit desktop-user sudo export returned zero;
all stored records passed whitelist validation. Transmission, Pan and aMule
launched with read-only filtered snapshots and reached ready native windows.
All 12 remaining offline GUI applications launched, mapped native windows and
remained alive during the bounded check. Desktop-user panel saving returned zero.
After app initialization had populated additional defaults, a second unchanged
save preserved all record mtimes. No claim of zero filesystem access traces.
Legacy desktop archives now migrate once to the narrower panel/theme whitelist;
GTK file-chooser state and unrelated app channels are excluded. Migration and
malformed-entry tests passed. Cold-boot acceptance of the final artifact remains
required. Usenet server connectivity remains deferred.
