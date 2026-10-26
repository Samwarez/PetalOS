"""Stage complete OS generations before changing any boot configuration.

Device identity, backup and encryption checks belong to the calling updater.
This module never discovers, opens or mounts a device. It also supports isolated
directory fixtures for interruption/retry tests.
"""
from pathlib import Path
import hashlib
import fcntl
import json
import os
import re
import tempfile


class InsufficientGenerationSpace(RuntimeError):
    """A public, credential-free explanation suitable for updater dialogs."""


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked(path, root, *, directory=False):
    assert path.resolve(strict=True).is_relative_to(root.resolve(strict=True))
    assert not any(p.is_symlink() for p in (path, *path.parents))
    info=path.stat()
    assert info.st_uid==os.geteuid() and not info.st_mode & 0o022
    assert path.is_dir() if directory else path.is_file()


def sync_directory(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


PREVIOUS = re.compile(r"\nmenuentry 'PetalOS previous release' \{\n    configfile (/petalos/rollback/[a-f0-9]{64}\.cfg)\n\}\n?$")


def without_previous(content):
    """Recognize only the updater's own trailing submenu, never arbitrary GRUB."""
    while match:=PREVIOUS.search(content):
        content=content[:match.start()].rstrip()+'\n'
    assert "menuentry 'PetalOS previous release'" not in content, 'Unrecognized rollback entry; refusing automatic retirement.'
    return content


def selected_release(content):
    kernels=[];initrds=[];live=[]
    for line in without_previous(content).splitlines():
        words=line.split()
        if words and words[0] in ('linux','linuxefi'):
            assert re.fullmatch(r'/(?:live/|petalos/releases/[a-f0-9]{24}/)?vmlinuz',words[1])
            kernels.append(words[1])
            paths=[w.split('=',1)[1] for w in words if w.startswith('live-media-path=')]
            assert len(paths)<=1
            live.append(paths[0] if paths else '/live')
        elif words and words[0] in ('initrd','initrdefi'):
            assert len(words)==2
            initrds.append(words[1])
    assert kernels and len(kernels)==len(initrds)==len(live)
    versions=set()
    for kernel,initrd,path in zip(kernels,initrds,live):
        assert initrd==kernel.removesuffix('vmlinuz')+'initrd.img'
        match=re.fullmatch(r'/petalos/releases/([a-f0-9]{24})/vmlinuz',kernel)
        version=match[1] if match else 'legacy'
        assert path==('/live' if version=='legacy' else '/petalos/releases/'+version+'/live')
        versions.add(version)
    assert len(versions)==1, 'A selector mixes OS generations.'
    return versions.pop()


def previous_content(boot, content):
    match=PREVIOUS.search(content)
    if not match:return None
    path=boot/match[1].lstrip('/');checked(path,boot)
    data=path.read_bytes()
    assert hashlib.sha256(data).hexdigest()==path.stem
    return without_previous(data.decode())


def generation_files(root, version, *, system):
    """Validate the complete deletion boundary before unlinking any file."""
    base=root/'petalos/releases'/version;checked(base,root,directory=True)
    manifest=base/'generation.json'
    if not manifest.exists() and not manifest.is_symlink():
        # Power loss between the final unlink and rmdir leaves only empty dirs.
        entries=list(base.iterdir())
        if entries==[]:return [],[base],None
        live=base/'live'
        assert entries==[live] and system
        checked(live,root,directory=True);assert not list(live.iterdir())
        return [],[live,base],None
    checked(manifest,root)
    data=manifest.read_bytes();metadata=json.loads(data)
    assert hashlib.sha256(data).hexdigest()[:24]==version
    assert metadata['format']==1 and set(metadata)=={'format','os','modules'}
    assert set(metadata['os'])=={'vmlinuz','initrd.img','filesystem.squashfs'}
    assert all(re.fullmatch(r'[a-f0-9]{64}',value) for value in metadata['os'].values())
    assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*\.squashfs',name) and
               name!='filesystem.squashfs' and re.fullmatch(r'[a-f0-9]{64}',value)
               for name,value in metadata['modules'].items())
    directories=[base];files=[]
    expected={manifest}
    if system:
        live=base/'live';checked(live,root,directory=True);directories.insert(0,live)
        expected.update(live/name for name in ['filesystem.squashfs','filesystem.module',*metadata['modules']])
    else:expected.update(base/name for name in ('vmlinuz','initrd.img'))
    # Interrupted generations may lack payloads, but never contain unknown files.
    for directory in directories:
        for path in directory.iterdir():
            if path in directories:continue
            assert path in expected or path.name.startswith('.petalos-partial-'), 'Unknown generation content.'
            checked(path,root);assert path.stat().st_nlink==1
            if path!=manifest:files.append(path)
    return files+[manifest],directories,metadata


