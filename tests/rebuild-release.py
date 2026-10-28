#!/usr/bin/env python3
"""Build a fresh release; authenticate sudo in the invoking terminal."""
from pathlib import Path
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tarfile

PROJECT = Path(__file__).resolve().parents[1]
LOG_LIMIT = 2 * 1024 * 1024


def validate_split_storage(config):
    includes = config / 'includes.chroot'
    installer = config / 'hooks/live/0080-split-storage.hook.chroot'
    initrd_hook = includes / 'etc/initramfs-tools/hooks/petalos-split-storage'
    if not installer.is_file() or not os.access(installer, os.X_OK):
        raise RuntimeError('Missing executable early split-storage installation hook.')
    if not initrd_hook.is_file() or not os.access(initrd_hook, os.X_OK):
        raise RuntimeError('Missing executable split-storage initramfs hook.')
    # Local initramfs hooks are already present when live-build runs its shell
    # hooks. Installing the helper at 0992 was too late for the 0912 refresh.
    for hook in (config / 'hooks/live').glob('*.hook.chroot'):
        commands = '\n'.join(line for line in hook.read_text().splitlines()
                             if line.strip() and not line.lstrip().startswith('#'))
        if re.search(r'\b(?:update-initramfs|mkinitramfs)\b', commands) and hook.name <= installer.name:
            raise RuntimeError('Split-storage helper must be installed before initramfs refresh: ' + hook.name)
    pair = includes/'usr/local/share/portable/native-split-unlock'
    pair_meta = json.loads((pair/'provenance.json').read_text())
    if (pair_meta.get('source_sha256') != digest(PROJECT/'local/split-unlock/unlock-pair.c')
        or pair_meta.get('builder_sha256') != digest(PROJECT/'local/split-unlock/build.py')
        or pair_meta.get('binary_sha256') != digest(pair/'portable-unlock-pair')):
        raise RuntimeError('Rebuild the reviewed split-storage unlock helper before building PetalOS.')


