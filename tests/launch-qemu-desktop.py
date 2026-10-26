#!/usr/bin/env python3
"""Launch the verified ISO with a disposable overlay of the encrypted test disk."""
from pathlib import Path
import datetime
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
TESTING = PROJECT.parent / "testing"
RELEASE = PROJECT.parent / "releases/20261011-171244-905383"
BASE = TESTING / "petal-test.img"


def main():
    if not (RELEASE / 'manifest.json').is_file():
        raise RuntimeError('Historical October 11 ISO fixture has been retired. Use tests/audit-vm.py with a retained audit state, or tests/run-installer-engine-vm.py with a reviewed release.')
    if os.geteuid() == 0:
        raise RuntimeError("QEMU must run as the normal user.")
    if not os.access("/dev/kvm", os.R_OK | os.W_OK):
        raise RuntimeError("KVM is unavailable.")
    runtime = Path(f"/run/user/{os.getuid()}")
    with (runtime / "petalos-qemu.lock").open("a") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if BASE.is_symlink() or not BASE.is_file() or BASE.stat().st_size != 16 * 1024**3:
            raise RuntimeError("Unexpected test-image identity.")
        for backing in Path("/sys/block").glob("loop*/loop/backing_file"):
            if Path(backing.read_text().strip()).resolve() == BASE.resolve():
                raise RuntimeError("Test image has a loop attachment; launch refused.")
        busy = subprocess.run(["fuser", str(BASE)], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
        if busy.returncode != 1:
            raise RuntimeError("Test image is busy or its busy state is unknown.")
        iso = RELEASE / "build/live-image-amd64.hybrid.iso"
        expected = json.loads((RELEASE / "manifest.json").read_text())["live-image-amd64.hybrid.iso"]
        checksum = hashlib.sha256()
        with iso.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                checksum.update(chunk)
        if iso.stat().st_size != expected["bytes"] or checksum.hexdigest() != expected["sha256"]:
            raise RuntimeError("ISO integrity check failed.")
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        session = TESTING / "sessions" / stamp
        session.mkdir(parents=True, mode=0o700)
        overlay = session / "test-overlay.qcow2"
        subprocess.run(["qemu-img", "create", "-q", "-f", "qcow2", "-F", "raw",
                        "-b", str(BASE), str(overlay)], check=True)
        info = json.loads(subprocess.check_output(
            ["qemu-img", "info", "--output=json", str(overlay)], text=True))
        if info.get("full-backing-filename") != str(BASE) or info.get("backing-filename-format") != "raw":
            raise RuntimeError("Unexpected overlay backing identity.")
        variables = session / "OVMF_VARS.fd"
        shutil.copy2("/usr/share/OVMF/OVMF_VARS_4M.fd", variables)
        monitor = runtime / "petalos-qemu-monitor.sock"
        if monitor.exists():
            raise RuntimeError("Existing QMP socket; inspect prior session before launching.")
        state = runtime / "petalos-qemu-session.json"
        state.write_text(json.dumps({"session": str(session), "iso": str(iso),
                                     "overlay": str(overlay), "qmp": str(monitor)}, indent=2))
        command = [
            "qemu-system-x86_64", "-enable-kvm", "-machine", "q35", "-cpu", "host",
            "-smp", "4", "-m", "8192",
            "-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd",
            "-drive", f"if=pflash,format=raw,file={variables}",
            "-drive", f"format=qcow2,file={overlay},if=virtio",
            "-drive", f"format=raw,file={iso},media=cdrom,readonly=on",
            "-boot", "order=d", "-nic", "user,model=virtio-net-pci",
            "-device", "virtio-vga", "-display", "gtk",
            "-serial", "none", "-monitor", "none",
            "-qmp", f"unix:{monitor},server=on,wait=off",
            "-name", "PetalOS rebuilt ISO — disposable test",
        ]
        print(f"Session directory: {session}", flush=True)
        print("Booting the rebuilt ISO; encrypted test-disk writes use its overlay.", flush=True)
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            # QEMU diagnostics only, not a guest console. Keep a bounded tail in RAM.
            tail = bytearray()
            while chunk := process.stderr.read1(4096):
                tail.extend(chunk)
                del tail[:-65536]
            result = process.wait()
            if result:
                (runtime / "petalos-qemu-launch.log").write_bytes(tail)
                raise RuntimeError("QEMU exited with an error; bounded launch log is in RAM.")
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait()
            if monitor.exists():
                monitor.unlink()


if __name__ == "__main__":
    os.umask(0o077)
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
