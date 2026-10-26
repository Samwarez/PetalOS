# PetalOS Phase 2 icon checklist

Recorded 2026-10-23 from the running preview of release
`20261023-211330-297439`, its actual installed desktop entries, the maintained
XFCE/Crystal Dock defaults and pinned Crystal Dock 2.16 source. This is an artwork
and integration inventory; no OS settings or live applications were changed.

The installed image has **105 desktop entries**, of which **92 pass the XFCE
visibility-field filters**, using **77 distinct icon references**. Those numbers
include aliases and duplicate launchers; they are not a count of unique drawings
or a claim that every listed entry is supported or actually displayed by each menu.
The [CSV](phase2-icon-inventory.csv) and [JSON](phase2-icon-inventory.json)
preserve every entry, including hidden/background-only entries.

## First batch: what appears on boot

### Bottom Crystal Dock

Sam explicitly requested battery and network status in the **bottom Crystal Dock**.
These are new functional requirements as well as artwork requirements. They remain
disabled in the current preview; this inventory does not claim they were enabled.

| Artwork family | Current use/reference | Variants or notes |
| --- | --- | --- |
| PetalOS applications/menu logo | `start-here` | Replace the current generic desktop logo; reuse for the top applications menu where appropriate. |
| Terminal | `org.xfce.terminalemulator`, `org.xfce.terminal` | One design can serve the launcher and running terminal. |
| File manager | `org.xfce.filemanager`, `org.xfce.thunar` | Launcher and running-window aliases should agree. |
| Tor Browser, RAM session | `portable-tor.png`; running browser also has its own identity | One consistent app design; retain a recognizable distinction from the offline HTML viewer. |
| PetalOS Helpers group | `preferences-system` | Group launcher and its open window. |
| Lock Private and desktop | `system-lock-screen` | Security/lock action; separate from merely unlocking Private. |
| Trash | `user-trash`, `user-trash-full` | Empty and full; same RAM Trash on desktop and dock. |
| **Battery status, requested** | New bottom-dock status requirement | Unknown, absent/no battery, empty/critical, low, medium, high, full; charging and charged-on-AC states. Percentage should remain available as text/tooltip. QEMU without a battery must not pretend to be a laptop at 0%. |
| **Network status, requested** | New bottom-dock status requirement | Offline, connecting, Wi-Fi strength, radio disabled/hardware blocked, Ethernet connected/disconnected, and link present with no usable route. |
| Running apps | Per-app icons in the complete table below | Also needed for grouped tasks, focus indicators and window menus; no separate custom drawing for each open window. |

There are seven current startup dock families plus the two requested indicator
families. Empty/full Trash and all status states increase the number of actual assets.
Separators and active-task dots are drawn by the dock rather than supplied icons.

The independent upstream Crystal Wi-Fi manager is deliberately disabled in the
current PetalOS patch. Adding status must retain NetworkManager's existing
ephemeral-profile/password-agent flow and the VPN helper. Merely enabling the
upstream manager is not the planned implementation. The wired/Wi-Fi link indicator
must not imply that VPN verification succeeded.

### Retained top XFCE panel

| Item | Artwork needed |
| --- | --- |
| Applications menu | PetalOS menu logo. |
| Window/task buttons | The same app icons as the dock, including custom helpers. |
| Workspace switcher | Workspace/grid design if replacing its text/miniatures. |
| NetworkManager tray item | Wired/Wi-Fi/offline/connecting/strength and VPN overlays; hardware-dependent states. |
| Bluetooth tray item | On, off, disconnected, connecting/active and hardware-blocked states; hardware-dependent visibility. |
| Power-manager plugin | Battery, charging, AC/no-battery and brightness icons; the VM may only show a power icon. |
| Petal/session action button | User/avatar plus lock, logout, restart, shutdown and suspend menu actions. |
| Clock/date | Currently text; no standalone icon required. |
| Separators | No bitmap/SVG required. |

The running preview has nm-applet, blueman-applet and XFCE power management.
Their presence does not mean every hardware-specific icon is visible in QEMU.
A permanent volume indicator is not currently enabled in the bottom dock; sound
notifications still need the volume/mute family below. Conky is text on the desktop,
but its Applications entry has an app icon.

### Desktop and file-manager places

- Home, File System/root, and empty/full RAM Trash.
- Private Files: distinguish locked/unavailable from unlocked/available.
- System Settings persistent store.
- RAM/Temporary Files store.
- Desktop, Documents, Downloads, Pictures, Music and Videos folders.
- USB/removable drive, microSD/card reader, generic disk, encrypted volume, eject.
- Network location and generic folder/file fallback.

The three storage areas need visibly different designs. A folder drawing must not
suggest that Private is unlocked when its encryption mapping is closed.

