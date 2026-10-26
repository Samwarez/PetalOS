#!/usr/bin/env python3
"""Prepare harmless boot comparisons in new regular files; never mount a device."""
from pathlib import Path
import argparse,hashlib,json,lzma,os,struct,subprocess,uuid

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--kernel-observation',action='store_true')
observation=parser.parse_args().kernel_observation

ROOT=Path('/home/sam/portable-live/testing/artifacts/tails-boot-comparison-20261019')
assert os.geteuid()!=0 and ROOT.resolve()==ROOT and ROOT.stat().st_uid==os.getuid()
def run(args,**kwargs):
    r=subprocess.run(args,capture_output=True,timeout=240,**kwargs)
    assert r.returncode==0,(Path(args[0]).name,r.stderr.decode(errors='replace')[-1200:])
    return r.stdout
def sha(p):
    with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

original=ROOT/'tails-original.img'
assert original.is_file() and not original.is_symlink()
assert sha(original)==json.loads((ROOT/'usb-download-verification.json').read_text())['sha256']
with original.open('rb') as stream:
    stream.seek(512);header=stream.read(512);assert header[:8]==b'EFI PART'
    table,count,width=struct.unpack_from('<QII',header,72)
    assert count<=256 and width==128
    stream.seek(table*512);entries=[stream.read(width) for _ in range(count)]
