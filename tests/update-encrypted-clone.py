#!/usr/bin/env python3
"""One-session root updater for a fresh, regular-file QEMU clone only."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager

PROJECT = Path(__file__).resolve().parents[1]
RELEASE = PROJECT.parent / "releases/20261011-171244-905383"
SESSIONS = PROJECT.parent / "testing/sessions"
MAPPER = Path("/dev/mapper/petal_release_system")


@contextmanager
def mount_workspace():
    # Never recursively delete a directory that might still contain a mount.
    work = Path(tempfile.mkdtemp(prefix="petalos-release-", dir="/run"))
    try:
        yield work
    finally:
        for name in ("boot", "system"):
            child = work / name
            if child.exists():
                if os.path.ismount(child):
                    raise RuntimeError("Updater mount remains; retain workspace for inspection.")
                child.rmdir()
        work.rmdir()


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def memory_boot_config(content):
    """Validate every kernel line before returning the updated public config."""
    lines = content.splitlines()
    for index, line in enumerate(lines):
        words = line.strip().split()
        if words and words[0] in ("linux", "linuxefi"):
            additions = []
            for option in ("init_on_alloc", "init_on_free"):
                existing = [word for word in words if word.startswith(option + "=")]
                if existing and existing != [option + "=1"]:
                    raise RuntimeError("Explicit memory initialization override needs review.")
                if not existing:
                    additions.append(option + "=1")
            if additions:
                lines[index] = line + " " + " ".join(additions)
    return "\n".join(lines) + "\n"


def main(ssh_module=None, host_public_key=None, configuration_module=None, replacement_ssh_module=None):
    if os.geteuid() != 0 or len(sys.argv) not in (2, 3):
        raise RuntimeError("Invoke through the prepared coordinator and sudo.")
    release = Path(sys.argv[2]) if len(sys.argv) == 3 else RELEASE
    if (release.parent != PROJECT.parent / "releases" or
            not re.fullmatch(r"\d{8}-\d{6}-\d+", release.name) or
            release.resolve(strict=True) != release or not release.is_dir()):
        raise RuntimeError("Unexpected release directory.")
    raw = Path(sys.argv[1])
    if raw.is_symlink() or not raw.is_file() or not raw.resolve().is_relative_to(SESSIONS.resolve()):
        raise RuntimeError("Only a registered regular test-clone file is accepted.")
    if not re.fullmatch(r"encrypted-boot-\d{8}-\d{6}-\d+\.img", raw.name):
        raise RuntimeError("Unexpected clone name.")
    initial = raw.stat()
    if initial.st_size != 16 * 1024**3 or initial.st_uid != int(os.environ["SUDO_UID"]):
        raise RuntimeError("Unexpected clone size or owner.")
    if any(name.startswith(("qemu-system", "qemu-nbd")) for name in run("/usr/bin/ps", "-eo", "comm=").splitlines()):
        raise RuntimeError("A QEMU process is running; update refused.")
    for path in Path("/sys/block").glob("loop*/loop/backing_file"):
        if Path(path.read_text().strip()).resolve() == raw.resolve():
            raise RuntimeError("Clone is already attached.")
    if subprocess.run(["/usr/bin/fuser", str(raw)], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode != 1:
        raise RuntimeError("Clone is busy or its busy state is unknown.")
    if MAPPER.exists():
        raise RuntimeError("Updater mapper already exists; inspect it first.")
    manifest = json.loads((release / "manifest.json").read_text())
    sources = {}
    for name in ("vmlinuz", "initrd.img", "filesystem.squashfs"):
        relative = f"binary/live/{name}"
        path = release / "build" / relative
        if path.is_symlink() or not path.is_file() or digest(path) != manifest[relative]["sha256"]:
            raise RuntimeError("Release artifact integrity check failed.")
        sources[name] = path
    loop = None
    mapped = False
    mounted = []

    def loop_identity():
        current = raw.stat()
        if (current.st_dev, current.st_ino, current.st_size) != (initial.st_dev, initial.st_ino, initial.st_size):
            raise RuntimeError("Clone identity changed.")
        backing = Path("/sys/class/block") / Path(loop).name / "loop/backing_file"
        if Path(backing.read_text().strip()).resolve() != raw.resolve():
            raise RuntimeError("Wrong loop backing file.")

    def partition(number):
        loop_identity()
        path = Path(f"{loop}p{number}")
        if (Path("/sys/class/block") / path.name).resolve().parent.name != Path(loop).name:
            raise RuntimeError("Wrong partition parent.")
        return path

    def mapper_identity():
        loop_identity()
        device = MAPPER.stat().st_rdev
        slaves = Path(f"/sys/dev/block/{os.major(device)}:{os.minor(device)}/slaves")
        if [p.name for p in slaves.iterdir()] != [partition(3).name]:
            raise RuntimeError("Wrong encrypted mapper backing device.")

    def tag(device, name):
        return run("/usr/sbin/blkid", "-s", name, "-o", "value", str(device))

    def mount(device, target, kind):
        loop_identity()
        if device == MAPPER:
            mapper_identity()
        subprocess.run(["/usr/bin/mount", "-t", kind, "-o", "nodev,nosuid,noexec,noatime",
                        str(device), str(target)], check=True)
        mounted.append((device, target))

    def replace(source, target):
        loop_identity()
        if target.is_symlink() or not target.is_file():
            raise RuntimeError("Unexpected destination path.")
        fd, temporary = tempfile.mkstemp(prefix=".petalos-release-", dir=target.parent)
        temp = Path(temporary)
        try:
            with os.fdopen(fd, "wb") as output, source.open("rb") as input_file:
                shutil.copyfileobj(input_file, output, 1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
            temp.chmod(0o644)
            if digest(temp) != digest(source):
                raise RuntimeError("Copied artifact integrity check failed.")
            os.replace(temp, target)
        finally:
            if temp.exists():
                temp.unlink()

    with mount_workspace() as work:
        boot = Path(work) / "boot"; boot.mkdir()
        system = Path(work) / "system"; system.mkdir()
        try:
            loop = run("/usr/sbin/losetup", "--find", "--show", "--partscan", str(raw))
            loop_identity()
            subprocess.run(["/usr/bin/udevadm", "settle", "--timeout=10"], check=True)
            table = json.loads(run("/usr/sbin/sfdisk", "--json", loop))["partitiontable"]
            parts = table["partitions"]
            if table["label"] != "gpt" or len(parts) != 4 or parts[1]["size"] != 2097152 or parts[2]["size"] != 8388608:
                raise RuntimeError("Unexpected test-image partition layout.")
            boot_device = partition(2); system_device = partition(3)
            if tag(boot_device, "LABEL") != "PORT_BOOT" or tag(boot_device, "TYPE") != "vfat":
                raise RuntimeError("Unexpected boot partition identity.")
            if tag(system_device, "LABEL") != "PORTABLE_SYSTEM" or tag(system_device, "TYPE") != "crypto_LUKS":
                raise RuntimeError("Unexpected system partition identity.")
            print("Enter the QEMU test SYSTEM-volume password at the cryptsetup prompt.", flush=True)
            subprocess.run(["/usr/sbin/cryptsetup", "open", str(system_device), MAPPER.name], check=True)
            mapped = True
            mapper_identity()
            if tag(MAPPER, "TYPE") != "ext4" or tag(MAPPER, "LABEL") != "LIVE_SYSTEM":
                raise RuntimeError("Unexpected inner system filesystem.")
            mount(boot_device, boot, "vfat")
            mount(MAPPER, system, "ext4")
            configs = [p for p in boot.rglob("grub.cfg") if not p.is_symlink()]
            active = [p.read_text() for p in configs if "live-media=/dev/mapper/portable_system" in p.read_text()]
            if not active:
                raise RuntimeError("Encrypted-system GRUB configuration not found.")
            kernels = set(); initrds = set()
            for config in active:
                for line in config.splitlines():
                    words = line.strip().split()
                    if words and words[0] in ("linux", "linuxefi"):
                        if not {"toram", "swap=false", "live-media=/dev/mapper/portable_system"}.issubset(words):
                            raise RuntimeError("Unexpected GRUB live boot arguments.")
                        kernels.add(words[1])
                    if words and words[0] in ("initrd", "initrdefi"):
                        if len(words) != 2:
                            raise RuntimeError("Unexpected initrd command.")
                        initrds.add(words[1])
            if not kernels or not initrds:
                raise RuntimeError("Missing boot artifact paths.")
            if configuration_module is not None:
                module = Path(configuration_module)
                if (module.is_symlink() or not module.is_file() or
                        not module.resolve().is_relative_to(SESSIONS.resolve()) or
                        module.name not in ("petalos-config.squashfs", "petalos-wayland-test.squashfs", "petalos-wayland-test-v2.squashfs", "petalos-wayland-test-v3.squashfs", "petalos-wayland-test-v4.squashfs", "petalos-wayland-test-v5.squashfs")):
                    raise RuntimeError("Unexpected public configuration module.")
                live = system / "live"
                selection = live / "filesystem.module"
                expected = ["filesystem.squashfs", "petalos-qemu-ssh.squashfs"]
                if selection.is_symlink() or selection.read_text().split() not in (expected, expected + ["petalos-wayland-test.squashfs"], expected + ["petalos-wayland-test-v2.squashfs"], expected + ["petalos-wayland-test-v3.squashfs"], expected + ["petalos-wayland-test-v4.squashfs"]):
                    raise RuntimeError("Unexpected existing live module selection.")
                target = live / module.name
                if target.exists() or target.is_symlink():
                    raise RuntimeError("Configuration module already exists; refuse overwrite.")
                boot_updates = {}
                for config in configs:
                    content = config.read_text()
                    if "live-media=/dev/mapper/portable_system" in content:
                        if re.search(r"\busername=", content):
                            raise RuntimeError("Explicit boot username needs review before account migration.")
                        boot_updates[config] = memory_boot_config(content)
                mapper_identity()
                shutil.copyfile(module, target)
                target.chmod(0o644)
                if digest(target) != digest(module):
                    raise RuntimeError("Configuration module integrity check failed.")
                selection.write_text("\n".join(expected + [module.name]) + "\n")
                for config, content in boot_updates.items():
                    config.write_text(content)
                print("Public configuration module installed; encrypted credentials and DATA untouched.", flush=True)
                return
            if ssh_module is not None:
                # Only the explicitly requested QEMU clone receives this module.
                module = Path(ssh_module)
                if (module.is_symlink() or not module.is_file() or
                        not module.resolve().is_relative_to(SESSIONS.resolve()) or
                        module.name != "petalos-qemu-ssh.squashfs"):
                    raise RuntimeError("Unexpected SSH test module.")
                live = system / "live"
                target = live / module.name
                if target.exists():
                    raise RuntimeError("SSH module already exists; refuse overwrite.")
                mapper_identity()
                shutil.copyfile(module, target)
                target.chmod(0o644)
                if digest(target) != digest(module):
                    raise RuntimeError("SSH module integrity check failed.")
                modules = live / "filesystem.module"
                if modules.exists() and modules.read_text().split() != ["filesystem.squashfs"]:
                    raise RuntimeError("Unexpected existing module selection.")
                modules.write_text("filesystem.squashfs\npetalos-qemu-ssh.squashfs\n")
                keys = system / ".petalos-qemu-ssh"
                keys.mkdir(mode=0o700)
                subprocess.run(["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "",
                                "-f", str(keys / "ssh_host_ed25519_key")], check=True)
                output = Path(host_public_key)
                if output.parent != raw.parent or output.exists() or output.is_symlink():
                    raise RuntimeError("Unexpected public host-key output.")
                shutil.copyfile(keys / "ssh_host_ed25519_key.pub", output)
                os.chown(output, int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"]))
                output.chmod(0o600)
                for config in configs:
                    content = config.read_text()
                    if "live-media=/dev/mapper/portable_system" not in content:
                        continue
                    lines = content.splitlines()
                    for index, line in enumerate(lines):
                        words = line.strip().split()
                        if words and words[0] in ("linux", "linuxefi"):
                            lines[index] = line + " petalos_qemu_ssh=1"
                    config.write_text("\n".join(lines) + "\n")
                subprocess.run(["/usr/bin/setfacl", "-m",
                                f"u:{os.environ['SUDO_UID']}:rw", "/dev/vhost-vsock"], check=True)
                print("Installed isolated SSH module and pinned public host key; firewall unchanged.", flush=True)
                return
            for config in configs:
                content = config.read_text()
                if "live-media=/dev/mapper/portable_system" in content:
                    config.write_text(memory_boot_config(content))
            for name, destinations in (("vmlinuz", kernels), ("initrd.img", initrds)):
                for destination in destinations:
                    if not re.fullmatch(r"/(?:live/)?" + re.escape(name), destination):
                        raise RuntimeError("Unexpected boot artifact destination.")
                    replace(sources[name], boot / destination.lstrip("/"))
            mapper_identity()
            replace(sources["filesystem.squashfs"], system / "live/filesystem.squashfs")
            if replacement_ssh_module is not None:
                module=Path(replacement_ssh_module)
                if (module.is_symlink() or not module.is_file() or
                    not module.resolve().is_relative_to(SESSIONS.resolve()) or
                    module.name!='petalos-qemu-ssh.squashfs'):
                    raise RuntimeError('Unexpected replacement public SSH module.')
                selection=system/'live/filesystem.module'
                expected=['filesystem.squashfs','petalos-qemu-ssh.squashfs']
                if selection.is_symlink() or selection.read_text().split() not in (expected,expected+['petalos-config.squashfs'],expected+['petalos-wayland-test.squashfs'],expected+['petalos-wayland-test-v2.squashfs'],expected+['petalos-wayland-test-v3.squashfs'],expected+['petalos-wayland-test-v4.squashfs'],expected+['petalos-wayland-test-v5.squashfs']):
                    raise RuntimeError('Unexpected existing module selection.')
                # Keep the pinned host identity inside encrypted SYSTEM. Only
                # public management configuration/packages are replaced.
                key=system/'.petalos-qemu-ssh/ssh_host_ed25519_key'
                if (key.parent.is_symlink() or key.parent.stat().st_uid!=0 or
                    key.parent.stat().st_mode&0o077 or key.is_symlink() or
                    not key.is_file() or key.stat().st_uid!=0 or key.stat().st_mode&0o077):
                    raise RuntimeError('Unsafe existing management host-key file.')
                replace(module,system/'live/petalos-qemu-ssh.squashfs')
                # New base contains every staged public setting. Selecting the
                # older configuration layer would override it with stale files.
                selection.write_text('\n'.join(expected)+'\n')
                print('Refreshed public SSH layer; stale settings layer unselected, host identity preserved.',flush=True)
            print("Verified kernel, initrd and squashfs replacements. Data partition was not opened.", flush=True)
        finally:
            # Never close a mapper or detach a loop if unmount fails or identity changed.
            for device, target in reversed(mounted):
                loop_identity()
                actual = Path(run("/usr/bin/findmnt", "-n", "-o", "SOURCE", "--target", str(target)))
                if actual.stat().st_rdev != device.stat().st_rdev:
                    raise RuntimeError("Cleanup mount identity mismatch; manual inspection required.")
                subprocess.run(["/usr/bin/umount", str(target)], check=True)
            if mapped or MAPPER.exists():
                mapper_identity()
                subprocess.run(["/usr/sbin/cryptsetup", "close", MAPPER.name], check=True)
            if loop:
                loop_identity()
                subprocess.run(["/usr/sbin/losetup", "--detach", loop], check=True)
    print("Clone update completed and all updater mounts/mappings were closed.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
