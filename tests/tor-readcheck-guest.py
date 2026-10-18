#!/usr/bin/python3
"""QEMU-only acceptance for the narrow no-password Tor readiness gate."""
import fcntl
import json
import os
from pathlib import Path
import pwd
import subprocess

assert os.geteuid()==0
assert Path('/sys/class/dmi/id/product_name').read_text().strip()=='Standard PC (Q35 + ICH9, 2009)'
account=pwd.getpwuid(1000)
assert account.pw_name=='Petal'
env={**os.environ,'HOME':account.pw_dir,'DISPLAY':':0','XAUTHORITY':account.pw_dir+'/.Xauthority'}
result={}
def user(command,timeout=30):
    return subprocess.run(['/usr/sbin/runuser','-u','Petal','--',*command],env=env,
        stdin=subprocess.DEVNULL,capture_output=True,timeout=timeout)
def root(command,timeout=90):
    return subprocess.run(command,stdin=subprocess.DEVNULL,capture_output=True,timeout=timeout)
def gate(*arguments):
    return user(['/usr/bin/sudo','-n','--','/usr/local/sbin/portable-check-tor-ready',*arguments]).returncode

def drop_policies():
    table=json.loads(subprocess.check_output(['/usr/sbin/nft','-j','list','table','inet','portable_vpn']))['nftables']
    chains=[x['chain'] for x in table if 'chain' in x and x['chain'].get('hook') in ('input','output','forward')]
    return len(chains)==3 and all(x.get('policy')=='drop' for x in chains)

before=subprocess.check_output(['/usr/sbin/nft','-j','list','table','inet','portable_vpn'])
assert user(['sudo','-K']).returncode==0
result['gate_allowed_without_cached_auth']=gate()==0
result['tor_prepare_without_cached_auth']=user(['/usr/local/bin/portable-tor','--prepare']).returncode==0
result['general_sudo_requires_password']=user(['sudo','-n','true']).returncode!=0
result['vpn_changes_require_password']=user(['sudo','-n','--','/usr/local/sbin/portable-vpn','disconnect']).returncode!=0
result['clock_commands_require_password']=user(['sudo','-n','--','/usr/bin/chronyc','tracking']).returncode!=0
result['extra_arguments_denied']=gate('--help')!=0
result['preserving_untrusted_environment_denied']=user(['sudo','-n','-E','--','/usr/local/sbin/portable-check-tor-ready']).returncode!=0
result['unprivileged_direct_call_denied']=user(['/usr/local/sbin/portable-check-tor-ready']).returncode!=0
with open('/run/portable-vpn.lock','rb') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    result['transaction_in_progress_denied']=gate()!=0
result['readchecks_leave_firewall_unchanged']=before==subprocess.check_output(['/usr/sbin/nft','-j','list','table','inet','portable_vpn'])
try:
    assert root(['systemctl','stop','chrony.service']).returncode==0
    result['unsynchronized_clock_denied']=gate()!=0
finally:
    assert root(['systemctl','start','chrony.service']).returncode==0
    assert root(['/usr/bin/chronyc','waitsync','30','0.5','0','1'],timeout=40).returncode==0
result['gate_recovers_after_clock_sync']=gate()==0
try:
    assert root(['/usr/local/sbin/portable-vpn','disconnect']).returncode==0
    result['disconnected_vpn_denied']=gate()!=0
    result['tor_prepare_when_disconnected_denied']=user(['/usr/local/bin/portable-tor','--prepare']).returncode!=0
    result['kill_switch_retained_while_disconnected']=drop_policies()
finally:
    reconnect=root(['/usr/local/sbin/portable-vpn','connect'],timeout=100)
    if reconnect.returncode:
        raise RuntimeError('VPN restoration failed; raw output suppressed and firewall retained.')
result['gate_recovers_after_reconnect']=gate()==0
result['kill_switch_retained_after_reconnect']=drop_policies()
result['general_sudo_still_requires_password']=user(['sudo','-n','true']).returncode!=0
print(json.dumps(result,sort_keys=True))
assert all(result.values()),'Tor read-only gate acceptance failed.'
