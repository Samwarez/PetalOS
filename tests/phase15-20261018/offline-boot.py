from pathlib import Path
import json,os,subprocess,sys
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c,system_state as s
assert os.geteuid()==0
out={'SYSTEM_state_ready_without_network':s.ready(),'Private_closed_without_network':not Path('/dev/mapper/portable_data').exists(),'no_WireGuard_at_startup':not Path('/sys/class/net/wg0').exists(),'no_swap':len(Path('/proc/swaps').read_text().splitlines())==1}
links=[p for p in Path('/sys/class/net').iterdir() if p.name not in ('lo','wg0')]
out['all_underlay_carriers_down']=bool(links) and all(p.joinpath('carrier').read_text().strip()=='0' for p in links)
out['desktop_compositor_ready']=subprocess.run(['pgrep','-u','1000','-x','labwc'],stdout=subprocess.DEVNULL).returncode==0
r=subprocess.run(['setpriv','--reuid=1000','--regid=1000','--clear-groups','--','sudo','-n','--','/usr/local/sbin/portable-compartment','launch','transmission'],capture_output=True,timeout=40)
out['network_app_launch_denied']=r.returncode!=0
out['offline_editor_launches']=c.start('offline-geany')['phase']=='ready';c.stop('offline-geany')
out['runtime_WireGuard_key_absent']=not Path('/etc/wireguard/wg0.conf').exists()
print(json.dumps(out))
