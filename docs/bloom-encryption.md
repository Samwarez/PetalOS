# Bloom 0.4.1: protection tiers and passphrases

Sam requested the installer name **Bloom**, three clear Fast/Balanced/Paranoid
choices, and passphrases without hardware-token support for this release. This
renames the app, launchers, window identity, desktop entry, Debian package and
polkit backend identity. The PetalOS operating system, release schemas, storage
labels and backup restrictions retain their existing names and meaning.

The unchanged pink flower emblem is used by Bloom. The primary command is
`bloom`; `petal-installer` is an executable compatibility alias. The portable
folder is `bloom-0.4.1-linux-amd64`; the Debian package is
`bloom-installer_0.4.1_all.deb`. Installing the Debian alternative replaces the
old `petalos-installer` package; the agent does not install or replace host
packages. Existing portable 0.3.0 artifacts remain preserved.

## Security and performance

All profiles use LUKS2 with `aes-xts-plain64`, a 512-bit XTS key comprising two
256-bit AES keys, and Argon2id keyslots. XTS's two-key total is not advertised as
512-bit AES security. The obsolete AES-128 and ambiguous low-memory choices are
removed from the new-install menu. Default selection remains Balanced.

| Profile | Minimum / maximum Argon2id RAM | Initial target | Parallel limit |
| --- | --- | --- | --- |
| Fast — Legacy Friendly | 32 / 64 MiB | 1 second | 1 CPU |
| Balanced — Recommended | 256 / 512 MiB | 2 seconds | 4 CPUs |
| Paranoid — Maximum Protection | 1 / 2 GiB | 5 seconds | 4 CPUs |

Creation minimums are independent of the tier: **SYSTEM 15 characters,
administrator 15, Private 24**. They apply in the GUI, CLI and privileged backend.
All three credentials must differ. Spaces are allowed; there is no required mix
of uppercase, numbers or symbols. Unicode code points count as characters; the
existing 512-byte UTF-8 cap and prohibition of NUL/line breaks still apply.
Existing media retain their credentials; update, settings and recovery operations
do not impose creation minimums on an existing passphrase.

Each new-password field has a live, local strength meter using Debian's
`libzxcvbn0` (zxcvbn-c), bundled with the portable edition and declared as a
Debian-package dependency. It estimates common dictionary words, repetitions,
sequences, keyboard patterns and substitutions, rather than awarding strength
for character classes alone. Length compliance is displayed separately from
the estimate: a repeated 24-character password can meet the minimum and still
show Very weak. Scores are advisory; the stated length and separation rules
determine acceptance. No password or score is sent to a service or persisted.

The meter uses conservative display bands at estimated 20/36/60/80 bits and
does not display bits or cracking-time predictions. It examines at most the
first 128 ASCII characters to bound typing work. Non-ASCII/control text or an
unavailable estimator displays **strength estimate unavailable**, never a guessed
high score. Unicode passwords remain accepted under the same backend rules.
The estimator cannot know how a password was chosen or guarantee security.

The backend first checks resource headroom and runs a real, non-destructive
`cryptsetup benchmark --pbkdf argon2id`. It caps RAM at the tier maximum and half
of available/total memory, accounting for cgroup-v2 ancestor limits, and caps
parallelism using CPU affinity. If a slow CPU requires the benchmark to reduce
memory below the tier floor, Bloom retries at twice and four times the initial
time budget. It rejects a tier still below its floor **before opening or erasing
the target**. It does not substitute PBKDF2 or a weaker tier.

The measured iteration/memory/parallel costs are validated, then fixed for the
three separately formatted and independently keyed volumes. Each real header
is read back to verify the cipher, key size and actual Argon2id values. The
completion result includes only these public calibration values. Updates and
recovery do not silently change existing keyslots or credential requirements.

The frontend and privileged backend enforce new-credential length and
separation. These checks cannot determine entropy. Guidance calls for unique,
randomly chosen words or characters, especially with Paranoid. No secrets are
written to plan files, environment variables, command arguments or reports.
The administrator credential remains separate from SYSTEM and Private and
retains its existing OS authentication mechanism; the Argon2id tiers describe
the storage keyslots, not the administrator password hash.

CPU calibration targets time on the **installer host**. OS and settings derive
sequentially under one SYSTEM prompt; Private is separate. Older computers may
unlock more slowly or lack sufficient memory. All tiers have the same ongoing
AES disk-encryption algorithm, so Fast cannot promise negligible I/O overhead
on hardware without AES acceleration. The OS still runs from RAM.

NIST describes AES-256 as retaining a substantial margin against known quantum
key-search attacks; this symmetric-key margin applies to every tier. Bloom does
not label the whole system or a weak passphrase "quantum safe", or promise
protection against arbitrary resources, compromised endpoints or all future
attacks. Paranoid's goal is higher offline-guessing cost with long random
credentials. Hardware tokens/additional factors are deferred at Sam's request.

## Sources

