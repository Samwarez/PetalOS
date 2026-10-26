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


# Project artwork reviewed for public source publication on 2026-10-26.
# Exact identities only; new/changed binary inputs still require review.
BINARY_INPUTS.update({
    "config/includes.chroot/usr/share/backgrounds/petalos-defaults/01-quiet-sakura.png": "3a2fcbef971cf03680a1b26e7a6fa75057362ef7c692e047e772373ab73671de",
    "config/includes.chroot/usr/share/backgrounds/petalos-defaults/02-cozy-code.png": "feba4ee224d1408af5ebeeeaae85b6ee0b7fd6de8ec13072bb08fe7efca2b15d",
    "config/includes.chroot/usr/share/backgrounds/petalos-defaults/03-midnight-petals.png": "0ec9b44f134dd999f9212f9e2b4059ec027b0efefff7677e8dc3617f352bf586",
    "config/includes.chroot/usr/share/backgrounds/petalos-defaults/04-petal-drift.png": "d233263e61e7adfad70ec393764e232f82345bd20d980e8c01789b3c4582a852",
    "config/includes.chroot/usr/share/backgrounds/petalos-defaults/PetalOS-Login-Petal-Drift-1920x1080.png": "d82383884391b3da1c69a7982518eba7d79cf5c8bb79b71bed9a0806a3fbf49d",
    "config/includes.chroot/usr/share/backgrounds/petalos-defaults/petal-cram-02.png": "3e9f211d6ac7aaeec32ec813aaf152ebd2b1d2289a59ace4bd24cef0d2f02561",
    "config/includes.chroot/usr/share/backgrounds/petalos-defaults/petal-wallpaper01.png": "efdbf7d357c6c37b9e4ff5f1cdf6211f565eaaacf581150c7618c131b48ec40d",
    "config/includes.chroot/usr/share/backgrounds/petalos-defaults/petal-wallpaper02.png": "58001143c62a945346a62f2806e36029be231303ae33e41801f1824f7378e056",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/error.png": "7e756e3eb09f6440e2d3e86f38bce21cead77458f26f63f1de53829e09e13cbf",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/fail-0.png": "25bb52811022b1f1a1cd992c853d5b3bf368415ef7bd5bc58d7d834571ddc6c3",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/fail-1.png": "0a7227cf59b378bd692c526e0fd93737875d4fa3565759c5df8ca7caa07a3bee",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/fail-2.png": "a796ac812a341a7fe886df847a4f0ff97c40800e46bf65659a5d680fb96b55b5",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/fail-3.png": "12caca4889d2cdc0bbdbe763cc1c294e142227e4974c37fc33e5fdea31b9a32b",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/fail-4.png": "d7e75e8a861e83925ad4fbc4eb3937c3c83e2e522695cf02cdf527a74b8d80cc",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/fail-5.png": "f2ab88a0593211d1f9bebe18b8cd5870674febc4941365c59e9b581700c59b84",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/idle-0.png": "27464000a0aa881739c936af1436b033a174899200f07005d414b3ea285c79c2",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/idle-1.png": "68ae7c47310b03722ea9aa322cd8e85dfac779865014005de12a2f5b2f06ef53",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/idle-2.png": "59be6cf830172a35ce495e80138df35b83baeff1f6282e0c9683c2a9bf522681",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/idle-3.png": "ed76563d3c34ecb7549d84c60dba03315da0703ffd4386cf655d05760db8df80",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/idle-4.png": "2da9da7c114832def06126b722f8261d577943813ea629ec0e9aa2d9d46aba29",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/idle-5.png": "2470cbacc1c504ecb5053642188810655433a8c85af4a4b990d479f6918e6032",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/ram1-0.png": "dc0fd53767e24c390a225fc3794440d3034494119574f0ce9ae972f226df8d39",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/ram1-1.png": "a76742f9d6dc4aabb65098ae25e6e80441dddd82ed82bb98b8a4c1c13eb2100b",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/ram1-2.png": "7429001bb5df08b58d1c9245257327a662fae55155b95019e461fe228e228872",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/ram1-3.png": "422c5ec5e8281b4f686cb04e2fc455ea301121e9e8c49717ea7865d4b4ca22f7",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/ram1-4.png": "eafc965215ae039c00482d38d816f5f1ddbb0f1edb0546439825162bad9507b6",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/ram1-5.png": "d7ae1e95510403e5ba3e7fbd96314c9929fc7b10a802ef82cc7d9fbe38d7031c",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/ram2-0.png": "fe2f40e0a4d81e54aa884626e1f54e6ca9cba3d11806dececb47d179b2c28d88",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/ram2-1.png": "4cd5bfdcde8cbc3f6f4bb886a998fc40ef6bd130b333f5673a19793b3533a890",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/ram2-2.png": "ca4b0dcc2474a96824e32238b56423103b3f513d0673be867d9016c0072721dc",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/ram2-3.png": "c79ccee967996e3fc074840ffb8085ba7014d69b6328cabbb8a8b950621ea145",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/ram2-4.png": "ed9f5ccbdb9e8a9b281186b853a22d9b5c3554519163da4f384b3bb974bc1765",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/ram2-5.png": "cb8d60b2e17bceccb25b4ed8ef70872653a88d5f4fe79f9359174fc573e925c5",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/ram3-0.png": "25347b3595430b6c14b1bc461a6c9c54a1a0c202dc98886a2ab93b8311ff3cfd",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/ram3-1.png": "2783151622fd6a1a0eb1e4d647cad0af4e48b6a27af83e7edb8c10eeae2f841a",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/ram3-2.png": "3724f5e4f37f3464200886866a8a99a15a78ba8d57cc7ba06a77efee89a28b96",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/ram3-3.png": "6013fa22bc42cab344914956d37aea794c26a47767bb47a05db4f1dc0965feeb",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/ram3-4.png": "704b51e2aeea7f55f80ff721b50d09e6e9e1b68c1710bcefd59aa55faa23e0df",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/ram3-5.png": "25affd5e2c8fa2c72cab2a4f854c7716fcfbcf8e81e0b18918ee1a3169b1a652",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-0.png": "fb939b1acb978aa2d1550a9874559cb18d9ca5e55764bb94e30ef277dc8a76f5",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-1.png": "aef0d3a4b5a431453bb11c8fb28718aed96ea5e4c3aab9dea5f8082a92517da6",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-10.png": "e5390ebe42b814554e07b42212a91e36cbe2a76b44bf4cc73bd52ad40d908fd7",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-11.png": "af959d890c764b4946744335ac10a393201548db442dff570faa50335d29f794",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-12.png": "677883b1095da406a04feaee480ddb947c5b740088c6246ba600906e6767934a",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-13.png": "7b4732d987c361a249dcc4668fc3e6afe119267c84be9a541d397afec09894f4",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-14.png": "1c0fe87026f2d4f94dade4d25c31b9b25e51a543c7a7cee60783f76f333fda12",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-15.png": "34c7dea8acd0645a575852e2001422cb153208dfff1847bfcb7690113445d8f2",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-16.png": "0e7ad29465130e968a4fce43d48c9547d41bc83b0e311cdfcbcd6c7232e92b21",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-17.png": "4c15a742da2a158ada4bf45b505a3ea3030553cdf75d940e78d1459377939214",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-18.png": "664fc0663433cd4246897b5ffb2166f214da5880a2445cc9eeeeaaa8f67f39ee",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-19.png": "01388e3eb3071a334bcb6854fb559131ed825989782ca373d38946d06ae2a867",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-2.png": "0cc7c64d93dcd82ebdeeddab24627a2ecf56269ee56c0be1075ba97fbb557cfe",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-3.png": "0662d7a6138a066aac487ccb89285a83e7d35387ba75c982f0e257be4bc4c822",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-4.png": "8bbadbab7911e4f790f69de69a17b9c7cf4b12ac8fc9d3098dbb61b8e4bf73b8",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-5.png": "1cf04dd57d8c8d3466a0b19a81ab514a574c4aa15fd3f2712f40f18ebcc67e38",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-6.png": "36ea1cf030495558d9a5b56d65fc3494775e6ea3f6c8bf1141336071b688bcb7",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-7.png": "ebb9f22213f1fea4bb624413e7d805c62783406f588d8e2ecc4dab47eea9cf7f",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-8.png": "f7ee418362ffaa87a947467335bc661de6a02dc2d14fc2257b1a1410d7c24e3f",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/startup-9.png": "344a4006d04e2da967a3eb785990ca3c91a9abce49be546ffc0da778c8dbcfa7",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/success-0.png": "5a28fbbe23b7e578aa02c7b2b0bf95c9542e06d02c8869ce4410a9a73ef277d9",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/success-1.png": "fc5405b161e6883fa3835a529f822d4a876328649931dc8513b8fe638c099caf",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/success-2.png": "319c28d0f375459735279b4f3e9d767272342d18b812f2199a4d76d20b8d3e40",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/success-3.png": "ae3e83891b403d28e979ce8a56ff51311f7da6ae38fdcba90a93021202d0c298",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/success-4.png": "18927c4fe5aa795db7ac63b4aa4a866024d9b53875d48f94824cf71c114695ea",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/success-5.png": "7b1b07adf00371280c2fe8eb97e0599d937ac2627f0f4a0ba74da0bc7554bae7",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/wait-0.png": "ab42298e0265d574d78f8c14fde31029fdbc8d2faf17bba6d139ef7a02371179",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/wait-1.png": "27faecf173abfb775833132577f5e1efd6bca591bcea7aa46fc643029f47eecc",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/wait-2.png": "e811e026218e9cd1d95b5b87160f3f112dbcc24676e584c0d8ed650b2190fa92",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/wait-3.png": "65a0ac85e16815e20b7e1967856bb7cc3173c3f2d5e4e5d3914e8cc2611f91df",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/wait-4.png": "d8702fe14602d9ab94d881d0c4690b80ec118b2153566a11f54a93b662d4b172",
    "config/includes.chroot/usr/share/plymouth/themes/petalos/wait-5.png": "f06ac82260c6ef995bf281c029c8fc3a494c2c9d7c38b24b426b3776173667ca",
    "config/includes.chroot/usr/share/portable/branding/grub.png": "2612b56820dac5ddea5c272d7335f991e41c0ad807e281e2b65c03d70148d5cd",
    "local/installer/petal_installer/assets/petal-emblem.png": "fa5d8b260497670fb534916f5c8fb388afcadfb9c7ce5ab6a745dd0b6729b49e"
})


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
