#!/usr/bin/python3 -B
"""Publish a prepared, verified PetalOS source snapshot and Bloom release assets.

Uses the user's authenticated gh CLI from a normal terminal. Source and history
secret scans run before pushing; the complete draft is checked before making
the repository/release public. Never opens a physical drive or runs sudo.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPO = 'Samwarez/PetalOS'
SCANNER_URL = 'https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz'
SCANNER_SHA = '551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb'


def digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def run(*args, cwd=None, capture=False):
    result = subprocess.run(list(map(str, args)), cwd=cwd, check=True,
                            text=True, capture_output=capture)
    return result.stdout.strip() if capture else None


def gh_json(*args):
    return json.loads(run('gh', 'api', *args, capture=True))


def git(*args, cwd=None, capture=False):
    return run('git', '-c', 'core.hooksPath=/dev/null', '-c', 'credential.helper=',
               '-c', 'credential.helper=!gh auth git-credential', *args, cwd=cwd, capture=capture)


def safe_relative(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] == '.git':
        raise RuntimeError('Unsafe source snapshot path.')
    return path


def check_source(snapshot, entries):
    names = set()
    for entry in entries:
        name = entry['path'];safe_relative(name)
        if name in names:
            raise RuntimeError('Duplicate source snapshot path.')
        names.add(name)
        path = snapshot / name
        if entry['mode'] == '120000':
            target = os.readlink(path)
            if not (name.startswith('config/hooks/') and target.startswith('/usr/share/live/build/hooks/')
                    and '..' not in PurePosixPath(target).parts):
                raise RuntimeError('Unreviewed source symlink.')
            data = target.encode()
        else:
            if path.is_symlink() or entry['mode'] not in ('100644', '100755'):
                raise RuntimeError('Unexpected source file type.')
            data = path.read_bytes()
        if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise RuntimeError('Source snapshot changed: ' + name)


def check_plan(plan_path):
    plan = json.loads(plan_path.read_text())
    if plan['repository'] != REPO or plan['format'] != 1:
        raise RuntimeError('Unsupported publication plan.')
    base = plan_path.parent
    manifest_path = base / 'publication/source-manifest.json'
    if digest(manifest_path) != plan['source_manifest_sha256']:
        raise RuntimeError('Prepared source inventory changed.')
    entries = json.loads(manifest_path.read_text())
    snapshot = base / 'publication/source'
    check_source(snapshot, entries)
    for item in plan['assets']:
        safe_relative(item['path'])
        path = base / item['path']
        if path.is_symlink() or path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
            raise RuntimeError('Release asset changed: ' + item['name'])
        if not 0 < item['bytes'] < 2 * 1024**3 or path.name != item['name']:
            raise RuntimeError('Invalid release asset size/name.')
    if digest(base / 'publication/release-notes.md') != plan['notes_sha256']:
        raise RuntimeError('Prepared release notes changed.')
    return plan, entries, snapshot


def save_state(path, state):
    pending = path.with_suffix('.tmp')
    pending.write_text(json.dumps(state, indent=2) + '\n')
    pending.replace(path)


def scanner(work):
    path = work / 'gitleaks'
    if path.exists():
        # Re-download and authenticate on each invocation; do not trust a
        # leftover executable from an interrupted publication.
        path.unlink()
    with urllib.request.urlopen(SCANNER_URL, timeout=60) as response:
        data = response.read(20 * 1024**2 + 1)
    if hashlib.sha256(data).hexdigest() != SCANNER_SHA:
        raise RuntimeError('Gitleaks download failed the pinned checksum.')
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        item = archive.getmember('gitleaks')
        if not item.isfile():
            raise RuntimeError('Invalid scanner archive.')
        path.write_bytes(archive.extractfile(item).read())
    path.chmod(0o700)
    return path


def source_scan(checkout, tool, reports):
    result = subprocess.run([sys.executable, '-B', str(checkout / 'scripts/check-staged-content.py'),
                             '--gitleaks', str(tool)], cwd=checkout, text=True, capture_output=True)
    report = reports / 'source-scan.json'
    try:
        record = json.loads(result.stdout)
    except ValueError:
        record = {'checker_exit': result.returncode, 'problems': [],
                  'diagnostic': result.stderr[-8000:]}
    report.write_text(json.dumps(record, indent=2) + '\n')
    if result.returncode:
        problems = record.get('problems', [])
        details = '; '.join(p['path'] + (':' + str(p['line']) if 'line' in p else '')
                            + ' [' + p['rule'] + ']' for p in problems[:8])
        raise RuntimeError('Source scan stopped publication' + (': ' + details if details else '')
                           + '. Details: ' + str(report))
    print('PASS exact staged-source/Gitleaks scan:', record['index_entries_checked'], 'files', flush=True)


def copy_snapshot(snapshot, entries, checkout):
    expected = {e['path'] for e in entries}
    for name in git('ls-files', '-z', cwd=checkout, capture=True).split('\0'):
        if name and name not in expected:
            (checkout / name).unlink()
    for item in entries:
        name = item['path'];target = checkout / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            target.unlink()
        source = snapshot / name
        if item['mode'] == '120000':
            target.symlink_to(os.readlink(source))
        else:
            target.write_bytes(source.read_bytes())
            target.chmod(0o755 if item['mode'] == '100755' else 0o644)
    check_source(checkout, entries)
    git('add', '-A', cwd=checkout)
    check_index(checkout, entries)


def check_index(checkout, entries):
    indexed = {}
    for record in git('ls-files', '--stage', '-z', cwd=checkout, capture=True).split('\0'):
        if not record:
            continue
        metadata, name = record.split('\t', 1)
        mode, object_id, stage = metadata.split()
        if stage != '0' or name in indexed:
            raise RuntimeError('Unmerged or duplicate publication index entry.')
        indexed[name] = (mode, object_id)
    if indexed.keys() != {e['path'] for e in entries}:
        raise RuntimeError('Publication index differs from the reviewed inventory.')
    for entry in entries:
        path = checkout / entry['path']
        data = os.readlink(path).encode() if entry['mode'] == '120000' else path.read_bytes()
        identity = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if indexed[entry['path']] != (entry['mode'], identity):
            raise RuntimeError('Staged source differs from the reviewed file: ' + entry['path'])


def release_or_none(tag):
    response = subprocess.run(['gh', 'api', f'repos/{REPO}/releases/tags/{tag}'],
                              text=True, capture_output=True)
    if response.returncode == 0:
        return json.loads(response.stdout)
    if '(HTTP 404)' in response.stderr:
        return None
    raise RuntimeError('Could not query the release. Check GitHub connectivity/authentication.')


def check_remote_assets(release, expected, *, complete):
    actual = {a['name']: a for a in release['assets']}
    allowed = {a['name']: a for a in expected}
    if not actual.keys() <= allowed.keys() or (complete and actual.keys() != allowed.keys()):
        raise RuntimeError('Remote release has an unexpected/missing asset; nothing will be overwritten.')
    for name, asset in actual.items():
        item = allowed[name]
        if asset['size'] != item['bytes'] or (asset.get('digest') and asset['digest'] != 'sha256:' + item['sha256']):
            raise RuntimeError('Remote asset differs from the verified local artifact: ' + name)
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--dry-run', action='store_true', help='Check the exact prepared source/assets; no network or publication')
    args = parser.parse_args()
    os.umask(0o077)
    if os.geteuid() == 0:
        raise RuntimeError('Run as your normal desktop user, not root.')
    candidates = sorted((ROOT.parent / 'release-dist').glob('*/publication-plan.json'))
    if args.plan is None and len(candidates) != 1:
        raise RuntimeError('Choose the prepared publication-plan.json explicitly with --plan.')
    plan_path = (args.plan or candidates[0]).resolve(strict=True)
    plan, entries, snapshot = check_plan(plan_path)
    base = plan_path.parent
    print('Verified prepared source:', len(entries), 'files; release:', plan['version'], flush=True)
    print('Publication will push reviewed source, upload the OS catalog/payloads, make PetalOS public, and test Bloom.', flush=True)
    if args.dry_run:
        print('Dry run passed; no GitHub change made.')
        return
    for name in ('git', 'gh'):
        if not shutil.which(name):
            raise RuntimeError('Required command missing: ' + name)
    state_path = base / 'publication/state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    plan_sha = digest(plan_path)
    if state and state.get('plan_sha256') != plan_sha:
        raise RuntimeError('Publication plan differs from the saved state.')
    state['plan_sha256'] = plan_sha
    if 'work' not in state:
        parent = ROOT.parent / 'publication-work';parent.mkdir(exist_ok=True)
        state['work'] = tempfile.mkdtemp(prefix=plan['version'] + '-', dir=parent)
    work = Path(state['work'])
    save_state(state_path, state)
    head = gh_json(f'repos/{REPO}/git/ref/heads/main')['object']['sha']
    if head not in {plan['expected_remote_head'], state.get('source_commit')}:
        raise RuntimeError('PetalOS main changed since preparation. Review it before retrying; no force push performed.')
    checkout = work / 'source'
    if not checkout.exists():
        git('clone', '--single-branch', '--branch', 'main', 'https://github.com/' + REPO + '.git', checkout)
    if not state.get('source_commit'):
        if git('rev-parse', 'HEAD', cwd=checkout, capture=True) != plan['expected_remote_head']:
            raise RuntimeError('Unexpected source checkout head.')
        copy_snapshot(snapshot, entries, checkout)
        tool = scanner(work)
        source_scan(checkout, tool, base / 'publication')
        empty_ignore = work / 'empty.gitleaksignore';empty_ignore.write_text('')
        run(tool, 'git', '--log-opts=--all', '--redact=100', '--no-banner',
            '--ignore-gitleaks-allow', '--gitleaks-ignore-path', empty_ignore,
            '--config', checkout / '.gitleaks.toml', checkout, cwd=checkout)
        summary = git('diff', '--cached', '--stat', cwd=checkout, capture=True)
        (base / 'publication/source-change-summary.txt').write_text(summary + '\n')
        user = gh_json('user')
        git('-c', 'user.name=' + user['login'], '-c',
            f'user.email={user["id"]}+{user["login"]}@users.noreply.github.com',
            'commit', '-m', 'Release verified PetalOS RC 1 with independent OS, settings and Private storage', cwd=checkout)
        state['source_commit'] = git('rev-parse', 'HEAD', cwd=checkout, capture=True)
        save_state(state_path, state)
    else:
        check_source(checkout, entries)
        check_index(checkout, entries)
        if git('rev-parse', 'HEAD', cwd=checkout, capture=True) != state['source_commit'] or git('status', '--porcelain', cwd=checkout, capture=True):
            raise RuntimeError('Publication checkout changed; refusing to push.')
    if head != state['source_commit']:
        git('push', 'origin', state['source_commit'] + ':refs/heads/main', cwd=checkout)
    tag = plan['version']
    release = release_or_none(tag)
    if release is None:
        run('gh', 'release', 'create', tag, '--repo', REPO, '--draft', '--target', state['source_commit'],
            '--title', 'PetalOS RC 1 — split-storage development release',
            '--notes-file', base / 'publication/release-notes.md')
        release = release_or_none(tag)
        state['release_id'] = release['id'];save_state(state_path, state)
    if state.get('release_id') != release['id'] or release['target_commitish'] != state['source_commit']:
        raise RuntimeError('Existing release does not belong to this prepared publication; nothing overwritten.')
    uploaded = check_remote_assets(release, plan['assets'], complete=False)
    for item in plan['assets']:
        if item['name'] not in uploaded:
            print('Uploading', item['name'], flush=True)
            run('gh', 'release', 'upload', tag, '--repo', REPO, base / item['path'])
    release = release_or_none(tag)
    check_remote_assets(release, plan['assets'], complete=True)
    # The original user request explicitly authorizes public source/releases.
    # Change visibility only after source/history scans and complete draft checks.
    run('gh', 'api', '--method', 'PATCH', f'repos/{REPO}', '--silent', '-F', 'private=false',
        '-f', 'description=PetalOS: a portable encrypted Debian live OS. Install and manage it with Bloom: https://github.com/Samwarez/Bloom',
        '-f', 'homepage=https://github.com/Samwarez/Bloom')
    run('gh', 'release', 'edit', tag, '--repo', REPO, '--draft=false', '--prerelease=false')
    state['published'] = True
    save_state(state_path, state)
    # Exercise exactly Bloom's default unauthenticated listing and downloader.
    # API/catalog/payload requests get no token and verify every downloaded byte.
    sys.path.insert(0, str(checkout / 'local/installer'))
    from petal_installer import InstallerError
    from petal_installer.releases import GitHub, verify_bundle
    try:
        public_download(plan, base, GitHub, verify_bundle)
    except InstallerError as error:
        raise RuntimeError('Release is published, but Bloom download verification stopped: '
                           + str(error) + ' Rerun this command to retry the check.') from None
    state['public_download_verified'] = True
    save_state(state_path, state)
    print('Published:', 'https://github.com/' + REPO + '/releases/tag/' + tag)
    print('PASS Bloom default listing and complete unauthenticated download/hash verification.')


def public_download(plan, base, GitHub, verify_bundle):
    tag = plan['version']
    client = GitHub(REPO, token=None)
    releases = client.releases()
    if not any(x['version'] == tag and x['installer_catalog'] for x in releases):
        raise RuntimeError('Public release is not visible in Bloom\'s default listing.')
    destination = base / 'public-download-check'
    if not destination.exists():
        last_role = [None]
        def progress(event):
            if event.get('payload') != last_role[0]:
                last_role[0] = event.get('payload');print('Bloom downloading:', last_role[0], flush=True)
        client.download(tag, 'base', destination, progress=progress)
    catalog, variant = verify_bundle(destination)
    if catalog['version'] != tag or variant['id'] != 'base' or digest(destination / 'petalos-release.json') != plan['catalog_sha256']:
        raise RuntimeError('Public download does not match the prepared release.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, OSError) as error:
        print('Publication stopped:', str(error), file=sys.stderr)
        raise SystemExit(1)
