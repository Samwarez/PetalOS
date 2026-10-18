# RC 1 ThinkPad hardware test — 2026-10-17

Test machine: ThinkPad T14s, Lenovo model 21CQCTO1WW. SSH pinned to existing
hardware identity, isolated spare host Ethernet, main VPN/firewall unchanged.
Private initially closed. Previous forced-shutdown boot journal was RAM-only
and is unavailable. Do not classify the sleep failure without reproduction.

| Finding | Current status |
|---|---|
| KeePassXC cannot save anywhere | Reproduced with real CLI in production sandbox. AppArmor rejected O_TMPFILE link with deleted-entry name lookup, errno 2. Added mediate_deleted to KeePassXC profile; real create/reopen/update and IPv4/IPv6 denial pass. User confirmed GUI save works. Source + guest RAM only. |
| Mail Reader opens unconfigured helper | Hidden launcher, removed default helper and vendor mail-key binding in source hook. Applied launcher/default changes in RAM. Saved panel layout untouched. |
| Solid/gradient wallpaper always black | Renderer used fixed #202020. Added XFCE rgba1/rgba2 and color-style handling, bounded RAM-generated gradient. Solid/both axes/wallpaper command tests pass; deployed renderer in RAM. User confirmed desktop background works. XFCE enum reference: https://github.com/xfce-mirror/xfdesktop/blob/master/common/xfdesktop-common.h |
| Private/Documents locked | Parent repair previously ran only when an app starts. Added repair of just Documents/Downloads parents after successful graphical unlock. Retry/cancel/error regressions pass. Source + RAM. Private unlocked; both parents owner1000 mode0700; explicit Petal read/write/search probe passed. User confirmed Thunar/Documents opens normally. |
| Trash includes desktop-setting.tar | Confirmed one known legacy archive in Private/.Trash-1000/files. This is persistent user Trash, not a root/home persistence leak. Left untouched. |
| Private/PortableSettings remains | Directory was empty after Private unlock; removed only the empty directory. |
| Players/editors cannot browse shared content | Current per-app mounts intentional but do not meet updated user requirement. Needs shared user-content access without system settings, credentials, host runtime, or network exposure. Pending. |
| Volume changes without indicator | Added trusted-desktop pactl helper + explicit Labwc volume/mute keys, percentage/progress notification. Source + RAM; compositor reconfigured successfully after supplying LABWC_PID. User saw working indicator but alerts stacked. Replaced hint-only coalescing with explicit --print-id/--replace-id and bounded ID in RAM lock file; mock two-press regression passed. RAM updated; latest visual check pending. |
| Airplane key disables but cannot re-enable Wi-Fi | Pending reproduction/state tracing. |
| Black screen after lid/sleep unlock | Release blocker; prior logs lost. Current s2idle-only machine. Found local suspend and sleep-delay inhibitor incorrectly required admin auth; no power/locker inhibitors registered. Added narrow local desktop suspend/inhibitor exceptions. All 16 authorization checks passed including protected admin actions and remote/app power-off checks. Refresh of actual local session controls + controlled resume test pending; NOT declared fixed. |

Root maintenance session authenticated via graphical administrator dialog;
RAM-only helper staged for this exact Lenovo model. Close helper session and
clear sudo state at the end of work. No build launched or physical card/image
update authorized as part of this live diagnostic session. Live changes reside
in RAM; stage source for a later combined build.

Added tests/keepass-save-guest.py: real database create/reopen/update/read-back
plus IPv4+IPv6 denials, all six PASS in production sandbox. Fixture only, no
real databases inspected. No external network used by probes. Temporary tracer
was fetched as public trixie package on host, staged only in guest RAM; remove
at end. Test profile was never put in complain mode; one comparison used an
unconfined synthetic child inside the same isolated sandbox, then returned to
the production profile. No user application confinement was disabled.

KeePassXC was still running from before Private unlock: worker storage=ram,
while Private was now available. User saved/closed it normally. Reopened with
Private available. Fresh production sandbox real CLI Private-folder create
passed. GUI Private/save confirmation pending. Existing running applications
do not gain mounts dynamically; safe restart required. Do not kill an editor
to refresh mounts while it has unsaved work.

Lid test 21:45 guest UTC: SSH remained responsive while lid was closed;
logind reported lid closed and repeatedly "Requested suspend operation not
supported, ignoring." /etc/systemd/sleep.conf.d/20-petalos.conf explicitly sets
AllowSuspend=no (historical QEMU failure gate). Kernel supports mem/freeze,
mem_sleep=s2idle; CanSuspend returns no. Therefore this test did NOT suspend
or resume. gtklock running, Private mapper absent while lid closed. Waiting
for actual open-lid unlock result. Do not conflate this with suspend recovery.
KeePassXC GUI save in Private confirmed by user after safe restart.