def verify_selected(boot, system, configs):
    """An existing manifest is checked against bytes, not a success marker."""
    versions={selected_release(content) for _,content in configs}
    for version in versions:
        if version=='legacy':
            checked(system/'live/filesystem.squashfs',system)
            for _,content in configs:
                if selected_release(content)!='legacy':continue
                for line in without_previous(content).splitlines():
                    words=line.split()
                    if words and words[0] in ('linux','linuxefi','initrd','initrdefi'):
                        checked(boot/words[1].lstrip('/'),boot)
            continue
        _,_,meta=generation_files(system,version,system=True)
        _,_,bootmeta=generation_files(boot,version,system=False)
        assert meta is not None and meta==bootmeta
        prefix=Path('petalos/releases')/version
        for name,value in meta['os'].items():
            path=system/prefix/'live'/name if name=='filesystem.squashfs' else boot/prefix/name
            checked(path,system if name=='filesystem.squashfs' else boot)
            assert digest(path)==value, 'Selected generation failed verification; retirement refused.'
        live=system/prefix/'live'
        selection=(live/'filesystem.module').read_text().split()
        assert selection[0]=='filesystem.squashfs' and len(selection)==len(set(selection))
        assert set(selection)=={'filesystem.squashfs',*meta['modules']}
        for name,value in meta['modules'].items():assert digest(live/name)==value
    return versions


def retire_unselected(boot, system, configs, keep, *, identity, checkpoint, drop_previous=False):
    """Only known OS payloads/configs; never state, credentials, EFI or backups."""
    assert verify_selected(boot,system,configs)<=keep
    changes=[];deletions=[];directories=[];references=set()
    for target,content in configs:
        checked(target,boot);assert target.read_text()==content
        match=PREVIOUS.search(content)
        if drop_previous:
            clean=without_previous(content)
            if clean!=content:changes.append((target,clean))
        elif match:
            previous=previous_content(boot,content)
            assert selected_release(previous) in keep
            assert not PREVIOUS.search(previous), 'Nested rollback chain must be flattened.'
            references.add(boot/match[1].lstrip('/'))
    for root in (boot,system):
        parent=root/'petalos/releases'
        if not parent.exists():continue
        checked(parent,root,directory=True)
        for base in sorted(parent.iterdir()):
            assert re.fullmatch(r'[a-f0-9]{24}',base.name), 'Unknown release directory.'
            if base.name in keep:continue
            files,dirs,_=generation_files(root,base.name,system=root==system)
            deletions.extend((root,p) for p in files);directories.extend(dirs)
    if 'legacy' not in keep:
        for root,relative in ((system,'live/filesystem.squashfs'),(boot,'live/vmlinuz'),
                              (boot,'live/initrd.img'),(boot,'vmlinuz'),(boot,'initrd.img')):
            path=root/relative
            if path.exists() or path.is_symlink():
                checked(path,root);assert path.stat().st_nlink==1;deletions.append((root,path))
    rollback=boot/'petalos/rollback'
    if rollback.exists():
        checked(rollback,boot,directory=True)
        for path in rollback.iterdir():
            checked(path,boot);assert path.stat().st_nlink==1
            if path.name.startswith('.petalos-partial-'):
                deletions.append((boot,path));continue
            assert re.fullmatch(r'[a-f0-9]{64}\.cfg',path.name)
            assert digest(path)==path.stem
            if path not in references:deletions.append((boot,path))
    # Remove menu references first. An interruption always leaves the active OS.
    for target,content in changes:
        identity()
        fd,name=tempfile.mkstemp(prefix='.petalos-partial-',dir=target.parent)
        temporary=Path(name)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(content.encode());stream.flush();os.fsync(stream.fileno());os.fchmod(stream.fileno(),0o644)
            identity();os.replace(temporary,target);sync_directory(target.parent)
        finally:temporary.unlink(missing_ok=True)
        checkpoint('retired-rollback-selector')
    for root,path in deletions:
        identity();checked(path,root);path.unlink();sync_directory(path.parent)
        checkpoint('retired-os-file')
    for path in directories:
        identity();path.rmdir();sync_directory(path.parent)
    checkpoint('retention-complete')
    return [(path,path.read_text()) for path,_ in configs]


