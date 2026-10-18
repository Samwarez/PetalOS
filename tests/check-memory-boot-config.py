#!/usr/bin/env python3
"""Check encrypted clone flags without touching a disk or encryption headers."""
import importlib.util
from pathlib import Path
s=importlib.util.spec_from_file_location('updater',Path(__file__).with_name('update-encrypted-clone.py'))
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
original='linux /live/vmlinuz toram swap=false live-media=/dev/mapper/portable_system\nlinuxefi /vmlinuz toram swap=false\ninitrd /initrd.img\n'
updated=m.memory_boot_config(original)
assert updated.count('init_on_alloc=1')==2 and updated.count('init_on_free=1')==2
assert m.memory_boot_config(updated)==updated
assert 'initrd /initrd.img\n' in updated
for suffix in (' init_on_free=0',' init_on_alloc=0',' init_on_free=1 init_on_free=1'):
    try:m.memory_boot_config('linux /vmlinuz'+suffix+'\n')
    except RuntimeError:pass
    else:raise AssertionError('Unsafe or ambiguous override accepted')
print('Memory boot flags: normal/failsafe, idempotence and override rejection passed.')
