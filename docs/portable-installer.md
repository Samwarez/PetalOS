# Portable PetalOS Installer 0.3.0

Sam requested a Linux installer that can run without installing a `.deb` on
2026-10-25. The portable archive contains the existing GTK/CLI app and a native
administrator bootstrap, with its Python/GTK/disk-tool runtime. Extract it and
run `petal-installer`; no permanent installer backend, polkit action or service
is created. The `.deb` remains an alternative.

## Runtime and privilege boundary

`local/installer/build-portable.py` resolves the installed amd64/all dependency
closure of explicit Debian trixie runtime packages. It verifies copied files
against dpkg package checksums and records package versions. Symlinks to public
package files become ordinary files; links into `/etc` and local host
configuration are excluded. Runtime libraries, GTK typelibs, schemas, fonts,
public Mozilla CA certificates, copyright files and common license texts are
included. GSettings and MIME caches are regenerated from the checked package
inputs. Image-loader paths are expanded into a sealed in-memory cache at launch,
so PNG/SVG decoding works after relocation without a host MIME database. The
archive contains no host credentials, VPN profiles or OS payload.

The normal-user launcher selects the bundled loader/Python/libraries and disables
Python user-site imports. Tool wrappers keep shell subcommands in the portable
runtime. Portable CLI execution and GTK administrator operations use the same
bridge and confirmations as the installed app. The authorization subprocess gets
a small host environment, excluding portable library paths, Python injection
variables and GitHub tokens.

The build pins a SHA-256 digest and exact byte count of the framed application
and runtime files into the **static** `petal-admin` executable. After the host's
generic `pkexec` authorization, that bootstrap:

1. Creates a fresh root-only directory under `/run` with dumps disabled.
2. Receives a bounded stream of regular files, rejecting escapes, aliases,
   duplicates, special modes, excessive entries and premature EOF.
3. Verifies the complete stream with the Linux kernel SHA-256 API. It does not
   execute any staged code before the compiled digest matches.
4. Forks a worker in a private mount namespace, with mount propagation disabled.
   The verified runtime supplies `/usr` read-only inside that namespace. Host
   device/mount checks and source/download paths remain accessible.
5. Executes the existing root-owned isolated Python backend. Its protocol
   accepts only reviewed installer operations. The backend independently
   reconstructs the plan, checks disk identity and verifies OS payloads before
   writing. Passwords arrive after the public-code stream and stay in memory.
6. Waits for worker cleanup and removes the staged runtime. EOF or a cancel
   packet reaches the worker's existing cancellation path. The GUI does not
   run with administrator privileges.

The worker reads packets without prefetching cancellation bytes and polls its
input descriptor without Python buffered IO. Its monitor stops and joins after
completion. This fixes a shutdown abort exposed by a real successful wipe when
the client kept its pipe open. Local regressions cover idle shutdown, immediate
queued cancellation, EOF and oversized/incomplete packets; the disposable VM
checks cancellation and a successful operation through the actual worker.

Private mount namespaces do not inherit future host mount events. The native
supervisor stays in the original namespace, and the root worker reads its live
`/proc/PID/mountinfo` before drive selection and on each target recheck. New host
mounts of the target or its children stop the operation. Missing or malformed
host mount information also stops it. Worker-owned mounts remain confined to
the worker and do not produce false host-mount refusals. The VM fixture mounts
the selected USB read-only in the original namespace only after the worker's
private namespace is ready, then verifies refusal and unchanged drive bytes.

There is no fallback to the installed backend, no modification of host polkit
rules and no disabling of device, mounted-volume or credential checks. This is
not a sandbox for arbitrary untrusted app code: the user must trust the portable
download just as they must trust an installed package. A matching checksum or
self-check is not an independent publisher signature. A forced supervisor kill
or power loss may leave only the root-protected public runtime until reboot.

The initial host contract is an amd64 Linux desktop with merged `/usr`, a usable
`pkexec` authentication agent, private mount namespaces and the kernel hash API.
No FUSE mount or unprivileged user namespace is required. Bundled glibc/loader
remove the app's dependency on the host Python, GTK and disk-tool versions.
Kernel, display/session services and administrator authorization remain host
facilities. Cross-distribution acceptance must be reported separately.

## Verification

The [2026-10-25 verification record](portable-installer-20261025.json) records
46 passing local tests, five native GTK checks on the exact packaged runtime,
and 25 successful disposable VM assertions, including the new external-host
mount refusal. The final extracted package matches maintained application source
and its archive/Debian package checksums. The agent's build/VM work changed no
host package or physical medium. No full installation/update or firmware
acceptance was repeated using the portable runtime.

Sam subsequently confirmed that the desktop administrator password prompt
worked and that the portable app successfully wiped the physical card using
the quick option. This is user-reported hardware acceptance. The GUI's quick
wipe is "Remove encryption keys only (quick)" (`keys-only`); this report does
not establish full overwrite/readback or forensic erasure. The agent did not
inspect the card or repeat the operation. Full physical installation/update/boot
and acceptance on other hosts remain outstanding.

```sh
python3 -B -m unittest discover -s local/installer/tests -v
python3 -B local/installer/build-portable.py
../installer-dist/petalos-installer-0.3.0-linux-amd64/petal-installer --portable-check
python3 -B tests/run-portable-installer-vm.py ../releases/COMPLETED_RELEASE \
  ../installer-dist/petalos-installer-0.3.0-linux-amd64
```

The fresh VM has no network, host shares, installed PetalOS backend or existing
writable image. Native GUI tests run as an ordinary uid using the packaged
Broadway display server and bundled Python/GTK. They assert that loaded shared
libraries come from the portable tree. The production native bootstrap is tested
as root inside the VM, including altered/traversing/truncated transfers, stale
plan refusal, cancellation, temporary-directory cleanup and real random
wipe/readback of a newly allocated disposable USB disk. The authorization prompt
itself is not bypassed in production; direct root launch in this isolated
fixture tests the worker after authorization and does not establish real desktop
polkit interaction acceptance.

The prior installer engine's installation/update/firmware results remain useful
history, but they are not a substitute for testing those operations using this
portable runtime. Physical media remain outside the agent's operations; the
user-performed quick wipe is recorded above. A clean split-storage OS release
is still required before the next physical installation.
