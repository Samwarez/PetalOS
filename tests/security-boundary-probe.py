#!/usr/bin/python3
"""Public-canary boundary tests; audit policy models code execution, no exploit."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile


def main():
    assert os.geteuid() == 0
    assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
    before = subprocess.check_output(['/usr/sbin/nft', '-j', 'list', 'table', 'inet', 'portable_vpn'])
    root = Path(tempfile.mkdtemp(prefix='petalos-boundary-', dir='/run'))
    private = Path(tempfile.mkdtemp(prefix='.public-boundary-', dir='/mnt/private'))
    os.chown(private, 1000, 1000)
    canary = private / 'canary'
    canary.write_text('public security test')
    os.chown(canary, 1000, 1000)
    browser_canary = Path('/mnt/private/Downloads/TorBrowser') / (root.name + '.public-canary')
    browser_canary.write_text('public security test')
    os.chown(browser_canary, 1000, 1000)
    loaded = False
    try:
        policy = Path('/etc/apparmor.d/petalos.torbrowser.Browser.firefox').read_text()
        policy = policy.replace('profile petalos_firefox @{petalos_firefox_executable} {', 'profile petalos_firefox_audit {')
        # Add only a diagnostic interpreter/library entry, retaining the actual
        # browser network, file and IPC permissions. This models an attacker
        # already executing code in the browser; it is not a browser exploit.
        policy += ''
        position = policy.rfind('}')
        policy = policy[:position] + '\n  /usr/bin/python3{,.13} ix,\n  /usr/lib/python3.13/{,**} mr,\n' + policy[position:]
        path = root / 'browser-audit.profile'
        path.write_text(policy)
        subprocess.run(['/usr/sbin/apparmor_parser', '-r', '-K', str(path)], check=True, capture_output=True)
        loaded = True
        address = socket.getaddrinfo('api.ipify.org', 443, socket.AF_INET, socket.SOCK_STREAM)[0][4]
        code = '''import json,socket
from pathlib import Path
r={}
try:
 with socket.create_connection(ADDRESS,timeout=5):r['direct_vpn_tcp_possible']=True
except OSError:r['direct_vpn_tcp_possible']=False
try:Path(CANARY).read_text();r['arbitrary_private_canary_denied']=False
except PermissionError:r['arbitrary_private_canary_denied']=True
try:Path(BROWSER_CANARY).read_text();r['tor_download_canary_readable']=True
except PermissionError:r['tor_download_canary_readable']=False
print(json.dumps(r))
'''.replace('ADDRESS', repr(address)).replace('BROWSER_CANARY', repr(str(browser_canary))).replace('CANARY', repr(str(canary)))
        probe = subprocess.run(['/usr/sbin/runuser', '-u', 'Petal', '--', '/usr/bin/aa-exec', '-p', 'petalos_firefox_audit', '--', '/usr/bin/python3', '-c', code], capture_output=True, text=True, timeout=15)
        if probe.returncode:
            raise RuntimeError('Diagnostic browser-policy probe failed; raw output suppressed.')
        result = json.loads(probe.stdout)
        result['unconfined_private_canary_readable'] = subprocess.run(['/usr/sbin/runuser', '-u', 'Petal', '--', '/usr/bin/test', '-r', str(canary)]).returncode == 0
        result['firewall_unchanged'] = before == subprocess.check_output(['/usr/sbin/nft', '-j', 'list', 'table', 'inet', 'portable_vpn'])
        print(json.dumps(result, sort_keys=True))
    finally:
        if loaded:
            subprocess.run(['/usr/sbin/apparmor_parser', '-R', str(root / 'browser-audit.profile')], check=True, capture_output=True)
        browser_canary.unlink(missing_ok=True)
        shutil.rmtree(private)
        shutil.rmtree(root)


if __name__ == '__main__':
    main()
