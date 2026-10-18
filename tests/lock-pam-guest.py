#!/usr/bin/python3 -I
"""Exercise installed PAM services with a synthetic invalid password."""
import json
import os
import subprocess

assert os.geteuid() == 0
code = '''import ctypes,json
from ctypes import POINTER,c_char_p,c_int,c_void_p
libc=ctypes.CDLL('libc.so.6')
libc.calloc.argtypes=(ctypes.c_size_t,ctypes.c_size_t);libc.calloc.restype=c_void_p
libc.strdup.argtypes=(c_char_p,);libc.strdup.restype=c_void_p
class Message(ctypes.Structure):_fields_=[('style',c_int),('text',c_char_p)]
class Response(ctypes.Structure):_fields_=[('text',c_void_p),('code',c_int)]
Callback=ctypes.CFUNCTYPE(c_int,c_int,POINTER(POINTER(Message)),POINTER(POINTER(Response)),c_void_p)
def conversation(count,messages,response,context):
 if not 0<count<=32:return 19
 memory=libc.calloc(count,ctypes.sizeof(Response))
 if not memory:return 19
 values=ctypes.cast(memory,POINTER(Response))
 for i in range(count):
  if messages[i].contents.style in (1,2):values[i].text=libc.strdup(b'public-invalid-lock-fixture')
 response[0]=values
 return 0
callback=Callback(conversation)
class Conv(ctypes.Structure):_fields_=[('callback',Callback),('data',c_void_p)]
conv=Conv(callback,None);pam=ctypes.CDLL('libpam.so.0')
pam.pam_start.argtypes=(c_char_p,c_char_p,POINTER(Conv),POINTER(c_void_p))
pam.pam_authenticate.argtypes=(c_void_p,c_int)
pam.pam_end.argtypes=(c_void_p,c_int)
result={}
for service,key in [(b'gtklock','gtklock_invalid_password_rejected'),(b'login','public_console_login_rejected')]:
 handle=c_void_p()
 status=pam.pam_start(service,b'Petal',ctypes.byref(conv),ctypes.byref(handle))
 assert status==0
 status=pam.pam_authenticate(handle,0)
 result[key]=status!=0
 pam.pam_end(handle,status)
print(json.dumps(result))
'''
result = subprocess.run(['/usr/bin/setpriv', '--reuid=1000', '--regid=1000', '--clear-groups',
    '/usr/bin/python3', '-I', '-c', code], capture_output=True, text=True, timeout=20)
assert result.returncode == 0, 'PAM fixture failed; raw output suppressed.'
report = json.loads(result.stdout)
print(json.dumps(report, sort_keys=True))
assert all(report.values())
