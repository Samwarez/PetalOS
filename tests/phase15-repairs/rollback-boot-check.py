"""Check that selecting retained configs really starts the older release."""
from pathlib import Path
import json,subprocess,sys
sys.path.insert(0,'/usr/local/lib/portable')
import system_state
from desktop_session import environment
e=environment();r=subprocess.run(['setpriv','--reuid=1000','--regid=1000','--clear-groups','--',
 'xfconf-query','-c','xsettings','-p','/Net/DoubleClickTime'],env=e,capture_output=True,text=True)
checks={
 'original_boot_path':all(not v.startswith('live-media-path=') for v in Path('/proc/cmdline').read_text().split()),
 'original_runtime':not Path('/usr/local/lib/portable/content_mounts.py').exists(),
 'original_initrd_without_marker':b'PETALOS_REPAIR_UNSIGNED_INITRD_MARKER' not in subprocess.check_output(['dmesg']),
 'desktop_active':subprocess.run(['systemctl','is-active','--quiet','display-manager.service']).returncode==0,
 'SYSTEM_settings_compatible':system_state.ready(),
 'saved_setting_retained':r.returncode==0 and r.stdout.strip()=='333',
 'Private_stayed_closed':not Path('/dev/mapper/portable_data').exists()}
print(json.dumps(checks));assert all(checks.values())
