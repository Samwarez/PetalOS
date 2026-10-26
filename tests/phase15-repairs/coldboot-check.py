"""Verify the actual generation boot and restored state, before reconnecting VPN."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
sys.path.insert(0,'/usr/local/lib/portable')
import system_state
from desktop_session import environment
expected=json.loads(Path('/tmp/petalos-public-repair-expected.json').read_text())
checks={}
for name,sha in expected['files'].items():
 if not name.startswith('root/'):continue
 p=Path('/')/name[5:]
 checks['source:'+name[5:]]=p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==sha
cmdline=Path('/proc/cmdline').read_text().split()
generation=expected['generation'];relative='petalos/releases/'+generation+'/live'
checks['generation_selected']='live-media-path=/'+relative in cmdline
medium=Path('/run/live/medium')
checks['selected_RAM_medium']=subprocess.check_output(['findmnt','-n','-o','FSTYPE','--mountpoint',str(medium)],text=True).strip()=='tmpfs'
checks['only_one_RAM_generation']=len(list((medium/'petalos/releases').iterdir()))==1 and not (medium/'live').exists()
checks['SYSTEM_state_not_copied_to_RAM']=not (medium/'.petalos-state').exists() and not (medium/'.petalos-auth').exists()
checks['SYSTEM_selected_state_ready']=system_state.ready()
checks['Private_closed']=not Path('/dev/mapper/portable_data').exists()
checks['content_service_active']=subprocess.run(['systemctl','is-active','--quiet','portable-ram-content.service']).returncode==0
for name in ('Documents','Downloads'):
 checks[name+'_is_tmpfs']=subprocess.check_output(['findmnt','-n','-o','FSTYPE','--mountpoint','/home/Petal/'+name],text=True).strip()=='tmpfs'
def entered(unit):return int(subprocess.check_output(['systemctl','show','-p','ActiveEnterTimestampMonotonic','--value',unit],text=True))
checks['content_ready_before_display']=0 < entered('portable-ram-content.service') <= entered('display-manager.service')
e=environment();pre=['setpriv','--reuid=1000','--regid=1000','--clear-groups','--']
r=subprocess.run(pre+['xfconf-query','-c','xsettings','-p','/Net/DoubleClickTime'],env=e,capture_output=True,text=True)
checks['saved_setting_333_restored']=r.returncode==0 and r.stdout.strip()=='333'
variables=list(Path('/sys/firmware/efi/efivars').glob('SecureBoot-*'))
checks['Secure_Boot_enabled']=len(variables)==1 and variables[0].read_bytes()[-1:]==b'\x01'
checks['unsigned_initrd_marker_executed']=b'PETALOS_REPAIR_UNSIGNED_INITRD_MARKER' in subprocess.check_output(['dmesg'])
checks['swap_absent']=len(Path('/proc/swaps').read_text().splitlines())==1
checks['no_general_home_persistence']=subprocess.check_output(['findmnt','-n','-o','FSTYPE','-T','/home/Petal'],text=True).strip()=='overlay'
failures=[k for k,v in checks.items() if not v]
print(json.dumps({'checks':checks,'failures':failures,'generation':generation,'marker_is_security_gap_confirmation_not_a_protection':True}))
assert not failures
