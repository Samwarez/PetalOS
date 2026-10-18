#!/usr/bin/env python3
"""Offline regression checks for changing exit addresses and fail-closed reporting."""
from pathlib import Path
from unittest.mock import patch
import contextlib
import io
import json
import os
import runpy
import subprocess
import sys
import tempfile
from types import SimpleNamespace

script = Path(__file__).resolve().parents[1] / 'config/includes.chroot/usr/local/bin/portable-check-exit-ip'
real_path = Path
cases = [(a,s,ok,4) for a,s,ok in [('152.89.162.5', 'ok', True), ('152.89.162.7', 'ok', True),
         ('127.0.0.1', 'ok', False), ('invalid', 'ok', False),
         ('152.89.162.5', 'guard', False), ('152.89.162.5', 'timeout', False)]]
cases += [('2001:4860:4860::8888','ok',True,6), ('fd77::1','ok',False,6),
          ('152.89.162.5','ok',False,6), ('invalid','ok',False,6),
          ('2001:4860:4860::8888','guard',False,6),('2001:4860:4860::8888','timeout',False,6)]
for address, scenario, succeeds, family in cases:
    with tempfile.TemporaryDirectory(dir='/dev/shm', prefix='petalos-exit-test-') as tmp:
        runtime = real_path(tmp)
        directory = runtime / 'portable-status'; directory.mkdir()
        cache = directory / ('exit-ipv6.json' if family == 6 else 'exit-ip.json')
        cache.write_text('{"address":"152.89.162.7","matches":true}')
        curls = []

        def path(value):
            return runtime if str(value) == f'/run/user/{os.getuid()}' else real_path(value)

        def command(args, **kwargs):
            if args[0] == '/usr/bin/findmnt': return SimpleNamespace(returncode=0, stdout='tmpfs\n')
            if args[0] == '/usr/bin/sudo': return SimpleNamespace(returncode=int(scenario == 'guard'))
            if args[0] == '/usr/bin/curl':
                curls.append(args)
                assert args[args.index('--interface') + 1] == 'wg0'
                assert args[args.index('--noproxy') + 1] == '*'
                assert f'-{family}' in args and '--max-time' in args and kwargs['timeout'] <= 15
                assert args[-1] == ('https://api6.ipify.org' if family == 6 else 'https://api.ipify.org')
                if scenario == 'timeout': raise subprocess.CalledProcessError(28, args)
                return SimpleNamespace(returncode=0, stdout=address + '\n')
            return SimpleNamespace(returncode=0)

        result = 0
        with patch('sys.argv', [str(script)]+(['--ipv6'] if family==6 else [])), patch('pathlib.Path', side_effect=path), patch('subprocess.run', side_effect=command), contextlib.redirect_stdout(io.StringIO()):
            try: runpy.run_path(str(script))
            except SystemExit as error: result = error.code
        assert (result == 0) == succeeds
        if succeeds:
            record = json.loads(cache.read_text())
            assert record['address'] == address and record['interface'] == 'wg0'
            assert 'expected' not in record and 'matches' not in record
        else:
            assert not cache.exists()
        if scenario == 'guard': assert not curls
        print(f'PASS: exit-IP case {scenario}/{address}')
