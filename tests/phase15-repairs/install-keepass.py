"""Install public repaired binaries only in the disposable RAM guest."""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys
assert os.geteuid() == 0
assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
assert 'toram' in Path('/proc/cmdline').read_text().split()
sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
c.stop('offline-keepassxc')
source = Path('/usr/local/share/portable/native-keepassxc')
record = json.loads((source/'provenance.json').read_text())
backup = Path('/run/petalos-keepass-before-repair')
backup.mkdir(mode=0o700, exist_ok=True)
for name, destination in [('keepassxc', '/usr/bin/keepassxc.portable-real'),
                          ('keepassxc-cli', '/usr/bin/keepassxc-cli')]:
    path = Path(destination)
    assert hashlib.sha256((source/name).read_bytes()).hexdigest() == record['binary_sha256'][name]
    if not (backup/name).exists():
        shutil.copy2(path, backup/name)
    temporary = path.with_name(path.name+'.repair')
    assert not temporary.exists()
    shutil.copyfile(source/name, temporary)
    temporary.chmod(0o755)
    os.replace(temporary, path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record['binary_sha256'][name]
print(json.dumps({'public_binaries_installed': 2, 'readbacks_match': True,
                  'original_binaries_preserved_in_guest_ram': True}))
