#!/usr/bin/env python3
"""Real signature checks with a stub browser: never launch host Tor/network."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

project = Path(__file__).resolve().parents[1]
cache = project.parent / 'provisioning/TorBrowser'
archive = next(cache.glob('tor-browser-linux-x86_64-*.tar.xz'))
keyring = project / 'config/includes.chroot/usr/local/share/portable/tor-browser-developers.keyring'
source = (project / 'config/includes.chroot/usr/local/bin/portable-tor').read_text()
for scenario in ('valid', 'invalid-signature', 'missing-signature'):
    with tempfile.TemporaryDirectory(prefix='petalos-tor-test-', dir='/dev/shm') as temporary:
        root = Path(temporary); home = root / 'home'; home.mkdir()
        private = root / 'private'; assets = private / 'Applications/TorBrowser'; assets.mkdir(parents=True)
        shutil.copyfile(archive, assets / archive.name)
        signature = assets / (archive.name + '.asc')
        if scenario == 'valid': shutil.copyfile(Path(str(archive) + '.asc'), signature)
        if scenario == 'invalid-signature': signature.write_text('invalid signature\n')
        commands = root / 'commands'; commands.mkdir()
        def command(name, body):
            path = commands / name; path.write_text('#!/bin/sh\n' + body + '\n'); path.chmod(0o755)
        command('mountpoint', 'exit 0')
        command('sudo', 'exit 0')  # Guard/clock are covered separately; no host privilege use.
        command('aa-exec', 'exit 0')  # Enforcement is covered in the real guest.
        command('findmnt', 'case "$*" in *SOURCE*) echo /dev/mapper/portable_data;; *) echo tmpfs;; esac')
        command('portable-message', 'exit 0')
        command('tar', '''touch "$HOME/extraction-marker"
mkdir -p "$HOME/.local/share/portable-tor/tor-browser/Browser/TorBrowser/Data/Browser/profile.default"
printf '#!/bin/sh\necho STUB_BROWSER_STARTED\n' > "$HOME/.local/share/portable-tor/tor-browser/Browser/start-tor-browser"
chmod 755 "$HOME/.local/share/portable-tor/tor-browser/Browser/start-tor-browser"''')
        script = root / 'portable-tor'
        helper = root / 'tor_archives.py'
        helper.write_text((project / 'config/includes.chroot/usr/local/lib/portable/tor_archives.py').read_text()
                          .replace('/mnt/private/Applications/TorBrowser', str(assets))
                          .replace('/usr/local/share/portable/tor-browser-developers.keyring', str(keyring)))
        script.write_text(source.replace('/mnt/private', str(private))
                          .replace('/usr/bin/sudo', str(commands / 'sudo'))
                          .replace('/usr/bin/aa-exec', str(commands / 'aa-exec'))
                          .replace('/usr/local/bin/portable-message', str(commands / 'portable-message'))
                          .replace('/usr/local/lib/portable/tor_archives.py', str(helper)))
        environment = {**os.environ, 'HOME': str(home), 'PATH': str(commands) + ':/usr/sbin:/usr/bin:/bin'}
        result = subprocess.run(['/bin/bash', str(script)], env=environment, input='\n',
                                text=True, capture_output=True, timeout=30)
        success = scenario == 'valid'
        assert (result.returncode == 0) == success
        assert (home / 'extraction-marker').exists() == success
        assert ('STUB_BROWSER_STARTED' in result.stdout) == success
        if success:
            profile = home / '.local/share/portable-tor/tor-browser/Browser/TorBrowser/Data/Browser/profile.default'
            assert 'user_pref("extensions.torlauncher.prompt_at_startup", false);' in (profile / 'prefs.js').read_text()
            assert 'prompt_at_startup' not in (profile / 'user.js').read_text()
            import json
            policy = profile.parents[3] / 'distribution/policies.json'
            assert json.loads(policy.read_text())['policies']['DisableAppUpdate'] is True
            # Simulate Tor requiring recovery after a failed bootstrap.
            recovery = 'user_pref("extensions.torlauncher.prompt_at_startup", true);\n'
            (profile / 'prefs.js').write_text(recovery)
            result = subprocess.run(['/bin/bash', str(script)], env=environment,
                                    input='\n', text=True, capture_output=True, timeout=30)
            assert result.returncode == 0
            assert (profile / 'prefs.js').read_text() == recovery
            result = subprocess.run(['/bin/bash', str(script), '--prepare'], env=environment,
                                    input='\n', text=True, capture_output=True, timeout=30)
            assert result.returncode == 0 and 'STUB_BROWSER_STARTED' not in result.stdout
            print('PASS: fresh RAM quickstart seed preserves subsequent recovery preference')
        print('PASS: Tor signature gate ' + scenario)
