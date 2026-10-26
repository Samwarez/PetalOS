# Historical test fixtures after storage cleanup

The cleanup keeps the October 23, 19 and 17 releases, the October 23 desktop
preview VM, October 19 acceptance VM and October 24 full-OS split-storage VM.
Earlier releases and the October 11 historical session are intentionally retired.

Five historical tools retain their original release identities. They now report
an explicit retirement error before creating files, opening devices or starting
a VM when that historical release is absent:

- `tests/launch-qemu-desktop.py`: October 11 ISO/overlay demonstration.
- `tests/verify-freed-memory-boot.py`: October 12 kernel-only verification.
- `tests/prepare-encrypted-qemu.py`: October 11 overlay-to-clone coordinator.
- `tests/update-encrypted-clone.py`: its historical default; existing explicit
  reviewed-release support remains, along with all regular-clone guards.
- `tests/inspect-card-update-root.py`: October 16 RC1 identity comparison. Its
  retirement check precedes helper import, passphrase requests and device access.

No newer release is silently substituted into a historical or card-specific
operation. Current work uses `tests/audit-vm.py` with a retained `state.json`, or
`tests/run-installer-engine-vm.py` / `tests/run-split-fullboot-vm.py` with the
retained October 23 release. Test-only fixture initrds are never installation
payloads. The physical card is outside this host-file cleanup.

A source snapshot of all five tools was created and checksum-verified before
adding these retirement guards. Cleanup must still check live host file/process,
mount and loop state immediately before deletion.
