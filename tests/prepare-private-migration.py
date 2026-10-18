#!/usr/bin/env python3
"""Preserve the current disk and migrate only a newly registered QEMU clone."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

PROJECT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',required=True,type=Path)
    parser.add_argument('--verify-existing-copy',action='store_true')
    args=parser.parse_args()
    assert os.geteuid()!=0
    runtime=Path(f'/run/user/{os.getuid()}');statefile=runtime/'petalos-encrypted-test.json'
    prior=json.loads(statefile.read_text());image=Path(prior['image'])
    assert prior['phase']=='ready-for-encrypted-boot' and prior['ssh']['user']=='Petal'
    assert not image.is_symlink() and image.is_file() and image.stat().st_size==16*1024**3
    assert image.resolve().is_relative_to((PROJECT.parent/'testing/sessions').resolve())
    module=args.module
    assert not module.is_symlink() and module.name=='petalos-wayland-test-v5.squashfs'
    assert module.resolve().is_relative_to(image.parent.resolve())
    manifest=json.loads((module.parent/'manifest.json').read_text())
    assert manifest['source_image']==str(image) and hashlib.sha256(module.read_bytes()).hexdigest()==manifest['module_sha256']
    with (runtime/'petalos-qemu.lock').open('a') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert not (runtime/'petalos-qemu-monitor.sock').exists(),'Shut down QEMU first.'
        assert subprocess.run(['fuser',str(image)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==1
        for backing in Path('/sys/block').glob('loop*/loop/backing_file'):
            assert Path(backing.read_text().strip()).resolve()!=image.resolve()
        transfer=runtime/'petalos-private-migration.json'
        if args.verify_existing_copy:
            candidate=json.loads(transfer.read_text())
            assert candidate['phase']=='failed' and candidate['source']==str(image) and candidate['module']==str(module)
            clone=Path(candidate['clone']);assert clone.parent==image.parent and not clone.is_symlink() and clone.is_file()
            assert clone.stat().st_size==16*1024**3 and clone.stat().st_uid==os.getuid()
            firmware=clone.with_name(clone.name.replace('encrypted-boot-','encrypted-OVMF-').replace('.img','.fd'))
            assert firmware.is_file() and not firmware.is_symlink()
        else:
            stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            clone=image.parent/f'encrypted-boot-{stamp}.img';firmware=image.parent/f'encrypted-OVMF-{stamp}.fd'
            assert not clone.exists() and not firmware.exists()
            candidate={'phase':'cloning','source':str(image),'clone':str(clone),'module':str(module)}
        def update(phase):
            candidate['phase']=phase
            temp=transfer.with_suffix('.tmp');temp.write_text(json.dumps(candidate,indent=2));temp.replace(transfer)
        if not args.verify_existing_copy:
            update('cloning')
            subprocess.run(['qemu-img','convert','-f','raw','-O','raw','-S','4k',str(image),str(clone)],check=True)
            shutil.copy2(prior['firmware'],firmware)
        update('awaiting-authentication')
        print('Verification only: enter host sudo, existing SYSTEM, and the SAME NEW Private passphrase chosen previously, twice. No DATA formatting or rewriting.' if args.verify_existing_copy else 'Working disk preserved. This terminal needs host sudo, existing SYSTEM passphrase, and a NEW distinct Private passphrase twice.',flush=True)
        try:
            subprocess.run(['sudo','--','/usr/bin/python3','-I',str(PROJECT/'tests/migrate-private-clone-root.py'),
                            str(image),str(clone),str(module),*(['--verify-existing-copy'] if args.verify_existing_copy else [])],check=True)
            state={**prior,'image':str(clone),'firmware':str(firmware),'configuration_module':str(module),
                   'private_migration':{'source':str(image),'kind':'fresh-volume-key'},
                   'ssh':{**prior['ssh'],'prior_image':str(image)}}
            temp=statefile.with_suffix('.tmp');temp.write_text(json.dumps(state,indent=2));temp.replace(statefile)
            update('complete')
            print('Fresh Private clone ready to boot. Original disk and its old passphrase remain unchanged.',flush=True)
        except BaseException:
            update('failed');raise

if __name__=='__main__':
    os.umask(0o077)
    main()
