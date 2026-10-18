#!/usr/bin/python3
"""Triage public installed versions against Debian tracker JSON, offline.

This is a candidate list, not proof of exploitability. Debian's open records
include historical, configuration-specific, ignored and unassigned issues.
Feed package rows from dpkg-query: binary, version, source, source version.
Map signed kernel packages to the actual linux version from Built-Using.
"""
import argparse
import collections
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packages', type=Path, required=True)
    parser.add_argument('--tracker', type=Path, required=True)
    parser.add_argument('--kernel-version')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    packages = json.loads(args.packages.read_text())
    tracker = json.loads(args.tracker.read_text())
    sources = collections.defaultdict(set)
    for binary, version, source, source_version in packages:
        sources[source or binary.split(':')[0]].add(source_version or version)
    if args.kernel_version:
        sources['linux'].add(args.kernel_version)
    comparisons = {}
    findings = []
    for source, versions in sources.items():
        for cve, item in tracker.get(source, {}).items():
            release = item.get('releases', {}).get('trixie')
            if not release:
                continue
            fixed = release.get('fixed_version')
            if fixed == '0':
                continue
            affected = []
            for version in sorted(versions):
                if release.get('status') == 'resolved' and fixed:
                    key = (version, fixed)
                    if key not in comparisons:
                        comparisons[key] = subprocess.run(['dpkg', '--compare-versions', version, 'ge', fixed]).returncode == 0
                    if comparisons[key]:
                        continue
                affected.append(version)
            if affected:
                findings.append({'source': source, 'installed_versions': affected,
                                 'cve': cve, 'status': release.get('status'),
                                 'urgency': release.get('urgency'), 'fixed_version': fixed,
                                 'nodsa': release.get('nodsa'), 'nodsa_reason': release.get('nodsa_reason'),
                                 'description': item.get('description', ''),
                                 'url': 'https://security-tracker.debian.org/tracker/' + cve})
    report = {'scope': 'Candidate records only; applicability requires review.',
              'installed_binary_packages': len(packages), 'installed_source_packages': len(sources),
              'candidate_records': findings}
    args.output.write_text(json.dumps(report, indent=2))
    print('Public version comparison complete; candidate details saved for review.')
    print(json.dumps(dict(collections.Counter(x['urgency'] for x in findings)), sort_keys=True))


if __name__ == '__main__':
    main()