def validate_inputs(config):
    validate_split_storage(config)
    includes = config / 'includes.chroot'
    import importlib.util
    spec = importlib.util.spec_from_file_location('prepare_tor', PROJECT/'scripts/prepare-tor-browser.py')
    tor = importlib.util.module_from_spec(spec);spec.loader.exec_module(tor)
    pin = json.loads((config/'tor-browser.json').read_text())
    bundle = includes/'usr/local/share/portable/tor-browser'
    if json.loads((bundle/'manifest.json').read_text()) != pin:
        raise RuntimeError('Bundled Tor manifest does not match this OS build.')
    tor.validate(bundle,pin,includes/'usr/local/share/portable/tor-browser-developers.keyring')
    media = includes/'usr/share/petalos/test-media'
    clip = json.loads((media/'hardware-test.json').read_text())
    if (clip['file']!='hardware-test.webm' or digest(media/clip['file'])!=clip['sha256']
            or clip['generator_sha256']!=digest(PROJECT/'scripts/generate-test-media.py')):
        raise RuntimeError('Bundled hardware test media differs from its reviewed generator/manifest.')
    dock=includes/'usr/local/share/portable/native-crystal-dock'
    meta=json.loads((dock/'provenance.json').read_text())
    if (meta.get('version')!='2.16' or meta.get('ctest')!='passed'
            or meta.get('binary_sha256')!=digest(dock/'crystal-dock')
            or meta.get('patch_sha256')!=digest(PROJECT/'local/crystal-dock/petalos-integration.patch')
            or meta.get('builder_sha256')!=digest(PROJECT/'local/crystal-dock/build.py')):
        raise RuntimeError('Rebuild the reviewed Crystal Dock component before building PetalOS.')
    graphics=includes/'usr/share/portable/branding/assets.json'
    supplied=json.loads(graphics.read_text())
    for name,expected in supplied['sha256'].items():
        if not re.fullmatch(r'(?:(?:wallpaper|boot)/[A-Za-z0-9][A-Za-z0-9_.-]*\.png|grub\.png)',name):
            raise RuntimeError('Unexpected branding asset path.')
        if name.startswith('wallpaper/'):
            path=includes/'usr/share/backgrounds/petalos-defaults'/name.split('/',1)[1]
        elif name.startswith('boot/'):
            path=includes/'usr/share/plymouth/themes/petalos'/name.split('/',1)[1]
        elif name=='grub.png':path=graphics.parent/name
        else:raise RuntimeError('Unexpected branding asset path.')
        if not re.fullmatch(r'[a-f0-9]{64}',expected) or digest(path)!=expected:
            raise RuntimeError('Supplied branding asset checksum mismatch.')
    # A changed Thunar dispatch must be rebuilt, not paired with a stale binary.
    thunar=includes/'usr/local/share/portable/native-thunar'
    provenance=json.loads((thunar/'provenance.json').read_text())
    if (provenance.get('debian_package_version')!='4.20.2-1+deb13u1'
            or provenance.get('builder_sha256')!=digest(PROJECT/'local/thunar-native/build.py')
            or provenance.get('binary_sha256')!=digest(thunar/'Thunar')
            or provenance.get('make_check')!='passed'
            or provenance.get('patch_sha256')!={name:digest(PROJECT/'local/thunar-native'/name)
                                               for name in ('volatile-trash.patch','ram-trash.c')}):
        raise RuntimeError('Rebuild the reviewed native Thunar inputs before building PetalOS.')
    # Pinned public Debian backports are generated inputs, not arbitrary debs.
    backports=includes/'usr/local/share/portable/security-backports'
    expected=json.loads((PROJECT/'local/security-backports/sources.json').read_text())
    manifest=json.loads((backports/'manifest.json').read_text())
    if manifest.get('format')!=1 or manifest.get('sources')!=expected:
        raise RuntimeError('Security backport inputs do not match reviewed sources.')
    for entry in manifest['packages']:
        if Path(entry['file']).name!=entry['file'] or not entry['file'].endswith('.deb'):
            raise RuntimeError('Unexpected security package input path.')
        archive=backports/entry['file']
        if archive.is_symlink() or digest(archive)!=entry['sha256']:
            raise RuntimeError('Security backport archive checksum mismatch.')
    loader = (includes / 'etc/systemd/system/portable-apparmor.service').read_text()
    for profile in (includes / 'etc/apparmor.d').glob('petalos.*'):
        if profile.name != 'petalos.wayland-probe' and '/etc/apparmor.d/' + profile.name not in loader.split():
            raise RuntimeError('Production AppArmor profile missing from live boot loader.')
    for name in ("bootstrap", "chroot", "binary"):
        content = (config / name).read_text()
        for key, value in re.findall(r'^([A-Z_]+)="([^"]*)"$', content, re.M):
            if "DISTRIBUTION" in key and value and value != "trixie":
                raise RuntimeError("Only Debian trixie is allowed for this build.")
    binary = (config / 'binary').read_text()
    for name in ('LB_BOOTAPPEND_LIVE', 'LB_BOOTAPPEND_LIVE_FAILSAFE'):
        match = re.search(r'^'+name+r'="([^"]*)"$', binary, re.M)
        required = {'toram', 'swap=false', 'init_on_alloc=1', 'init_on_free=1'}
        if not match or not required <= set(match.group(1).split()):
            raise RuntimeError('Required RAM/zeroing boot defaults are missing.')
    for path in config.rglob("*"):
        if path.is_symlink():
            # live-build's distribution-provided hooks are the only input links.
            target = path.resolve(strict=True)
            if not target.is_relative_to(Path("/usr/share/live/build/hooks")):
                raise RuntimeError("Unexpected build-input symlink; review required.")
        elif path.is_file():
            if path.name in ("data.key", "wg0.conf", "root-admin.hash", "admin.hash", "shadow", "gshadow") or path.suffix in (
                ".kdbx", ".gpg", ".key"
            ) or re.search(
                rb"(?im)^\s*(PrivateKey|PresharedKey|Password)\s*=\s*\S+",
                path.read_bytes(),
            ):
                raise RuntimeError("Potential secret in build inputs; contents suppressed.")


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def seed_package_cache(stage):
    """Reuse public packages from the newest completed release, not its chroot."""
    releases = sorted((PROJECT.parent / "releases").glob("*/manifest.json"), reverse=True)
    count = 0
    for category in ("packages.bootstrap", "packages.chroot", "packages.binary"):
        for manifest in releases:
            source = manifest.parent / "build/cache"
            if source.is_symlink() or not source.is_dir():
                continue
            directory = source / category
            if directory.is_symlink() or not directory.is_dir():
                continue
            copied = 0
            for package in directory.glob("*.deb"):
                if package.is_symlink() or not package.is_file() or not os.access(package, os.R_OK):
                    continue
                destination = stage / "cache" / category / package.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(package, destination)
                count += 1
                copied += 1
            if copied:
                print(f"Reused {copied} archives for {category} from {manifest.parent.name}.", flush=True)
                break
    # Reuse the newly verified trixie Wayland archives, not the staged guest.
    caches = sorted((PROJECT.parent/'testing/public-packages').glob('*/manifest.json'), reverse=True)
    if caches:
        import importlib.util
        spec = importlib.util.spec_from_file_location('approved_cache', PROJECT/'tests/cache-wayland-test-packages.py')
        approved = importlib.util.module_from_spec(spec); spec.loader.exec_module(approved)
        manifest = caches[0]
        if manifest.is_symlink() or manifest.parent.is_symlink():
            raise RuntimeError('Unexpected public package-cache symlink.')
        entries = json.loads(manifest.read_text())
        if len(entries) != len(approved.PACKAGES) or {e['package']:e['version'] for e in entries} != approved.PACKAGES:
            raise RuntimeError('Public cache differs from approved trixie versions.')
        for entry in entries:
            if entry['file'] != entry['package']+'.deb':
                raise RuntimeError('Unexpected cached package path.')
            archive = manifest.parent/entry['file']
            if archive.is_symlink() or digest(archive) != entry['sha256']:
                raise RuntimeError('Cached public archive integrity failure.')
            identity = subprocess.check_output(['dpkg-deb','-f',str(archive),'Package','Version','Architecture'],text=True)
            if identity.splitlines() != ['Package: '+entry['package'],'Version: '+entry['version'],'Architecture: amd64']:
                raise RuntimeError('Cached archive package identity mismatch.')
            name = entry['package']+'_'+entry['version'].replace(':','%3a')+'_amd64.deb'
            destination = stage/'cache/packages.chroot'/name
            destination.parent.mkdir(parents=True,exist_ok=True)
            if destination.exists() and digest(destination) != entry['sha256']:
                raise RuntimeError('Conflicting public package cache entry.')
            shutil.copyfile(archive,destination);count += 1
        print(f"Reused {len(entries)} verified Wayland archives.",flush=True)
    print(f"Total reusable public package archives: {count}.", flush=True)