## PetalOS helpers and special windows

Some current helpers share generic artwork; separate designs or small action
overlays can make them easier to identify.

| Function | Proposed asset name or family | Current reference |
| --- | --- | --- |
| VPN Profiles / Connect | `petalos-vpn` | `network-vpn` |
| Disconnect VPN | `petalos-vpn-disconnect` | `network-vpn` |
| Check VPN exit IP | `petalos-check-ip` | `network-vpn` |
| Check VPN IPv6 | `petalos-check-ipv6` | `network-vpn` |
| Unlock Private Storage | `petalos-private-unlock` | `drive-harddisk` |
| Lock Private and Desktop | `petalos-lock` | `system-lock-screen` |
| Download Mode | `petalos-download-mode` | `folder-download`; on/off state if displayed persistently |
| Save Desktop Settings | `petalos-save-desktop` | `document-save` |
| Save App Preferences | `petalos-save-preferences` | `document-save` |
| Install verified Tor archive | `petalos-tor-install` | Absolute `portable-tor.png` path |
| Start/open SABnzbd | `petalos-sabnzbd` | `sabnzbdplus` |
| Stop SABnzbd | `petalos-sabnzbd-stop` | `process-stop` |
| Start Printing | `petalos-print-start` | `printer` |
| Stop Printing | `petalos-print-stop` | `printer` |
| Display Brightness | `petalos-brightness` | `display-brightness` |
| PetalOS Guide | `petalos-guide` | `help-about` |
| Window Appearance | `petalos-window-appearance` | `preferences-system-windows` |
| Helpers group | `petalos-helpers` | `preferences-system` |
| Start/restart Crystal Dock | `petalos-dock` | `user-desktop` |
| Administrator authorization | `petalos-admin` | Shared graphical authorization dialog; needs a matching window/task identity. |
| SYSTEM passphrase dialog | `petalos-system-unlock` | Keep distinct from administrator and Private dialogs. |
| Private passphrase dialog | `petalos-private-unlock` | Include a wrong-passphrase/warning treatment. |
| Initial administrator setup | `petalos-admin-setup` | Same administrator family, separate setup label. |

These proposed `petalos-*` names are an art brief, not already-installed filenames.

### Blank VPN task icon: observed issue

The launcher already has `Icon=network-vpn` in
[`portable-vpn-connect.desktop`](../config/includes.chroot/usr/share/applications/portable-vpn-connect.desktop).
In the running desktop's **Tango** GTK icon theme it resolves to an installed
GNOME PNG; the symbolic variant also resolves. Thus it is not simply missing
all artwork.

The manager creates an ordinary GTK window titled VPN Profiles
([`portable-vpn-profiles`](../config/includes.chroot/usr/local/bin/portable-vpn-profiles):62)
without explicitly assigning a matching application identity or window icon.
Crystal Dock matches Wayland app IDs against desktop entries and resolves artwork
through Qt. The open task's missing icon needs an app-ID/launcher-matching and
Qt-theme lookup check; the exact runtime cause has not yet been isolated.
The same review should cover Helpers and the shared password dialogs. A new PNG
alone is not acceptance evidence. Check the icon on the launcher, open window,
top task list and dock group.

## Status and notification variants

Use shape/state changes as well as color, and keep short text/tooltips available.

| Family | Required variants | Existing names/aliases to cover |
| --- | --- | --- |
| Battery | Unknown, missing, critical/empty, low, medium, high/full, charging, charged/AC | `battery-missing`, `battery-empty`, `battery-caution`, `battery-low`, `battery-good`, `battery-full`, charging/charged variants and `*-symbolic`; modern percentage-step aliases may share art. |
| Wi-Fi | No signal; weak, fair, good, excellent; connecting; disabled; hardware-blocked | `network-wireless-*`, `nm-signal-00/25/50/75/100`, corresponding secure/symbolic aliases. |
| Ethernet | Connected, disconnected, acquiring, no route | `network-wired*`, `nm-device-wired*`, `nm-no-connection*`. |
| Generic network | Offline, unknown, activity/error/no route | `network-offline`, `network-error`, `network-no-route`, transmit/receive variants. |
| VPN | Disconnected/blocked, connecting, verified, failure, not yet checked | `network-vpn*`, `nm-vpn-*`; actual tunnel checks must control any verified label. |
| Bluetooth | Enabled, disabled, blocked, connecting, active/disconnected | `bluetooth-*`. |
| Volume | Muted, low, medium, high | `audio-volume-muted/low/medium/high`, symbolic variants. Current hotkey helper chooses high or muted plus percentage. |
| Brightness | Brightness/sun with level | `display-brightness`; level can be drawn rather than a separate icon for every percentage. |
| Notifications | Normal, disabled/do-not-disturb | `notification-symbolic`, `notification-disabled-symbolic`. |
| Results | Information, success, warning, error | `dialog-information`, `emblem-default`, `dialog-warning`, `dialog-error`. |
| Storage/security | Locked, unlocked, unavailable, saving/busy, failed | Private and SYSTEM artwork must keep their authentication purposes distinct. |

