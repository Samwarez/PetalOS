#!/usr/bin/python3 -I
"""QEMU negative authentication checks; no real credential supplied or logged."""
import json
import os
import subprocess

assert os.geteuid() == 0
report = {}
policy = subprocess.run(['/usr/sbin/visudo', '-c'], capture_output=True, timeout=10)
report['sudo_policy_valid'] = policy.returncode == 0
base = ['/usr/bin/setpriv', '--reuid=1000', '--regid=1000', '--clear-groups',
        '/usr/bin/sudo', '-n', '--', '/usr/local/sbin/portable-lock-auth']
invalid = subprocess.run(base, input=b'public-invalid-lock-fixture\x00', capture_output=True, timeout=15)
report['invalid_password_rejected'] = invalid.returncode == 1
report['verifier_output_empty'] = not invalid.stdout and not invalid.stderr
extra = subprocess.run(base + ['unexpected'], input=b'', capture_output=True, timeout=5)
report['caller_arguments_rejected'] = extra.returncode != 0
wrong = subprocess.run(['/usr/bin/setpriv', '--reuid=948', '--regid=948', '--clear-groups',
    '/usr/bin/sudo', '-n', '--', '/usr/local/sbin/portable-lock-auth'],
    input=b'public-invalid-lock-fixture\x00', capture_output=True, timeout=5)
report['application_role_rejected'] = wrong.returncode != 0
print(json.dumps(report, sort_keys=True))
assert all(report.values())
