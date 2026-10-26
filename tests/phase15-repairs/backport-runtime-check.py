"""Installed polkit authentication/negative inputs and libxml2 document checks."""
from pathlib import Path
import ctypes,json,os,resource,subprocess,sys,time
assert os.geteuid()==0
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
credentials=json.load(sys.stdin)
helper='/usr/lib/polkit-1/polkit-agent-helper-1'
command=['setpriv','--reuid=1000','--regid=1000','--clear-groups','--',helper,'root']
def bounded():
 resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
out={}
for name,value in [('oversized',b'a'*4097),('initial_nul',b'\0\n')]:
 p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,preexec_fn=bounded)
 try:
  p.stdin.write(value);p.stdin.flush();p.wait(timeout=4)
  data=p.stdout.read()
  out[name+'_rejected_with_input_still_open']=p.returncode==1 and b'FAILURE' in data and b'PAM_PROMPT' not in data
  assert out[name+'_rejected_with_input_still_open']
 finally:
  p.stdin.close()
  if p.poll() is None:p.kill();p.wait()
for name,password in [('wrong','public-synthetic-wrong-administrator'),('valid',credentials['administrator'])]:
 r=subprocess.run(command,input=b'public-synthetic-cookie\n'+password.encode()+b'\n',capture_output=True,timeout=15,preexec_fn=bounded)
 # The fabricated cookie must never authorize an action, even after correct
 # PAM authentication. Check stages without printing any credential or output.
 assert r.returncode==1 and b'FAILURE' in r.stdout and b'SUCCESS' not in r.stdout
 if name=='wrong':
  out['wrong_administrator_rejected']=b'pam_authenticate failed' in r.stderr
  assert out['wrong_administrator_rejected']
 else:
  out['correct_administrator_passed_PAM']=b'error response to PolicyKit daemon' in r.stderr and b'pam_authenticate failed' not in r.stderr
  out['fabricated_cookie_still_denied']=any(message in r.stderr for message in
   (b'No pending authentication request',b'No session for cookie'))
  if not (out['correct_administrator_passed_PAM'] and out['fabricated_cookie_still_denied']):
   print(json.dumps(dict(out,diagnostic_stages={s:s.encode() in r.stderr for s in
    ('pam_authenticate failed','pam_acct_mgmt failed','error response to PolicyKit daemon','Error getting authority','No authentication agent found','No session for cookie','No pending authentication request')})))
  assert out['correct_administrator_passed_PAM'] and out['fabricated_cookie_still_denied']
del credentials
lib=ctypes.CDLL('libxml2.so.2')
lib.xmlReadMemory.argtypes=[ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_int];lib.xmlReadMemory.restype=ctypes.c_void_p
lib.xmlDocDumpMemory.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(ctypes.c_int)]
lib.xmlFreeDoc.argtypes=[ctypes.c_void_p]
xml_free=ctypes.CFUNCTYPE(None,ctypes.c_void_p).in_dll(lib,'xmlFree')
data=b'<p:root xmlns:p="urn:petalos:public-fixture">'+b'<p:child>public text</p:child>'*1000+b'</p:root>'
doc=lib.xmlReadMemory(data,len(data),b'public.xml',None,2048);assert doc
buffer=ctypes.c_void_p();size=ctypes.c_int()
try:
 lib.xmlDocDumpMemory(doc,ctypes.byref(buffer),ctypes.byref(size))
 result=ctypes.string_at(buffer,size.value)
 assert result.count(b'<p:child>public text</p:child>')==1000
 again=lib.xmlReadMemory(result,len(result),b'public-roundtrip.xml',None,2048);assert again
 lib.xmlFreeDoc(again);out['installed_libxml2_namespace_roundtrip']=True
finally:
 if buffer.value:xml_free(buffer)
 lib.xmlFreeDoc(doc)
out['polkit_version']=subprocess.check_output(['dpkg-query','-W','-f=${Version}','polkitd'],text=True)
out['libxml2_version']=subprocess.check_output(['dpkg-query','-W','-f=${Version}','libxml2'],text=True)
print(json.dumps(out))
