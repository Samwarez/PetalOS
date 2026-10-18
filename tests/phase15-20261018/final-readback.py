"""Read only the restored public initrd from the powered-off audit image's FAT32."""
from pathlib import Path
import hashlib,json,struct,subprocess
image=Path('/home/sam/portable-live/testing/audit/20261017-221958-817753/audit.img')
runtime=Path('/run/user/1000/petalos-audit-20261017-221958-817753')
assert not (runtime/'running.json').exists()
assert subprocess.run(['fuser',str(image)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==1
assert image.is_file() and not image.is_symlink() and image.stat().st_size==16*1024**3
parts=json.loads(subprocess.check_output(['/usr/sbin/sfdisk','--json',str(image)],text=True))['partitiontable'];boot=parts['partitions'][1];assert boot['node']==str(image)+'2'
offset=boot['start']*parts['sectorsize']
with image.open('rb') as f:
 def read(n,p):f.seek(p);return f.read(n)
 b=read(512,offset);u16=lambda p:struct.unpack_from('<H',b,p)[0];u32=lambda p:struct.unpack_from('<I',b,p)[0]
 assert b[510:512]==b'\x55\xaa' and u16(22)==0 and u16(17)==0
 sector=u16(11);cluster_bytes=b[13]*sector;fat=offset+u16(14)*sector;data=fat+b[16]*u32(36)*sector;root=u32(44)
 def chain(start):
  seen=set();c=start
  while 2<=c<0x0ffffff8:
   assert c not in seen and len(seen)<200000;seen.add(c)
   yield read(cluster_bytes,data+(c-2)*cluster_bytes)
   c=struct.unpack('<I',read(4,fat+c*4))[0]&0x0fffffff
 def find(start,wanted):
  for block in chain(start):
   for p in range(0,len(block),32):
    row=block[p:p+32]
    if row[0]==0:return None
    if row[0]==0xe5 or row[11]==0x0f:continue
    if row[:11]==wanted:return (struct.unpack_from('<H',row,20)[0]<<16)|struct.unpack_from('<H',row,26)[0],struct.unpack_from('<I',row,28)[0],row[11]
  return None
 live=find(root,b'LIVE       ');assert live and live[2]&16
 initrd=find(live[0],b'INITRD  IMG');assert initrd and not initrd[2]&16
 h=hashlib.sha256();remaining=initrd[1]
 for block in chain(initrd[0]):
  h.update(block[:remaining]);remaining-=min(remaining,len(block))
  if not remaining:break
 assert remaining==0
 digest=h.hexdigest();assert digest=='2625d4f7a1c7ec10a0ec156e10c62df7874e595beacde15354dfc496cbd90247'
result={'audit_VM_powered_off':True,'QMP_and_serial_sockets_removed':not (runtime/'qmp.sock').exists() and not (runtime/'serial.sock').exists(),'image_not_in_use':True,'restored_boot_initrd_readback_sha256':digest,'matches_original_release':True}
Path(__file__).resolve().parents[2].joinpath('docs/audit-phase15-20261018/final-cleanup.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