def verify_release(release, state):
    stage = release/'build'
    validate_inputs(stage/'config')
    squashfs = stage / "binary/live/filesystem.squashfs"
    verification_paths = (
        'usr/local/lib/portable/tor_archives.py',
        'usr/local/share/portable/tor-browser/manifest.json',
        'usr/local/share/portable/tor-browser-developers.keyring',
        'usr/share/petalos/test-media/hardware-test.json',
        'usr/share/petalos/test-media/hardware-test.webm',
        'usr/share/applications/portable-test-media.desktop',
        'etc/udev/rules.d/99-portable-storage.rules',
        'usr/local/sbin/portable-check-vpn', 'usr/local/sbin/portable-vpn',
        'usr/local/sbin/portable-check-tor-ready',
        'usr/local/bin/portable-tor', 'usr/local/bin/portable-offline',
        'usr/local/bin/portable-pan', 'usr/local/bin/portable-desktop',
        'usr/lib/live/config/0015-petal-account', 'usr/lib/live/config/0055-petal-auth',
        'usr/lib/live/config/0056-petal-private',
        'etc/live/config.conf.d/10-petal-account.conf', 'etc/hostname',
        'usr/lib/live/config/1085-petal-polkit',
        'etc/polkit-1/rules.d/00-petal-admin.rules',
        'etc/NetworkManager/conf.d/90-portable-dns.conf',
        'etc/bluetooth/main.conf',
        'etc/xdg/mimeapps.list', 'etc/xdg/xfce4/helpers.rc',
        'usr/share/xfce4/helpers/portable-tor.desktop',
        'usr/share/applications/firefox-esr.desktop',
        'usr/share/applications/portable-tor.desktop',
        'usr/local/bin/portable-web-browser',
        'etc/os-release', 'usr/lib/os-release',
        'usr/local/lib/portable/system_state.py',
        'usr/local/lib/portable/desktop_settings.py',
        'usr/local/lib/portable/volatile_trash.py',
        'usr/local/bin/portable-trash',
        'usr/local/bin/portable-lock',
        'usr/local/sbin/portable-lock-auth',
        'etc/lightdm/lightdm.conf.d/99-petalos-wayland.conf',
        'etc/sudoers.d/zz-petal-readchecks',
        'etc/apparmor.d/petalos.offline',
        'etc/apparmor.d/abstractions/petalos-offline-common',
        'etc/apparmor.d/petalos.torbrowser.Browser.firefox',
        'etc/apparmor.d/petalos.torbrowser.Tor.tor',
        'etc/systemd/system/portable-apparmor.service',
        'etc/systemd/system/portable-telemetry.timer',
        'etc/NetworkManager/conf.d/95-portable-privacy.conf',
        'etc/sysctl.d/95-portable-hardening.conf',
    )
    for relative in verification_paths:
        actual = subprocess.check_output(
            ["/usr/bin/unsquashfs", "-cat", str(squashfs), relative]
        )
        if actual != (stage / "config/includes.chroot" / relative).read_bytes():
            raise RuntimeError("Built configuration differs from staged input; contents suppressed.")
    tor_pin = json.loads((stage/'config/tor-browser.json').read_text())
    relative = 'usr/local/share/portable/tor-browser/'+tor_pin['archive']
    checksum = hashlib.sha256()
    with subprocess.Popen(['unsquashfs','-cat',str(squashfs),relative],stdout=subprocess.PIPE) as process:
        while block := process.stdout.read(1024**2):checksum.update(block)
        if process.wait() or checksum.hexdigest()!=tor_pin['sha256']:
            raise RuntimeError('Built Tor Browser archive differs from the pinned signed input.')
    signature = subprocess.check_output(['unsquashfs','-cat',str(squashfs),relative+'.asc'])
    if signature!=(stage/'config/includes.chroot'/str(relative+'.asc')).read_bytes():
        raise RuntimeError('Built Tor Browser signature differs from its verified input.')
    listing = subprocess.check_output(
        ["/usr/bin/unsquashfs", "-ll", str(squashfs)], text=True
    )
    if ".portable-keys" in listing or re.search(r"/data\.key$", listing, re.M):
        raise RuntimeError("Forbidden data-unlock key path in squashfs.")
    packages = subprocess.check_output(['/usr/bin/unsquashfs', '-cat', str(squashfs),
                                        'var/lib/dpkg/status'], text=True)
    if re.search(r'^Package: (?:vlc\S*|libvlc\S*)$', packages, re.M):
        raise RuntimeError('VLC packages remain in the release.')
    if re.search(r'^Package: synaptic$', packages, re.M):
        raise RuntimeError('Synaptic remains in the release.')
    installed_versions={}
    for stanza in packages.split('\n\n'):
        fields=dict(line.split(': ',1) for line in stanza.splitlines()
                    if line and not line[0].isspace() and ': ' in line)
        if fields.get('Status')=='install ok installed':
            installed_versions[fields['Package']]=fields['Version']
    backport_root=stage/'config/includes.chroot/usr/local/share/portable/security-backports'
    backport_manifest=json.loads((backport_root/'manifest.json').read_text())
    critical={'amule':'usr/bin/amule','libxml2':'usr/lib/x86_64-linux-gnu/libxml2.so.2.9.14',
              'polkitd':'usr/lib/polkit-1/polkit-agent-helper-1',
              'libpoppler147':'usr/lib/x86_64-linux-gnu/libpoppler.so.147.0.0'}
    for entry in backport_manifest['packages']:
        name=entry['package'];version=installed_versions.get(name)
        if version is None:
            if name in critical:raise RuntimeError('Required security package missing from image.')
            continue
        if subprocess.run(['dpkg','--compare-versions',version,'ge',entry['version']]).returncode:
            raise RuntimeError('Image contains an older dependency than the reviewed security repair.')
        if name in critical and version==entry['version']:
            payload=subprocess.check_output(['dpkg-deb','--fsys-tarfile',str(backport_root/entry['file'])])
            with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
                member=archive.getmember('./'+critical[name])
                if not member.isfile():raise RuntimeError('Security executable is not a regular package file.')
                expected=archive.extractfile(member).read()
            target=critical[name]+('.portable-real' if name=='amule' else '')
            actual=subprocess.check_output(['unsquashfs','-cat',str(squashfs),target])
            if actual!=expected:raise RuntimeError('Security executable differs from reviewed package.')
    cups = subprocess.check_output(['/usr/bin/unsquashfs', '-cat', str(squashfs),
                                    'etc/cups/cupsd.conf'], text=True)
    directives = [line.split() for line in cups.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    listeners = [line for line in directives if line[0] in ('Listen', 'Port')]
    if (listeners != [['Listen', '/run/cups/cups.sock']] or
            ['Browsing', 'Off'] not in directives or ['WebInterface', 'No'] not in directives):
        raise RuntimeError('Manual printing has unexpected network exposure.')
    if re.search(r'/usr/bin/vlc(?:\.portable-real)?$', listing, re.M):
        raise RuntimeError('VLC executable remains in the release.')
    # Check every explicit public file, without extracting unrelated OS files.
    public = stage/'config/includes.chroot'
    removed_debs={'usr/local/share/portable/security-backports/'+entry['file']
                  for entry in backport_manifest['packages']}
    paths = sorted(str(path.relative_to(public)) for path in public.rglob('*')
                   if path.is_file() and str(path.relative_to(public)) not in removed_debs)
    # The native-player hook installs this verified staging artifact into
    # the diverted executable and removes the redundant staging copy.
    installed_paths = {
        'usr/local/share/portable/native-parole/parole': 'usr/bin/parole.portable-real',
        'usr/local/share/portable/native-conky/conky': 'usr/bin/conky',
        'usr/local/share/portable/native-keepassxc/keepassxc': 'usr/bin/keepassxc.portable-real',
        'usr/local/share/portable/native-keepassxc/keepassxc-cli': 'usr/bin/keepassxc-cli',
        'usr/local/share/portable/native-thunar/Thunar': 'usr/bin/Thunar',
        'usr/local/share/portable/native-crystal-dock/crystal-dock': 'usr/bin/crystal-dock',
    }
    with tempfile.TemporaryDirectory(prefix='public-artifact-check-', dir=state) as directory:
        extracted = Path(directory)/'root'
        subprocess.run(['/usr/bin/unsquashfs','-no-progress','-no-xattrs','-d',str(extracted),
                        str(squashfs),*[installed_paths.get(path, path) for path in paths]],
                       check=True,stdout=subprocess.DEVNULL)
        for relative in paths:
            if (extracted/installed_paths.get(relative, relative)).read_bytes() != (public/relative).read_bytes():
                raise RuntimeError('Public build input differs in final artifact: '+relative+'; contents suppressed.')
    checked = 0
    for bootfile in (stage/'binary').rglob('*.cfg'):
        if bootfile.is_symlink():continue
        for line in bootfile.read_text(errors='replace').splitlines():
            words = line.strip().split()
            if words and words[0] in ('linux','linuxefi','append') and 'boot=live' in words:
                if not {'toram','swap=false','init_on_alloc=1','init_on_free=1'} <= set(words):
                    raise RuntimeError('Generated bootloader lacks required RAM/zeroing options.')
                checked += 1
    if not checked:raise RuntimeError('No generated live bootloader entry verified.')
    initrd_listing=set(subprocess.check_output(['/usr/bin/lsinitramfs',str(stage/'binary/live/initrd.img')],text=True).splitlines())
    required={'scripts/init-premount/portable-unlock','scripts/panic/plymouth',
              'usr/share/plymouth/themes/petalos/petalos.script'}
    if not {'bin/portable-unlock-pair', 'usr/bin/portable-unlock-pair'} & initrd_listing:
        raise RuntimeError('Final initramfs is missing the split-storage unlock helper.')
    required.update('usr/share/plymouth/themes/petalos/'+name.split('/',1)[1]
                    for name in json.loads((public/'usr/share/portable/branding/assets.json').read_text())['sha256']
                    if name.startswith('boot/'))
    if (not required<=initrd_listing or
            not {'bin/petalos-splash','usr/bin/petalos-splash'}&initrd_listing):
        raise RuntimeError('Final initramfs is missing PetalOS branding/unlock components.')
    print(f"Verified {len(paths)} public files and {checked} live bootloader entries.",flush=True)
    outputs = ("binary/live/vmlinuz", "binary/live/initrd.img",
               "binary/live/filesystem.squashfs", "live-image-amd64.hybrid.iso",
               "binary/boot/grub/petalos/grub.png", "binary/boot/grub/petalos/theme.txt",
               "binary/boot/grub/petalos/unicode.pf2")
    manifest = {name: {"sha256": digest(stage / name),
                       "bytes": (stage / name).stat().st_size}
                for name in outputs}
    (release / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    if os.geteuid() == 0:
        raise RuntimeError("Run this coordinator as Sam, not root.")
    subprocess.run([sys.executable,'-B',str(PROJECT/'scripts/prepare-tor-browser.py')],check=True)
    validate_inputs(PROJECT / "config")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    release = PROJECT.parent / "releases" / stamp
    stage = release / "build"
    stage.mkdir(parents=True)
    shutil.copytree(PROJECT / "config", stage / "config", symlinks=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(PROJECT / "auto", stage / "auto", symlinks=True)
    seed_package_cache(stage)
    runtime = Path(f"/run/user/{os.getuid()}")
    if runtime.stat().st_uid != os.getuid():
        raise RuntimeError("Unexpected runtime-directory owner.")
    state = runtime / "petalos-build" / stamp
    state.mkdir(parents=True, mode=0o700)
    log = state / "build.log"
    status = state / "status.json"

    def update(phase):
        temp = state / "status.tmp"
        temp.write_text(json.dumps({"phase": phase, "release": str(release)}))
        temp.replace(status)

    def run(command):
        # Sudo reads its password from the terminal, never this output pipe.
        with log.open("a+b") as output:
            process = subprocess.Popen(
                command, cwd=stage, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, umask=0o022,
            )
            try:
                while chunk := process.stdout.read1(65536):
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.buffer.flush()
                    output.write(chunk)
                    output.flush()
                    if output.tell() > LOG_LIMIT:
                        output.seek(-LOG_LIMIT, os.SEEK_END)
                        tail = output.read()
                        output.seek(0)
                        output.truncate(0)
                        output.write(tail)
                        output.flush()
                if process.wait():
                    raise RuntimeError("Build command failed; see bounded RAM log.")
            except BaseException:
                if process.poll() is None:
                    process.terminate()
                    process.wait()
                raise

    print(f"New release directory: {release}", flush=True)
    print(f"Bounded RAM log and status: {state}", flush=True)
    try:
        update("configuring")
        run(["/usr/bin/lb", "config"])
        validate_inputs(stage / "config")
        update("awaiting-sudo-authentication")
        run(["/usr/bin/sudo", "-v"])
        update("building")
        run(["/usr/bin/sudo", "--", "/usr/bin/lb", "build"])
        update("verifying")
        verify_release(release, state)
        update("complete")
        print("Build and artifact verification completed. Existing image preserved.")
    except BaseException:
        update("failed")
        raise


if __name__ == "__main__":
    os.umask(0o077)
    try:
        if len(sys.argv) == 1:
            main()
        elif len(sys.argv) == 3 and sys.argv[1] == '--verify-existing':
            if os.geteuid() == 0:
                raise RuntimeError('Run verification as Sam, not root.')
            release = Path(sys.argv[2]).resolve(strict=True)
            if release.parent != PROJECT.parent/'releases':
                raise RuntimeError('Expected an existing project release directory.')
            state = Path(f'/run/user/{os.getuid()}/petalos-build')/release.name
            if state.stat().st_uid != os.getuid():
                raise RuntimeError('Unexpected verification-directory owner.')
            verify_release(release, state)
            (state/'status.json').write_text(json.dumps({'phase':'complete','release':str(release)}))
            print('Build and artifact verification completed. Existing image preserved.')
        else:
            raise RuntimeError('Usage: rebuild-release.py [--verify-existing RELEASE]')
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
