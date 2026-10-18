from pathlib import Path
import json,subprocess,sys,tarfile,time,xml.etree.ElementTree as ET
sys.path.insert(0,'/usr/local/lib/portable')
from desktop_session import environment
from system_state import STATE
e=environment();pre=['setpriv','--reuid=1000','--regid=1000','--clear-groups','--'];key='.config/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml';archive=STATE/'Desktop/desktop-settings.tar'
def value(data):
 p=ET.fromstring(data).find("./property[@name='Net']/property[@name='DoubleClickTime']");return None if p is None else p.attrib.get('value')
def archived():
 with tarfile.open(archive) as f:
  try:return value(f.extractfile(key).read())
  except KeyError:return None
def current():
 r=subprocess.run(pre+['xfconf-query','-c','xsettings','-p','/Net/DoubleClickTime'],env=e,capture_output=True,text=True);return {'returncode':r.returncode,'value':r.stdout.strip() if r.stdout.strip().isdigit() else None}
def save():subprocess.run(pre+['/usr/local/bin/portable-save-settings'],env=e,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=15)
out={'restored_runtime':current(),'archived_before_test':archived(),'disk_before_test':value((Path('/home/Petal')/key).read_bytes())}
subprocess.run(pre+['xfconf-query','-c','xsettings','-p','/Net/DoubleClickTime','-s','322'],env=e,capture_output=True,check=True)
out['runtime_after_change']=current();save();out['archive_immediately_after_save']=archived()
time.sleep(7);out['disk_after_settling']=value((Path('/home/Petal')/key).read_bytes());save();out['archive_after_wait_and_resave']=archived()
print(json.dumps(out))
