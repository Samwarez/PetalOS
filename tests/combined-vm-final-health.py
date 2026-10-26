"""Final bounded health and active storage-access checks; no raw journal export."""
from pathlib import Path
import errno
import json
import os
import subprocess
import sys
assert os.geteuid() == 0
sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
import system_state
checks = {'Private_closed': not Path('/dev/mapper/portable_data').exists(),
          'SYSTEM_state_ready': system_state.ready(),
          'no_swap': len(Path('/proc/swaps').read_text().splitlines()) == 1,
          'root_is_volatile_overlay': subprocess.check_output(['findmnt','-n','-o','FSTYPE','--mountpoint','/'],text=True).strip() == 'overlay',
          'home_is_volatile': subprocess.check_output(['findmnt','-n','-o','FSTYPE','-T','/home/Petal'],text=True).strip() in ('overlay','tmpfs'),
          'no_failed_system_units': not subprocess.check_output(['systemctl','--failed','--no-legend','--plain'],text=True).strip(),
          'all_app_workers_stopped': all(not c.worker_alive(c.read_record(a)) for a in c.ROLES)}
target = system_state.FULL/'public-combined-readonly-negative-canary'
assert not target.exists()
try:
    fd = os.open(target, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600);os.close(fd)
    checks['full_SYSTEM_view_rejects_even_root_write'] = False
    target.unlink()
except OSError as error:
    checks['full_SYSTEM_view_rejects_even_root_write'] = error.errno == errno.EROFS
probe = '''import os
from pathlib import Path
targets=['/dev/vda','/dev/vda3','/dev/mapper/portable_system','/run/portable-storage/system-volume']
for name in targets:
 try:
  fd=os.open(name,os.O_RDONLY);os.close(fd)
 except PermissionError:continue
 raise SystemExit(1)
'''
checks['desktop_cannot_open_raw_disk_or_full_SYSTEM_view'] = subprocess.run(
    ['setpriv','--reuid=1000','--regid=1000','--clear-groups','--','python3','-I','-c',probe],capture_output=True,timeout=5).returncode == 0
kernel = subprocess.check_output(['dmesg'],text=True,errors='replace')
checks['no_kernel_OOM_or_panic'] = not any(text in kernel for text in ('Out of memory: Killed process','Kernel panic','BUG: unable to handle','segfault at'))
checks['journal_is_volatile'] = 'Storage=volatile' in Path('/etc/systemd/journald.conf.d/zz-portable-ram.conf').read_text() and not any(Path('/var/log/journal').glob('*/*.journal'))
table = json.loads(subprocess.check_output(['nft','-j','list','table','inet','portable_vpn']))
chains = {e['chain']['name']: e['chain'].get('policy') for e in table['nftables'] if 'chain' in e}
checks['all_firewall_default_policies_drop'] = all(chains.get(n) == 'drop' for n in ('input','output','forward'))
checks['temporary_Tor_block_table_removed'] = subprocess.run(['nft','list','table','inet','petalos_repair_tor_block'],capture_output=True).returncode != 0
memory = {k:int(v.split()[0]) for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())}
versions = {name:subprocess.check_output(['dpkg-query','-W','-f=${Version}',name],text=True) for name in ('amule','polkitd','libxml2','libpoppler147','keepassxc-full')}
print(json.dumps({'checks': checks, 'available_RAM_MiB': round(memory['MemAvailable']/1024), 'package_versions': versions}))
assert all(checks.values())