NetworkManager ships multi-frame `nm-stage*-connecting*` and
`nm-vpn-connecting*` sequences. These can be a coordinated small animation or
aliased to a consistent connecting design rather than independently illustrated
frames. Cellular/modem states are an optional extension unless that hardware is
included in the supported baseline.

The current Crystal battery component has limited state artwork; the requested
richer states are a design/integration requirement, not a statement that current
code already renders all of them.

## Complete installed application and settings artwork table

This groups all 92 XFCE-eligible desktop entries by their 77 current icon
references. Reusing a design across aliases is expected. The CSV contains exact
desktop IDs, visibility fields and categories.

| Current icon reference | Application/settings entries |
| --- | --- |
| `/usr/share/icons/hicolor/128x128/apps/portable-tor.png` | Install Tor Archive; Tor Browser (RAM session) |
| `amule` | aMule (VPN) |
| `atril` | Atril Document Viewer |
| `blueman` | Bluetooth Manager |
| `blueman-device` | Bluetooth Adapters |
| `conky-logomark-violet` | conky |
| `display-brightness` | Display Brightness |
| `document-save` | Save App Preferences; Save Desktop Settings |
| `drive-harddisk` | Unlock Private Storage |
| `firefox-esr` | Local HTML Viewer (offline) |
| `folder-download` | Toggle Download Mode |
| `geany` | Geany |
| `gvim` | Vim |
| `help-about` | PetalOS Guide |
| `io.github.quodlibet.ExFalso` | Ex Falso |
| `io.github.quodlibet.QuodLibet` | Quod Libet |
| `keepassxc` | KeePassXC |
| `lazpaint` | LazPaint |
| `libreoffice-calc` | LibreOffice Calc |
| `libreoffice-draw` | LibreOffice Draw |
| `libreoffice-impress` | LibreOffice Impress |
| `libreoffice-math` | LibreOffice Math |
| `libreoffice-startcenter` | LibreOffice |
| `libreoffice-writer` | LibreOffice Writer |
| `mini.xterm` | UXTerm; XTerm |
| `multimedia-volume-control` | Volume Control |
| `network-vpn` | Check VPN Exit IP; Check VPN IPv6; VPN Profiles / Connect; Disconnect VPN |
| `org.gnome.gThumb` | gThumb |
| `org.gnome.pan` | Pan |
| `org.xfce.about` | About Xfce |
| `org.xfce.appfinder` | Application Finder; Run Program... |
| `org.xfce.Dictionary` | Dictionary |
| `org.xfce.filemanager` | File Manager |
| `org.xfce.mousepad` | Text Editor Settings; Mousepad |
| `org.xfce.notes` | Notes |
| `org.xfce.notification` | Notifications |
| `org.xfce.panel` | Panel |
| `org.xfce.parole` | Parole Media Player |
| `org.xfce.powermanager` | Power Manager |
| `org.xfce.ristretto` | Ristretto Image Viewer |
| `org.xfce.screenshooter` | Screenshot |
| `org.xfce.session` | Session and Startup |
| `org.xfce.settings.accessibility` | Accessibility |
| `org.xfce.settings.appearance` | Appearance |
| `org.xfce.settings.color` | Color Profiles |
| `org.xfce.settings.default-applications` | Default Applications |
| `org.xfce.settings.display` | Display |
| `org.xfce.settings.editor` | Settings Editor |
| `org.xfce.settings.keyboard` | Keyboard |
| `org.xfce.settings.manager` | Settings Manager |
| `org.xfce.settings.mouse` | Mouse and Touchpad |
| `org.xfce.taskmanager` | Task Manager |
| `org.xfce.terminal` | Xfce Terminal |
| `org.xfce.terminal-settings` | Xfce Terminal Settings |
| `org.xfce.terminalemulator` | Terminal Emulator |
| `org.xfce.thunar` | Bulk Rename; Thunar Preferences; Thunar File Manager |
| `org.xfce.volman` | Removable Drives and Media |
| `org.xfce.webbrowser` | Web Browser |
| `org.xfce.workspaces` | Workspaces |
| `org.xfce.xfdesktop` | Desktop |
| `pan` | Pan Usenet Reader (VPN) |
| `preferences-system` | PetalOS Helpers |
| `preferences-system-network` | Advanced Network Configuration |
| `preferences-system-windows` | Window Appearance |
| `printer` | Start Printing; Stop Printing; Print Settings |
| `process-stop` | Stop SABnzbd |
| `sabnzbdplus` | SABnzbd (VPN); SABnzbd+ |
| `stock_xfburn` | Xfburn |
| `system-lock-screen` | Lock Private and Desktop |
| `torbrowser` | Tor Browser Launcher Settings; Tor Browser |
| `transmission` | Transmission (VPN) |
| `user-desktop` | Start Crystal Dock |
| `xarchiver` | Xarchiver |
| `xfce-sensors` | Sensor Viewer |
| `xfce4-clipman-plugin` | Clipboard Manager Settings; Clipboard Manager |
| `xfsm-logout` | Log Out |
| `xsane` | XSane |

