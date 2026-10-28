#!/usr/bin/python3 -B
"""Build the portable amd64 runtime from checksum-verified trixie package files.

No package install, network request, host configuration or physical media write.
Only dpkg-owned public runtime files and maintained installer sources are read.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from petal_installer import __version__
from petal_installer.portable import chunks

PACKAGES = '''python3 python3-gi gir1.2-gtk-3.0 libgtk-3-bin librsvg2-common libzxcvbn0 cryptsetup-bin dmsetup gdisk parted
udev dosfstools e2fsprogs util-linux psmisc openssl sbsigntool initramfs-tools-core
squashfs-tools cpio gzip zstd coreutils dash findutils grep sed tar ca-certificates
fonts-dejavu-core adwaita-icon-theme gsettings-desktop-schemas shared-mime-info'''.split()


def run(arguments):
    return subprocess.check_output(arguments, text=True)


def package_closure():
    rows = run(['dpkg-query', '-W', '-f=${binary:Package}\t${Version}\t${db:Status-Status}\t${Depends}\t${Pre-Depends}\t${Provides}\t${Architecture}\n'])
    records = {};providers = {}
    for row in rows.splitlines():
        name, version, status, depends, pre, provides, architecture = row.split('\t')
        if status != 'installed' or architecture not in ('amd64', 'all'):continue
        short = name.split(':')[0]
        records[short] = {'package': name, 'version': version, 'depends': depends + ',' + pre}
        for item in provides.split(','):
            key = re.split(r'\s|:', item.strip())[0]
            if key:providers.setdefault(key, []).append(short)
    todo = PACKAGES[:];seen = set()
    while todo:
        name = todo.pop()
        if name in seen:continue
        if name not in records:raise RuntimeError('Build dependency is not installed: ' + name)
        seen.add(name)
        for clause in records[name]['depends'].split(','):
            if not clause.strip():continue
            options = [re.split(r'\s|:', item.strip())[0] for item in clause.split('|')]
            selected = next((option for option in options if option in records), None)
            if selected is None:
                selected = next((sorted(providers[option])[0] for option in options if option in providers), None)
            if selected is None:raise RuntimeError('Unresolved installed dependency: ' + name + ' / ' + clause)
            todo.append(selected)
    return [records[name] for name in sorted(seen)]


def copy_runtime(destination, packages):
    runtime = destination / 'runtime';runtime.mkdir()
    entries = {};checksums = {};metadata = Path('/var/lib/dpkg/info')
    for record in packages:
        name = record['package']
        check = metadata / (name + '.md5sums')
        if not check.is_file():check = metadata / (name.split(':')[0] + '.md5sums')
        if check.is_file():
            for line in check.read_text().splitlines():
                digest, path = line.split(maxsplit=1)
                original = Path('/') / path
                checksums[str(original.parent.resolve() / original.name)] = digest
        for value in run(['dpkg-query', '-L', name]).splitlines():
            path = Path(value)
            if not path.is_absolute():continue
            value = str(path.parent.resolve() / path.name)
            if not value.startswith('/usr/') or not path.is_file():continue
            if '/__pycache__/' in value or value.endswith(('.pyc', '.pyo', '.a', '.h')):continue
            if value.startswith(('/usr/include/', '/usr/share/man/', '/usr/share/info/', '/usr/share/lintian/')):continue
            if value.startswith('/usr/share/doc/') and path.name not in ('copyright', 'LICENSE', 'LICENSE.gz'):continue
            if value.startswith('/usr/lib/systemd/') and '/lib' not in value[len('/usr/lib/systemd/'):]:
                # Retain dlopen/runtime pieces; service definitions are harmless
                # but unnecessary. Keep systemd libraries under /usr/lib/*.
                if path.suffix in ('.service', '.target', '.socket', '.timer'):continue
            entries[value] = path
    copied = set()
    for value, source in sorted(entries.items()):
        resolved = source.resolve(strict=True)
        # Distro aliases into /etc are host configuration, not portable inputs.
        if not str(resolved).startswith('/usr/'):continue
        expected = checksums.get(str(resolved))
        if expected is None:raise RuntimeError('Runtime file has no package checksum: ' + str(resolved))
        content = resolved.read_bytes()
        if hashlib.md5(content).hexdigest() != expected:raise RuntimeError('Installed package file changed: ' + str(resolved))
        target = runtime / value.lstrip('/');target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content);target.chmod(0o755 if source.stat().st_mode & 0o111 else 0o644)
        copied.add(value)
    # Include upstream license texts referenced by the package copyright files.
    shutil.copytree('/usr/share/common-licenses', runtime / 'usr/share/common-licenses', dirs_exist_ok=True)
    # A standard public CA bundle, excluding locally added host certificates.
    certificates = sorted((runtime / 'usr/share/ca-certificates/mozilla').glob('*.crt'))
    assert certificates, 'No packaged CA certificates were found.'
    bundle = runtime / 'etc/ssl/certs/ca-certificates.crt';bundle.parent.mkdir(parents=True)
    bundle.write_bytes(b'\n'.join(path.read_bytes() for path in certificates))
    # /lib64 is a merged-/usr alias; explicitly provide the loader there.
    loader = runtime / 'usr/lib64/ld-linux-x86-64.so.2';loader.parent.mkdir(parents=True, exist_ok=True)
    source = runtime / 'usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2'
    assert source.is_file();shutil.copyfile(source, loader);loader.chmod(0o755)
    schemas = runtime / 'usr/share/glib-2.0/schemas'
    subprocess.run(['/usr/bin/glib-compile-schemas', str(schemas)], check=True)
    subprocess.run(['/usr/bin/update-mime-database', str(runtime / 'usr/share/mime')],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return copied


LAUNCHER = '''#!/bin/sh
set -eu
petal_parent=${0%/*}
[ "$petal_parent" != "$0" ] || petal_parent=.
petal_dir=$(CDPATH= cd -- "$petal_parent" && pwd -P)
case "$petal_dir" in *:*) echo 'Move the app to a path without colon characters.' >&2; exit 1;; esac
petal_runtime="$petal_dir/runtime"
unset PYTHONPATH PYTHONSTARTUP PYTHONINSPECT LD_PRELOAD LD_AUDIT GTK_MODULES GTK3_MODULES
export PYTHONHOME="$petal_runtime/usr" PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
export LD_LIBRARY_PATH="$petal_runtime/usr/lib/x86_64-linux-gnu:$petal_runtime/usr/lib"
export GI_TYPELIB_PATH="$petal_runtime/usr/lib/x86_64-linux-gnu/girepository-1.0"
export GSETTINGS_SCHEMA_DIR="$petal_runtime/usr/share/glib-2.0/schemas"
export GTK_PATH="$petal_runtime/usr/lib/x86_64-linux-gnu/gtk-3.0"
export GIO_MODULE_DIR="$petal_runtime/usr/lib/x86_64-linux-gnu/gio/modules"
export GIO_USE_VFS=local GIO_USE_VOLUME_MONITOR=unix
export XDG_DATA_DIRS="$petal_runtime/usr/share"
export GSETTINGS_BACKEND=memory
export SSL_CERT_FILE="$petal_runtime/etc/ssl/certs/ca-certificates.crt"
export FONTCONFIG_FILE="$petal_dir/fonts.conf"
exec "$petal_runtime/usr/lib64/ld-linux-x86-64.so.2" --library-path "$LD_LIBRARY_PATH" \\
    "$petal_runtime/usr/bin/python3" -s -P -B "$petal_dir/app/portable-entry.py" "$@"
'''


def stage(destination):
    assert platform.machine() == 'x86_64'
    assert 'VERSION_CODENAME=trixie' in Path('/etc/os-release').read_text()
    destination.mkdir()
    spec = importlib.util.spec_from_file_location('installer_package', HERE / 'build-package.py')
    package = importlib.util.module_from_spec(spec);spec.loader.exec_module(package)
    with tempfile.TemporaryDirectory(prefix='petalos-portable-source-') as temporary:
        staged = Path(temporary) / 'package';package.stage(staged)
        shutil.copytree(staged / 'usr/lib/bloom-installer', destination / 'app')
    shutil.copyfile(HERE / 'portable-entry.py', destination / 'app/portable-entry.py')
    packages = package_closure()
    print('Bundling', len(packages), 'installed trixie runtime packages', flush=True)
    copied = copy_runtime(destination, packages)
    loader_directory = destination / 'runtime/usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/2.10.0/loaders'
    pixbuf = run(['/usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders',
                  *map(str, sorted(loader_directory.glob('*.so')))])
    (destination / 'app/pixbuf-loaders.cache.in').write_text(pixbuf.replace(str(destination), '@PETAL_ROOT@'))
    tools = destination / 'tools';tools.mkdir()
    for value in sorted(copied):
        if not value.startswith(('/usr/bin/', '/usr/sbin/')):continue
        source = Path(value)
        if not source.stat().st_mode & 0o111:continue
        target = tools / source.name
        if target.exists():continue
        target.write_text('#!/bin/sh\npetal_tool_dir=$(CDPATH= cd -- "${0%/*}/.." && pwd -P)\nexec "$petal_tool_dir/bloom" --portable-tool ' + value + ' "$@"\n')
        target.chmod(0o755)
    launcher = destination / 'bloom';launcher.write_text(LAUNCHER);launcher.chmod(0o755)
    compatibility = destination / 'petal-installer';compatibility.write_text(LAUNCHER);compatibility.chmod(0o755)
    # Fontconfig supports prefix="relative", so relocation needs no rewriting.
    (destination / 'fonts.conf').write_text('''<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig><dir prefix="relative">runtime/usr/share/fonts</dir>
<cachedir prefix="xdg">fontconfig</cachedir><config></config></fontconfig>
''')
    files = []
    for prefix in ('app', 'runtime'):
        for path in sorted((destination / prefix).rglob('*')):
            if not path.is_file():continue
            assert not path.is_symlink()
            files.append({'path': str(path.relative_to(destination)), 'mode': 0o755 if path.stat().st_mode & 0o111 else 0o644,
                          'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    value = {'format': 1, 'name': 'Bloom', 'bootstrap': 'bloom-admin', 'version': __version__, 'architecture': 'amd64', 'files': files,
             'packages': [{'package': p['package'], 'version': p['version']} for p in packages]}
    digest = hashlib.sha256();length = 0
    for data in chunks(destination, value):digest.update(data);length += len(data)
    assert length <= 1024**3
    value.update(payload_sha256=digest.hexdigest(), payload_bytes=length)
    with tempfile.TemporaryDirectory(prefix='petalos-portable-native-') as temporary:
        pin = Path(temporary) / 'portable-pin.h'
        pin.write_text('#define PAYLOAD_BYTES UINT64_C(' + str(length) + ')\n#define PAYLOAD_SHA256 "' + digest.hexdigest() + '"\n')
        subprocess.run(['/usr/bin/gcc', '-std=gnu11', '-O2', '-static', '-Wall', '-Wextra', '-Werror',
                        '-fstack-protector-strong', '-D_FORTIFY_SOURCE=3', '-Wl,-z,relro,-z,now,-z,noexecstack',
                        '-I', temporary, str(HERE / 'portable-admin.c'), '-o', str(destination / 'bloom-admin')], check=True)
    value['bootstrap_sha256'] = hashlib.sha256((destination / 'bloom-admin').read_bytes()).hexdigest()
    (destination / 'portable.json').write_text(json.dumps(value, indent=2) + '\n')
    (destination / 'README.txt').write_text('''Bloom ''' + __version__ + ''' — portable Linux amd64

Extract the entire folder, then run ./bloom (or double-click it).
No .deb installation, FUSE or host Python/GTK/disk-tool installation is needed.
To use the CLI: ./bloom --help
Verify the portable runtime: ./bloom --portable-check

Drive operations ask for administrator authorization. Your desktop must have
pkexec and its authorization agent. Initial target: Debian 13 / compatible amd64
Linux desktops with merged /usr, mount namespaces and the kernel SHA-256 API.
No app policy or service is installed. The temporary root-only worker lives
under /run and is removed after normal completion, errors or cancellation.
Power loss or forced termination may leave its public runtime until reboot.
The GUI stays unprivileged. Passwords travel only through a private pipe.
Do not run the entire app with sudo. Trust the complete portable app download;
its self-check is integrity checking, not an independent publisher signature.

The OS build is a separate download. A clean layout-2 OS build is still needed
before using this installer on physical PetalOS media. No card was modified by
building or testing this package.

Runtime package versions are recorded in portable.json. Package copyright and
upstream licenses are under runtime/usr/share/doc and usr/share/common-licenses.
''')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'installer-dist')
    args = parser.parse_args();args.output.mkdir(parents=True, exist_ok=True)
    name = 'bloom-' + __version__ + '-linux-amd64'
    target = args.output / name
    if target.exists():raise RuntimeError('Portable output exists; choose a new --output directory.')
    with tempfile.TemporaryDirectory(prefix='.portable-stage-', dir=args.output) as temporary:
        pending = Path(temporary) / name
        value = stage(pending)
        pending.rename(target)
    archive = args.output / (name + '.tar.gz')
    with tarfile.open(archive, 'x:gz', compresslevel=6) as output:
        output.add(target, arcname=name)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_name(archive.name + '.sha256').write_text(checksum + '  ' + archive.name + '\n')
    print('Portable app:', target)
    print('Portable archive:', archive)
    print('Verified runtime files:', len(value['files']), 'uncompressed bytes:', value['payload_bytes'])


if __name__ == '__main__':main()
