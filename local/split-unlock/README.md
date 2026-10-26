# Split-storage initramfs unlock helper

Build with `python3 -B local/split-unlock/build.py`. The static executable and
source/builder/binary provenance are generated under ignored
`config/includes.chroot/usr/local/share/portable/native-split-unlock/`.
Release preflight rejects changed source paired with a stale binary. Hook 0080
installs the helper before package hooks and the first initramfs refresh at
0912; the initramfs hook includes it and normal askpass. Preflight also rejects
missing/nonexecutable hooks or an initramfs refresh ordered before installation.
Run `python3 -B tests/check-split-build-hooks.py` to exercise this build ordering
and packaging with Debian's real initramfs copy functions, without sudo.

One Plymouth or text prompt pipes the passphrase to this helper. It keeps at most
512 bytes in locked, non-dumpable RAM, sends them to each cryptsetup child through
anonymous pipes and clears its buffer. It requires different sibling block
partitions, opens OS read-only, opens SYSTEM independently and rolls OS back if
settings fails. It never opens Private or loads a SYSTEM-held automatic DATA key.

Test with `python3 -B local/split-unlock/test.py`. The fake cryptsetup is selected
only at compile time in an isolated test build. Production has a fixed tool path
and no runtime override environment. The VM uses the production static binary
against actual encrypted sibling partitions.

Legacy combined-layout boot remains supported. New installer plans require
layout 2 and never turn an update into a repartitioning migration. One-prompt
unlock is not atomic against power loss/SIGKILL; keys are transient, and OS is
read-only. Graceful termination during activation is deferred until both
mappings have been closed.
