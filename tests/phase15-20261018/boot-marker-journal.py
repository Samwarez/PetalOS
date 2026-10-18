from pathlib import Path
import json,subprocess
marker='PETALOS_PHASE15_UNSIGNED_INITRD_EXECUTED'
a=subprocess.check_output(['dmesg'],text=True)
b=subprocess.check_output(['journalctl','-b','-k','-o','cat','--no-pager'],text=True)
out={'dmesg_bytes':len(a),'journal_kernel_bytes':len(b),'marker_in_current_dmesg':marker in a,'marker_in_current_boot_kernel_journal':marker in b,'dmesg_includes_early_linux_version':'Linux version ' in a,'kernel_journal_includes_early_linux_version':'Linux version ' in b,'initramfs_unpack_error':any(t in b for t in ('Initramfs unpacking failed','junk within compressed archive')),'SecureBoot_enabled':any(p.read_bytes()[-1:]==b'\1' for p in Path('/sys/firmware/efi/efivars').glob('SecureBoot-*'))}
print(json.dumps(out))
