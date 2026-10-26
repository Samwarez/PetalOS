"""CLI entry point. JSON output is also the GUI/core integration boundary."""
from pathlib import Path
import argparse
import json
import os
import sys

from . import InstallerError, __version__
from . import linux
from . import portable
from .plans import ENCRYPTION, WIPE_METHODS, make_plan
from .releases import GitHub, verify_bundle
from .encryption import calibrate, SHARED_EXPLANATION, PORTABILITY_EXPLANATION


def parser():
    result = argparse.ArgumentParser(prog='bloom', description='Bloom — install and manage PetalOS')
    result.add_argument('--version', action='version', version=__version__)
    result.add_argument('--json', action='store_true', help='Machine-readable results/errors; progress goes to stderr.')
    result.add_argument('--repo', default='Samwarez/PetalOS', help='GitHub owner/repository')
    sub = result.add_subparsers(dest='command', required=True)
    releases = sub.add_parser('releases', help='List GitHub release versions')
    releases.add_argument('--prereleases', action='store_true')
    variants = sub.add_parser('variants', help='List the variants for a release version')
    variants.add_argument('--version', required=True)
    download = sub.add_parser('download', help='Download and verify one version/variant')
    download.add_argument('--version', required=True)
    download.add_argument('--variant', required=True)
    download.add_argument('--destination', type=Path, required=True)
    verify = sub.add_parser('verify', help='Verify a downloaded local bundle')
    verify.add_argument('bundle', type=Path)
    pack = sub.add_parser('bundle-create', help='Package reviewed local build artifacts for the installer; no upload')
    for option in ('kernel', 'initrd', 'rootfs', 'shim', 'grub', 'mokmanager'):
        pack.add_argument('--' + option, type=Path, required=True)
    pack.add_argument('--module', action='append', default=[], metavar='NAME=PATH')
    pack.add_argument('--version', required=True)
    pack.add_argument('--variant', required=True)
    pack.add_argument('--name', required=True)
    pack.add_argument('--local-ai', action='store_true')
    pack.add_argument('--destination', type=Path, required=True)
    export = sub.add_parser('bundle-from-build', help='Export a completed split-storage live-build release for local installation')
    export.add_argument('release', type=Path)
    export.add_argument('--version', required=True)
    export.add_argument('--variant', default='base')
    export.add_argument('--name', default='PetalOS')
    export.add_argument('--local-ai', action='store_true')
    export.add_argument('--destination', type=Path, required=True)
    sub.add_parser('devices', help='Inspect Linux disks without writing to them')
    profiles = sub.add_parser('encryption', help='Encryption choices and real host measurements')
    profiles.add_argument('--benchmark', action='store_true', help='Measure RAM cipher throughput; does not touch any disk.')
    profiles.add_argument('--calibrate', choices=ENCRYPTION, help='Measure an Argon2id tier using RAM only; no drive is changed.')
    for mode in ('install', 'update', 'wipe', 'system-store'):
        operation = sub.add_parser(mode, help='Review a ' + mode + ' plan; write only with --execute and confirmation')
        operation.add_argument('--device', required=True, help='Exact whole-disk path from devices')
        if mode in {'install', 'update'}:
            operation.add_argument('--bundle', type=Path, required=True)
        if mode == 'install':
            operation.add_argument('--encryption', choices=ENCRYPTION, default='balanced')
            operation.add_argument('--system-gib', type=int)
            operation.add_argument('--os-gib', type=int)
            operation.add_argument('--erase-mode', choices=('random', 'quick'), default='random')
        if mode == 'update':
            operation.add_argument('--retention', choices=('production', 'test'), default='production')
        if mode == 'wipe':
            operation.add_argument('--method', choices=WIPE_METHODS, default='keys-and-random')
        if mode != 'system-store':
            operation.add_argument('--execute', action='store_true', help='Execute the reviewed operation as administrator')
            operation.add_argument('--confirm', help='Exact plan_sha256 from the reviewed plan; otherwise an interactive confirmation is required')
    store = sub.add_parser('store', help='Open SYSTEM using its passphrase, inspect or import; requires root')
    store.add_argument('--device', required=True, help='Whole disk; only its SYSTEM partition is opened')
    store.add_argument('--import', dest='source', type=Path)
    store.add_argument('--kind', choices=('vpn', 'wallpaper', 'theme', 'override'))
    store.add_argument('--name')
    store.add_argument('--replace', action='store_true', help='Atomically replace that exact existing settings filename')
    recovery = sub.add_parser('recovery', help='Verify the SYSTEM passphrase against both independent headers without opening them')
    recovery.add_argument('--device', required=True, help='Whole disk from devices')
    image = sub.add_parser('image-wipe', help='DEVELOPMENT: execute a wipe on an owned regular image file only')
    image.add_argument('--image', type=Path, required=True)
    image.add_argument('--method', choices=WIPE_METHODS, default='keys-and-random')
    image.add_argument('--confirm', required=True, help='WIPE followed by the absolute image path')
    sub.add_parser('gui', help='Open the optional soft-pink Linux GTK overlay')
    return result


