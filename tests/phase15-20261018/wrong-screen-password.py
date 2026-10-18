"""Type only a deliberately wrong public value into the disposable locker."""
from pathlib import Path
import importlib.util,json,subprocess,time
project=Path(__file__).resolve().parents[2]
p=project/'tests/phase15-20261018/qmp.py';v={};exec(compile(p.read_text().split("if sys.argv[1]=='capture':")[0],str(p),'exec'),v)
spec=importlib.util.spec_from_file_location('driver',project/'tests/audit-vm.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
work,state=a.state(project.parent/'testing/audit/20261017-221958-817753/state.json')
probe='pgrep -u 1000 -x gtklock >/dev/null'
assert a.ssh(work,probe,capture_output=True).returncode==0
for ch in 'audit-wrong':
 v['request']('send-key',{'keys':[{'type':'qcode','data':'minus' if ch=='-' else ch}],'hold-time':20});time.sleep(.06)
v['request']('send-key',{'keys':[{'type':'qcode','data':'ret'}],'hold-time':20});time.sleep(5)
r={'wrong_SCREEN_credential_leaves_locker_running':a.ssh(work,probe,capture_output=True).returncode==0,'Private_stays_closed':a.ssh(work,'test ! -e /dev/mapper/portable_data',capture_output=True).returncode==0}
v['request']('send-key',{'keys':[{'type':'qcode','data':'ctrl'},{'type':'qcode','data':'a'}],'hold-time':20});time.sleep(.1);v['request']('send-key',{'keys':[{'type':'qcode','data':'backspace'}],'hold-time':20})
(project/'docs/audit-phase15-20261018/wrong-screen-password-result.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
