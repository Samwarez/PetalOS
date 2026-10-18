#!/usr/bin/python3 -I
"""QEMU-only public canaries model code execution inside app boundaries."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c

assert os.geteuid() == 0
assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
assert 'toram' in Path('/proc/cmdline').read_text().split()
before = subprocess.check_output(['/usr/sbin/nft', '-j', 'list', 'table', 'inet', 'portable_vpn'])
fixture = Path(tempfile.mkdtemp(prefix='.public-compartment-', dir='/mnt/private'))
download = Path('/mnt/private/Downloads/TorBrowser') / (fixture.name + '.canary')
policy_file = c.BASE / 'boundary-audit.profile'
loaded = False
try:
    os.chown(fixture, 1000, 1000)
    (fixture / 'canary').write_text('public boundary fixture')
    download.write_text('public boundary fixture')
    os.chown(download, 1000, 1000)
    c.grant(download.parent, c.ROLES['browser'])
    policy = Path('/etc/apparmor.d/petalos.browser').read_text().replace(
        'profile petalos_browser @{petalos_browser_executable} {', 'profile petalos_browser_boundary_audit {')
    position = policy.rfind('}')
    policy = policy[:position] + '\n /usr/bin/python3{,.13} ix,\n /usr/lib/python3.13/{,**} mr,\n' + policy[position:]
    policy_file.write_text(policy)
    subprocess.run(['/usr/sbin/apparmor_parser', '-r', '-K', str(policy_file)], check=True, capture_output=True)
    loaded = True
    code = '''import json,os,socket
from pathlib import Path
r={'uid':os.getuid(),'groups':os.getgroups()}
r['parent_home_hidden']=not Path('/home/Petal').exists()
r['parent_x_socket_hidden']=not Path('/tmp/.X11-unix/X0').exists()
r['private_canary_hidden']=not Path(PRIVATE_CANARY).exists()
r['own_download_readable']=Path(DOWNLOAD).read_text()=='public boundary fixture'
for family,name,address in [(socket.AF_INET,'ipv4_socket_denied',('1.1.1.1',443)),(socket.AF_INET6,'ipv6_socket_denied',('2606:4700:4700::1111',443))]:
 try:
  s=socket.socket(family,socket.SOCK_STREAM);s.close();r[name]=False
 except PermissionError:r[name]=True
r['capabilities_zero']='CapEff:\\t0000000000000000' in Path('/proc/self/status').read_text()
print(json.dumps(r))
'''.replace('PRIVATE_CANARY', repr(str(fixture / 'canary'))).replace('DOWNLOAD', repr(str(download)))
    result = subprocess.run(c.sandbox('browser', ['/usr/bin/aa-exec', '-p', 'petalos_browser_boundary_audit', '--', '/usr/bin/python3', '-I', '-c', code]), capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise RuntimeError('Boundary probe failed; raw output suppressed.')
    report = json.loads(result.stdout)
    report['firewall_unchanged'] = before == subprocess.check_output(['/usr/sbin/nft', '-j', 'list', 'table', 'inet', 'portable_vpn'])
    print(json.dumps(report, sort_keys=True))
    assert report['uid'] == 941 and report['groups'] == []
    assert all(value is True for name, value in report.items() if name not in ('uid', 'groups'))
finally:
    if loaded:
        subprocess.run(['/usr/sbin/apparmor_parser', '-R', str(policy_file)], check=True, capture_output=True)
    policy_file.unlink(missing_ok=True)
    download.unlink(missing_ok=True)
    shutil.rmtree(fixture)
