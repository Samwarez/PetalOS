#!/usr/bin/env python3
"""Fault injection against directory fixtures; never opens any block device."""
from pathlib import Path
import importlib.util, os, tempfile, sys
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('generations',Path(__file__).with_name('release_generations.py'))
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
os.umask(0o077)
CONFIG="""set timeout=5
menuentry 'PetalOS fixture' {
 linux /live/vmlinuz boot=live toram swap=false init_on_alloc=1 init_on_free=1 live-media=/dev/mapper/portable_system
 initrd /live/initrd.img
}
"""
if sys.argv[1:] == ['--layout2']:
    CONFIG=CONFIG.replace('live-media=/dev/mapper/portable_system',
        'live-media=/dev/mapper/portable_os petalos.layout=2 '
        'petalos.os=11111111-1111-4111-8111-111111111111 '
        'petalos.system=22222222-2222-4222-8222-222222222222 '
        'petalos.private=33333333-3333-4333-8333-333333333333')
elif sys.argv[1:]:
    raise SystemExit('Usage: check-release-generations.py [--layout2]')

def fixture(base):
    boot=base/'boot';system=base/'system';source=base/'source'
    for p in (boot/'live',system/'live',source,boot/'EFI/BOOT'):p.mkdir(parents=True)
    for name in ('vmlinuz','initrd.img','filesystem.squashfs'):
        (source/name).write_bytes(('new '+name).encode())
        ((system if name=='filesystem.squashfs' else boot)/'live'/name).write_bytes(('old '+name).encode())
    (system/'live/fixture.squashfs').write_bytes(b'public management fixture')
    (system/'settings-canary').write_text('preserve settings')
    (boot/'EFI/BOOT/BOOTX64.EFI').write_bytes(b'preserve EFI fixture')
    for p in (boot/'grub.cfg',boot/'EFI/BOOT/grub.cfg'):p.write_text(CONFIG)
    return boot,system,{p.name:p for p in source.iterdir()}

def configs(boot):return [(p,p.read_text()) for p in sorted(boot.rglob('grub.cfg'))]

def consistent(boot,system):
    for _,content in configs(boot):
        kernel=initrd=live=None
        for line in content.splitlines():
            words=line.split()
            if words and words[0]=='linux':
                kernel=boot/words[1].lstrip('/')
                live=system/next((x.split('=',1)[1].lstrip('/') for x in words if x.startswith('live-media-path=')),'live')
            elif words and words[0]=='initrd':initrd=boot/words[1].lstrip('/')
        values=[kernel.read_bytes(),initrd.read_bytes(),(live/'filesystem.squashfs').read_bytes()]
        assert all(x.startswith(b'old ') for x in values) or all(x.startswith(b'new ') for x in values)
        if values[0].startswith(b'new '):
            assert (live/'filesystem.module').read_text().split()==['filesystem.squashfs','fixture.squashfs']
            assert (live/'fixture.squashfs').read_bytes()==b'public management fixture'
    assert (system/'settings-canary').read_text()=='preserve settings'

stages=('generation-directories','staged-vmlinuz','staged-initrd.img','staged-filesystem.squashfs',
        'complete-generation-verified','activated-config-0','activated-config-1')
for stopped in stages:
    with tempfile.TemporaryDirectory(prefix='petalos-generation-fixture-') as directory:
        boot,system,sources=fixture(Path(directory));hashes={n:g.digest(p) for n,p in sources.items()}
        def checkpoint(name):
            consistent(boot,system)
            if name==stopped:raise InterruptedError('public interruption fixture')
        try:g.stage_and_activate(boot,system,sources,hashes,configs(boot),['filesystem.squashfs','fixture.squashfs'],checkpoint=checkpoint)
        except InterruptedError:pass
        else:raise AssertionError('Interruption did not occur')
        consistent(boot,system)
        generation,installed=g.stage_and_activate(boot,system,sources,hashes,configs(boot),['filesystem.squashfs','fixture.squashfs'])
        consistent(boot,system)
        before=configs(boot)
        g.stage_and_activate(boot,system,sources,hashes,configs(boot),['filesystem.squashfs','fixture.squashfs'])
        assert configs(boot)==before
        assert (boot/'live/vmlinuz').read_bytes()==b'old vmlinuz'
        assert (system/'live/filesystem.squashfs').read_bytes()==b'old filesystem.squashfs'
        assert any(p.read_text()==CONFIG for p in (boot/'petalos/rollback').glob('*.cfg'))
        assert all(g.digest(p)==h for p,h in installed.items())
print('PASS seven interrupted staging/activation points retain coherent boot choices; retry, rollback and repeat work')

