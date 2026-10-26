# Tails boot comparison and phase-one acceptance

**Decision:** S-01 remains a real boot-media authentication limitation, but is
accepted for the phase-one RC under Sam's instruction on 2026-10-19: matching
Tails's protection against this particular issue is sufficient. It does not
require a repair or per-computer enrollment for this release. This is a scope
decision supported by a direct comparison, not a claim that the weakness was
fixed or that PetalOS as a whole has Tails-equivalent security.

## Reference and preserved inputs

The reference is the official **Tails 7.15 amd64 USB image**. Its 1,889,533,952
bytes matched SHA-256
`2bad37833f2e44abbf68646a460759c26d1fc32589c2e0437099743bc6b6197b`
from Tails's [HTTPS release metadata](https://tails.net/install/v2/Tails/amd64/stable/latest.json).
This is HTTPS/checksum verification; a separate OpenPGP signature check is not
claimed. The original image remains unchanged.

The PetalOS comparison is the confirmed harmless-marker result documented in
[the repair record](README.md): modified external initramfs code executed with
Secure Boot enabled. The source baseline for this comparison is local commit
`00cf3c819f91c1ee781312024ef8d7e648219c21`.

Public artifacts and screenshots are retained outside Git at
`/home/sam/portable-live/testing/artifacts/tails-boot-comparison-20261019`.
The [bounded evidence](tails-boot-comparison.json) records hashes, preparation,
runtime observations, and test-harness limitations. Existing audit evidence,
PetalOS images, backups, physical cards, host disks and host firmware were not
modified. Each Tails run used a new local firmware-variable file, no network
device, no host-disk passthrough, and a disposable 8 GiB image overlay. No
passwords or encrypted personal storage were supplied to Tails.

## Direct comparison

| Test | Observed outcome |
| --- | --- |
| Original USB payload in the disposable overlay | Boot reached the graphical GNOME environment. This was a boot test, not a Tails application acceptance test. |
| Replace only the external initramfs with a correctly repacked copy containing a harmless marker and its startup-order entry | Marker executed and appeared on the virtual serial console; the graphical environment still loaded. The released kernel, Shim, GRUB and GRUB configuration matched the original on readback. |
| Repeat the initramfs marker with a read of the kernel boot messages | The marker executed and the signed guest kernel reported **Secure boot enabled**. This run stopped after observing those lines. |
| Change one byte in the signed kernel while retaining the original initramfs | Kernel did not boot. A direct GRUB `linux /live/vmlinuz` command reported **`error: bad shim signature.`** The screenshot was inspected and its hash retained. |

All four used identical initial Secure Boot firmware templates. The negative
control establishes that kernel signature enforcement was active; the marker
was not obtained by disabling that protection. Reading EFI variables directly
in the early Tails initramfs produced empty fields, so those fields are not used
as evidence of enabled or disabled Secure Boot. The follow-up kernel-message
observation directly confirmed that Secure Boot was enabled; it did not require
changing the kernel, bootloader, configuration or trust settings.

The actual released GRUB configuration uses `linux /live/vmlinuz ...` followed
by `initrd /live/initrd.img`. PE signature metadata identifies Microsoft's
signatures on Shim and Debian signatures on GRUB and the kernel. Those static
observations support the mechanism; the execution and rejection tests establish
the behavior being compared.

Reproduction fixtures:

- [tails-boot-prepare.py](../../tests/phase15-repairs/tails-boot-prepare.py):
  validates the original image, uses a local copy of mtools without mounting
  devices, preserves early CPIO records, and prepares/readbacks disposable
  initramfs and kernel variants.
- [tails-boot-compare.py](../../tests/phase15-repairs/tails-boot-compare.py):
  starts bounded QEMU runs with fresh firmware variables and disposable image
  overlays, captures evidence, and stops each process.

## Meaning and remaining limits

For the demonstrated attacker capability—altering the removable boot medium
before it is used—both tested systems accepted modified external initramfs code
before encrypted storage was unlocked. The attacker did not need an encryption
passphrase or signing key to make that change. No passphrase capture was
implemented or attempted.

This supports parity for **the specific S-01 execution path**. It does not compare
every bootloader vulnerability, rollback rule, firmware variant, update path,
root/module verification mechanism, or resistance to other attacks. The tests
used QEMU and this exact Tails release, not every machine or future Tails version.

Tails itself recommends protecting the installation from modification and
reinstalling/upgrading from a trusted system if corruption is suspected; see
[its trusted-computer guidance](https://tails.net/doc/about/warnings/computer/).
PetalOS must retain the same practical warning: encryption at rest does not
protect a subsequently entered passphrase from a compromised boot environment.

The remaining RC acceptance work is the combined PetalOS build, representative
tests of that exact image, and hardware checks. Stronger authenticated boot may
be pursued later as an improvement; it is no longer an S-01 release blocker
under the agreed benchmark. Other audit findings and their acceptance tests
are unaffected.
