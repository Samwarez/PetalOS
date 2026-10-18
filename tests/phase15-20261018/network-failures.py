"""Bounded active tunnel failure tests; never change credentials/firewall policy."""
from pathlib import Path
import collections,ipaddress,json,os,socket,struct,subprocess,sys,threading,time
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
from vpn_profiles import select
assert os.geteuid()==0
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
def run(args,timeout=110):
 try:return subprocess.run(args,stdin=subprocess.DEVNULL,capture_output=True,timeout=timeout)
 except subprocess.TimeoutExpired:return None
def ok(args,t=110):
 r=run(args,t);return r is not None and r.returncode==0
name,profile=select();expected=(ipaddress.ip_address(profile['host']),profile['port'])
route=json.loads(run(['ip','-j','-4','route','show','default']).stdout);interface=route[0]['dev']
capture=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3));capture.bind((interface,0));capture.settimeout(.25)
counts=collections.Counter();done=threading.Event()
def observe():
 while not done.is_set():
  try:frame,address=capture.recvfrom(160)
  except socket.timeout:continue
  if address[2]!=socket.PACKET_OUTGOING or len(frame)<14:continue
  proto=int.from_bytes(frame[12:14],'big')
  if proto==0x0806:counts['arp']+=1;continue
  if proto==0x0800 and len(frame)>=42:
   pos=14+(frame[14]&15)*4
   if frame[23]==17 and len(frame)>=pos+8:
    sport,dport=struct.unpack('!HH',frame[pos:pos+4]);dst=ipaddress.ip_address(frame[30:34])
    if (dst,dport)==expected:counts['wireguard']+=1;continue
    if (sport,dport)==(68,67):counts['dhcp']+=1;continue
   counts['unexpected_ip']+=1
  elif proto==0x86dd:counts['unexpected_ip']+=1
t=threading.Thread(target=observe,daemon=True);t.start()
report={};resolv=Path('/etc/resolv.conf').read_bytes();before=run(['nft','-s','-j','list','table','inet','portable_vpn']).stdout
def probes():
 # Public test IPs; send only synthetic one-byte traffic, count uplink headers.
 code='''import socket
for family,target in ((socket.AF_INET,('198.51.100.1',443)),(socket.AF_INET,('1.1.1.1',53)),(socket.AF_INET,('1.1.1.1',123)),(socket.AF_INET6,('2001:db8::1',443))):
 s=socket.socket(family,socket.SOCK_DGRAM);s.settimeout(.3)
 try:s.sendto(b'x',target)
 except OSError:pass
 s.close()
'''
 for uid in (0,1000,940,942,943,944,945):
  assert ok(['setpriv','--reuid='+str(uid),'--regid='+str(uid),'--clear-groups','--bounding-set=-all','--no-new-privs','python3','-I','-c',code],5)
try:
 report['initial_gate']=ok(['/usr/local/sbin/portable-check-network-ready'],25)
 report['apps_running_before']={a:c.worker_alive(c.read_record(a)) for a in ('transmission','pan','amule','sabnzbd')}
 assert ok(['ip','link','set','wg0','down'],5)
 report['live_gate_denies_tunnel_loss']=not ok(['/usr/local/sbin/portable-check-network-ready'],25)
 probes()
 report['stale_connection_report_exists']=Path('/run/portable-vpn-checks.json').exists()
 assert ok(['ip','link','set','wg0','up'],5)
 report['link_up_alone_restores_gate']=ok(['/usr/local/sbin/portable-check-network-ready'],25)
 if not report['link_up_alone_restores_gate']:
  assert ok(['/usr/local/sbin/portable-vpn','disconnect'])
  assert ok(['/usr/local/sbin/portable-vpn','connect',name])
 report['link_recovery_without_reboot']=ok(['/usr/local/sbin/portable-check-network-ready'],25)
 Path('/etc/resolv.conf').write_text('nameserver 192.0.2.53\noptions timeout:1 attempts:1\n')
 report['DNS_failure_denies_gate']=not ok(['/usr/local/sbin/portable-check-network-ready'],25)
 Path('/etc/resolv.conf').write_bytes(resolv)
 report['DNS_recovery_without_reboot']=ok(['/usr/local/sbin/portable-check-network-ready'],25)
 report['disconnect']=ok(['/usr/local/sbin/portable-vpn','disconnect'])
 probes();report['disconnected_gate_denied']=not ok(['/usr/local/sbin/portable-check-network-ready'],25)
 report['repeated_disconnect']=ok(['/usr/local/sbin/portable-vpn','disconnect'])
 report['missing_profile_rejected']=not ok(['/usr/local/sbin/portable-vpn','connect','audit-does-not-exist'])
 report['failed_profile_no_tunnel']=not Path('/sys/class/net/wg0').exists()
 probes()
 report['reconnect']=ok(['/usr/local/sbin/portable-vpn','connect',name])
 report['gate_after_reconnect']=ok(['/usr/local/sbin/portable-check-network-ready'],25)
 report['same_profile_switch']=ok(['/usr/local/sbin/portable-vpn','switch',name])
 report['apps_survive_transitions']={a:c.worker_alive(c.read_record(a)) for a in ('transmission','pan','amule','sabnzbd')}
finally:
 Path('/etc/resolv.conf').write_bytes(resolv)
 if Path('/sys/class/net/wg0').exists():ok(['ip','link','set','wg0','up'],5)
 if not ok(['/usr/local/sbin/portable-check-network-ready'],25):
  ok(['/usr/local/sbin/portable-vpn','disconnect']);report['finally_recovery']=ok(['/usr/local/sbin/portable-vpn','connect',name])
 done.set();t.join(2);capture.close()
report['firewall_unchanged']=before==run(['nft','-s','-j','list','table','inet','portable_vpn']).stdout
report['packet_counts']=dict(counts)
print(json.dumps(report,sort_keys=True))