with tempfile.TemporaryDirectory(prefix='petalos-generation-fixture-') as directory:
    boot,system,sources=fixture(Path(directory));hashes={n:g.digest(p) for n,p in sources.items()}
    original=g.os.replace
    def failed_replace(source,target):
        if Path(target).name=='initrd.img':raise OSError('fixture interrupted write')
        original(source,target)
    with patch.object(g.os,'replace',side_effect=failed_replace):
        try:g.stage_and_activate(boot,system,sources,hashes,configs(boot),['filesystem.squashfs','fixture.squashfs'])
        except OSError:pass
        else:raise AssertionError('Write failure was ignored')
    consistent(boot,system);assert all(c==CONFIG for _,c in configs(boot))
    assert not list(boot.rglob('.petalos-partial-*'))
print('PASS interrupted payload write leaves boot selectors unchanged and removes its temporary file')

with tempfile.TemporaryDirectory(prefix='petalos-generation-fixture-') as directory:
    boot,system,sources=fixture(Path(directory));hashes={n:g.digest(p) for n,p in sources.items()}
    from types import SimpleNamespace
    with patch.object(g.os,'statvfs',return_value=SimpleNamespace(f_bavail=0,f_frsize=4096)):
        try:g.stage_and_activate(boot,system,sources,hashes,configs(boot),['filesystem.squashfs','fixture.squashfs'])
        except g.InsufficientGenerationSpace:pass
        else:raise AssertionError('Insufficient space was ignored')
    consistent(boot,system);assert all(c==CONFIG for _,c in configs(boot))
    assert not (boot/'petalos/releases').exists() and not (system/'petalos/releases').exists()
print('PASS insufficient capacity refuses before payload staging or boot activation')

# Retention tests use ordinary directories and disposable public canaries only.
def update(boot,system,sources,label,*,retention='test',checkpoint=lambda _:None):
    for name,path in sources.items():path.write_bytes(('new '+label+' '+name).encode())
    return g.stage_and_activate(boot,system,sources,{n:g.digest(p) for n,p in sources.items()},
        configs(boot),['filesystem.squashfs','fixture.squashfs'],retention=retention,checkpoint=checkpoint)


def assert_retained(boot,system,expected,*,previous):
    for root in (boot,system):
        parent=root/'petalos/releases'
        actual={p.name for p in parent.iterdir()} if parent.exists() else set()
        assert actual==expected-{'legacy'},(actual,expected)
    assert (system/'live/filesystem.squashfs').exists()==('legacy' in expected)
    for _,content in configs(boot):
        prior=g.previous_content(boot,content)
        assert (prior is not None)==previous
        if prior is not None:
            assert not g.PREVIOUS.search(prior)
            assert g.selected_release(prior) in expected
    assert (system/'live/fixture.squashfs').read_bytes()==b'public management fixture'
    assert (boot/'EFI/BOOT/BOOTX64.EFI').read_bytes()==b'preserve EFI fixture'
    consistent(boot,system)


with tempfile.TemporaryDirectory(prefix='petalos-retention-fixture-') as directory:
    boot,system,sources=fixture(Path(directory))
    a,_=update(boot,system,sources,'A')
    assert_retained(boot,system,{'legacy',a},previous=True)
    b,_=update(boot,system,sources,'B')
    assert_retained(boot,system,{a,b},previous=True)
    before=configs(boot)
    update(boot,system,sources,'B')
    assert configs(boot)==before
    assert_retained(boot,system,{a,b},previous=True)
    c,_=update(boot,system,sources,'C',retention='production')
    assert_retained(boot,system,{c},previous=False)
    assert not list((boot/'petalos/rollback').iterdir())
    update(boot,system,sources,'C',retention='production')
    assert_retained(boot,system,{c},previous=False)
print('PASS successive test builds retain only current + one previous; production retains only current; repeats are idempotent')


# Simulate a two-payload storage limit: the third build cannot stage unless
# the oldest payload is retired first. The active version must remain readable.
with tempfile.TemporaryDirectory(prefix='petalos-retention-fixture-') as directory:
    boot,system,sources=fixture(Path(directory))
    a,_=update(boot,system,sources,'A')
    from types import SimpleNamespace
    def two_payload_limit(root):
        count=len(list(system.rglob('filesystem.squashfs')))
        return SimpleNamespace(f_bavail=0 if count>=2 else 64*1024**2,f_frsize=1)
    with patch.object(g.os,'statvfs',side_effect=two_payload_limit):
        b,_=update(boot,system,sources,'B')
    assert_retained(boot,system,{a,b},previous=True)
print('PASS oldest release is retired before staging into capacity limited to two OS payloads')


