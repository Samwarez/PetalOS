# Desktop defaults and persistent overrides

Fresh live users receive the PetalOS XFCE panel layout through /etc/skel,
with the browser dock launcher pointing to portable-tor and the final dock
item containing Private, VPN connect/disconnect, exit-IP check, save settings
and SAB start/stop helpers. GTK file choosers receive a Private bookmark.
The stock theme and wallpaper remain until actual branding assets are selected.

Xsession restores the existing selective desktop-settings archive after user
creation and before starting XFCE. Its saved files overwrite matching defaults;
defaults missing from the archive remain. Saved customized layouts take
precedence. No whole-home persistence, personal archive ingestion, terminal
flag removal or archive-extraction redesign was introduced.

These panel defaults are embedded in release 20261011-203223-487513 and
retained in 20261011-215606-115947. The squashfs panel XML was compared
with the source. All eight launcher targets exist and their desktop-entry
fields were parsed successfully with GLib. Sam confirmed saved panel settings restore in that
release. Actual fresh-user launcher rendering without saved overrides still
requires a desktop test; existing saved settings deliberately take precedence.

The browser shortcut is named "Tor Browser (RAM session)". The grouped
launcher contains Unlock Private Storage, VPN connect/disconnect, Exit IP,
Save Desktop Settings, and SAB start/stop. Launcher definitions remain in
/usr/share/applications; panel defaults reference those shared entries.

Sam tested the baked defaults after renaming the selective settings archive
to desktop-settings.tar.saved and rebooting the updated VM. He confirmed
the panel checks out, then shut down the VM. Fresh default rendering and
the earlier saved-settings restore have therefore both been user-tested.

The subsequent staged multi-profile change updates the shared VPN entries
to launch a graphical profile manager. That change has not been built;
the current image still uses its original VPN menu wrapper.

## Friendly storage navigation

The desktop file manager offers three curated storage bookmarks:

- **Private Files** → `/mnt/private` (requires the independent Private unlock).
- **System Settings** → `/mnt/system-state` (selective encrypted persistence;
  existing file ownership and access restrictions still apply).
- **Temporary Files (RAM)** → `/home/Petal` (volatile documents, pictures and
  downloads; contents disappear on shutdown).

Raw block-device entries, including PORT_BOOT and the backing encryption
volumes, are hidden through UDisks presentation hints. Filesystem labels,
mountpoints and encryption identities are unchanged. This is presentation,
not an access-control boundary. Standard file-manager navigation can remain.

Applied in the current QEMU RAM session and staged for the next build after
release `20261015-193931-862289`; the completed release and physical card do
not contain this follow-up yet.
