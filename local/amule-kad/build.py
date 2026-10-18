#!/usr/bin/env python3
"""Build the patched trixie GUI without installing packages on the host."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

ORIGINAL = 'a647309642331f3e033fdf0196e7232cdc67f46739d12a0294be06885f70c8bd'
DEBIAN = '8f8fe2b8bda5fb51ad945872523ba53fbc8fd9f8d81b493cc8ebd7d07237e779'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source_archive', type=Path)
    p.add_argument('debian_archive', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--sysroot', type=Path)
    p.add_argument('--jobs', type=int, default=4)
    p.add_argument('--resume', action='store_true', help='Reuse a checksum-verified prepared source tree')
    args = p.parse_args()
    if os.geteuid() == 0:
        p.error('Build as the ordinary user.')
    for archive, expected in [(args.source_archive, ORIGINAL), (args.debian_archive, DEBIAN)]:
        if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
            p.error('Source archive checksum mismatch.')
    args.output = args.output.resolve()
    source = args.output / 'aMule-2.3.3'
    patch = Path(__file__).with_name('connect-options.patch')
    prepared = args.output / 'prepared.json'
    if args.resume:
        state = json.loads(prepared.read_text())
        assert state['patch_sha256'] == hashlib.sha256(patch.read_bytes()).hexdigest()
        assert state['prefs_sha256'] == hashlib.sha256((source / 'src/kademlia/kademlia/Prefs.cpp').read_bytes()).hexdigest()
        applied = state['debian_patches']
    else:
        args.output.mkdir(exist_ok=False, parents=True)
        for archive in (args.source_archive, args.debian_archive):
            with tarfile.open(archive) as t:
                t.extractall(args.output, filter='data')
        source = args.output / 'aMule-2.3.3'
        patches = args.output / 'debian/patches'
        applied = []
        for line in (patches / 'series').read_text().splitlines():
            name = line.split('#', 1)[0].strip()
            if not name:
                continue
            patch = patches / name
            subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)], cwd=source, check=True)
            applied.append({'name': name, 'sha256': hashlib.sha256(patch.read_bytes()).hexdigest()})
        patch = Path(__file__).with_name('connect-options.patch')
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)], cwd=source, check=True)
        prepared.write_text(json.dumps({
            'patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
            'prefs_sha256': hashlib.sha256((source / 'src/kademlia/kademlia/Prefs.cpp').read_bytes()).hexdigest(),
            'debian_patches': applied}))
    env = os.environ.copy()
    for flag in ('CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS'):
        env[flag] = subprocess.check_output(['dpkg-buildflags', '--get', flag], text=True,
                                          env={**env, 'DEB_BUILD_MAINT_OPTIONS': 'hardening=+all'}).strip()
    env['CPPFLAGS'] += ' -DASIO_SOCKETS=1'
    options = ['--prefix=/usr', '--disable-dependency-tracking', '--disable-ccache',
               '--disable-debug', '--disable-embedded-crypto', '--enable-geoip',
               '--enable-upnp', '--with-denoise-level=0', '--with-boost',
               '--disable-amule-daemon', '--disable-amulecmd', '--disable-ed2k',
               '--disable-webserver', '--disable-amule-gui', '--disable-cas',
               '--disable-wxcas', '--disable-alc', '--disable-alcc']
    if args.sysroot:
        root = args.sysroot.resolve()
        lib = root / 'usr/lib/x86_64-linux-gnu'
        env['PATH'] = str(root / 'usr/bin') + ':' + env['PATH']
        env['LD_LIBRARY_PATH'] = str(lib)
        env['PKG_CONFIG'] = str(root / 'usr/bin/pkgconf')
        env['CPPFLAGS'] += f' -I{root}/usr/include'
        env['LDFLAGS'] += f' -L{lib} -Wl,-rpath-link,{lib}'
        env['PKG_CONFIG_SYSROOT_DIR'] = str(root)
        env['PKG_CONFIG_LIBDIR'] = f'{lib}/pkgconfig:{root}/usr/share/pkgconfig'
        options += [f'--with-wx-config={lib}/wx/config/gtk3-unicode-3.2',
                    f'--with-wx-prefix={root}/usr', f'--with-wx-exec-prefix={root}/usr',
                    f'--with-crypto-prefix={root}/usr', f'--with-libupnp-prefix={root}/usr',
                    f'--with-geoip-headers={root}/usr/include', f'--with-geoip-lib={lib}']
    if not args.resume or not (source / 'config.status').exists():
        subprocess.run(['./configure', *options], cwd=source, env=env, check=True)
    configuration = (source / 'config.h').read_text()
    for feature in ('SUPPORT_GEOIP', 'ASIO_SOCKETS'):
        if '#define ' + feature + ' 1' not in configuration:
            raise RuntimeError('Required feature not enabled: ' + feature)
    if '-DENABLE_UPNP=1' not in (source / 'src/Makefile').read_text():
        raise RuntimeError('Required UPnP feature not enabled')
    subprocess.run(['make', '-j', str(max(1, min(args.jobs, 8)))], cwd=source, env=env, check=True)
    executable = args.output / 'amule'
    shutil.copyfile(source / 'src/amule', executable)
    subprocess.run(['objcopy', '--only-keep-debug', str(executable), str(args.output / 'amule.debug')], check=True)
    subprocess.run(['strip', '--strip-unneeded', str(executable)], check=True)
    executable.chmod(0o755)
    checksum = hashlib.sha256(executable.read_bytes()).hexdigest()
    (args.output / 'amule.sha256').write_text(checksum + '  amule\n')
    (args.output / 'provenance.json').write_text(json.dumps({
        'debian_package_version': '1:2.3.3-3.2', 'source_sha256': ORIGINAL,
        'debian_archive_sha256': DEBIAN, 'debian_patches': applied,
        'patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
        'binary_sha256': checksum, 'configure_options': options,
        'acceptance': 'diagnostic candidate; not integrated into OS image'
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