def dispatch(args, progress=lambda event: None, *, github_token=None):
    client = GitHub(args.repo, token=github_token if github_token is not None else os.environ.get('GH_TOKEN'))
    if args.command == 'releases':
        return client.releases(args.prereleases)
    if args.command == 'variants':
        catalog, _, _ = client.catalog(args.version)
        return {'version': catalog['version'], 'variants': catalog['variants']}
    if args.command == 'download':
        return client.download(args.version, args.variant, args.destination, progress)
    if args.command == 'verify':
        catalog, variant = verify_bundle(args.bundle)
        return {'verified': True, 'version': catalog['version'], 'variant': variant['id'],
                'local_ai': variant['local_ai'], 'payloads': len(variant['payloads']),
                'scope': 'Payload consistency against the local catalog; independent publisher signature not established.'}
    if args.command == 'bundle-create':
        from .bundles import create_bundle
        modules = {}
        for value in args.module:
            if '=' not in value:raise InstallerError('Modules use NAME.squashfs=/path/to/file syntax.')
            name, path = value.split('=', 1)
            if name in modules:raise InstallerError('Duplicate module name.')
            modules[name] = Path(path)
        return create_bundle(args.destination, args.version, args.variant, args.name,
            {role: getattr(args, role) for role in ('kernel', 'initrd', 'rootfs', 'shim', 'grub', 'mokmanager')},
            modules=modules, local_ai=args.local_ai)
    if args.command == 'bundle-from-build':
        from .bundles import from_build
        return from_build(args.release, args.destination, args.version, args.variant, args.name, local_ai=args.local_ai)
    if args.command == 'devices':
        return linux.devices()
    if args.command == 'encryption':
        if args.calibrate:return {'tier': args.calibrate, 'calibration': calibrate(args.calibrate),
                                  'scope': 'RAM-only measurement on this computer; no drive changes.'}
        return linux.benchmark() if args.benchmark else {'profiles': ENCRYPTION,
            'protection': SHARED_EXPLANATION, 'calibration': PORTABILITY_EXPLANATION}
    if args.command in {'install', 'update', 'wipe', 'system-store'}:
        plan = make_plan(args.command, linux.choose(args.device), bundle=getattr(args, 'bundle', None),
            encryption=getattr(args, 'encryption', 'balanced'), system_gib=getattr(args, 'system_gib', None),
            os_gib=getattr(args, 'os_gib', None),
            wipe_method=getattr(args, 'method', 'keys-and-random'), erase_mode=getattr(args, 'erase_mode', 'random'),
            retention=getattr(args, 'retention', 'production'))
        if not getattr(args, 'execute', False):return plan
        if os.geteuid() != 0 and portable.root() is None:
            raise InstallerError('Execute from an administrator terminal, or use the GUI administrator prompt.')
        confirmation = args.confirm
        if confirmation is None:
            if not sys.stdin.isatty():raise InstallerError('Execution requires --confirm with the exact reviewed plan_sha256.')
            print(human(plan), file=sys.stderr)
            word = 'ERASE' if args.command in ('install', 'wipe') else 'UPDATE'
            entered = input('Type ' + word + ' to confirm the drive and operation above: ')
            if entered != word:raise InstallerError('Cancelled before writing to the drive.')
            confirmation = plan['plan_sha256']
        if confirmation != plan['plan_sha256']:raise InstallerError('Plan confirmation does not match; review the current plan.')
        from .bridge import request_from_plan, collect_credentials
        if portable.root() is not None:
            from .bridge import privileged
            return privileged(request_from_plan(plan, getattr(args, 'bundle', None)),
                              collect_credentials(args.command, encryption=plan.get('encryption', {}).get('id', 'balanced')), progress)
        from .engine import execute
        return execute(request_from_plan(plan, getattr(args, 'bundle', None)),
                       collect_credentials(args.command, encryption=plan.get('encryption', {}).get('id', 'balanced')), progress)
    if args.command == 'store':
        from .store import system_session, inventory, import_file, checked_payload
        if args.source:
            if not args.kind or not args.name:
                raise InstallerError('Imports require --kind and --name.')
            # Refuse invalid sources before unlocking or mounting the drive.
            checked_payload(args.kind, args.source)
        elif args.kind or args.name or args.replace:
            raise InstallerError('--kind and --name require --import.')
        if portable.root() is not None:
            from .bridge import collect_credentials, privileged
            plan = make_plan('system-store', linux.choose(args.device))
            request = {'mode': 'store', 'device': args.device, 'plan_sha256': plan['plan_sha256'],
                       'action': 'import' if args.source else 'list'}
            if args.source:request.update(source=str(args.source.absolute()), kind=args.kind, name=args.name, replace=args.replace)
            return privileged(request, collect_credentials('store'), progress)
        with system_session(args.device, writable=bool(args.source)) as state:
            return import_file(state, args.kind, args.source, args.name, replace=args.replace) if args.source else inventory(state)
    if args.command == 'recovery':
        if portable.root() is not None:
            from .bridge import collect_credentials, privileged
            plan = make_plan('system-store', linux.choose(args.device))
            return privileged({'mode': 'recovery', 'device': args.device, 'plan_sha256': plan['plan_sha256']},
                              collect_credentials('recovery'), progress)
        from .recovery import verify_pair
        return verify_pair(args.device)
    if args.command == 'image-wipe':
        from .image_wipe import wipe_image
        return wipe_image(args.image, args.method, args.confirm, progress)
    if args.command == 'gui':
        from .gui import run
        run(args.repo)
        return None
    raise InstallerError('Unknown command.')


