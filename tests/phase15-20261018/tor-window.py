from pathlib import Path
import json,sys
sys.path.insert(0,'/usr/local/lib/portable')
from desktop_session import environment
from wayland_context import Connection,integer,string
e=environment();c=Connection(Path(e['XDG_RUNTIME_DIR'])/e['WAYLAND_DISPLAY']);c.watch_windows()
try:
 targets=[h for h,a in c.windows.items() if a in ('Tor Browser','torbrowser','org.torproject.torbrowser','firefox') or 'torbrowser' in a.lower()]
 out={'application_ids':sorted(c.windows.values()),'browser_target_count':len(targets)}
 if len(targets)==1:
  name,version=c.globals['wl_seat'];seat=c.allocate();c.send(2,0,integer(name)+string('wl_seat')+integer(1)+integer(seat));c.roundtrip();c.send(targets[0],3);c.send(targets[0],4,integer(seat));c.roundtrip();out['activation_requested']=True
 print(json.dumps(out))
finally:c.close()
