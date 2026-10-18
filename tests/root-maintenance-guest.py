#!/usr/bin/python3 -I
"""Ephemeral authenticated SSH stdin session; no listener or installed service."""
import contextlib
import io
import json
import os
import subprocess
import sys

assert os.geteuid() == 0
assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() in ('qemu', 'kvm')
print('PETAL_ROOT_SESSION_READY', flush=True)
for line in sys.stdin:
    if len(line) > 1048576:
        break
    try:
        request = json.loads(line)
        if request.get('op') == 'close':
            break
        assert request.get('op') == 'exec' and isinstance(request.get('source'), str)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            exec(compile(request['source'], '<public-maintenance>', 'exec'), {'__name__': '__main__'})
        response = {'ok': True, 'output': output.getvalue()[-65536:]}
    except BaseException as error:
        response = {'ok': False, 'error_type': type(error).__name__}
    print('PETAL_ROOT_RESULT:' + json.dumps(response), flush=True)
