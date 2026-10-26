"""Actual aMule preview helper hands a selected Private file to native Parole."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
assert os.geteuid() == 0
sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c
assert c.private_available()
source = Path('/home/Petal/Downloads/petalos-audit-av.webm')
c.stop('amule');c.home('amule');c.storage_setup('amule')
target = Path('/mnt/private/Downloads/amule/combined-preview.webm')
assert source.is_file() and not target.exists()
shutil.copyfile(source, target);os.chown(target, 1000, 1000);target.chmod(0o600)
c.start('amule')
assert c.read_record('amule')['storage'] == 'private'
command = c.sandbox('amule', ['aa-exec', '-p', 'petalos_amule', '--',
    '/usr/local/bin/portable-amule-player', str(target)], extra_binds=[
        (c.BASE/'amule/identity.json', '/run/petalos-compartment.json', False),
        (c.BASE/'amule/media', '/run/user/944/portable-media', False)])
result = subprocess.run(command, capture_output=True, timeout=45)
checks = {'actual_preview_helper_succeeded': result.returncode == 0,
          'Parole_ready_with_selected_Private_file': c.read_record('offline-parole').get('phase') == 'ready' and c.worker_alive(c.read_record('offline-parole')),
          'selected_media_unchanged': hashlib.sha256(target.read_bytes()).digest() == hashlib.sha256(source.read_bytes()).digest()}
print(json.dumps(checks))
assert all(checks.values())