def rewrite_config(content, generation, rollback):
    """Every kernel/initrd pair selects the matching SYSTEM live directory."""
    lines=[];kernels=0;initrds=0;unchanged=True
    prefix='/petalos/releases/'+generation
    for line in content.splitlines():
        words=line.split()
        if words and words[0] in ('linux','linuxefi'):
            assert re.fullmatch(r'/(?:live/|petalos/releases/[a-f0-9]{24}/)?vmlinuz',words[1])
            assert ('live-media=/dev/mapper/portable_system' in words or
                    {'live-media=/dev/mapper/portable_os', 'petalos.layout=2'} <= set(words))
            unchanged &= words[1]==prefix+'/vmlinuz' and 'live-media-path='+prefix+'/live' in words
            words[1]=prefix+'/vmlinuz'
            words=[w for w in words if not w.startswith('live-media-path=')]
            words.append('live-media-path='+prefix+'/live')
            line='    '+' '.join(words);kernels+=1
        elif words and words[0] in ('initrd','initrdefi'):
            assert len(words)==2 and re.fullmatch(r'/(?:live/|petalos/releases/[a-f0-9]{24}/)?initrd.img',words[1])
            unchanged &= words[1]==prefix+'/initrd.img'
            line='    '+words[0]+' '+prefix+'/initrd.img';initrds+=1
        lines.append(line)
    assert kernels and kernels==initrds
    if unchanged:return content
    if rollback:lines+=['',"menuentry 'PetalOS previous release' {",'    configfile '+rollback,'}']
    return '\n'.join(lines)+'\n'


