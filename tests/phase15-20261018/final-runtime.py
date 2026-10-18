from pathlib import Path
import json,subprocess,sys
sys.path.insert(0,'/usr/local/lib/portable')
from desktop_session import environment
from system_state import ready,FULL
r=subprocess.run(['setpriv','--reuid=1000','--regid=1000','--clear-groups','--','xfconf-query','-c','xsettings','-p','/Net/DoubleClickTime'],env=environment(),capture_output=True,text=True)
log=subprocess.check_output(['dmesg'],text=True)
out={'settled_desktop_setting_restored_on_second_boot':r.returncode==0 and r.stdout.strip()=='322','Private_still_closed':not Path('/dev/mapper/portable_data').exists(),'SYSTEM_selective_state_ready':ready(),'RAM_canary_absent':not Path('/home/Petal/petalos-phase15-ram-canary').exists(),'no_swap':len(Path('/proc/swaps').read_text().splitlines())==1,'no_runtime_WireGuard_key':not Path('/etc/wireguard/wg0.conf').exists(),'unsigned_initrd_marker_present':'PETALOS_PHASE15_UNSIGNED_INITRD_EXECUTED' in log,'failed_units':subprocess.check_output(['systemctl','--failed','--no-legend','--plain'],text=True).splitlines()}
out['EFI_pstore_backend_registered']='Registered efi as persistent store backend' in log
out['optional_services_active']={n:subprocess.run(['systemctl','is-active','--quiet',n],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0 for n in ('systemd-homed.service','systemd-oomd.service','nscd.service','cups.service')}
print(json.dumps(out))
