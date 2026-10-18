# Audit evidence retained in version control

`REPORT.md` is the bounded review performed before the initial Git commit.
Its original revision identifier is the source-manifest hash, not a Git commit.
The report and public JSON evidence are retained unchanged by the import.

`public-source-before-audit.tar.gz` is a local backup and is deliberately excluded
from Git. Historical links to that archive and other local images/releases will
only resolve on the original workstation. VM disks, credentials, access keys,
runtime screenshots and personal data are not included.

The audit's aMule experiment is historical: the custom candidate was subsequently
abandoned for the supported build. No audit repair was implemented during the
version-control import. See the [candidate status](../../local/amule-kad/README.md)
for its retained source context.
