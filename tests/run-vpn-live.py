#!/usr/bin/env python3
"""Boot a read-only live ISO with a RAM-only test overlay; no disks or NICs."""
from pathlib import Path
import argparse
import gzip
import os
import shutil
import subprocess
import tempfile

project = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("build", type=Path, help="Build directory containing binary/live and ISO")
parser.add_argument("--scripts-from-source", action="store_true",
                    help="Overlay current VPN scripts in guest RAM for pre-build verification")
parser.add_argument('--apps', action='store_true', help='Exercise isolated app/storage checks with the simulated VPN')
args = parser.parse_args()
build = args.build.resolve(strict=True)
if os.geteuid() == 0:
    parser.error("QEMU must run as the normal user")
iso = build / "live-image-amd64.hybrid.iso"
if not iso.is_file():
    parser.error("Expected regular ISO file")
with tempfile.TemporaryDirectory(prefix="petalos-live-test-", dir="/dev/shm") as tmp:
    work = Path(tmp)
    extracted = work / "unpacked"
    subprocess.run(["unmkinitramfs", str(build / "binary/live/initrd.img"),
                    str(extracted)], check=True, stdout=subprocess.DEVNULL)
    orders = list(extracted.rglob("scripts/init-bottom/ORDER"))
    if len(orders) != 1:
        raise RuntimeError("Could not identify init-bottom order")
    overlay = work / "overlay"
    scripts = overlay / "scripts/init-bottom"
    scripts.mkdir(parents=True)
    (scripts / "ORDER").write_text(orders[0].read_text() +
        '\n/scripts/init-bottom/petalos-tests "$@"\n')
    hook = scripts / "petalos-tests"
    hook.write_text('''#!/bin/sh
set -eu
mkdir -p "$rootmnt/usr/local/lib/petalos-tests" "$rootmnt/etc/systemd/system/multi-user.target.wants"
cp /petalos-tests/vpn-live-guest "$rootmnt/usr/local/lib/petalos-tests/verify"
if [ -f /petalos-tests/apps-live-guest ]; then
    cp /petalos-tests/apps-live-guest "$rootmnt/usr/local/lib/petalos-tests/"
fi
chmod 700 "$rootmnt/usr/local/lib/petalos-tests/verify"
cp /petalos-tests/petalos-tests.service "$rootmnt/etc/systemd/system/petalos-tests.service"
ln -s ../petalos-tests.service "$rootmnt/etc/systemd/system/multi-user.target.wants/petalos-tests.service"
if [ -d /petalos-tests/sbin ]; then
    cp /petalos-tests/sbin/* "$rootmnt/usr/local/sbin/"
    mkdir -p "$rootmnt/usr/local/lib/portable"
    cp /petalos-tests/vpn_profiles.py "$rootmnt/usr/local/lib/portable/"
    cp /petalos-tests/nftables.conf "$rootmnt/etc/nftables.conf"
    if [ -d /petalos-tests/bin ]; then
        cp /petalos-tests/bin/* "$rootmnt/usr/local/bin/"
    fi
fi
''')
    hook.chmod(0o755)
    payload = overlay / "petalos-tests"
    payload.mkdir()
    shutil.copy2(project / "tests/vpn-live-guest", payload / "vpn-live-guest")
    if args.apps:
        shutil.copy2(project / 'tests/apps-live-guest', payload / 'apps-live-guest')
    if args.scripts_from_source:
        (payload / "sbin").mkdir()
        for name in ("portable-vpn", "portable-check-vpn", "portable-vpn-profile", 'portable-unlock-data', 'portable-unlock-passphrase'):
            shutil.copy2(project / "config/includes.chroot/usr/local/sbin" / name,
                         payload / "sbin" / name)
        shutil.copy2(project / 'config/includes.chroot/usr/local/lib/portable/vpn_profiles.py', payload / 'vpn_profiles.py')
        shutil.copy2(project / 'config/includes.chroot/etc/nftables.conf', payload / 'nftables.conf')
        if args.apps:
            (payload / 'bin').mkdir()
            for name in ('portable-sab-manager', 'portable-sabnzbd', 'portable-save-settings', 'portable-restore-settings', 'portable-offline'):
                shutil.copy2(project / 'config/includes.chroot/usr/local/bin' / name, payload / 'bin' / name)
    (payload / "petalos-tests.service").write_text('''[Unit]
Description=PetalOS isolated network verification
After=nftables.service network.target
Requires=nftables.service
[Service]
Type=oneshot
ExecStart=/usr/local/lib/petalos-tests/verify
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
''')
    if args.apps:
        service = payload / 'petalos-tests.service'
        service.write_text(service.read_text().replace('[Service]\n', '[Service]\nEnvironment=PETALOS_APP_TEST=1\n'))
    archive = subprocess.check_output(
        ["bash", "-c", "find . -print0 | cpio --null -o -H newc --quiet"], cwd=overlay
    )
    initrd = work / "test-initrd.img"
    with initrd.open("wb") as output:
        with (build / "binary/live/initrd.img").open("rb") as source:
            shutil.copyfileobj(source, output)
        output.write(gzip.compress(archive))
    # Only the ISO is attached, read-only. All test storage is created in guest RAM.
    command = ["qemu-system-x86_64", "-accel", "kvm", "-cpu", "host", "-m", "8192",
               "-smp", "2", "-kernel", str(build / "binary/live/vmlinuz"),
               "-initrd", str(initrd), "-append",
               "boot=live components toram swap=false console=ttyS0 systemd.unit=multi-user.target systemd.mask=serial-getty@ttyS0.service",
               "-drive", f"file={iso},format=raw,media=cdrom,readonly=on",
               "-nic", "none", "-nographic", "-no-reboot"]
    # Retain only bounded RAM diagnostics; never print arbitrary guest output.
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log = work / "guest.log"
    origin = "current source scripts in RAM" if args.scripts_from_source else "ISO scripts"
    print(f"Booting isolated live guest with {origin} (maximum seven minutes).", flush=True)
    with log.open("w+b") as output:
        try:
            # A watchdog bounds boot failures that never reach the test service.
            import threading
            timer = threading.Timer(420, process.kill)
            timer.start()
            lines = []
            for line in process.stdout:
                output.write(line)
                output.flush()
                if output.tell() > 2 * 1024 * 1024:
                    output.seek(-2 * 1024 * 1024, os.SEEK_END)
                    tail = output.read()
                    output.seek(0)
                    output.truncate(0)
                    output.write(tail)
                    output.flush()
                decoded = line.decode(errors="replace").strip()
                if decoded.startswith(("PASS:", "FAIL:", "LIVE_TEST_")):
                    print(decoded, flush=True)
                    lines.append(decoded)
            process.wait()
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
                process.wait()
    if "LIVE_TEST_FAILURES=0" not in lines:
        # Keep diagnostics in RAM for inspection after failure, without exposing keys.
        retained = Path(f"/run/user/{os.getuid()}/petalos-live-test")
        retained.mkdir(mode=0o700, exist_ok=True)
        shutil.copy2(log, retained / "guest.log")
        print(f"Test incomplete or failed; bounded RAM diagnostics: {retained / 'guest.log'}")
        raise SystemExit(1)
