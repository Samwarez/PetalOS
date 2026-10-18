#!/usr/bin/python3
"""Preparation/state preservation tests; native clients and guards are stubbed."""
from pathlib import Path
import configparser
import json
import os
import re
import subprocess
import tempfile

project=Path(__file__).resolve().parents[1]
source_root=project/'config/includes.chroot/usr/local'
for app in ('transmission','pan','amule'):
    with tempfile.TemporaryDirectory(prefix='petalos-download-test-',dir='/dev/shm') as temporary:
        root=Path(temporary);private=root/'private';home=root/'home';home.mkdir()
        state=private/'AppState'/app
        prepare=root/'prepare.sh'
        prepare.write_text('#!/bin/sh\n[ "${FAKE_BLOCK:-0}" != 1 ] || exit 1\nmkdir -p "'+str(state)+'"\nprintf "%s\\n" "'+str(state)+'"\n')
        prepare.chmod(0o755)
        commands=root/'commands';commands.mkdir()
        findmnt=commands/'findmnt';findmnt.write_text('#!/bin/sh\necho tmpfs\n');findmnt.chmod(0o755)
        native=root/'native.sh';native.write_text('#!/bin/sh\ntouch "'+str(root/'native-started')+'"\n');native.chmod(0o755)
        source=(source_root/'bin'/('portable-'+app)).read_text()
        source=re.sub(r"/usr/bin/python3 -I -c '[^\n]*'", '/usr/bin/true', source, count=1)
        source=source.replace('/usr/local/bin/portable-download-prepare',str(prepare)).replace('/mnt/private',str(private))
        source=source.replace('/usr/local/share/portable/transmission-defaults.json',str(source_root/'share/portable/transmission-defaults.json'))
        source=source.replace('/usr/bin/transmission-gtk.portable-real','/bin/sh '+str(native)).replace('/usr/bin/pan.portable-real','/bin/sh '+str(native)).replace('/usr/bin/amule.portable-real','/bin/sh '+str(native))
        source=source.replace('/home/Petal',str(home))
        script=root/'wrapper';script.write_text(source)
        environment={**os.environ,'HOME':str(home),'PATH':str(commands)+':/usr/bin:/bin'}
        def run(block=False):
            return subprocess.run(['/bin/bash',str(script),'--prepare'],env={**environment,'FAKE_BLOCK':str(int(block))},
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10).returncode
        assert run()==0 and not (root/'native-started').exists()
        if app=='transmission':
            file=state/'settings.json';value=json.loads(file.read_text());value['cache-size-mb']=17;file.write_text(json.dumps(value))
        elif app=='pan':
            file=state/'preferences.xml';file.write_text('<preferences><int name="cache-size-megs" value="17"/></preferences>')
            for name in ('article-cache','encode-cache'):
                assert (state/name).resolve()==home/'.cache/portable-pan'/name
                (state/name).unlink()
                (state/name).symlink_to('/home/user/.cache/portable-pan/'+name)
            assert run()==0
            for name in ('article-cache','encode-cache'):
                assert (state/name).resolve()==home/'.cache/portable-pan'/name
            (state/'article-cache').unlink()
            (state/'article-cache').symlink_to('/home/other/.cache/portable-pan/article-cache')
            assert run()!=0
            (state/'article-cache').unlink()
            (state/'article-cache').symlink_to(home/'.cache/portable-pan/article-cache')
            print('PASS: Pan migrates known legacy RAM cache links and rejects unrelated links')
        else:
            file=state/'amule.conf';value=configparser.ConfigParser(interpolation=None);value.optionxform=str;value.read(file)
            value.set('eMule','Nick','disposable-test')
            with file.open('w') as output:value.write(output)
        before=file.read_text()
        assert run()==0
        if app=='amule':
            value.read(file);assert value.get('eMule','Nick')=='disposable-test' and value.get('eMule','NewVersionCheck')=='0'
        else:
            assert file.read_text()==before
        assert run(block=True)!=0 and not (root/'native-started').exists()
        print('PASS: '+app+' prepares encrypted state, retains overrides, refuses failed guard and does not start native app')