def stage_and_activate(boot, system, sources, hashes, configs, modules, *, identity=lambda:None, checkpoint=lambda _:None, retention='test', module_sources=None, module_hashes=None):
    assert retention in ('preserve','test','production')
    branding=None
    branding_source=Path(sources['vmlinuz']).parent.parent/'boot/grub/petalos'
    if branding_source.is_dir():
        import importlib.util
        spec=importlib.util.spec_from_file_location('petalos_boot_branding',Path(__file__).with_name('boot_branding.py'))
        boot_branding=importlib.util.module_from_spec(spec);spec.loader.exec_module(boot_branding)
        branding=boot_branding.verified(branding_source)
    system=Path(system);checked(system,system,directory=True);identity()
    parent=system/'petalos';parent.mkdir(mode=0o755,exist_ok=True);checked(parent,system,directory=True)
    fd=os.open(parent/'update.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'r+b') as lock:
        checked(parent/'update.lock',system)
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        generation,installed=_stage_and_activate(boot,system,sources,hashes,configs,modules,identity=identity,checkpoint=checkpoint,retention=retention,module_sources=module_sources,module_hashes=module_hashes)
        if branding is not None:
            installed.update(boot_branding.install(boot,branding,configs,identity=identity))
            checkpoint('branding-installed')
        return generation,installed


def _stage_and_activate(boot, system, sources, hashes, configs, modules, *, identity, checkpoint, retention, module_sources=None, module_hashes=None):
    """Return verified installed paths; interrupted staging may be retried.

    Existing generation payloads are immutable. Each config activation is one
    replacement: until then its old kernel, initrd and live directory remain
    selected. Test retention keeps at most one previous release; production
    keeps none after successful activation. Preserve mode is for old fixtures.
    """
    boot,system=Path(boot),Path(system)
    assert not boot.resolve().is_relative_to(system.resolve()) and not system.resolve().is_relative_to(boot.resolve())
    assert set(sources)==set(hashes)=={'vmlinuz','initrd.img','filesystem.squashfs'}
    assert modules and modules[0]=='filesystem.squashfs' and len(set(modules))==len(modules)
    assert all(re.fullmatch(r'[A-Za-z0-9._-]+\.squashfs',n) and not n.startswith('.') for n in modules)
    assert configs, 'No boot selectors supplied.'
    for name in sources:
        assert digest(sources[name])==hashes[name]
    metadata={'format':1,'os':hashes,'modules':{}}
    if module_sources is not None:
        assert set(module_sources)==set(modules[1:])
        assert module_hashes is not None and set(module_hashes)==set(module_sources)
    def module_source(name):
        return Path(module_sources[name]) if module_sources is not None else system/'live'/name
    for name in modules[1:]:
        source=module_source(name)
        if module_sources is None:checked(source,system)
        metadata['modules'][name]=digest(source)
        if module_hashes is not None:assert metadata['modules'][name]==module_hashes[name]
    encoded=json.dumps(metadata,sort_keys=True,separators=(',',':')).encode()
    generation=hashlib.sha256(encoded).hexdigest()[:24]
    prefix=Path('petalos/releases')/generation
    installed={}
    previous={}
    if retention!='preserve':
        assert all(not Path(path).resolve().is_relative_to(root.resolve())
                   for path in sources.values() for root in (boot,system)), 'Use independent build inputs for offline replacement.'
        for target,content in configs:
            checked(target,boot);assert target.read_text()==content
            old=without_previous(content) if selected_release(content)!=generation else previous_content(boot,content)
            if old is not None:previous[target]=old
        active=verify_selected(boot,system,configs)
        old_versions={selected_release(content) for content in previous.values()}-{generation}
        assert len(old_versions)<=1, 'Ambiguous previous releases; manual review required.'
        # A partially activated update may select two generations. Keep both
        # until every selector has moved to the verified replacement.
        keep=active|{generation}
        if retention=='test' and active=={generation}:keep|=old_versions
        configs=retire_unselected(boot,system,configs,keep,identity=identity,checkpoint=checkpoint,drop_previous=True)
    # Count only missing payloads: retrying a fully staged release must work
    # without requiring a second copy. Keep room for metadata and settings.
    capacities=[('boot',boot,[(sources[n],boot/prefix/n,hashes[n]) for n in ('vmlinuz','initrd.img')]),
                ('SYSTEM',system,[(sources['filesystem.squashfs'],system/prefix/'live/filesystem.squashfs',hashes['filesystem.squashfs'])]+
                 [(module_source(n),system/prefix/'live'/n,metadata['modules'][n]) for n in modules[1:]])]
    for label,root,payloads in capacities:
        needed=16*1024**2
        for source,target,expected in payloads:
            if target.exists() or target.is_symlink():
                checked(target,root)
                assert digest(target)==expected,'Existing generation payload differs; refusing overwrite.'
            else:needed+=((source.stat().st_size+4095)//4096)*4096
        fs=os.statvfs(root);available=fs.f_bavail*fs.f_frsize
        if available<needed:
            raise InsufficientGenerationSpace(
                f'Insufficient {label} space: {needed} bytes required, {available} available. '+
                ('Previous releases and boot selection were preserved. Move or explicitly retire an old release before retrying.'
                 if retention=='preserve' else 'The active release was preserved; older rollback files may have been retired. More space is required.'))

    def directory(path,root):
        identity()
        if path!=root:directory(path.parent,root)
        path.mkdir(mode=0o755,exist_ok=True);checked(path,root,directory=True)
        sync_directory(path.parent)

    def copy(source,target,expected,*,replace=False):
        identity();checked(target.parent,boot if target.is_relative_to(boot) else system,directory=True)
        if target.exists() or target.is_symlink():
            checked(target,boot if target.is_relative_to(boot) else system)
            if digest(target)==expected:
                installed[target]=expected;return
            assert replace,'Existing generation payload differs; refusing overwrite.'
        fd,name=tempfile.mkstemp(prefix='.petalos-partial-',dir=target.parent)
        temporary=Path(name)
        try:
            with os.fdopen(fd,'wb') as output,source.open('rb') as input_file:
                count=0
                while chunk:=input_file.read(4*1024**2):
                    output.write(chunk);count+=len(chunk)
                    if count % (64*1024**2)==0:
                        output.flush();os.fsync(output.fileno());identity()
                output.flush();os.fsync(output.fileno());os.fchmod(output.fileno(),0o644)
            assert digest(temporary)==expected
            identity();os.replace(temporary,target);sync_directory(target.parent)
            installed[target]=expected
        finally:temporary.unlink(missing_ok=True)

    def public_bytes(data,target,*,replace=False):
        fd,name=tempfile.mkstemp(prefix='petalos-public-generation-')
        source=Path(name)
        try:
            with os.fdopen(fd,'wb') as f:f.write(data)
            copy(source,target,hashlib.sha256(data).hexdigest(),replace=replace)
        finally:source.unlink()

    # Reject unsafe configs and calculate all new references before staging.
    plans=[]
    for target,content in configs:
        checked(target,boot)
        old=target.read_bytes();assert old.decode()==content
        prior=previous.get(target) if retention!='preserve' else content
        if retention=='production':prior=None
        backup=Path('petalos/rollback')/(hashlib.sha256(prior.encode()).hexdigest()+'.cfg') if prior is not None else None
        updated=rewrite_config(content,generation,None if backup is None else '/'+str(backup))
        # An idempotent update may still need its retained previous menu.
        if backup is not None and not PREVIOUS.search(updated):
            updated=updated.rstrip()+"\n\nmenuentry 'PetalOS previous release' {\n    configfile /"+str(backup)+"\n}\n"
        plans.append((target,prior.encode() if prior is not None else None,backup,updated.encode()))
    assert plans
    for root,relative in ((boot,prefix),(system,prefix/'live'),(boot,Path('petalos/rollback'))):
        directory(root/relative,root)
    # Reclaim only this generator's interrupted temporary files, under its
    # exclusive update lock. No previous release or settings are deleted.
    for root,relative in ((boot,prefix),(system,prefix),(system,prefix/'live'),(boot,Path('petalos/rollback'))):
        for temporary in (root/relative).glob('.petalos-partial-*'):
            checked(temporary,root)
            assert temporary.stat().st_nlink==1
            identity();temporary.unlink()
    # A matching manifest makes a partially staged generation resumable. Never
    # infer completeness from directory existence or a stale success marker.
    for root in (boot,system):
        public_bytes(encoded,root/prefix/'generation.json')
    checkpoint('generation-directories')
    for name,root,relative in (('vmlinuz',boot,prefix/'vmlinuz'),
                               ('initrd.img',boot,prefix/'initrd.img'),
                               ('filesystem.squashfs',system,prefix/'live/filesystem.squashfs')):
        copy(sources[name],root/relative,hashes[name]);checkpoint('staged-'+name)
    for name in modules[1:]:
        copy(module_source(name),system/prefix/'live'/name,metadata['modules'][name])
    public_bytes(('\n'.join(modules)+'\n').encode(),system/prefix/'live/filesystem.module')
    for _,old,relative,content in plans:
        if old is not None and content!=old:public_bytes(old,boot/relative)
    for target,expected in installed.items():assert digest(target)==expected
    sync_directory(boot/prefix);sync_directory(system/prefix/'live')
    checkpoint('complete-generation-verified')
    for number,(target,_,_,content) in enumerate(plans):
        public_bytes(content,target,replace=True)
        checkpoint('activated-config-'+str(number))
    for target,expected in installed.items():assert digest(target)==expected
    if retention!='preserve':
        keep={generation}
        if retention=='test':keep|={selected_release(content) for content in previous.values()}
        retire_unselected(boot,system,[(target,target.read_text()) for target,_ in configs],keep,
                          identity=identity,checkpoint=checkpoint)
        # Deleted temporary rollback files are not final readback targets.
        installed={path:value for path,value in installed.items() if path.exists()}
    return generation,installed
