#!/usr/bin/env python3
"""Compile affected source routines; require old failures and repaired outcomes.

These bounded source probes do not substitute for installed-package workflows.
Only allocation/copy boundaries and unrelated GUI/log helpers are substituted.
"""
from pathlib import Path
import json,os,resource,subprocess,sys,tempfile

package,original,patched=sys.argv[1:]
old=Path(original).read_text();new=Path(patched).read_text()
assert old!=new
def bounded():
 resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
 resource.setrlimit(resource.RLIMIT_CORE,(0,0))
def function(text,start,end):
 assert text.count(start)==1
 return text[text.index(start):text.index(end,text.index(start))]

with tempfile.TemporaryDirectory(prefix='petalos-source-regression-') as directory:
 work=Path(directory)
 def compile(text,name,flags=()):
  p=work/(name+'.cpp');p.write_text(text);exe=work/name
  subprocess.run(['g++','-O1','-g','-Wall','-Wextra','-Werror=return-type',str(p),'-o',str(exe),*flags],check=True,capture_output=True)
  return exe
 results={}
 if package=='amule':
  for label,text in [('original',old),('repaired',new)]:
   block=function(text,'case OP_SERVERMESSAGE: {','\n\t\t\t\twxString strMessages').split('{',1)[1]
   probe='''#include <cstdint>
#include <cstring>
#include <string>
#include <new>
using wxString=std::string;
#define wxT(x) x
#define AddDebugLogLineN(...) ((void)0)
namespace theStats {void AddDownOverheadServer(uint32_t) {}}
bool parse(const uint8_t *packet,uint32_t size) {
'''+block+'''
bool result=std::string(buffer)=="ok!";delete[] buffer;return result;}
int main(){uint8_t packet[5]={0,0,'o','k','!'};
for(unsigned size=0;size<3;size++){
 try{parse(packet,size);return 10;}catch(const wxString&){}catch(...){return 11;}}
return parse(packet,5)?0:12;}
'''
   exe=compile(probe,label);r=subprocess.run([str(exe)],capture_output=True,timeout=5,preexec_fn=bounded)
   results[label+'_exit']=r.returncode
  assert results['original_exit']!=0 and results['repaired_exit']==0
 elif package=='policykit-1':
  import shlex
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','glib-2.0'],text=True))
  for label,text in [('original',old),('repaired',new)]:
   routine=function(text,'char *\nread_cookie (','\ngboolean\nsend_dbus_message')
   probe='#include <stdio.h>\n#include <string.h>\n#include <stdlib.h>\n#include <errno.h>\n#include <glib.h>\n'+routine+'''\nint main(int argc,char **argv){char *s=read_cookie(argc,argv);if(!s){puts("rejected");return 0;}printf("length=%zu\\n",strlen(s));free(s);return 0;}\n'''
   exe=compile(probe,label,flags);checks=[]
   for value,expected in [(b'public-cookie\n',b'length=13'),(b'a'*4096+b'\n',b'length=4096'),
       (b'a'*4097+b'\n',b'rejected'),(b'\0\n',b'rejected'),(b'',b'rejected')]:
    r=subprocess.run([str(exe)],input=value,capture_output=True,timeout=3,preexec_fn=bounded)
    checks.append(r.returncode==0 and r.stdout.strip()==expected)
   results[label+'_cases']=checks
   if label=='repaired':
    # A producer that never ends its oversized line must not keep the helper
    # waiting to drain it. Keep stdin open until the helper exits.
    p=subprocess.Popen([str(exe)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,preexec_fn=bounded)
    try:
     p.stdin.write(b'a'*4097);p.stdin.flush();p.wait(timeout=3)
     assert p.stdout.read().strip()==b'rejected'
     results['oversized_open_stream_rejected_without_wait']=True
    finally:
     p.stdin.close()
     if p.poll() is None:p.kill();p.wait()
  assert not all(results['original_cases']) and all(results['repaired_cases'])
 elif package=='libxml2':
  types=function(old,'typedef struct _xmlDictEntry xmlDictEntry;','\n/*\n * A mutex')
  for label,text in [('original',old),('repaired',new)]:
   routine=function(text,'static const xmlChar *\nxmlDictAddQString(','\n#ifdef WITH_BIG_KEY')
   probe='''#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
typedef unsigned char xmlChar;
'''+types+'''
typedef struct _xmlDict *xmlDictPtr;
static void *xmlMalloc(size_t n){return n>65536?nullptr:calloc(1,n);}
static const xmlChar *xmlDictAddString(xmlDictPtr,const xmlChar *,unsigned){return nullptr;}
static void *bounded_copy(void *to,const void *from,size_t n){if(n>64)throw std::runtime_error("oversized copy after undersized allocation");return memcpy(to,from,n);}
#define memcpy bounded_copy
'''+routine+'''
int main(){_xmlDict dict={};const xmlChar p[]="p",name[]="name";
try{
 if(xmlDictAddQString(&dict,p,1,name,1u<<30)!=nullptr)return 10;
 const auto normal=xmlDictAddQString(&dict,p,1,name,4);
 if(!normal || strcmp((const char*)normal,"p:name"))return 11;
 if(xmlDictAddQString(&dict,p,UINT32_MAX-3,name,16)!=nullptr)return 12;
 while(dict.strings){auto next=dict.strings->next;free(dict.strings);dict.strings=next;}
}catch(...){return 13;}return 0;}
'''
   exe=compile(probe,label);r=subprocess.run([str(exe)],capture_output=True,timeout=3,preexec_fn=bounded)
   results[label+'_exit']=r.returncode
  assert results['original_exit']!=0 and results['repaired_exit']==0
 elif package=='poppler':
  # The runtime regression uses generated AES-256/R6 PDFs against pdfinfo and
  # Atril's actual library. No mocked hash routine is claimed as that test.
  results={'installed_PDF_regression_required':True}
 else:raise AssertionError('Unknown source regression')
 print(json.dumps({'package':package,'source_regression':results},sort_keys=True))
