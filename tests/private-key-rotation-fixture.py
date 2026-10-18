#!/usr/bin/python3 -I
"""Public RAM fixture proving old-header limitations and fresh-key isolation."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

def main():
    assert os.geteuid()==0
    assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
    root=Path(tempfile.mkdtemp(prefix='petalos-key-fixture-',dir='/run'));root.chmod(0o700)
    mapped=[];names=('petal_key_fixture_original','petal_key_fixture_fresh','petal_key_fixture_attack')
    assert all(not (Path('/dev/mapper')/name).exists() for name in names)
    def run(args):return subprocess.run(args,capture_output=True,check=True,timeout=45)
    def accepts(image,key,header=None):
        args=['cryptsetup','open','--test-passphrase','--key-file',str(key)]
        if header:args+=['--header',str(header)]
        r=subprocess.run([*args,str(image)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=45)
        assert r.returncode in (0,2);return r.returncode==0
    def open_map(image,key,name,header=None):
        args=['cryptsetup','open','--key-file',str(key)]
        if header:args+=['--header',str(header),'--readonly']
        run([*args,str(image),name]);mapped.append(name)
        path=Path('/dev/mapper')/name;info=path.stat()
        slaves=list(Path(f'/sys/dev/block/{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}/slaves').iterdir())
        assert len(slaves)==1 and slaves[0].name.startswith('loop')
        backing=Path('/sys/class/block')/slaves[0].name/'loop/backing_file'
        assert Path(backing.read_text().strip()).resolve()==image.resolve()
        return path
    try:
        legacy=root/'synthetic-legacy';human=root/'synthetic-human'
        for key in (legacy,human):key.write_bytes(os.urandom(64));key.chmod(0o600)
        original=root/'original.img';fresh=root/'fresh.img'
        for image in (original,fresh):
            with image.open('xb') as stream:stream.truncate(64*1024**2)
        # Reduced KDF cost belongs only to this disposable synthetic fixture.
        def format(image,key):
            run(['cryptsetup','luksFormat','--batch-mode','--type','luks2','--offset','32768',
                 '--pbkdf','pbkdf2','--pbkdf-force-iterations','1000','--key-file',str(key),str(image)])
        format(original,legacy)
        run(['cryptsetup','luksAddKey','--key-file',str(legacy),'--key-slot','1',
             '--pbkdf','pbkdf2','--pbkdf-force-iterations','1000',str(original),str(human)])
        header=root/'synthetic-header'
        run(['cryptsetup','luksHeaderBackup','--header-backup-file',str(header),str(original)])
        slots=json.loads(run(['cryptsetup','luksDump','--dump-json-metadata',str(original)]).stdout)['keyslots']
        assert set(slots)=={'0','1'} and accepts(original,legacy) and accepts(original,human)
        run(['cryptsetup','luksKillSlot','--key-file',str(human),str(original),'0'])
        assert not accepts(original,legacy) and accepts(original,human)
        assert accepts(original,legacy,header)
        print('PASS: slot removal rejects old key against new header; old header still accepts it.')
        old=open_map(original,human,names[0]);marker=b'PetalOS public encryption fixture'.ljust(4096,b'!')
        with old.open('r+b',buffering=0) as stream:assert stream.write(marker)==len(marker);os.fsync(stream.fileno())
        format(fresh,human);new=open_map(fresh,human,names[1])
        with new.open('r+b',buffering=0) as stream:assert stream.write(marker)==len(marker);os.fsync(stream.fileno())
        attack=open_map(fresh,legacy,names[2],header)
        with attack.open('rb') as stream:assert stream.read(len(marker))!=marker
        with new.open('rb') as stream:assert stream.read(len(marker))==marker
        assert accepts(fresh,human) and not accepts(fresh,legacy)
        print('PASS: old header/key cannot read new ciphertext; correct fresh key reads public marker.')
    finally:
        for name in reversed(mapped):run(['cryptsetup','close',name])
        shutil.rmtree(root)
    print('Synthetic RAM fixture mappings/files removed; real volumes untouched.')

if __name__=='__main__':main()
