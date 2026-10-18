#!/usr/bin/env python3
"""Boot the detached, updated encrypted test clone without an ISO."""
from pathlib import Path
import fcntl
import json
import os
import re
import signal
import socket
import subprocess
import sys


def main():
    if os.geteuid() == 0:
        raise RuntimeError("Run QEMU as Sam.")
    runtime = Path(f"/run/user/{os.getuid()}")
    state = json.loads((runtime / "petalos-encrypted-test.json").read_text())
    if state["phase"] != "ready-for-encrypted-boot":
        raise RuntimeError("Clone update has not completed successfully.")
    image = Path(state["image"])
    allowed = Path(__file__).resolve().parents[2] / "testing/sessions"
    if image.is_symlink() or not image.is_file() or not image.resolve().is_relative_to(allowed.resolve()):
        raise RuntimeError("Unexpected encrypted test-image path.")
    if not re.fullmatch(r"encrypted-boot-\d{8}-\d{6}-\d+\.img", image.name) or image.stat().st_size != 16 * 1024**3:
        raise RuntimeError("Unexpected encrypted test-image identity.")
    firmware = Path(state["firmware"])
    if firmware.is_symlink() or not firmware.is_file() or firmware.parent != image.parent:
        raise RuntimeError("Unexpected firmware file.")
    with (runtime / "petalos-qemu.lock").open("a") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for backing in Path("/sys/block").glob("loop*/loop/backing_file"):
            if Path(backing.read_text().strip()).resolve() == image.resolve():
                raise RuntimeError("Test clone is still attached; launch refused.")
        if Path("/dev/mapper/petal_release_system").exists():
            raise RuntimeError("Updater mapper still exists; launch refused.")
        if subprocess.run(["fuser", str(image)], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode != 1:
            raise RuntimeError("Test clone is busy or busy state is unknown.")
        monitor = runtime / "petalos-qemu-monitor.sock"
        if monitor.exists():
            raise RuntimeError("An existing QMP socket requires inspection.")
        command = ["qemu-system-x86_64", "-enable-kvm", "-machine", "q35", "-cpu", "host",
                   "-smp", "4", "-m", "8192",
                   "-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd",
                   "-drive", f"if=pflash,format=raw,file={firmware}",
                   "-drive", f"format=raw,file={image},if=virtio",
                   "-boot", "order=c", "-nic", "user,model=virtio-net-pci",
                   "-device", "virtio-vga,xres=1280,yres=800", "-display", "gtk,zoom-to-fit=off", "-serial", "none",
                   "-monitor", "none", "-qmp", f"unix:{monitor},server=on,wait=off",
                   "-name", "PetalOS encrypted rebuilt-system test"]
        ssh = state.get("ssh")
        relay = None
        if ssh:
            if ssh.get("cid") != 42 or ssh.get("port") != 2222:
                raise RuntimeError("Unexpected SSH management identity.")
            if not os.access("/dev/vhost-vsock", os.R_OK | os.W_OK):
                raise RuntimeError("Vsock device access is unavailable; SSH launch refused.")
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 2222))
            # Explicit placement preserves the existing NIC/VGA/disk PCI paths.
            command.extend(["-device", "vhost-vsock-pci,guest-cid=42,addr=0x5"])
            command.extend(["-global", "virtio-blk-pci.bootindex=1"])
        print("Booting the updated encrypted clone without an ISO.", flush=True)
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            if ssh:
                relay = subprocess.Popen(["socat", "TCP4-LISTEN:2222,bind=127.0.0.1,reuseaddr,fork",
                                          "VSOCK-CONNECT:42:22"], start_new_session=True,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print("Dedicated SSH management relay: 127.0.0.1:2222 (pinned host key).", flush=True)
            tail = bytearray()
            while chunk := process.stderr.read1(4096):
                tail.extend(chunk); del tail[:-65536]
            if process.wait():
                (runtime / "petalos-encrypted-launch.log").write_bytes(tail)
                raise RuntimeError("QEMU failed; bounded launch diagnostics remain in RAM.")
        finally:
            if relay is not None:
                try:
                    os.killpg(relay.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                relay.wait()
            if process.poll() is None:
                process.terminate(); process.wait()
            if monitor.exists():
                monitor.unlink()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
