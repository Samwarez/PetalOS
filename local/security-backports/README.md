# Trixie security backports

These are focused security repairs for the exact Debian trixie source versions
in `sources.json`. Sources were downloaded through signed APT metadata in the
disposable VM; every archive and patch has a pinned SHA-256. No unstable package
is used. Candidate packages have a `+petalos1` Debian version suffix so they are
identifiable and later Debian security revisions can supersede them.

- aMule: upstream server-message minimum-length validation. This does not
  include, revive or depend on the abandoned custom Kad candidate.
- libxml2: upstream QName pool-sizing repair, with a checked `size_t` combined
  length also used for the older implementation's existing-pool comparison.
- Poppler: apply the existing 127-byte PDF password limit inside the R6 hash
  routine. This preserves trixie's older GooString API rather than importing
  upstream's broader string refactor.
- polkit: bounded cookie input plus the follow-up initial-NUL correction. An
  oversized line is rejected immediately, without draining an unbounded stream.

Build as an ordinary user in trixie/amd64, after installing that exact source
package's Debian build dependencies:

```
python3 build.py PACKAGE /path/to/verified/source-archives /new/output/directory
```

The builder preserves Debian's feature selection, hardening flags and enabled
test targets. `regression.py` compiles the affected source routines with bounded
allocation/input fixtures and requires the original to fail while the repair
passes. These source tests do not prove installed GUI compatibility or full
protocol correctness. Poppler's acceptance specifically requires generated
AES-256/R6 PDFs against the built library, including correct and incorrect long
passwords and an ordinary encrypted-document workflow.

After building all four packages, stage their output directories:

```
python3 local/security-backports/stage.py /build/amule /build/libxml2 /build/policykit-1 /build/poppler
```

This verifies source and patch identities, archive hashes and Debian package
metadata, then creates ignored inputs under
`config/includes.chroot/usr/local/share/portable/security-backports/`.
The `0890-security-backports` image hook upgrades affected packages that are
already installed, preserves newer Debian versions, and removes duplicate deb
archives from the OS. It runs before the app wrappers are installed. The final
artifact verifier checks package versions and the four critical executables or
libraries against their package payloads.

Installed-package tests in the disposable VM passed polkit's bounded-input and
administrator-authentication stages, libxml2 namespace-document round trips,
and Poppler R6 password handling and actual page rendering under the Atril role.
The original Poppler crashed on the long-password controls; the backport opens
and renders valid passwords and rejects incorrect ones without a crash. aMule
starts under its existing profile, and its malformed-packet source regression
rejects the bad lengths while retaining a valid server message. This does not
claim a complete live eD2k/Kad protocol test.

Polkit's five packaged tests passed. **Poppler's Debian source omits its external
PDF test corpus and deliberately permits `dh_auto_test` failure.** This build
reported 18 of 71 tests passing and 53 failing; its successful package build is
not a passing full upstream test suite. The separate R6/rendering regressions
are the evidence for this focused repair. Do not suppress that limitation or
describe all dependency tests as passing. See
[repair evidence](../../docs/phase15-repairs/README.md) and the public package
provenance there. The new combined ISO and a clean-machine reproducibility
build remain separate release gates. Original images and audit findings are
preserved.
