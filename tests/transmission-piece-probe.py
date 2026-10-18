#!/usr/bin/python3
"""Verify pieces of the one agent-selected public Debian torrent; print counts."""
from pathlib import Path
import hashlib
import json

data=Path('/run/user/1000/petalos-app-acceptance/official-debian-netinst.torrent').read_bytes()
assert len(data)<1024*1024
index=0

def decode(depth=0):
    global index
    assert depth<32
    token=data[index:index+1]
    if token==b'i':
        end=data.index(b'e',index);value=int(data[index+1:end]);index=end+1;return value
    if token in (b'l',b'd'):
        index+=1;items=[]
        while data[index:index+1]!=b'e':items.append(decode(depth+1))
        index+=1
        return dict(zip(items[::2],items[1::2])) if token==b'd' else items
    end=data.index(b':',index);length=int(data[index:end]);index=end+1
    value=data[index:index+length];assert len(value)==length;index+=length;return value

info=decode()[b'info']
name=info[b'name'].decode();assert Path(name).name==name and name not in ('.','..')
size=info[b'length'];piece_size=info[b'piece length'];hashes=info[b'pieces']
base=Path('/mnt/private/Downloads/transmission')
candidates=[base/name,base/'incomplete'/name,base/'incomplete'/(name+'.part')]
file=next((p for p in candidates if p.is_file() and not p.is_symlink()),None)
verified=0
if file:
    with file.open('rb') as stream:
        remaining=size
        for offset in range(0,len(hashes),20):
            block=stream.read(min(piece_size,remaining))
            if hashlib.sha1(block).digest()==hashes[offset:offset+20]:verified+=len(block)
            remaining-=len(block)
print(json.dumps({'verified_public_download_bytes':verified,'expected_bytes':size,'complete':verified==size}))
