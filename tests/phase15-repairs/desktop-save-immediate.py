from pathlib import Path
import json,subprocess,sys,tarfile,xml.etree.ElementTree as ET
sys.path.insert(0,'/usr/local/lib/portable')
from desktop_session import environment
from system_state import STATE
state=json.loads(subprocess.check_output(['/usr/local/sbin/portable-storage','status']))
if not state['download_mode']:subprocess.run(['/usr/local/sbin/portable-storage','download-toggle'],check=True,capture_output=True)
e=environment();pre=['setpriv','--reuid=1000','--regid=1000','--clear-groups','--'];key='.config/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml'
out=[]
for n in (331,332,333):
 subprocess.run(pre+['xfconf-query','-c','xsettings','-p','/Net/DoubleClickTime','-s',str(n)],env=e,check=True,capture_output=True)
 subprocess.run(pre+['/usr/local/bin/portable-save-settings'],env=e,check=True,capture_output=True,timeout=20)
 with tarfile.open(STATE/'Desktop/desktop-settings.tar') as a:
  actual=ET.fromstring(a.extractfile(key).read()).find("./property[@name='Net']/property[@name='DoubleClickTime']").attrib['value']
 out.append({'requested':n,'archived':int(actual),'match':str(n)==actual})
assert all(x['match'] for x in out)
print(json.dumps({'rapid_immediate_saves':out,'expected_after_reboot':333}))