After lid open and SYSTEM authentication, gtklock had exited and all desktop
processes were alive. DRM card0-eDP-1 was connected but disabled, brightness
32/255 and backlight power0. Reapplying the enabled eDP-1 configuration via
public trixie wlr-randr restored physical scanout; user confirmed desktop
returned without reboot. Output-management state had still said Enabled=yes:
logical enablement and physical power/scanout state differed.

Added wlr-randr to desktop package list and portable-display-wake helper,
invoked by portable-lock only after gtklock returns success. Keeps original
lock fd in parent and child, skips intentionally disabled monitors and skips
internal panels if lid remains closed. No Private reopening. Host tests cover
failed storage/authentication never waking and helper connector/lid handling;
live helper exit0. Source+RAM deployed. User repeating lid/open/unlock now;
actual suspend still AllowSuspend=no and NOT verified.

The first post-auth wake attempt was insufficient: user saw desktop briefly,
then black. Temporary power-manager SIGSTOP and display restore kept scanout
on; manager was SIGCONT'd afterward and is running normally. No daemon left
paused. Inspected XFCE 4.20 manager source: lid-lock handler synchronously calls
xfce_screensaver_lock, then sets DPMS off after it returns. Our foreground
LockCommand waited until authentication/unlock, incorrectly deferring that
DPMS-off until after unlock. This explains the second blackout.

Corrected portable-lock to use gtklock --daemonize with --unlock-command set
to the display recovery helper. Verified exact gtklock 4.0.0 source
(commit 66321fb2bf0d5869d779e7ac6b4d8d9c272ea707): daemon parent waits for
SIGUSR1 sent by compositor locked callback; not a blind background spawn.
Private closure precedes invocation. Locker daemon inherits flock descriptor.
New regression verifies storage failure blocks locker, daemon readiness failure
reports error, helper is not called directly by LockCommand, and unlock hook
is supplied. Source+RAM installed, desktop restored, user repeats lid test.
Suspend remains disabled and untested. Previous synchronous-parent tests were
replaced to match this final readiness contract. No successful test claimed yet.
Source refs: https://github.com/xfce-mirror/xfce4-power-manager/blob/xfce4-power-manager-4.20.0/src/xfpm-manager.c
and https://github.com/jovanlanik/gtklock/tree/v4.0.0/src .

Confirmed real ThinkPad s2idle cycle: kernel suspend entry 22:04:00 and exit
22:06:54 guest UTC. systemd-suspend.service completed successfully; same boot ID
8cc4a75b-8267-4ff3-9029-20c22a2ea62b, user confirmed sleep LED and usable desktop.
Private remained closed. This cycle started with Private already closed; an
open-Private sleep cycle is still a separate pending privacy check.

Source 20-petalos.conf now AllowSuspend=yes, all three hibernation variants no.
Synthetic sleep hook checks PASS: pre locks, closure error/timeout powers off,
post never unlocks; lock-ready regression PASS. Source+RAM only, not rebuilt.
Removed CtrlAltR test binding/helper and standalone RAM override; installed
source-equivalent RAM config and verified suspend yes, disk sleep variants no.
Diagnostic tracer/output tool temp copies removed; packaged wlr-randr remains
in RAM for the production helper. Privileged maintenance52660 closed, helper
files removed and Petal sudo timestamps cleared. Host isolated peer remains.
SSH-only link survives normal operation but root maintenance43084 timed out
while asleep; ordinary SSH reconnected with pinned identity. User entered
admin once for post-wake logs/cleanup, then maintenance closed again.

Open-Private sleep boundary passed: Sam unlocked Private, closed/reopened lid,
authenticated SYSTEM and confirmed Private stayed locked. Ordinary pinned SSH
confirmed portable_data mapping absent, unchanged boot ID, suspend service
Result=success and ExecMainStatus=0. Functional s2idle/resume + separate Private
closure/unlock behavior now verified on this ThinkPad. This does not establish
RAM erasure or broader forensic guarantees. Changes remain source+guest RAM
until the next combined build/card update.


VeraCrypt portable AppImage 1.26.29: mount appeared stuck. Function-only
backtrace showed mount worker awaiting AdminPasswordGUIRequestHandler and GUI
inside WaitDialog::OnAdminPasswordRequest modal loop. Three native VeraCrypt
windows included a hidden administrator prompt. Trusted compositor activation
brought it forward; Sam confirmed visible, entered administrator password,
and actual exFAT filesystem mounted successfully. No content inspected.
Temporary RAM debugger/dependencies removed; admin session closed afterward.
Window stacking remains a usability issue; no general focus-policy change was
made. The AppImage runtime FUSE mount must not be mistaken for a decrypted
volume when checking whether an interrupted mount attempt can be terminated.
