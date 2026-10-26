#!/usr/bin/python3 -B
"""Mock command flow: auto tests run at connect and failures remove stale results."""
import os
from pathlib import Path
import subprocess
import tempfile

project = Path(__file__).resolve().parents[1]
original = (project / 'config/includes.chroot/usr/local/sbin/portable-vpn').read_text()

with tempfile.TemporaryDirectory(prefix='petalos-vpn-flow-') as temporary:
    root = Path(temporary)
    bindir = root / 'bin'; bindir.mkdir()
    (root / 'run/portable-vpn').mkdir(parents=True)
    (root / 'etc/wireguard').mkdir(parents=True)
    mock = bindir / 'mock'
    mock.write_text('''#!/usr/bin/python3 -B
import os,sys,pathlib,json
r=pathlib.Path(os.environ['FIXTURE_ROOT']);cmd=pathlib.Path(sys.argv[0]).name;a=sys.argv[1:]
with (r/'calls').open('a') as f:f.write(cmd+' '+(' '.join(a) if cmd!='require-state' else '')+'\\n')
if cmd=='ip':sys.exit(0 if (r/'link').exists() else 1)
if cmd=='wg-quick':
 if a[0]=='up':(r/'link').touch()
 else:(r/'link').unlink(missing_ok=True)
elif cmd=='portable-vpn-profile' and a[0]=='prepare':
 if os.environ.get('PROFILE_FAIL')=='1':sys.exit(1)
 (r/'run/portable-vpn/resolv.conf').write_text('nameserver 10.0.0.1\\n')
elif cmd=='chronyc':
 (r/'clock-attempted').touch()
 if os.environ.get('CLOCK_FAIL')=='1':sys.exit(1)
elif cmd=='portable-check-vpn':
 if not a:
  assert (r/'clock-attempted').exists()
  if os.environ.get('TLS_FAIL')=='1':sys.exit(1)
elif cmd=='portable-test-vpn-connection':
 assert (r/'clock-attempted').exists()
 if os.environ.get('TEST_FAIL')=='1':sys.exit(1)
 (r/'run/portable-vpn-checks.json').write_text('public fixture report')
elif cmd=='rm':
 for v in a:
  if v.startswith('-'):continue
  p=pathlib.Path(v);assert p.is_relative_to(r);p.unlink(missing_ok=True)
''')
    mock.chmod(0o755)
    commands = ('nft', 'systemctl', 'ip', 'wg-quick', 'chronyc', 'flock',
                'portable-vpn-profile', 'portable-check-vpn', 'portable-test-vpn-connection',
                'require-state', 'install', 'cp', 'chmod', 'rm')
    for name in commands:
        (bindir / name).symlink_to(mock)
    source = original.replace('[[ $EUID -eq 0 ]]', '[[ 0 -eq 0 ]]')
    source = source.replace('/run/', str(root / 'run') + '/').replace('/etc/', str(root / 'etc') + '/')
    source = source.replace('/usr/bin/python3', str(bindir / 'require-state'))
    for name in ('portable-vpn-profile', 'portable-check-vpn', 'portable-test-vpn-connection'):
        source = source.replace('/usr/local/sbin/' + name, str(bindir / name))
    script = root / 'vpn'; script.write_text(source)
    environment = {'PATH': str(bindir), 'FIXTURE_ROOT': str(root), 'LC_ALL': 'C'}
    report = root / 'run/portable-vpn-checks.json'

    def run(action, **extra):
        result = subprocess.run(['/bin/bash', str(script), action], env={**environment, **extra},
                                capture_output=True, text=True, timeout=10)
        return result.returncode

    assert run('connect') == 0 and report.exists()
    calls = (root / 'calls').read_text()
    assert calls.count('portable-test-vpn-connection') == 1
    assert calls.index('portable-check-vpn --transport-only') < calls.index('chronyc waitsync')
    assert calls.index('chronyc waitsync') < calls.index('portable-check-vpn \n')
    assert calls.index('portable-check-vpn \n') < calls.index('portable-test-vpn-connection')
    assert calls.index('portable-test-vpn-connection') < calls.index('portable-vpn-profile commit')
    assert run('disconnect') == 0 and not report.exists() and not (root / 'link').exists()
    assert run('disconnect') == 0
    print('PASS connect runs automatic checks after clock attempt; disconnect clears report and is repeatable')

    report.write_text('stale public fixture')
    (root / 'calls').write_text('')
    assert run('connect', TEST_FAIL='1') == 20
    assert not report.exists() and not (root / 'link').exists()
    assert 'portable-vpn-profile commit' not in (root / 'calls').read_text()
    print('PASS required post-connect failure rolls back, removes stale success and preserves saved selection')

    report.write_text('stale public fixture')
    (root / 'calls').write_text('')
    assert run('connect', CLOCK_FAIL='1', TLS_FAIL='1') == 21
    assert not report.exists() and not (root / 'link').exists()
    calls = (root / 'calls').read_text()
    assert 'portable-vpn-profile commit' not in calls
    assert 'portable-test-vpn-connection' not in calls
    assert 'portable-check-vpn \n' in calls
    print('PASS clock plus TLS failure rolls back before automatic checks or saved-profile commit')

    assert run('connect', CLOCK_FAIL='1') == 0
    assert report.exists() and (root / 'link').exists()
    assert run('disconnect') == 0
    print('PASS unavailable time source retains a TLS-verified tunnel; the separate Tor clock gate remains required')

    report.write_text('stale public fixture')
    assert run('connect', PROFILE_FAIL='1') != 0
    assert not report.exists() and not (root / 'link').exists()
    print('PASS invalid profile cannot retain an earlier success report')
