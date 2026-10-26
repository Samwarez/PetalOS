"""Prepare a synthetic GUI database on a tiny disposable RAM mount."""
from pathlib import Path
import hashlib, json, os, subprocess, sys
sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
assert os.geteuid() == 0
assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
app = 'offline-keepassxc'
c.stop(app); c.home(app); c.storage_setup(app)
folder = c.ram_folder(app, 'Documents')
assert subprocess.run(['mountpoint', '-q', str(folder)]).returncode != 0
uid = c.ROLES[app]
subprocess.run(['mount', '-t', 'tmpfs', '-o', f'size=2M,nodev,nosuid,noexec,mode=0700,uid={uid},gid={uid}',
                'tmpfs', str(folder)], check=True, capture_output=True)
code = """import subprocess
p='/mnt/ram/Documents/keepassxc/public-gui-fixture.kdbx'
r=subprocess.run(['/usr/bin/keepassxc-cli','db-create','-p',p],input=b'public-disposable-fixture-only\\n'*2,capture_output=True)
assert r.returncode==0
"""
r = subprocess.run(c.sandbox(app, ['aa-exec', '-p', 'petalos_offline_keepassxc', '--',
                                  'python3', '-I', '-c', code]), capture_output=True, timeout=30)
assert r.returncode == 0
p = folder/'public-gui-fixture.kdbx'
Path('/run/petalos-keepass-gui-test.json').write_text(json.dumps({'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}))
r = c.start(app, [str(p)])
print(json.dumps({'gui_ready': r['phase'] == 'ready', 'synthetic_tiny_ram_volume_mounted': True}))
