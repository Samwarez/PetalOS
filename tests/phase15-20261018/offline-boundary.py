"""Active probes in unchanged offline sandbox/profile; synthetic files only."""
from pathlib import Path
import json,os,subprocess,sys,secrets
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
from offline_files import delegate
assert os.geteuid()==0
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
app='offline-geany'; c.protected(c.BASE);c.protected(c.BASE/app);c.home(app);c.storage_setup(app)
display=c.display_server(app)
probe='''import json,os,socket,subprocess,sys
from pathlib import Path
sys.path.insert(0,'/usr/local/lib/portable')
from wayland_context import Connection
r={};w=Connection('/run/user/949/wayland-0');names=set(w.globals);w.close()
forbidden={'wp_security_context_manager_v1','zwlr_screencopy_manager_v1','zwlr_export_dmabuf_manager_v1','zwlr_virtual_pointer_manager_v1','zwp_virtual_keyboard_manager_v1','zwlr_data_control_manager_v1','ext_data_control_manager_v1','zwlr_layer_shell_v1','ext_session_lock_manager_v1','zwlr_foreign_toplevel_manager_v1','ext_foreign_toplevel_list_v1'}
r['privileged_wayland_protocols_hidden']=not bool(names&forbidden)
r['usable_wayland_protocols']={'wl_compositor','xdg_wm_base','wl_seat'}<=names
for path in ['/mnt/system-state','/home/Petal','/run/user/1000','/run/dbus/system_bus_socket','/dev/vda','/dev/mapper','/tmp/.X11-unix']:
 r['hidden:'+path]=not Path(path).exists()
for f in [socket.AF_INET,socket.AF_INET6]:
 try:s=socket.socket(f);s.close();r['network_denied:'+str(f)]=False
 except PermissionError:r['network_denied:'+str(f)]=True
status=Path('/proc/self/status').read_text();r['capabilities_zero']='CapEff:\\t0000000000000000' in status;r['no_new_privs']='NoNewPrivs:\\t1' in status
for target in ['/etc/shadow','/etc/wireguard/wg0.conf']:
 try:
  fd=os.open(target,os.O_RDONLY);os.close(fd);r['read_denied:'+target]=False
 except OSError:r['read_denied:'+target]=True
p=Path('/mnt/ram/Documents/geany')/'audit-public-create-save.txt'
try:
 p.write_text('public synthetic v1');p.write_text('public synthetic v2');r['save_reopen']=p.read_text()=='public synthetic v2'
finally:p.unlink(missing_ok=True)
print(json.dumps(r))
'''
try:
 r=subprocess.run(c.sandbox(app,['aa-exec','-p','petalos_offline_geany','--','python3','-I','-c',probe],wayland=display),capture_output=True,text=True,timeout=30)
 assert r.returncode==0,'Offline fixture failed; application output suppressed'
 report=json.loads(r.stdout)
finally:
 os.close(display['lease']);display['connection'].close();display['path'].unlink(missing_ok=True)
# Pin selected-file behavior and mode-0600 ownership, independently of old tests.
p=Path('/home/Petal/Documents/geany/audit-owner-0600.txt')
code="import os; fd=os.open('/mnt/ram/Documents/geany/audit-owner-0600.txt',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.write(fd,b'public synthetic');os.close(fd)"
r=subprocess.run(c.sandbox(app,['aa-exec','-p','petalos_offline_geany','--','python3','-I','-c',code]),capture_output=True,timeout=10)
assert r.returncode==0
try:
 r=subprocess.run(['setpriv','--reuid=1000','--regid=1000','--clear-groups','python3','-I','-c','import os; f=os.open("/home/Petal/Documents/geany/audit-owner-0600.txt",os.O_RDONLY);os.close(f)'],capture_output=True,timeout=5)
 report['desktop_can_read_new_mode0600_app_file']=r.returncode==0
 report['mode0600_file_owner']=p.stat().st_uid
finally:p.unlink()
print(json.dumps(report,sort_keys=True))
