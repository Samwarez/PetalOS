#!/usr/bin/python3
"""Root QEMU acceptance checks. Uses public canaries; never reads credentials."""
from pathlib import Path
import json
import os
import pwd
import shutil
import subprocess
import tempfile


def main():
    assert os.geteuid() == 0
    assert Path('/sys/class/dmi/id/product_name').read_text().strip() in ('Standard PC (Q35 + ICH9, 2009)', 'Standard PC (i440FX + PIIX, 1996)')
    account = pwd.getpwuid(1000)
    assert account.pw_name in ('user', 'Petal')
    home = Path(account.pw_dir)
    environment = {**os.environ, 'HOME': str(home), 'DISPLAY': ':0',
                   'XAUTHORITY': str(home/'.Xauthority')}
    before = subprocess.check_output(['/usr/sbin/nft', '-j', 'list', 'table', 'inet', 'portable_vpn'])
    result = {}
    def user(command):
        return subprocess.run(['/usr/sbin/runuser','-u',account.pw_name,'--',*command],
                              env=environment,capture_output=True,timeout=20)
    network = Path('/mnt/private/Network')
    assert network.is_dir()
    fixture = Path(tempfile.mkdtemp(prefix='.public-aa-canary-',dir=network))
    os.chown(fixture, account.pw_uid, account.pw_gid)
    canary = fixture/'canary.conf'
    canary.write_text('SocksPort 0\nDisableNetwork 1\n')
    os.chown(canary,account.pw_uid,account.pw_gid)
    canary.chmod(0o600)
    try:
        # Prove DAC permits the same account to read this harmless fixture.
        result['unconfined_canary_read'] = user(['/usr/bin/python3','-c',
            'from pathlib import Path; assert Path('+repr(str(canary))+').read_text()']).returncode == 0
        code = '''import socket,json,subprocess,tempfile,os
from pathlib import Path
r={"enforcing":Path("/proc/self/attr/current").read_text().strip()=="petalos_offline (enforce)"}
for family,label in [(socket.AF_INET,"ipv4_denied"),(socket.AF_INET6,"ipv6_denied")]:
 try: socket.socket(family,socket.SOCK_STREAM);r[label]=False
 except PermissionError:r[label]=True
with tempfile.TemporaryDirectory(dir=os.environ["HOME"]) as d:
 p=Path(d)/"public-canary";p.write_text("public test");r["home_write"]=p.read_text()=="public test"
with tempfile.TemporaryDirectory(dir="/mnt/private") as d:
 p=Path(d)/"public-canary";p.write_text("public test");r["private_write"]=p.read_text()=="public test"
try:Path("/usr/share/petalos-no-write-canary").write_text("public test");r["root_write_denied"]=False
except OSError:r["root_write_denied"]=True
try:subprocess.run(["/usr/bin/sudo","-n","true"],capture_output=True);r["sudo_execution_denied"]=False
except PermissionError:r["sudo_execution_denied"]=True
try:Path(CANARY).read_text();r["vpn_directory_read_denied"]=False
except PermissionError:r["vpn_directory_read_denied"]=True
print(json.dumps(r));assert all(r.values())
'''.replace('CANARY',repr(str(canary)))
        probe=user(['/usr/local/bin/portable-offline','/usr/bin/python3','-c',code])
        assert probe.returncode==0, 'Offline confinement probe failed; output suppressed.'
        result.update(json.loads(probe.stdout))
        for executable in ('geany','keepassxc','vim'):
            result[executable+'_startup']=user(['/usr/bin/'+executable,'--version']).returncode==0
        browser=home/'.local/share/portable-tor/tor-browser/Browser'
        tor=browser/'TorBrowser/Tor/tor'
        assert tor.is_file()
        allowed=Path(tempfile.mkdtemp(prefix='public-aa-canary-',dir=browser/'TorBrowser/Data/Tor'))
        os.chown(allowed,account.pw_uid,account.pw_gid)
        try:
            config=allowed/'torrc'
            config.write_text('SocksPort 0\nDisableNetwork 1\nDataDirectory '+str(allowed)+'\n')
            os.chown(config,account.pw_uid,account.pw_gid)
            result['tor_allowed_config']=user([str(tor),'--verify-config','-f',str(config)]).returncode==0
            denied=user([str(tor),'--verify-config','-f',str(canary)])
            result['tor_private_config_denied']=denied.returncode!=0 and b'Permission denied' in denied.stdout+denied.stderr
        finally:
            shutil.rmtree(allowed)
        result['firefox_startup']=user(['/usr/bin/aa-exec','-p','petalos_firefox','--',str(browser/'firefox.real'),'--version']).returncode==0
        result['missing_profile_fails_closed']=user(['/usr/bin/aa-exec','-p','petalos-intentionally-absent','--','/usr/bin/true']).returncode!=0
        result['firewall_unchanged']=before==subprocess.check_output(['/usr/sbin/nft','-j','list','table','inet','portable_vpn'])
        print(json.dumps(result,sort_keys=True))
        assert all(result.values()), 'AppArmor acceptance check failed.'
    finally:
        shutil.rmtree(fixture)

if __name__=='__main__':main()
