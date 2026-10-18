# XFCE native-Wayland migration

Current acceptance and remaining work: [2026-10-13 checkpoint](wayland-acceptance-20261013.md).
Historical progress notes below include superseded pending states.

Sam chose XFCE on Wayland, seamless application windows and no X11 application
fallback on 2026-10-13. The future local AI/voice/vision/avatar design must use
separate permissions and a trusted action broker. Do not give the inference
model an unrestricted desktop socket, root terminal or automatic Private access.

Debian trixie ships XFCE 4.20 and Labwc 0.8.3. XFCE upstream calls its Wayland
support experimental; xfwm4 is still X11-only. Labwc supplies window management
for the native session. Source has an optional `PetalOS XFCE (Wayland test)`
session; the accepted production default has not changed.

The test session forces native GTK/Qt/Firefox/SDL backends, unsets DISPLAY in
the actual session client, and overrides wlroots' Xwayland executable with a
fixed denial helper. Debian's Labwc package depends on xwayland, so installation
alone must not be mistaken for running or accepting X11 compatibility clients.
Confirm there is no Xwayland process during application acceptance.

The security-context-v1 client in `wayland_context.py` creates restricted
compositor listeners. Do not expose the unrestricted desktop socket to network
application compartments. The headless QEMU test
`tests/wayland-context-guest.py` passed normal-window protocol availability,
hidden screenshot/input/control/factory protocols, creator disconnect, lease
revocation and continued compositor responsiveness using trixie Labwc. This
does not yet prove real-UID/filesystem integration, clipboard policy or full
GUI/session acceptance. Production broker integration remains pending.

Required follow-up: actual XFCE panel/background/theme, native app inventory,
application role/profile integration, graphical sudo/polkit/admin-setup dialogs,
Wayland screen lock, persistence overrides, browser/Tor connectivity and all
VPN failure/reconnect tests. Check every existing application and panel plugin;
an older application may support Wayland, and a current build may still require
X11. Report incompatible features rather than enabling a silent fallback.

The X11 sandbox prototype from the previous night remains unfinished. Preserve
the original disk/release and snapshots; never promote its old GUI liveness
checks as acceptance. No physical-card update is authorized.

2026-10-13 graphical test: the optional session reached a usable XFCE desktop,
but Sam reported missing wallpaper and flickering during movement. The running
QEMU guest launcher was changed in RAM to `WLR_RENDERER=pixman` and
`LIBGL_ALWAYS_SOFTWARE=1`, then LightDM restarted successfully. This is a VM
experiment, not a source default for hardware. Labwc, panel and xfdesktop each
have one process; Xwayland has none. The Wayland output is `Virtual-1`; its
workspace0 wallpaper was set to the bundled `/usr/share/backgrounds/xfce/xfce-blue.jpg`
with image-style 5. Existing settings only had older monitor0/monitor1 keys.
Visual acceptance of both changes remains pending; do not treat process counts
or successful xfconf writes as proof of rendering correctness.

Follow-up: Sam confirmed software rendering eliminated flicker, but initially
no wallpaper appeared. The desktop uses a separate D-Bus session from
`/run/user/1000/bus`; earlier settings writes went to a different xfconfd.
Apply graphical configuration using the active desktop's session environment,
not an assumed systemd-user bus. The bundled wallpaper and image-style were
now written and read back successfully through that actual session, followed
by xfdesktop reload. Wallpaper visual confirmation remains pending. The
temporary settings window and RAM diagnostic log were cleaned up.

Resolved visually: Sam confirmed flicker is gone and the native `swaybg`
renderer displays the wallpaper. The integration probe found one fallback
workspace group with one active workspace but zero monitors; xfdesktop needs
that monitor association to populate its backdrop workspace. Correct settings,
Adwaita and disabling icons did not fix it. Icons and theme were restored.

Source now includes trixie `swaybg`, a Wayland-only trusted desktop autostart
helper, bundled default wallpaper and existing XFCE per-monitor overrides.
The helper watches xfconf changes without logging image paths or copying
Private content. A public RAM-staged copy ran successfully in the guest:
one renderer, settings change replaced it, restoring settings replaced it
again. QEMU-only software rendering is conditional on DMI vendor `QEMU`;
the current guest matches. No Xwayland process was present. No rebuild yet.
The guest helper/binary are test copies in `/run/user/1000`, not installed
packages. Boot ordering, monitor hotplug and xfdesktop crash/restart stacking
still need acceptance before promoting the Wayland session to production.

Continuation: the wallpaper helper now tracks xfdesktop restarts and output
changes. QEMU checks passed helper-stop cleanup, single initial renderer,
renderer replacement after desktop restart and helper survival. Monitor
hotplug itself remains untested. The active network-readiness gate passed.

Prepared in source, not staged/accepted: native compartment listener binding
replaces Xephyr/private xfwm4; trusted foreign-toplevel observation checks mapped
native windows without collecting titles; fixed Petal-session discovery replaces
hardcoded X11 environment in private-admin setup; browser policy uses Wayland
instead of X abstraction. `tests/wayland-native-boundary-guest.py` is a public
real-UID/mount/network/AppArmor/native-window fixture. Syntax passed; live
security/application acceptance is pending. Offline app migration is still
unfinished. Do not build/promote these source changes yet.

The native graphical sudo prompt appeared and accepted Sam's private password.
The initial host heredoc launcher then hit EOF; it did not leave a maintenance
channel. `tests/open-root-maintenance.py` fixes SSH stdin ownership and disables
echo/canonical input only on its own PTY. A second native graphical prompt is
currently awaiting input, host exec session 44008. No root-ready response has
been received for it. Public helper at `/tmp/petalos-public-maintenance.py`;
remove that and `/run/petalos-root-maintenance.py`, then close the authenticated
lease at completion. Never send the password through host tools/chat.

Sources: [XFCE roadmap](https://wiki.xfce.org/releng/wayland_roadmap),
[trixie session package](https://packages.debian.org/trixie/xfce4-session),
[Labwc 0.8.3 global filter](https://github.com/labwc/labwc/blob/0.8.3/src/server.c),
[security-context protocol](https://gitlab.freedesktop.org/wayland/wayland-protocols/-/blob/main/staging/security-context/security-context-v1.xml).
