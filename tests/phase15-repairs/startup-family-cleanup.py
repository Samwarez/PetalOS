"""Cancel after a real SAB backend is ready; retain only pre-existing workers."""
from pathlib import Path
import json,os,signal,sys
assert os.geteuid()==0
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
broker={'__name__':'fixture'}
p=Path('/usr/local/sbin/portable-compartment')
exec(compile(p.read_text(),str(p),'exec'),broker)
original_start=c.start
was_viewer=c.worker_alive(c.read_record('sab-viewer'))
was_backend=c.worker_alive(c.read_record('sabnzbd'))
def cancel(*_):
 signal.signal(signal.SIGTERM,signal.SIG_IGN)
 raise c.CompartmentError('Injected startup cancellation')
def controlled_start(app,arguments=()):
 if app=='sab-viewer':
  assert c.worker_alive(c.read_record('sabnzbd'))
  signal.raise_signal(signal.SIGTERM)
 return original_start(app,arguments)
broker['start']=controlled_start
old_handler=signal.getsignal(signal.SIGTERM)
out={}
try:
 with c.action_lock('sabnzbd'):
  c.stop('sab-viewer');c.stop('sabnzbd')
  for existing in (False,True):
   if existing:original_start('sabnzbd')
   prior=c.read_record('sabnzbd') if existing else None
   signal.signal(signal.SIGTERM,cancel)
   try:broker['start_family']('sabnzbd','sab-viewer')
   except c.CompartmentError:pass
   else:raise AssertionError('Cancellation not reported')
   record=c.read_record('sabnzbd')
   alive=c.worker_alive(record)
   assert alive==existing
   assert not c.worker_alive(c.read_record('sab-viewer'))
   if existing:assert record['token']==prior['token']
   out['existing_backend_preserved' if existing else 'new_backend_removed']=True
  c.stop('sabnzbd')
finally:
 signal.signal(signal.SIGTERM,old_handler)
 if was_backend:original_start('sabnzbd')
 if was_viewer:original_start('sab-viewer')
print(json.dumps(out))
