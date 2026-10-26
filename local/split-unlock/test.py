#!/usr/bin/python3 -B
"""Exercise native pair transaction failures with an isolated fake cryptsetup."""
from pathlib import Path
import json
import os
import signal
import subprocess
import tempfile
import time

SOURCE = Path(__file__).with_name('unlock-pair.c')
with tempfile.TemporaryDirectory(prefix='petalos-pair-unit-') as temporary:
    root = Path(temporary)
    tool = root / 'cryptsetup'
    tool.write_text('''#!/usr/bin/python3
from pathlib import Path
import sys,time
root=Path(''' + repr(str(root)) + ''')
args=sys.argv[1:]
if args[0]=='close':
 (root/args[1]).unlink(missing_ok=True)
 raise SystemExit(0)
value=sys.stdin.buffer.read()
if value!=b'public-fixture-shared':raise SystemExit(2)
name=args[-1]
if name=='portable_system' and (root/'fail-settings').exists():raise SystemExit(2)
if name=='portable_system' and (root/'sleep-settings').exists():time.sleep(0.4)
if name=='portable_os' and '--readonly' not in args:raise SystemExit(4)
(root/name).touch()
''')
    tool.chmod(0o755)
    helper = root / 'pair'
    subprocess.run(['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-DPAIR_TEST',
                    '-DCRYPTSETUP=' + json.dumps(str(tool)), str(SOURCE), '-o', str(helper)], check=True)
    args = [str(helper), '--stdin', '/fixture/os', '/fixture/settings']
    def run(secret):
        for name in ('portable_os', 'portable_system'):
            (root/name).unlink(missing_ok=True)
        return subprocess.run(args, input=secret, capture_output=True, timeout=5)
    value = run(b'public-fixture-shared')
    assert value.returncode == 0 and not value.stdout and not value.stderr
    assert (root/'portable_os').exists() and (root/'portable_system').exists()
    print('PASS native helper unlocks both headers from one stdin secret with OS read-only')
    for secret in (b'private-fixture', b'', b'a'*513, b'line\nline', b'null\0byte'):
        value = run(secret)
        assert value.returncode and not (root/'portable_os').exists() and not (root/'portable_system').exists()
        assert not value.stdout and not value.stderr
    print('PASS wrong, empty, overlong, multiline and NUL credentials leave neither mapping open')
    (root/'fail-settings').touch()
    value = run(b'public-fixture-shared')
    assert value.returncode == 3 and not (root/'portable_os').exists() and not (root/'portable_system').exists()
    print('PASS settings mismatch rolls back the OS mapping and returns a distinct recovery error')
    (root/'fail-settings').unlink()
    (root/'sleep-settings').touch()
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process.stdin.write(b'public-fixture-shared');process.stdin.close()
    deadline = time.monotonic()+3
    while not (root/'portable_os').exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert (root/'portable_os').exists()
    process.send_signal(signal.SIGTERM)
    process.wait(timeout=5)
    assert process.returncode != 0 and not (root/'portable_os').exists() and not (root/'portable_system').exists()
    print('PASS termination during paired activation removes both mappings before exit')
