# Graphical QEMU session — 2026-10-11

Launched `tests/launch-qemu-desktop.py` as Sam. It verified the release ISO
against its manifest and checked that the base test image had no visible
loop attachment or open-file user before creating a fresh qcow2 overlay.

Session directory:

`/home/sam/portable-live/testing/sessions/20261011-184902-563580`

The VM uses KVM, q35, 4 vCPUs, 8 GiB RAM, UEFI OVMF, a GTK display and
user-mode NAT with virtio networking. The rebuilt release ISO is read-only
and selected first in boot order. QMP confirmed the VM is running and both
the ISO and backing `testing/petal-test.img` are read-only. Only the fresh
qcow2 overlay and copied OVMF variables are writable. Original firmware
variables, original image and physical card were not changed.

This is an ISO desktop test with access to the existing encrypted test disk
through its overlay. The encrypted disk's system partition still contains
the earlier release; it has not been updated. Booting that disk directly
would not test the rebuilt release. Desktop arrival and any private-storage
password prompt require observation in the QEMU window. No screenshot,
private configuration or personal file was read into diagnostics.

The encrypted volumes use the existing test credentials, entered privately
inside the VM if requested. No selected personal profile or application data
was provisioned. The guest's production kill switch remains configured;
NAT availability does not bypass it. No host port forwarding was enabled.

Runtime session metadata and the QMP socket are under `/run/user/1000`.
The launcher holds a lease for the lifetime of the VM. Shut down through
the guest desktop before inspecting or maintaining the overlay. The overlay
is preserved after exit for review; no automatic disk cleanup occurs.
