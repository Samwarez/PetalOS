#!/usr/bin/python3
"""Public directory fixtures only: wallpapers, supplied assets and offline GRUB."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import runpy
import sys
import tempfile
import subprocess
import shutil
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/'config/includes.chroot/usr/share'
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);obj=importlib.util.module_from_spec(spec);sys.modules[name]=obj;spec.loader.exec_module(obj);return obj
w=module('wallpapers',ROOT/'config/includes.chroot/usr/local/lib/portable/wallpapers.py')
with tempfile.TemporaryDirectory(prefix='petalos-public-wallpapers-') as temporary:
    base=Path(temporary);source=base/'seeds';target=base/'state';source.mkdir();target.mkdir(mode=0o700)
    (source/'default.png').write_bytes(b'public initial wallpaper')
    w.seed(target,source,uid=os.getuid());assert (target/'default.png').read_bytes()==b'public initial wallpaper'
    (target/'default.png').write_bytes(b'customized public wallpaper')
    w.seed(target,source,uid=os.getuid());assert (target/'default.png').read_bytes()==b'customized public wallpaper'
    (source/'additional.png').write_bytes(b'public extra wallpaper')
    with patch.object(w.os,'fsync',side_effect=OSError('public write fault')):
        try:w.seed(target,source,uid=os.getuid())
        except OSError:pass
        else:raise AssertionError('Wallpaper write fault ignored')
    assert not (target/'additional.png').exists() and not list(target.glob('.petalos-wallpaper-*'))
    w.seed(target,source,uid=os.getuid());assert (target/'additional.png').read_bytes()==b'public extra wallpaper'
    alias=base/'alias';alias.symlink_to(target,target_is_directory=True)
    try:w.seed(alias,source,uid=os.getuid())
    except OSError:pass
    else:raise AssertionError('Linked persistent seed directory accepted')
print('PASS wallpaper seed, custom-file preservation, interrupted write cleanup/retry and symlink refusal')

renderer=runpy.run_path(str(ROOT/'config/includes.chroot/usr/local/libexec/portable-wayland-wallpaper'))
with tempfile.TemporaryDirectory(prefix='petalos-public-background-') as temporary:
    p=Path(temporary);default=p/'default.png';custom=p/'custom.png';default.touch();custom.touch()
    function=renderer['command'];env=function.__globals__;env['DEFAULT']=str(default);env['FALLBACK']=str(default)
    values={};env['query']=lambda prop:values.get(prop,'')
    with patch('subprocess.run') as run:
        args=function({'eDP-1':'PanelModel'})
        assert str(default) in args
        assert run.call_args.args[0][4]=='/backdrop/screen0/monitorPanelModel/workspace0/last-image'
    values['/backdrop/screen0/monitorPanelModel/workspace0/last-image']=str(custom)
    assert str(custom) in function({'eDP-1':'PanelModel'})
    values['/backdrop/screen0/monitorPanelModel/workspace0/image-style']='0'
    assert 'solid_color' in function({'eDP-1':'PanelModel'}) and '-i' not in function({'eDP-1':'PanelModel'})
print('PASS initial XFCE folder selection, saved wallpaper override and solid-color override')

assets=json.loads((PUBLIC/'portable/branding/assets.json').read_text())
for name,sha in assets['sha256'].items():
    if name.startswith('wallpaper/'):p=PUBLIC/'backgrounds/petalos-defaults'/name.split('/',1)[1]
    elif name.startswith('boot/'):p=PUBLIC/'plymouth/themes/petalos'/name.split('/',1)[1]
    else:p=PUBLIC/'portable/branding'/name
    assert hashlib.sha256(p.read_bytes()).hexdigest()==sha
assert assets['default_wallpaper']=='04-petal-drift.png' and len(assets['sha256'])==72
print('PASS 72 supplied PNG checksums and requested default wallpaper')

with tempfile.TemporaryDirectory(prefix='petalos-public-theme-alias-') as temporary:
    base=Path(temporary);backgrounds=base/'backgrounds';lock=backgrounds/'petalos/petalos-lock.png'
    lock.parent.mkdir(parents=True);lock.write_bytes(b'public lock wallpaper')
    commands=base/'bin';commands.mkdir()
    for name,body in [('dpkg-query','printf "24.004.60-5\\n"'),('plymouth-set-default-theme','exit 0')]:
        command=commands/name;command.write_text('#!/bin/sh\n'+body+'\n');command.chmod(0o755)
    hook=(ROOT/'config/hooks/live/0993-phase2-branding.hook.chroot').read_text().split('# Integrate only')[0]
    hook=hook.replace('/usr/share/backgrounds',str(backgrounds))
    for _ in range(2):
        subprocess.run(['/bin/sh','-c',hook],env={**os.environ,'PATH':str(commands)+':'+os.environ['PATH']},check=True)
    alias=backgrounds/'petalos-wallpapers'
    assert alias.is_symlink() and os.readlink(alias)=='/mnt/system-state/Wallpapers'
    assert lock.read_bytes()==b'public lock wallpaper'
print('PASS branding hook retains existing lock wallpaper and creates persistent-library alias idempotently')

with tempfile.TemporaryDirectory(prefix='petalos-public-binary-hook-') as temporary:
    base=Path(temporary);binary=base/'binary';grub=binary/'boot/grub';grub.mkdir(parents=True)
    source=base/'config/includes.chroot/usr/share/portable/branding';source.mkdir(parents=True)
    for name in ('grub.png','theme.txt'):shutil.copyfile(PUBLIC/'portable/branding'/name,source/name)
    (grub/'unicode.pf2').write_bytes(b'public font fixture')
    (grub/'grub.cfg').write_text('menuentry "Live system" {\n linux /live/vmlinuz boot=live toram swap=false\n initrd /live/initrd.img\n}\n')
    (grub/'config.cfg').write_text('set gfxmode=800x600\nsource /boot/grub/theme.cfg\n')
    hook=ROOT/'config/hooks/live/0990-brand-boot.hook.binary'
    subprocess.run(['/usr/bin/python3','-B',str(hook)],cwd=binary,check=True)
    content=(grub/'grub.cfg').read_text()
    assert 'PetalOS RC 1' in content and ' linux /live/vmlinuz boot=live toram swap=false' in content
    assert (grub/'petalos/grub.png').read_bytes()==(source/'grub.png').read_bytes()
    assert 'set theme=/boot/grub/petalos/theme.txt' in (grub/'theme.cfg').read_text()
    subprocess.run(['/usr/bin/python3','-B',str(hook)],cwd=binary,check=True)
    assert (grub/'grub.cfg').read_text()==content
print('PASS real binary hook stages supplied artwork, retains kernel arguments and is idempotent')

import boot_branding as b
import release_generations as g
os.umask(0o077)
with tempfile.TemporaryDirectory(prefix='petalos-public-boot-theme-') as temporary:
    base=Path(temporary);boot=base/'boot';boot.mkdir();release=base/'release';source=release/'build/binary/boot/grub/petalos';source.mkdir(parents=True)
    for name in b.NAMES:(source/name).write_bytes(('public '+name).encode())
    manifest={str(p.relative_to(release/'build')):{'sha256':b.digest(p)} for p in source.iterdir()};(release/'manifest.json').write_text(json.dumps(manifest))
    config=boot/'grub.cfg';config.write_text("set timeout=5\nmenuentry 'PetalOS' {\n linux /live/vmlinuz boot=live toram swap=false live-media=/dev/mapper/portable_system\n initrd /live/initrd.img\n}\nmenuentry 'failsafe' {\n linux /live/vmlinuz boot=live nosplash toram swap=false live-media=/dev/mapper/portable_system\n initrd /live/initrd.img\n}\n")
    previous="\nmenuentry 'PetalOS previous release' {\n    configfile /petalos/rollback/"+'a'*64+".cfg\n}\n"
    config.write_text(config.read_text()+previous)
    spec=b.verified(source)
    with patch.object(b.os,'replace',side_effect=OSError('public interrupted staging')):
        try:b.install(boot,spec,[(config,config.read_text())])
        except OSError:pass
        else:raise AssertionError('Interrupted branding accepted')
    assert b.BEGIN not in config.read_text()
    installed=b.install(boot,spec,[(config,config.read_text())]);content=config.read_text()
    assert g.PREVIOUS.search(content) and previous.strip() not in g.without_previous(content)
    assert 'quiet splash' in content and 'boot=live nosplash toram' in content
    assert all(b.digest(p)==sha for p,sha in installed.items())
    b.install(boot,spec,[(config,content)]);assert config.read_text()==content
    (source/'grub.png').write_bytes(b'changed fixture')
    try:b.verified(source)
    except AssertionError:pass
    else:raise AssertionError('Corrupt branding source accepted')
print('PASS offline GRUB checksums, interruption/retry, rollback compatibility, failsafe and idempotence')
