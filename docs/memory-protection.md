# Memory protection limits

Closing Private removes its active dm-crypt mapping/key and ends its application
roles. That does not prove all plaintext, passphrase, CPU/GPU or kernel copies
were overwritten. Dropping caches frees memory; it is not a verified full wipe.
A panic or crash does not erase RAM. Controlled shutdown is preferable to a
panic, but sudden power loss can bypass software cleanup.

Source boot defaults now request `init_on_alloc=1 init_on_free=1`, and the
normal encrypted-release updater prepares those same flags for a detached test
clone. No running boot or physical card has been updated with those flags.
They zero newly allocated/freed memory, not every possible memory location.
A diskless, network-free QEMU boot of the SHA256-verified release kernel passed
and reported `heap alloc:on, heap free:on`. The normal encrypted desktop boot
has not been updated with these flags. Full-image boot, realistic performance
and memory-retention testing remain pending.
See [kernel parameters](https://docs.kernel.org/admin-guide/kernel-parameters.html)
and [Tails' current memory-erasure limits](https://tails.net/contribute/design/memory_erasure/).

Swap remains disabled; core dumps are disabled by limits and kernel policy;
journals are bounded in RAM. Hibernation is disabled in staged sleep policy.
Suspend is currently disabled because its QEMU test unexpectedly powered off.
A complete, reliable shutdown-scrub implementation has not been added.

Hardware memory encryption needs verified CPU, firmware and kernel support;
portable software cannot assume it exists. Conventional QEMU testing cannot
prove physical RAM erasure or protect guest memory from a privileged host.
The host may retain RAM or other copies outside the guest's control.

Do not claim forensic nonrecoverability, guaranteed memory erasure or Tails
equivalence from functional VM tests. Existing automatic DATA keys and old
header/backups require separate retirement review for independent Private
protection after compelled SYSTEM disclosure.
