#!/usr/bin/python3 -B
"""Build a root-owned Debian installer package without sudo or host installation."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from petal_installer import __version__


def stage(destination):
    lib = destination / 'usr/lib/bloom-installer';lib.mkdir(parents=True)
    shutil.copytree(Path(__file__).parent / 'petal_installer', lib / 'petal_installer',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(Path(__file__).parent / 'backend.py', lib / 'backend.py')
    (lib / 'backend.py').chmod(0o755)
    shared = lib / 'petal_installer/shared';shared.mkdir(exist_ok=True)
    for source in [ROOT / 'tests/release_generations.py', ROOT / 'tests/boot_branding.py',
                   ROOT / 'config/includes.chroot/usr/local/lib/portable/vpn_profiles.py']:
        shutil.copy2(source, shared / source.name)
    binary = destination / 'usr/bin/bloom';binary.parent.mkdir(parents=True)
    binary.write_text("#!/usr/bin/python3 -B\nimport sys\nsys.path.insert(0,'/usr/lib/bloom-installer')\nfrom petal_installer.cli import main\nraise SystemExit(main(['gui'] if len(sys.argv)==1 else None))\n")
    binary.chmod(0o755)
    compatibility = binary.with_name('petal-installer');shutil.copyfile(binary, compatibility);compatibility.chmod(0o755)
    policy = destination / 'usr/share/polkit-1/actions/org.petalos.bloom.policy';policy.parent.mkdir(parents=True)
    policy.write_text('''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN" "http://www.freedesktop.org/standards/PolicyKit/1/policyconfig.dtd">
<policyconfig>
 <vendor>Bloom</vendor>
 <action id="org.petalos.bloom.execute">
  <description>Bloom: install or manage PetalOS on the selected drive</description>
  <message>Administrator authorization is needed for this PetalOS drive operation.</message>
  <defaults><allow_any>no</allow_any><allow_inactive>no</allow_inactive><allow_active>auth_admin</allow_active></defaults>
  <annotate key="org.freedesktop.policykit.exec.path">/usr/lib/bloom-installer/backend.py</annotate>
 </action>
</policyconfig>
''')
    desktop = destination / 'usr/share/applications/bloom-installer.desktop';desktop.parent.mkdir(parents=True)
    desktop.write_text('''[Desktop Entry]
Type=Application
Name=Bloom
GenericName=PetalOS Installer
Comment=Install, update and manage your portable PetalOS
Exec=bloom gui
Icon=bloom-installer
Terminal=false
Categories=System;Settings;
StartupWMClass=bloom
''')
    icon = destination / 'usr/share/icons/hicolor/256x256/apps/bloom-installer.png';icon.parent.mkdir(parents=True)
    shutil.copyfile(Path(__file__).parent / 'petal_installer/assets/petal-emblem.png', icon)
    docs = destination / 'usr/share/doc/bloom-installer';docs.mkdir(parents=True)
    shutil.copyfile(Path(__file__).parent / 'README.md', docs / 'README.md')
    control = destination / 'DEBIAN/control';control.parent.mkdir()
    control.write_text(f'''Package: bloom-installer
Version: {__version__}
Architecture: all
Maintainer: Bloom local development
Conflicts: petalos-installer
Replaces: petalos-installer
Provides: petalos-installer
Depends: python3 (>= 3.11), python3-gi, gir1.2-gtk-3.0, cryptsetup-bin, dmsetup, gdisk, parted, udev, dosfstools, e2fsprogs, util-linux, psmisc, openssl, sbsigntool, initramfs-tools-core, squashfs-tools, pkexec, cpio, gzip, zstd
Section: admin
Priority: optional
Description: Bloom, a portable PetalOS installer with a soft-pink graphical overlay
 Fresh installation, OS-only updates, wipe and offline SYSTEM maintenance.
''')
    # Copying from user source must never retain writable code or odd owners in
    # the privileged package. dpkg-deb normalizes all owners to root below.
    destination.chmod(0o755)
    for path in destination.rglob('*'):
        if path.is_dir():path.chmod(0o755)
        elif path.is_file():path.chmod(0o755 if path in (binary, compatibility, lib / 'backend.py') else 0o644)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'installer-dist')
    args = parser.parse_args();args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bloom-installer-package-') as temporary:
        stage_root = Path(temporary) / 'root';stage(stage_root)
        output = args.output / f'bloom-installer_{__version__}_all.deb'
        subprocess.run(['/usr/bin/dpkg-deb', '--root-owner-group', '--build', str(stage_root), str(output)], check=True)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_name(output.name + '.sha256').write_text(digest + '  ' + output.name + '\n')
    print('Built installer package:', output)


if __name__ == '__main__':main()