- [NIST post-quantum FAQ](https://csrc.nist.gov/projects/post-quantum-cryptography/faqs): practical limits of Grover's algorithm and long-lived AES-192/AES-256 security margins.
- [RFC 9106, Argon2](https://www.rfc-editor.org/rfc/rfc9106.html): memory-hard password derivation, parameter tradeoffs, and 2 GiB / memory-constrained recommendations. Bloom's calibrated LUKS profiles are not claimed to reproduce the RFC's exact fixed parameter sets.
- [cryptsetup luksFormat manual](https://man7.org/linux/man-pages/man8/cryptsetup-luksFormat.8.html): automatic benchmarking can reduce memory/parallelism; actual header values must be checked. Bloom fixes already-measured parameters and keeps headroom instead of guessing forced iteration counts.

## Verification scope

Historical 0.4.0 results: [portable runtime and GUI](bloom-portable-20261025.json),
[fresh installation, update and signed boot](bloom-installer-vm-20261025.json),
and [all three native tier/header checks](bloom-encryption-native-20261025.json).
The 0.4.0 local suite passed 53 checks; six native GTK tests passed on the packaged
runtime, including the tier selector and dialog fit. The portable worker suite
passes 25 disposable VM assertions. The engine suite completed an actual Fast
installation with calibrated, verified headers, OS-only update with byte-identical
settings/Private partitions, interrupted wipe/retry and signed UEFI one-prompt
unlock. Its OS payload is synthetic and stops before a full desktop session.
All three tiers separately pass real native calibration, nine actual LUKS2
header checks and correct/wrong credential tests using newly created files.
The agent performed no physical-card action or host package installation.

`tests/check-bloom-encryption.py` calibrates each production tier on the real
host CPU, creates new mode-0600 regular images in a private `/tmp` directory,
formats OS/settings/Private headers with independent fresh keys, reads each
header back, and checks correct/wrong disposable credentials. It never accepts
a block-device target, opens a mapping or uses personal credentials. Its public
results are [native encryption checks](bloom-encryption-native-20261025.json).

Unit regressions cover minimum resource refusal before target opening, slow-CPU
time extension, bad benchmark output, unexpected low-cost parameters, stored
header mismatch and distinct long Paranoid credentials. Native GTK checks cover
Bloom branding, all three choices, changing descriptions and dialog height.
Portable runtime/worker acceptance uses a new networkless QEMU VM and disposable
USB, preserving all earlier images and physical media. Physical installation
still requires a clean split-storage OS build and separate explicit instruction.

## Future option: an installation-specific Private keyfile

Deferred design discussion, not an implemented feature or a change to existing
media. A random, per-installation secret could be stored root-only inside the
encrypted SYSTEM settings store and combined with the Private passphrase so
**both** are required. It must survive OS-only updates and never be baked into
the generic OS image, initrd, boot partition, source or public release.

Simply adding a second LUKS keyslot for a keyfile provides another independent
unlock method: passphrase **or** keyfile. That does not enforce the proposed
requirement. A future design needs a reviewed combination/enrollment protocol,
recovery and backup handling, locking tests and an explicit migration decision.
Any passphrase-only recovery slot would bypass the requirement by design. Loss
of the sole required keyfile without a recovery path would make Private
unrecoverable even with the correct passphrase.

A hidden filename supplies no cryptographic security. Such a keyfile binds
unlocking to possession of the installation secret, not to a running PetalOS
environment: anyone who can obtain the keyfile and Private passphrase can use
them from another OS. SYSTEM encryption protects the file when shut down; root
compromise after SYSTEM unlock can expose it. SYSTEM settings can also contain
VPN credentials and other sensitive preferences, so SYSTEM remains important.

See the [cryptsetup FAQ](https://gitlab.com/cryptsetup/cryptsetup/-/blob/main/FAQ.md)
for the volume-key/keyslot model and the
[zxcvbn-c API](https://github.com/tsyrogit/zxcvbn-c/blob/master/zxcvbn.h) for the
local estimator interface.

## Future option: a duress passphrase

Sam requested exploration of a separate duress passphrase that invalidates
encryption keys, similar to Bloom's quick key-only wipe. Deferred only: there
is no duress credential, trigger, key removal or migration in Bloom 0.4.1.

A future design must define the affected stores explicitly; Private-only
revocation is a possible scope, not a decided policy. It must also define which
authentication prompts recognize duress and whether it shuts down the session.
An unlocked dm-crypt mapping already holds the volume key in kernel memory:
invalidating disk keyslots alone does not revoke that mapping or data already
read into memory. Such a path would need to stop readers and close the mapping
as well as invalidate every applicable unlock method, accounting for LUKS2
metadata redundancy. Header backups can restore old unlock methods and flash
remapping limits host-level erasure guarantees, as with the existing quick wipe.

This requires isolated failure/interruption and false-trigger tests, a recovery
and backup policy, and explicit opt-in before any real-media implementation.
No existing keyslots, headers, backups or data are changed by recording the idea.