Duplicate/legacy candidates include Pan's two desktop IDs, raw and guarded SAB
entries, generic terminal/file-manager/browser aliases, and the distribution Tor
launcher/settings alongside PetalOS's guarded Tor launcher. Review which entries
are actually intended for the final menus before commissioning distinct artwork;
their presence alone is not a request to remove apps or bypass wrappers.

The 13 other installed entries are preserved in the CSV/JSON but are hidden,
background-only or restricted to another desktop. They include the deliberately
hidden Mail Reader and Window Manager Tweaks. Do not spend a separate art slot on
background services such as Xwayland, portals or the notification daemon unless
their identity is actually exposed in a user-facing dialog.

## Menu categories, file types and common controls

### Menu-category artwork

Development (`applications-development`), Education/Science
(`applications-science`), Games (`applications-games`), Graphics
(`applications-graphics`), Internet (`applications-internet`), Multimedia
(`applications-multimedia`), Office (`applications-office`), Settings
(`preferences-system`), System (`applications-system`), Utilities
(`applications-utilities`), Other (`applications-other`), and Session
(`system-log-out`). Only populated categories need to appear in menus.

### Common file-type families

Generic document, plain text/source code, PDF, image, audio, video, archive,
spreadsheet, presentation, drawing, KeePass database, disk/encrypted-container
image, executable/script, and symbolic-link/locked/read-only emblems. Application
thumbnails are separate from file-type icons and should not be mistaken for
persistent history.

### Shared actions and window controls

Open, save/save-as, add/new, import, remove, copy, cut, paste, undo/redo, search,
refresh/retry, stop/cancel, close, settings, help/about, previous/next, back/forward,
parent folder, home, eject, play, pause, fullscreen, minimize, maximize, restore,
lock/unlock, logout, suspend, restart and shutdown.

Crystal Dock's actual context menus reference `configure`, `list-add`,
`edit-copy`, `edit-delete`, `window-close`, `trash-empty`,
`application-exit`, `help-contents`, `help-about` and
`preferences-desktop-wallpaper`. Some names need aliases in a theme even when
the custom drawing is identical.

Sam also observed that Tor Browser currently shows no minimize button. A runtime
desktop GTK probe reports `icon:minimize,maximize,close`, while the browser's
own title-bar controls show only close. The missing control is confirmed; the
sandbox/client-decoration cause still needs validation. Include minimize,
maximize/restore and close in the artwork brief, but fix button availability
separately rather than treating this as only an icon problem.

## Asset delivery and acceptance

- Transparent square SVG masters are suitable for scalable artwork; transparent
  PNG masters are also suitable, particularly for the supplied pixel-art style.
  Keep intentional pixel edges crisp when generating smaller sizes.
- Dock icons should remain clear at 48, 56, 64, 96 and 128 pixels. Supply a
  256-pixel or larger raster master for high-density displays if using PNG.
- Tray/status designs need legible 16, 22, 24, 32 and 48 pixel versions or
  purpose-designed symbolic SVGs; shrinking the detailed dock picture is not
  always legible.
- Keep a full-color application set and a coherent symbolic status/action set.
  Reuse standard icon names through aliases; no need to draw every alias twice.
- Include a recognizable generic-application fallback so an unmatched window
  never becomes an invisible task.
- Theme changes alone do not override the absolute Tor PNG path. The launcher,
  running browser identity and theme aliases must be integrated together.
- Acceptance covers cold boot, locked/unlocked Private, Wi-Fi/Ethernet transitions,
  VPN failure/reconnect, battery charging/low/unknown states, scaled displays,
  dock zoom, GTK/Qt menus, sandboxed app tasks and grouped windows.
- This is a complete inventory of the inspected desktop-entry and startup
  surfaces, plus a practical theme brief. It is not an exhaustive audit of every
  internal toolbar glyph or every MIME type in all third-party applications;
  retain an upstream fallback theme for uncovered icons.
