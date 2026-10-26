#!/usr/bin/python3
"""Check production storage modules after an actual full live OS/RAM boot."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

# Direct console output keeps test records independent of journald formatting.
sys.stdout = open('/dev/ttyS0', 'w', buffering=1)
sys.path.insert(0, '/usr/local/lib/portable')
data = json.loads(Path('/root/.petalos-split-test-input.json').read_text())
results = {}


def check(name, condition):
    results[name] = bool(condition)
    if not condition:
        raise RuntimeError('Full-boot check failed: ' + name)
    print('SPLIT_PASS ' + name, flush=True)


try:
    from compartments import ram_ready
    from private_storage import identity, backend, authenticate_system
    import system_state
    import account_auth
    ram_ready()
    check('actual_live_root_and_home_in_ram', True)
    check('no_swap', len(Path('/proc/swaps').read_text().splitlines()) == 1)
    for relative, expected in data['runtime_files'].items():
        check('runtime_matches_source_' + Path(relative).name,
              hashlib.sha256(Path('/' + relative).read_bytes()).hexdigest() == expected)
    state = identity()
    check('production_boot_captured_three_independent_volumes', state['layout'] == 2 and set(state['devices']) == {'os', 'system', 'data'})
    check('os_mapping_closed_after_actual_toram', not backend().mapped('os'))
    check('settings_ready_in_actual_live_os', system_state.ready())
    check('private_closed_after_actual_boot', not backend().mapped('data'))
    check('independent_settings_canary_readable', (system_state.STATE / 'Desktop/fullboot-canary').read_bytes() == b'fullboot-independent-settings')
    check('administrator_credential_in_settings_partition', bool(account_auth.load_hash()))
    check('system_screen_verifier_accepts_system', authenticate_system(data['credentials']['system'].encode()))
    check('screen_verifier_rejects_private', not authenticate_system(data['credentials']['private'].encode()))
    check('screen_verifier_does_not_open_private', not backend().mapped('data'))
    adapter = backend()
    adapter.unlock(state, data['credentials']['private'].encode())
    check('private_opens_with_own_passphrase_in_live_os', adapter.is_unlocked(state))
    check('private_data_independent', Path('/mnt/private/fullboot-canary').read_bytes() == b'fullboot-independent-private')
    adapter.close_private(state)
    check('private_reclosed_in_live_os', not adapter.mapped('data'))
    print('SPLIT_RESULT ' + json.dumps({'stage': 'full-boot', 'checks': results, 'passed': True}), flush=True)
except BaseException as error:
    import traceback
    location = traceback.extract_tb(error.__traceback__)[-1]
    print('SPLIT_RESULT ' + json.dumps({'checks': results, 'passed': False,
        'failure_type': type(error).__name__, 'failure_source': Path(location.filename).name + ':' + str(location.lineno)}), flush=True)
finally:
    subprocess.run(['/usr/bin/systemctl', 'poweroff', '--no-block'])
