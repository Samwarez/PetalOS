#!/usr/bin/python3
"""Build a small static initramfs helper; never touch media or host packages."""
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).with_name('unlock-pair.c')
OUTPUT = ROOT/'config/includes.chroot/usr/local/share/portable/native-split-unlock'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-static','-fstack-protector-strong',
           '-D_FORTIFY_SOURCE=2','-Wl,-z,relro,-z,now,-z,noexecstack']
    with tempfile.TemporaryDirectory(prefix='petalos-pair-build-') as temporary:
        target=Path(temporary)/'portable-unlock-pair'
        subprocess.run(['gcc',*flags,str(SOURCE),'-o',str(target)],check=True)
        import shutil
        shutil.copyfile(target,OUTPUT/target.name)
        (OUTPUT/target.name).chmod(0o755)
    record={'format':1,'source_sha256':digest(SOURCE),'builder_sha256':digest(Path(__file__)),
            'binary_sha256':digest(OUTPUT/'portable-unlock-pair'),'flags':flags}
    (OUTPUT/'provenance.json').write_text(json.dumps(record,indent=2)+'\n')
    print('Built static dual-volume unlock helper.')


if __name__=='__main__':main()