def human(value):
    if isinstance(value, dict) and 'plan_sha256' in value:
        lines = [value['mode'].replace('-', ' ').title() + ' plan',
                 value['target']['model'] + ' — ' + value['target']['path'],
                 'Review only. No drive changes occur until explicit execution and administrator authentication.',
                 'Plan confirmation: ' + value['plan_sha256']]
        if 'release' in value:
            release = value['release']
            lines.append('Version ' + release['version'] + ' · ' + release['name'] +
                         (' · local AI agent' if release['local_ai'] else ''))
        if 'encryption' in value:
            policy = value['encryption']
            lines.extend(['Protection: ' + policy['name'], policy['description'],
                          'Calibration runs on this computer before erasing; other computers may unlock more slowly.'])
        lines.extend(str(i + 1) + '. ' + step for i, step in enumerate(value['steps']))
        if value['preserves']:
            lines.append('Preserves: ' + '; '.join(value['preserves']))
        lines.extend('Requires: ' + item for item in value['requires'])
        lines.extend('Limit: ' + item for item in value.get('limits', []))
        return '\n'.join(lines)
    return json.dumps(value, indent=2, ensure_ascii=False)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        def progress(event):
            print(json.dumps(event), file=sys.stderr, flush=True)
        result = dispatch(args, progress)
        if result is not None:
            print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else human(result))
        return 0
    except KeyboardInterrupt:
        error = 'Cancelled. A write operation may already have removed keys or partially changed the selected media; inspect its progress before retrying.' if args.command == 'image-wipe' or getattr(args, 'execute', False) else 'Cancelled.'
    except InstallerError as exception:
        error = str(exception)
    except Exception:
        # Never expose subprocess arguments, HTTP auth headers, profile text or secrets.
        error = 'Operation stopped unexpectedly. No raw diagnostic data was printed.'
    print(json.dumps({'error': error}) if args.json else error, file=sys.stderr)
    return 1
