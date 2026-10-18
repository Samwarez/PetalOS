#!/usr/bin/env python3
"""Check exact Git index blobs without displaying possible secret values."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile


MAX_FILE_BYTES = 5 * 1024 * 1024
ROOT_FILES = {'.gitignore', '.gitattributes', '.gitleaks.toml', 'AGENTS.md', 'README.md'}
SOURCE_DIRS = {'auto', 'config', 'local', 'tests', 'docs', 'scripts'}
FORBIDDEN_DIRS = {
    '.git', '.build', '__pycache__', 'chroot', 'binary', 'cache', 'backups',
    'snapshots', 'releases', 'mounts', 'mnt', 'private', 'appstate',
    'portablesettings', 'systemsettings', '.petalos-auth', '.portable-keys',
    'node_modules', '.venv',
}
FORBIDDEN_SUFFIX = re.compile(
    r'\.(?:iso|img|raw|qcow\d*|vmdk|vdi|vhdx?|squashfs|luks|fd|deb|udeb|'
    r'key|pem|p12|pfx|gpg|age|kdbx?|keyx|hash|hdr|header|ppk|ovpn|'
    r'py[co]|o|so|a|debug|log|tmp|tgz|zip|7z|tar(?:\..+)?)$', re.I)
FORBIDDEN_NAME = re.compile(
    r'^(?:\.env(?:\..*)?|shadow|gshadow|id_(?:rsa|ed25519|ecdsa|dsa).*|'
    r'ssh_host_.*|authorized_keys.*|known_hosts.*|credentials(?:[-.].*)?|'
    r'wg.*\.conf|.*-adb\.conf|.*luks.*header.*)$', re.I)
RULES = {
    'private-key-block': rb'-----BEGIN (?:[A-Z0-9 ]*PRIVATE KEY|PGP PRIVATE KEY BLOCK)-----',
    'password-hash': rb'\$(?:[156]|2[aby]|y|gy|argon2(?:id|i|d))\$[A-Za-z0-9./$=,+-]{12,}',
    'github-token': rb'(?<![A-Za-z0-9])(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})',
    'ssh-access-key': rb'\b(?:ssh-(?:rsa|ed25519)|ecdsa-sha2-nistp\d+)\s+[A-Za-z0-9+/]{40,}={0,3}',
    'wireguard-key-value': rb'(?im)^\s*(?:PrivateKey|PresharedKey)\s*=\s*[A-Za-z0-9+/]{42,}={0,3}',
    'aws-access-key': rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'slack-token': rb'\bxox[baprs]-[A-Za-z0-9-]{20,}',
}
# Reviewed distro assets and public Tor verification key, not access keys.
# Changing one requires deliberate review and updating its content identity.
BINARY_INPUTS = {'config/includes.chroot/usr/share/icons/hicolor/128x128/apps/portable-tor.png': '33f9c256c82c2c5797cf8835c50ca9b5715922969cbe8f89dd757217d18c8826', 'config/includes.chroot/usr/share/backgrounds/petalos/petalos-lock.png': 'd82383884391b3da1c69a7982518eba7d79cf5c8bb79b71bed9a0806a3fbf49d', 'config/includes.chroot/usr/local/share/portable/tor-browser-developers.keyring': 'c2ed2cb463bf384630f2c746448399ab944c3aeade4619f940f07372a57780d7'}


def git(*arguments):
    return subprocess.check_output(['git', *arguments])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gitleaks', type=Path, help='additional Gitleaks executable')
    args = parser.parse_args()
    os.chdir(git('rev-parse', '--show-toplevel').decode().strip())
    entries = []
    problems = []

    def reject(path, rule, line=None):
        item = {'path': path, 'rule': rule}
        if line is not None:
            item['line'] = line
        problems.append(item)

    for record in git('ls-files', '--stage', '-z').split(b'\0'):
        if not record:
            continue
        metadata, raw_path = record.split(b'\t', 1)
        mode, object_id, stage = metadata.decode().split()
        path = raw_path.decode('utf-8', errors='strict')
        p = PurePosixPath(path)
        if stage != '0' or mode not in {'100644', '100755', '120000'}:
            reject(path, 'unmerged-or-unsupported-index-entry')
            continue
        if p.is_absolute() or '..' in p.parts or any(ord(c) < 32 for c in path):
            reject(path, 'unsafe-path')
            continue
        if path not in ROOT_FILES and (len(p.parts) < 2 or p.parts[0] not in SOURCE_DIRS):
            reject(path, 'outside-maintained-source')
        if any(part.lower() in FORBIDDEN_DIRS for part in p.parts[:-1]):
            reject(path, 'generated-or-data-directory')
        if FORBIDDEN_SUFFIX.search(p.name) or FORBIDDEN_NAME.fullmatch(p.name):
            reject(path, 'artifact-or-credential-filename')
        if path.startswith('config/includes.chroot/usr/local/share/portable/native-'):
            reject(path, 'generated-native-artifact')
        if 'Network/Profiles/' in path or ('/wireguard/' in path and p.suffix == '.conf'):
            reject(path, 'vpn-profile')
        size = int(git('cat-file', '-s', object_id))
        if size > MAX_FILE_BYTES:
            reject(path, 'file-exceeds-5-MiB')
            continue
        data = git('cat-file', 'blob', object_id)
        if mode == '120000':
            target = data.decode('utf-8', errors='strict')
            if not (path.startswith('config/hooks/') and
                    target.startswith('/usr/share/live/build/hooks/') and
                    '..' not in PurePosixPath(target).parts):
                reject(path, 'unreviewed-symlink-target')
        else:
            binary = b'\0' in data
            try:
                data.decode('utf-8')
            except UnicodeDecodeError:
                binary = True
            if binary and hashlib.sha256(data).hexdigest() != BINARY_INPUTS.get(path):
                reject(path, 'unexpected-binary-or-changed-asset')
            for label, pattern in RULES.items():
                for match in re.finditer(pattern, data):
                    reject(path, label, data[:match.start()].count(b'\n') + 1)
        entries.append((path, mode, data))

    if not entries:
        reject('(index)', 'empty-index')
    scanner = 'not-requested'
    if args.gitleaks and not problems:
        runtime = Path('/run/user') / str(os.getuid())
        if not runtime.is_dir() or runtime.stat().st_uid != os.getuid():
            raise RuntimeError('Owned RAM runtime directory required for the staged scan.')
        with tempfile.TemporaryDirectory(prefix='petalos-staged-scan-', dir=runtime) as tmp:
            directory = Path(tmp)
            source = directory / 'source'
            source.mkdir(mode=0o700)
            for path, mode, data in entries:
                target = source / path
                target.parent.mkdir(parents=True, exist_ok=True)
                # Never follow or materialize absolute source-tree symlinks.
                # Scan their target strings as plain data instead.
                target.write_bytes(data)
            report = directory / 'findings.json'
            config = source / '.gitleaks.toml'
            ignore = directory / 'empty.gitleaksignore'
            ignore.write_text('')
            command = [str(args.gitleaks.resolve()), 'dir', str(source), '--no-banner',
                       '--redact=100', '--report-format', 'json', '--report-path', str(report),
                       '--ignore-gitleaks-allow', '--gitleaks-ignore-path', str(ignore),
                       '--timeout', '120']
            if config.exists():
                command += ['--config', str(config)]
            result = subprocess.run(command, capture_output=True, timeout=130)
            if result.returncode not in (0, 1) or not report.exists():
                reject('(scanner)', 'gitleaks-did-not-complete')
            else:
                findings = json.loads(report.read_text())
                for finding in findings:
                    name = Path(finding['File'])
                    if name.is_absolute():
                        name = name.relative_to(source)
                    reject(str(name), 'gitleaks:' + finding['RuleID'], finding['StartLine'])
                if result.returncode and not findings:
                    reject('(scanner)', 'gitleaks-nonzero-without-report')
            scanner = 'pass' if not problems else 'failed'

    print(json.dumps({
        'index_entries_checked': len(entries),
        'total_bytes': sum(len(data) for _, _, data in entries),
        'largest_files': sorted(
            [{'path': path, 'bytes': len(data)} for path, _, data in entries],
            key=lambda item: item['bytes'], reverse=True)[:5],
        'gitleaks': scanner, 'problems': problems,
    }, indent=2))
    return bool(problems)


if __name__ == '__main__':
    raise SystemExit(main())
