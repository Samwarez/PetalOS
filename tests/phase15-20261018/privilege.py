from pathlib import Path
import json,os,subprocess,sys
assert os.geteuid()==0
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
def as_user(args):return subprocess.run(['setpriv','--reuid=1000','--regid=1000','--clear-groups',*args],capture_output=True,timeout=15)
r={}
for key,cmd in {
 'general_sudo_denied':['sudo','-n','true'],
 'worker_entry_denied':['sudo','-n','/usr/local/sbin/portable-compartment','--worker','amule','0'*32],
 'unknown_storage_action_denied':['sudo','-n','/usr/local/sbin/portable-storage','unlock-anything'],
 'extra_root_command_denied':['sudo','-n','/usr/local/sbin/portable-lock-auth','/bin/sh']}.items():r[key]=as_user(cmd).returncode!=0
for device in ('/dev/vda','/dev/vda2','/dev/vda3','/dev/vda4','/dev/mapper/portable_system','/dev/mapper/portable_data'):
 if not Path(device).exists():continue
 # Open-only permission checks; no disk contents read or written.
 for flag,label in [('os.O_RDONLY','read'),('os.O_WRONLY','write')]:
  x=as_user(['python3','-I','-c','import os;f=os.open('+repr(device)+','+flag+');os.close(f)'])
  r['raw_'+label+'_denied:'+device]=x.returncode!=0
desktop=subprocess.check_output(['pgrep','-u','1000','-x','labwc'],text=True).split()[0]
start=Path('/proc',desktop,'stat').read_text().rsplit(') ',1)[1].split()[19]
for action in ('org.freedesktop.policykit.exec','org.freedesktop.udisks2.filesystem-mount-system','org.freedesktop.udisks2.modify-device','org.freedesktop.systemd1.manage-units'):
 x=subprocess.run(['pkcheck','--action-id',action,'--process',desktop+','+start+',1000'],capture_output=True,timeout=15)
 r['polkit_auth_required:'+action]=x.returncode==2 and b'Authorization requires authentication' in x.stderr
 r['polkit_exit:'+action]=x.returncode
 if x.returncode not in (0,1):r['polkit_test_error:'+action]=x.stderr.decode()[:400]
r['sudo_valid']=subprocess.run(['visudo','-c'],capture_output=True).returncode==0
r['core_dump_disabled']=Path('/proc/sys/kernel/core_pattern').read_text().strip()=='|/bin/false'
print(json.dumps(r,sort_keys=True))
