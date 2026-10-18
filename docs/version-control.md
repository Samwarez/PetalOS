# Version-control boundary

The Git root is the former live-build working directory, `portable-live/build`.
The neighboring `releases`, `testing`, `provisioning`, `handoff`, public archive
caches and encrypted disk files remain outside Git. The physical card is neither
read nor copied as part of the repository import.

Included: maintained live-build configuration, runtime helpers and policies,
desktop assets, native Parole/Conky patches and builders, tests and management
scripts, technical documentation, and public text evidence from the bounded
Phase 1.5 audit. The abandoned custom aMule candidate is retained as reference
source only; the supported build still selects the Debian package.

Excluded: generated live-build trees and native executables, package caches,
release images, VM disks/firmware variables/state, mounted filesystems, personal
data, local conversation handoff, snapshots/backups, passwords and password
hashes, real VPN profiles, private/encryption keys, LUKS header backups, and SSH
development-access identities. Exclusions do not remove any local file.

The public Tor developer verification keyring and distro artwork are intentional
binary inputs. Synthetic tests contain public canary strings and an all-zero
mock WireGuard public key; they are not working credentials. The source also
retains its existing rejection of a retired public default password. That string
does not enable authentication and was not removed at the expense of the check.
Actual disposable audit credentials remain outside the repository.

The audit directory's source snapshot archive is excluded. Its checksum and
links in the historical report identify local evidence, not a downloadable Git
artifact. Other dated reports can likewise reference local releases, images and
test sessions that are deliberately not uploaded. Preserve those files locally.

Before this import, all 73 existing source snapshot checksum records passed;
a new code/documentation snapshot was created and read back. Existing backups,
builds and VM images were preserved. This is not a restore test of encrypted
personal backups.

The initial staged inventory contained 578 files (about 5.8 MB); its largest
file was the 2.1 MB public dependency-triage evidence. Gitleaks 8.30.1 and the
additional index checks found no secrets after the six verified checksum false
positives were narrowly classified. Exact comparisons against the three external
audit credentials also found no matches. The three intended binary inputs were
reviewed: two PNG assets without text/EXIF metadata and a Tor keyring containing
one public primary key, three public subkeys and no secret-key packets.

Eleven isolated guard cases passed, including detecting unsafe staged content
when its working-tree copy was clean, force-added credential/artifact paths,
password hashes, WireGuard key assignments, SSH access keys, a file over 5 MiB,
and an unexpected absolute symlink. Existing build-input validation passed.
The import did not perform a new OS build or remediate the audit findings.

## Before every commit

Stage explicit paths. Review `git diff --cached`, then run the staged-content
checker. It reads Git blobs, not just the working tree, so ignore rules cannot
hide an already staged forbidden file. It checks file sizes, artifact/credential
paths, key/hash/token signatures, unexpected binary data and symlink targets.
With `--gitleaks`, it also scans a RAM-only extraction of the exact index with
the default Gitleaks rules and the repository's narrow checksum exceptions.
Findings report paths/rules/line numbers only, never matched values.

The six Gitleaks exceptions are specific SHA-256 file checksums in two historical
audit JSON files, verified against the files they describe. They are not password
hashes and do not exempt those files wholesale. Do not broaden exceptions merely
to make a scan pass. No scanner proves the absence of every possible secret;
review newly added files and avoid putting sensitive material in the checkout.

Do not force-add generated outputs or credentials. Physical-card work and
publication beyond the specifically authorized private repository still require
separate instructions. Git is a source-history tool, not the backup of encrypted
stores or a replacement for independently verified recovery copies.