# Enumerate every checkpoint through retirement, staging and activation; inject
# an interruption at each one and retry. Every active selector stays coherent.
def interrupted_update(stop=None,retention='test'):
    with tempfile.TemporaryDirectory(prefix='petalos-retention-fault-') as directory:
        boot,system,sources=fixture(Path(directory))
        update(boot,system,sources,'A');b,_=update(boot,system,sources,'B')
        events=[]
        def checkpoint(name):
            consistent(boot,system)
            events.append(name)
            if len(events)==stop:raise InterruptedError('retention fixture')
        try:c,_=update(boot,system,sources,'C',checkpoint=checkpoint,retention=retention)
        except InterruptedError:
            consistent(boot,system)
            c,_=update(boot,system,sources,'C',retention=retention)
        assert_retained(boot,system,{b,c} if retention=='test' else {c},previous=retention=='test')
        return len(events)
count=interrupted_update()
for stop in range(1,count+1):interrupted_update(stop)
print('PASS interruption/retry at all',count,'test retention/staging/activation checkpoints preserves active boot and settings')
count=interrupted_update(retention='production')
for stop in range(1,count+1):interrupted_update(stop,retention='production')
print('PASS interruption/retry at all',count,'production retirement/staging/activation checkpoints preserves active boot and settings')


for bad in ('unknown-file','symlink','corrupt-active','empty-selectors','stale-selector'):
    with tempfile.TemporaryDirectory(prefix='petalos-retention-reject-') as directory:
        base=Path(directory);boot,system,sources=fixture(base)
        a,_=update(boot,system,sources,'A');b,_=update(boot,system,sources,'B')
        outside=base/'unrelated';outside.write_bytes(b'never delete')
        if bad=='unknown-file':(system/'petalos/releases'/a/'personal-file').write_text('preserve')
        elif bad=='symlink':(system/'petalos/releases'/a/'live/filesystem.squashfs').unlink();(system/'petalos/releases'/a/'live/filesystem.squashfs').symlink_to(outside)
        elif bad=='corrupt-active':(system/'petalos/releases'/b/'live/filesystem.squashfs').write_bytes(b'corrupt')
        entries=configs(boot)
        if bad=='empty-selectors':entries=[]
        elif bad=='stale-selector':entries=[(p,c+'# stale\n') for p,c in entries]
        before=configs(boot)
        for name,path in sources.items():path.write_bytes(('new C '+name).encode())
        try:g.stage_and_activate(boot,system,sources,{n:g.digest(p) for n,p in sources.items()},
            entries,['filesystem.squashfs','fixture.squashfs'],retention='test')
        except AssertionError:pass
        else:raise AssertionError('Unsafe retirement was accepted: '+bad)
        assert configs(boot)==before
        assert outside.read_bytes()==b'never delete'
        assert (system/'petalos/releases'/a).exists()
        assert (system/'petalos/releases'/b).exists()
        assert (system/'settings-canary').read_text()=='preserve settings'
print('PASS unknown content, symlinks, corrupt active payloads, empty/stale selectors refuse before retirement')

with tempfile.TemporaryDirectory(prefix='petalos-retention-lock-') as directory:
    boot,system,sources=fixture(Path(directory));update(boot,system,sources,'A')
    before=configs(boot)
    with (system/'petalos/update.lock').open('r+b') as lock:
        g.fcntl.flock(lock,g.fcntl.LOCK_EX|g.fcntl.LOCK_NB)
        try:update(boot,system,sources,'B')
        except BlockingIOError:pass
        else:raise AssertionError('Concurrent updater was accepted')
    assert configs(boot)==before
    consistent(boot,system)
print('PASS concurrent update is refused under the existing exclusive lock')

with tempfile.TemporaryDirectory(prefix='petalos-retention-legacy-') as directory:
    boot,system,sources=fixture(Path(directory))
    update(boot,system,sources,'A',retention='preserve')
    update(boot,system,sources,'B',retention='preserve')
    c,_=update(boot,system,sources,'C',retention='preserve')
    assert all(content.count("menuentry 'PetalOS previous release'")>=2 for _,content in configs(boot))
    (boot/'petalos/rollback/.petalos-partial-fixture').write_bytes(b'interrupted public config')
    d,_=update(boot,system,sources,'D')
    assert_retained(boot,system,{c,d},previous=True)
    assert all(content.count("menuentry 'PetalOS previous release'")==1 for _,content in configs(boot))
    assert not list((boot/'petalos/rollback').glob('.petalos-partial-*'))
print('PASS legacy accumulated rollback menus/generations are bounded and public interrupted-config temporaries reclaimed')
