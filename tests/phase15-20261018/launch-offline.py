"""Reuse the exact audit launcher, pausing vCPUs until its NIC is link-down."""
from pathlib import Path
import importlib.util,json,socket,subprocess,threading,time
PROJECT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('audit_driver',PROJECT/'tests/audit-vm.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
work,state=a.state(PROJECT.parent/'testing/audit/20261017-221958-817753/state.json')
runtime=Path('/run/user/1000/petalos-audit-20261017-221958-817753');original=subprocess.Popen
result=PROJECT/'docs/audit-phase15-20261018/offline-launch.json'
def disable_before_boot(process):
 try:
  deadline=time.monotonic()+20
  while not (runtime/'qmp.sock').exists():
   assert process.poll() is None and time.monotonic()<deadline;time.sleep(.1)
  with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
   s.settimeout(15);s.connect(str(runtime/'qmp.sock'));f=s.makefile('rwb',buffering=0);json.loads(f.readline())
   def req(command,args=None):
    f.write(json.dumps({'execute':command,**({'arguments':args} if args is not None else {})}).encode()+b'\n')
    while True:
     r=json.loads(f.readline());assert 'error' not in r
     if 'return' in r:return r['return']
   req('qmp_capabilities');before=req('query-status');assert before['status']=='prelaunch'
   filters=req('query-rx-filter');assert len(filters)==1
   req('set_link',{'name':filters[0]['name'],'up':False})
   result.write_text(json.dumps({'vCPUs_initially_paused':True,'NIC_disabled_before_first_instruction':True,'device_name':filters[0]['name']}))
   req('cont')
 except BaseException as e:
  result.write_text(json.dumps({'failed':type(e).__name__}));process.terminate()
def start(args,*p,**kw):
 if isinstance(args,list) and args and args[0]=='qemu-system-x86_64':
  assert '-S' not in args;process=original([*args,'-S'],*p,**kw);threading.Thread(target=disable_before_boot,args=(process,),daemon=True).start();return process
 return original(args,*p,**kw)
a.subprocess.Popen=start
a.launch(work,state)
