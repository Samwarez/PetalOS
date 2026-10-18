#!/usr/bin/env python3
"""Preserve the tested overlay; update a new sparse clone through sudo."""
from pathlib import Path
import datetime
import fcntl
import json
import os
import shutil
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
BASE = PROJECT.parent / "testing/petal-test.img"


def main():
    if os.geteuid() == 0:
        raise RuntimeError("Run the coordinator as Sam.")
    runtime = Path(f"/run/user/{os.getuid()}")
    session = json.loads((runtime / "petalos-qemu-session.json").read_text())
    overlay = Path(session["overlay"])
    expected = PROJECT.parent / "testing/sessions/20261011-184902-563580/test-overlay.qcow2"
    if overlay != expected or overlay.is_symlink() or not overlay.is_file():
        raise RuntimeError("Unexpected source overlay.")
    with (runtime / "petalos-qemu.lock").open("a") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for image in (overlay, BASE):
            if subprocess.run(["fuser", str(image)], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode != 1:
                raise RuntimeError("Source image is busy or busy state is unknown.")
            for path in Path("/sys/block").glob("loop*/loop/backing_file"):
                if Path(path.read_text().strip()).resolve() == image.resolve():
                    raise RuntimeError("Source image has a loop attachment.")
        chain = json.loads(subprocess.check_output(
            ["qemu-img", "info", "--output=json", "--backing-chain", str(overlay)], text=True))
        if len(chain) != 2 or chain[0].get("full-backing-filename") != str(BASE) or chain[1]["format"] != "raw":
            raise RuntimeError("Unexpected overlay backing chain.")
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        raw = overlay.parent / f"encrypted-boot-{stamp}.img"
        if raw.exists():
            raise RuntimeError("Clone already exists.")
        state = {"phase": "cloning", "image": str(raw),
                 "release": str(PROJECT.parent / "releases/20261011-171244-905383"),
                 "firmware": str(overlay.parent / f"encrypted-OVMF-{stamp}.fd")}
        status = runtime / "petalos-encrypted-test.json"

        def update(phase):
            state["phase"] = phase
            temp = status.with_suffix(".tmp")
            temp.write_text(json.dumps(state, indent=2))
            temp.replace(status)

        try:
            update("cloning")
            print("Creating a sparse clone; original disk and tested overlay are preserved.", flush=True)
            subprocess.run(["qemu-img", "convert", "-f", "qcow2", "-O", "raw", "-S", "4k",
                            str(overlay), str(raw)], check=True)
            shutil.copy2(overlay.parent / "OVMF_VARS.fd", state["firmware"])
            update("awaiting-authentication")
            print("Sudo authentication, then the QEMU test SYSTEM-volume password, are required.", flush=True)
            subprocess.run(["/usr/bin/sudo", "--", "/usr/bin/python3", "-B",
                            str(PROJECT / "tests/update-encrypted-clone.py"), str(raw)], check=True)
            update("ready-for-encrypted-boot")
            print("Encrypted boot candidate is ready and detached.", flush=True)
        except BaseException:
            update("failed")
            raise


if __name__ == "__main__":
    os.umask(0o077)
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
