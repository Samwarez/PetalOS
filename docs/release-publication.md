# PetalOS split-storage development release

The clean build `20261026-145911-818721` exports catalog version
`rc1-layout2-20261026-145911-818721`, base variant, amd64, without a local AI
agent. Its catalog SHA-256 is
`90087752102293254fd967a6fe7f84a6f7a680ae3f25e06c4d9081094720646a`.

The exported kernel/initramfs/rootfs match the clean build manifest. Both
verification report hashes match `verification.json`: 63 focused storage
checks, five full-OS provisioning checks and 16 live RAM-boot checks pass.
The full-OS check uses the production storage code without a runtime overlay.
One SYSTEM prompt unlocks independently keyed OS/settings; OS closes after
loading into RAM, while Private stays closed until separately authenticated.
The focused update check preserves encrypted settings and Private byte-for-byte.

These results cover direct-kernel VM boot. Fresh firmware boot, graphical startup
and physical hardware acceptance remain separate. Focused fixtures use test-only
PBKDF2; production Bloom Argon2id acceptance is recorded separately. Test
credentials, test initramfs files and VM disks are never release assets.

Sam authorized public project source and releases. The prepared publisher runs
from the normal desktop user's terminal with authenticated `gh` and `git`:

```sh
python3 -B scripts/publish-split-release.py
```

It verifies the prepared source inventory and exact asset hashes, scans the
staged source and existing remote history with checksum-pinned Gitleaks, commits
from an isolated checkout, and pushes without force. It uploads to a draft,
checks the asset inventory, then makes PetalOS and that release public. The
repository description and homepage link to Bloom. Finally, Bloom's actual
default client lists and downloads the complete release without a token and
verifies every payload against the catalog. Download verification is retained
outside Git under the release export. Existing local branches, working-tree
changes and the main Git index are preserved.

The source snapshot includes maintained build/runtime code, patches, tests,
technical documentation and exact-hash reviewed public artwork. Generated
native executables/package archives, OS/VM images, credentials, handoff files,
backups and local hardware reports are excluded. Some historical documentation
links name local screenshots/reports that are deliberately not part of Git.
Third-party notices and the existing no-blanket-license policy remain in force.

The prepared inventory, source snapshot, release notes and resumable publication
state live under `../release-dist/VERSION/publication/`, outside the source Git
root. `--dry-run` checks that prepared source and the assets without networking
or changing GitHub. If the reviewed remote branch has advanced, the publisher
stops for a new review; it never overwrites a conflicting commit or asset.
