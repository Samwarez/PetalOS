# Security hardening checkpoint — unfinished

Sam requested a pause for the night. No rebuild, release promotion, test-disk
clone update or physical-card write was performed. Do not build or present this
prototype as accepted: GUI/browser failures remain.

## Verified during this session

- Existing backup checksums were verified before changes. The initial code
  snapshot `snapshots/code-before-compartments-20261012-223226.tar.gz` is preserved
  and its checksum passed.
- Sam entered a new private administrator password in the guest's hidden
  dialog. Only the hash was stored in encrypted SYSTEM at
  `/.petalos-auth/root-admin.hash`, outside squashfs. Guest-side validation of
  that protected file passed without displaying/copying its contents.
- General sudo rejected the public Petal login password; a graphical sudo
  `/usr/bin/true` test accepted the private administrator password. Exact
  read-only network readiness remained passwordless. Sudo policy validation
  passed. Public Petal login is unchanged.
- Dedicated real application UIDs 940–945 and 947 were created. Actual running
  Tor/backend/browser/network applications had their expected AppArmor labels
  in enforce mode. The initial process-liveness checks were too weak for GUI
  acceptance and have been replaced in source.
- A public-canary, simulated browser-code-execution probe passed: UID 941,
  no supplementary groups/effective capabilities, IPv4/IPv6 socket creation
  denied, parent home/X11 socket and unrelated Private canary hidden, own Tor
  download canary readable, and firewall unchanged during that probe.
- The Tor SAFECOOKIE front-end test passed authentication and rejected VPN
  address queries, SOCKS/transport reconfiguration, LOADCONF and shutdown.
  At that point the isolated Tor backend had bootstrapped to 100%.
- Scoped UID firewall drops were added without removing existing rules:
  network roles cannot initiate host-loopback connections or send over a
  physical interface. WireGuard/DNS/time constraints remain. The final active
  network gate passed after prototype applications were stopped.
- The SAB management Unix bridge answered HTTP 303. Private browser PulseAudio
  started, and its listed sources contained only playback monitors. Audible
  playback and microphone-negative tests remain unverified.
- Host Python syntax/build-input validation and desktop-helper, download
  preparation, exit-IP and SAB navigation fixture tests passed. These do not
  establish full application acceptance or failure-case security.

## Open failures and review requirements

- Sam reported frozen/black nested windows and broken title characters.
  Titles now use ASCII; Xephyr uses `-noreset`, `XEPHYR_NO_SHM=1`, and a private
  xfwm4 window manager. Writable private `/dev/shm` and software rendering were
  added. Sam subsequently saw Transmission inside the larger black container.
  Main-window maximization is implemented, but Transmission still failed the
  mapped-window readiness check (empty `_NET_CLIENT_LIST`). Diagnose this with
  public-only state; do not dump saved settings or application logs.
- Tor previously reported another browser holding its profile lock. Real-UID
  orphan cleanup, fresh RAM-home reset and bubblewrap `--die-with-parent` were
  added. A new browser passed mapped-window startup but could not load sites.
- The final Unix SOCKS HTTPS probe timed out. A subsequent direct backend
  control query also timed out; Tor's process was sleeping in `do_epoll_wait`.
  Initial successful bootstrap/control tests must not be confused with this
  later failure. Recreate/test the backend, SOCKS bridge and native browser
  control flow separately. Never relax the browser's direct-network denial.
- Review supervisor termination, orphan Xephyr/process cleanup and PID identity
  handling. New `reset_ram` uses pidfds and fd-safe rmtree, but failure/restart
  tests are still required. Avoid privileged writes through mutable role homes.
- Review shared public Tor distribution caching: cache selection must follow
  an installed signed archive change. Make sure failed extraction cannot make
  an incomplete cache look accepted. Test tampered/missing policies fail closed.
- File-association import is staged, not tested. It reads bounded selected files
  as Petal into root-owned RAM staging and delegates readonly copies. Test
  symlinks, concurrent mutations, size limits, unsupported flags and restart.
- ACL delegation now pins inodes, rejects unexpected owners/types and skips
  symlinks. Persistence, explicit-0600 downloads and access while apps remain
  open need tests. Do not restore broad Private traversal to application UIDs.
- Existing local/offline wrappers still share the parent desktop and trusted
  Petal context. Offline real-UID isolation is unfinished/unexposed by the
  broker. This is a remaining attack surface, not full desktop isolation.
- Re-run failure/disconnect/reconnect checks, Tor HTTP confirmation, audio,
  complete GUI acceptance and encrypted reboot after fixes, then one batched
  build and preserved-clone update. Vendor CVEs and authenticated boot/rollback
  design from the audit remain separate unresolved issues.

## Current VM and next session

The disk remains
`/home/sam/portable-live/testing/sessions/20261011-184902-563580/encrypted-boot-20261012-211751-400024.img`.
Inspect `/run/user/1000/petalos-encrypted-test.json` and actual QEMU processes
before any storage operation. Dedicated pinned SSH remains the test transport.

All tracked prototype compartments were stopped before the pause. The
authenticated temporary root-stdin maintenance session is being closed;
it is not a persistent service/listener. Check for residual dedicated-role
processes before resuming. Never kill all UID-1000 processes.

Source and guest RAM have diverged. Native network binaries were diverted in
guest RAM and public wrappers/profiles/admin policy were staged there, while
some latest source edits have not been staged. Inspect actual files. The
current disk still boots the older release; RAM-only changes disappear after
shutdown. The new private admin hash survives in encrypted SYSTEM, but its
automatic boot restoration requires the new OS hook/service, not the older
release. Do not tell Sam it is already baked into a release.

For future authenticated root maintenance use guest sudo's graphical askpass
and Sam's private credential; never ask for it in chat or put it in host tool
arguments. The passwordless broker is not a general maintenance channel.

The new trixie packages in the VM are xserver-xephyr and wmctrl. Source package
lists also include acl and xauth. No unstable packages were installed.