efi=[entry for entry in entries if entry[:16]==uuid.UUID('c12a7328-f81f-11d2-ba4b-00a0c93ec93b').bytes_le]
assert len(efi)==1
offset=struct.unpack_from('<Q',efi[0],32)[0]*512
mcopy=ROOT/'mtools/usr/bin/mcopy'
stage=ROOT/('kernel-observation-inputs' if observation else 'minimal-inputs');stage.mkdir(mode=0o700,exist_ok=False)
paths=['/live/initrd.img','/live/vmlinuz','/EFI/BOOT/BOOTX64.EFI','/EFI/BOOT/grubx64.efi','/EFI/debian/grub.cfg']
def extract(image,path,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    run([str(mcopy),'-i',str(image)+'@@'+str(offset),'::'+path,str(target)])
for path in paths:extract(original,path,stage/path.lstrip('/'))
marker=stage/'petalos-comparison-marker'
marker.write_text('''#!/bin/sh
case "$1" in prereqs) exit 0;; esac
modprobe efivarfs 2>/dev/null || :
mkdir -p /sys/firmware/efi/efivars
mount -t efivarfs efivarfs /sys/firmware/efi/efivars 2>/dev/null || :
sb=$(od -An -j4 -N1 -tu1 /sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c 2>/dev/null | tr -d ' ')
setup=$(od -An -j4 -N1 -tu1 /sys/firmware/efi/efivars/SetupMode-8be4df61-93ca-11d2-aa0d-00e098032b8c 2>/dev/null | tr -d ' ')
printf 'PETALOS_TAILS_UNSIGNED_INITRD_MARKER SecureBoot=%s SetupMode=%s\\n' "$sb" "$setup" > /dev/ttyS0
echo PETALOS_TAILS_UNSIGNED_INITRD_MARKER > /dev/kmsg
''')
marker.chmod(0o755)
if observation:
    # efivarfs is not available this early in Tails's stock initramfs. Read
    # the signed kernel's already-generated Secure Boot message instead.
    with marker.open('a') as out:out.write("dmesg | grep -i 'secure boot' > /dev/ttyS0\n")
# Preserve every existing CPIO record and the early archives verbatim. Tails
# places already-compressed modules in uncompressed CPIO before the final XZ
# archive; recompressing the merged extraction would inflate its packed image.
data=(stage/'live/initrd.img').read_bytes()
def records(content,offset=0):
    while True:
        start=offset;assert content[offset:offset+6]==b'070701'
        fields=[int(content[offset+6+8*i:offset+14+8*i],16) for i in range(13)]
        name=content[offset+110:offset+110+fields[11]-1].decode()
        begin=(offset+110+fields[11]+3)&~3
        offset=(begin+fields[6]+3)&~3
        yield start,offset,name,fields,content[begin:begin+fields[6]]
        if name=='TRAILER!!!':break
pos=0
while True:
    while data[pos]==0:pos+=1
    if data[pos:pos+6]!=b'070701':break
    for start,end,name,fields,body in records(data,pos):pos=end
assert data[pos:pos+6]==b'\xfd7zXZ\0'
raw=lzma.decompress(data[pos:]);out=bytearray();changed=0

def record(name,fields,body):
    fields=fields.copy();fields[6]=len(body);fields[11]=len(name.encode())+1
    value=b'070701'+b''.join(f'{field:08x}'.encode() for field in fields)+name.encode()+b'\0'
    value+=b'\0'*(-len(value)%4);value+=body;value+=b'\0'*(-len(value)%4)
    return value
entries=list(records(raw));next_inode=max(entry[3][0] for entry in entries)+1
for start,end,name,fields,body in entries:
    if name=='scripts/init-top/ORDER':
        body+=b'/scripts/init-top/petalos-comparison-marker "$@"\n';changed+=1
        out.extend(record(name,fields,body))
    elif name=='TRAILER!!!':
        out.extend(record('scripts/init-top/petalos-comparison-marker',
                   [next_inode,0o100755,0,0,1,0,0,0,0,0,0,0,0],marker.read_bytes()))
        out.extend(raw[start:end])
    else:out.extend(raw[start:end])
assert changed==1
out+=b'\0'*(-len(out)%512)
compressed=run(['xz','-9','-T4','--check=crc32','--stdout'],input=out)
initrd=stage/'probe-initrd.img';initrd.write_bytes(data[:pos]+compressed)
assert initrd.stat().st_size < len(data)+1024*1024,'Unexpected initramfs expansion.'
verify=stage/'readback';run(['unmkinitramfs',str(initrd),str(verify)])
assert (verify/'main/scripts/init-top/petalos-comparison-marker').read_bytes()==marker.read_bytes()
bad_kernel=stage/'negative-vmlinuz';data=bytearray((stage/'live/vmlinuz').read_bytes())
assert data[:2]==b'MZ';data[len(data)//2]^=1;bad_kernel.write_bytes(data)
results={}
variants=[('probe','/live/initrd.img',initrd)]
if not observation:variants.append(('kernel-negative','/live/vmlinuz',bad_kernel))
for mode,path,replacement in variants:
    filename=('tails-probe-observed.img' if observation else 'tails-probe-minimal.img') if mode=='probe' else 'tails-kernel-negative.img'
    image=ROOT/filename;assert not image.exists()
    run(['cp','--reflink=auto','--sparse=always','--',str(original),str(image)])
    assert subprocess.run(['fuser',str(image)],capture_output=True).returncode==1
    run([str(mcopy),'-o','-i',str(image)+'@@'+str(offset),str(replacement),'::'+path])
    checked={}
    for item in paths:
        target=stage/('readback-'+mode)/item.lstrip('/');extract(image,item,target)
        expected=replacement if item==path else stage/item.lstrip('/')
        assert sha(target)==sha(expected)
        checked[item]=sha(target)
    results[mode]={'image_sha256':sha(image),'changed_file':path,'boot_file_readback_sha256':checked}
result={'format':1,'scope':'Only new disposable regular image copies; original official image preserved.',
        'original_image_sha256':sha(original),'partition_offset':offset,'probe_marker_sha256':sha(marker),
        'original_boot_file_sha256':{p:sha(stage/p.lstrip('/')) for p in paths},'variants':results}
(ROOT/('preparation-observed.json' if observation else 'preparation.json')).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'prepared':list(results),'original_unchanged':True,'modified_boot_file_readback':True}))
