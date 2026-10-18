#!/usr/bin/python3
"""Read-only root checks for the new Petal live boot; no credential reads."""
import json
import subprocess
from pathlib import Path
import pwd

assert pwd.getpwuid(1000).pw_name == 'Petal'
r = {}
r['sudo_policy_valid'] = subprocess.run(['/usr/sbin/visudo','-c'],capture_output=True).returncode == 0
r['no_passwordless_live_rule'] = 'NOPASSWD' not in Path('/etc/sudoers.d/live').read_text()
p = json.loads(subprocess.check_output(['/usr/sbin/apparmor_status','--json']))['profiles']
r['profiles_enforced'] = all(p.get(n) == 'enforce' for n in ['petalos_firefox','petalos_tor','petalos_offline','petalos_offline_sab'])
n = json.loads(subprocess.check_output(['/usr/sbin/nft','-j','list','table','inet','portable_vpn']))['nftables']
c = [x['chain'] for x in n if 'chain' in x and x['chain'].get('hook') in ('input','output','forward')]
r['firewall_all_drop'] = len(c) == 3 and all(x.get('policy') == 'drop' for x in c)
opts = subprocess.check_output(['findmnt','-n','-o','OPTIONS','--target','/mnt/private'],text=True).strip().split(',')
r['private_mount_hardened'] = all(x in opts for x in ['nodev','nosuid','noexec','noatime'])
r['no_swap'] = len(Path('/proc/swaps').read_text().splitlines()) == 1
r['root_is_overlay'] = subprocess.check_output(['findmnt','-n','-o','FSTYPE','/'],text=True).strip() == 'overlay'
r['home_on_overlay'] = subprocess.check_output(['findmnt','-n','-o','FSTYPE','--target','/home/Petal'],text=True).strip() == 'overlay'
r['telemetry_timer_active'] = subprocess.run(['systemctl','is-active','--quiet','portable-telemetry.timer']).returncode == 0
r['background_units_masked'] = all(subprocess.run(['systemctl','is-enabled',x],capture_output=True,text=True).stdout.strip() == 'masked' for x in ['tor.service','avahi-daemon.service','cups.service','ssh.service'])
r['core_dumps_discarded'] = Path('/proc/sys/kernel/core_pattern').read_text().strip() == '|/bin/false'
r['kernel_pointers_restricted'] = Path('/proc/sys/kernel/kptr_restrict').read_text().strip() == '2'
r['private_source_correct'] = subprocess.check_output(['findmnt','-n','-o','SOURCE','--target','/mnt/private'],text=True).strip() == '/dev/mapper/portable_data'
print(json.dumps(r,sort_keys=True))
assert all(r.values()), 'Boot hardening acceptance failed.'
