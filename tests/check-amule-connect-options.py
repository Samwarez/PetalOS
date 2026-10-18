#!/usr/bin/env python3
"""Compile the actual upstream/patched function; exhaustively check all flags."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tarfile
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('source_archive', type=Path)
args = p.parse_args()
assert hashlib.sha256(args.source_archive.read_bytes()).hexdigest() == 'a647309642331f3e033fdf0196e7232cdc67f46739d12a0294be06885f70c8bd'
patch = Path(__file__).resolve().parents[1] / 'local/amule-kad/connect-options.patch'
stub = r'''
#include <cstdint>
#include <cstdio>
bool required, requested, supported, firewalled, running, udpBlocked, verified;
struct App { bool IsFirewalled() {return firewalled;} } app, *theApp=&app;
struct thePrefs {
 static bool IsClientCryptLayerRequired() {return required;}
 static bool IsClientCryptLayerRequested() {return requested;}
 static bool IsClientCryptLayerSupported() {return supported;}
};
struct CKademlia { static bool IsRunning() {return running;} };
struct CUDPFirewallTester {
 static bool IsFirewalledUDP(bool) {return udpBlocked;}
 static bool IsVerified() {return verified;}
};
struct CPrefs {static uint8_t GetMyConnectOptions(bool, bool);};
'''
main = r'''
int main() {
 unsigned failed=0;
 for(unsigned i=0;i<512;i++) {
  bool encryption=i&1, callback=i&2;
  required=i&4; requested=i&8; supported=i&16; firewalled=i&32;
  running=i&64; udpBlocked=i&128; verified=i&256;
  unsigned expected=((callback&&firewalled&&running&&!udpBlocked&&verified)?8:0)
   | ((encryption&&required)?4:0) | ((encryption&&requested)?2:0)
   | ((encryption&&supported)?1:0);
  if(CPrefs::GetMyConnectOptions(encryption,callback)!=expected) failed++;
 }
 std::printf("%u\n",failed);
 return 0;
}
'''


def function(text):
    a = text.index('uint8_t CPrefs::GetMyConnectOptions(')
    b = text.index('\n}', a) + 2
    return text[a:b]


with tempfile.TemporaryDirectory(prefix='petalos-amule-options-test-') as tmp:
    root = Path(tmp)
    with tarfile.open(args.source_archive) as t:
        original = t.extractfile('aMule-2.3.3/src/kademlia/kademlia/Prefs.cpp').read().decode()
    target = root / 'src/kademlia/kademlia/Prefs.cpp'
    target.parent.mkdir(parents=True)
    target.write_text(original)
    subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)], cwd=root, check=True,
                   stdout=subprocess.DEVNULL)
    counts = []
    for label, text in [('upstream', original), ('patched', target.read_text())]:
        source = root / (label + '.cpp')
        source.write_text(stub + function(text) + main)
        binary = root / label
        subprocess.run(['g++', '-std=c++17', '-O2', str(source), '-o', str(binary)], check=True)
        counts.append(int(subprocess.check_output([str(binary)], text=True)))
    assert counts[0] > 0, 'Negative control did not reproduce the original bug'
    assert counts[1] == 0, 'Patched function produced an incorrect bitmask'
    print(f'PASS: actual patched function matches all 512 combinations; upstream fails {counts[0]}')
