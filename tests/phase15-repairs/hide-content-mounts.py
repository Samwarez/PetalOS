import json,os,subprocess
assert os.geteuid()==0
for name in ('Documents','Downloads'):
 subprocess.run(['mount','-o','remount,bind,x-gvfs-hide','/home/Petal/'+name],check=True,capture_output=True)
print(json.dumps({'content_mount_display_hint_installed':True}))
