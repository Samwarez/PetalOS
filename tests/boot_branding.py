"""Offline-only GRUB artwork staging; never opens or discovers a device."""
from pathlib import Path
import hashlib
import json
import os
import re
import tempfile

NAMES=('grub.png','theme.txt','unicode.pf2')
BEGIN='# PetalOS graphics begin\n'
END='# PetalOS graphics end\n'


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def verified(source):
    source=Path(source)
    if not source.is_dir():return None
    release=source.parents[4]
    manifest=json.loads((release/'manifest.json').read_text())
    hashes={}
    for name in NAMES:
        p=source/name;assert not p.is_symlink() and p.is_file() and p.stat().st_size<=8*1024**2
        relative=str(p.relative_to(release/'build'))
        assert digest(p)==manifest[relative]['sha256']
        hashes[name]=manifest[relative]['sha256']
    key=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()[:24]
    return source,hashes,key


def block(prefix):
    assert re.fullmatch(r'/(?:boot/grub/petalos|petalos/branding/[a-f0-9]{24})',prefix)
    return BEGIN+f'''set menu_color_normal=light-magenta/black
set menu_color_highlight=white/magenta
if loadfont {prefix}/unicode.pf2; then
    set gfxmode=auto
    set gfxpayload=keep
    insmod all_video
    insmod gfxterm
    insmod png
    terminal_output gfxterm
    set theme={prefix}/theme.txt
    export theme
fi
'''+END


def rewrite(content,prefix):
    assert content.count(BEGIN)==content.count(END) and content.count(BEGIN)<=1
    if BEGIN in content:
        before,rest=content.split(BEGIN);_,after=rest.split(END)
        content=before+after
    lines=[]
    for line in content.splitlines():
        words=line.split()
        if words and words[0] in ('linux','linuxefi') and 'boot=live' in words and 'nosplash' not in words:
            words+=[w for w in ('quiet','splash') if w not in words]
            line='    '+' '.join(words)
        lines.append(line)
    # Keep the updater's rollback entry trailing so its bounded-retention
    # parser still recognizes it on the next update. Override theme setup
    # immediately before the first menu entry.
    index=next(i for i,line in enumerate(lines) if line.lstrip().startswith(('menuentry ','submenu ')))
    return '\n'.join(lines[:index]).rstrip()+'\n'+block(prefix)+'\n'.join(lines[index:]).rstrip()+'\n'


def install(boot, spec, configs, *, identity=lambda:None):
    source,hashes,key=spec;boot=Path(boot);installed={}
    def checked(path,root,*,directory=False):
        assert path.resolve(strict=True).is_relative_to(root.resolve(strict=True))
        assert not any(p.is_symlink() for p in (path,*path.parents))
        info=path.stat();assert info.st_uid==os.geteuid() and not info.st_mode & 0o022
        assert path.is_dir() if directory else path.is_file()
    def sync_directory(path):
        fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)
    destination=boot/'petalos/branding'/key
    def directory(path):
        if path!=boot:directory(path.parent)
        identity();path.mkdir(mode=0o755,exist_ok=True);checked(path,boot,directory=True)
    directory(destination)
    def write(path,data,expected):
        identity();checked(path.parent,boot,directory=True)
        fd,name=tempfile.mkstemp(prefix='.petalos-branding-',dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as output:
                output.write(data);output.flush();os.fsync(output.fileno());os.fchmod(output.fileno(),0o644)
            assert digest(Path(name))==expected
            identity();os.replace(name,path);sync_directory(path.parent)
            installed[path]=expected
        finally:Path(name).unlink(missing_ok=True)
    for name,sha in hashes.items():
        path=destination/name
        if path.exists() or path.is_symlink():
            checked(path,boot);assert digest(path)==sha
            installed[path]=sha
        else:
            assert digest(source/name)==sha
            write(path,(source/name).read_bytes(),sha)
    prefix='/petalos/branding/'+key
    for path,_ in configs:
        checked(path,boot)
        data=rewrite(path.read_text(),prefix).encode()
        write(path,data,hashlib.sha256(data).hexdigest())
    return installed
