"""Synthetic encrypted PDF through the actual Atril role and Poppler library."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
assert os.geteuid()==0 and subprocess.check_output(['systemd-detect-virt'],text=True).strip() in ('qemu','kvm')
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
app='offline-atril';c.home(app);c.storage_setup(app)
folder=c.ram_folder(app,'Documents');plain=folder/'public-r6-input.pdf';encrypted=folder/'public-r6-encrypted.pdf'
assert not plain.exists() and not encrypted.exists()
objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
 b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << >> /Contents 4 0 R >>']
stream=b'0 0 1 rg 10 10 180 180 re f\n'
objects.append(b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'endstream')
data=bytearray(b'%PDF-1.4\n');offsets=[0]
for number,obj in enumerate(objects,1):
 offsets.append(len(data));data+=str(number).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
xref=len(data);data+=b'xref\n0 5\n0000000000 65535 f \n'
for offset in offsets[1:]:data+=f'{offset:010} 00000 n \n'.encode()
data+=b'trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n'+str(xref).encode()+b'\n%%EOF\n'
plain.write_bytes(data)
try:
 subprocess.run(['qpdf','--encrypt','a'*127,'public-synthetic-owner','256','--',str(plain),str(encrypted)],
  check=True,capture_output=True,timeout=10)
 for p in (plain,encrypted):os.chown(p,1000,1000);p.chmod(0o600)
 c.grant(folder,c.ROLES[app],content=True)
 code='''import json,resource,subprocess,sys
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
probe="import cairo,gi,json,sys;gi.require_version('Poppler','0.18');from gi.repository import Poppler;d=Poppler.Document.new_from_file('file:///mnt/ram/Documents/atril/public-r6-encrypted.pdf',sys.argv[1]);s=cairo.ImageSurface(cairo.FORMAT_ARGB32,200,200);d.get_page(0).render(cairo.Context(s));s.flush();p=bytes(s.get_data()[100*s.get_stride()+400:100*s.get_stride()+404]);print(json.dumps({'pages':d.get_n_pages(),'blue_pixel':p==bytes([255,0,0,255])}))"
out={}
for name,password in [('correct_127','a'*127),('correct_truncated_128','a'*128),('correct_truncated_1024','a'*1024),('incorrect_short','public-wrong-password'),('incorrect_long','b'*1024)]:
 r=subprocess.run([sys.executable,'-I','-c',probe,password],capture_output=True,timeout=15)
 result=json.loads(r.stdout) if r.returncode==0 else {}
 out[name]={'exit':r.returncode,'one_page_reported':result.get('pages')==1,'blue_page_rendered':result.get('blue_pixel',False),'crashed':r.returncode<0,'public_fixture_stderr':r.stderr.decode(errors='replace')[-500:]}
print(json.dumps(out))
'''
 r=subprocess.run(c.sandbox(app,['aa-exec','-p','petalos_offline_atril','--','python3','-I','-c',code]),
  capture_output=True,text=True,timeout=90)
 assert r.returncode==0,'PDF fixture failed; raw output suppressed'
 cases=json.loads(r.stdout)
 version=subprocess.check_output(['dpkg-query','-W','-f=${Version}','libpoppler147'],text=True)
 print(json.dumps({'package_version':version,
  'cases':cases,'under_actual_Atril_role':True,'synthetic_document_only':True}))
 assert cases['correct_127']['exit']==0 and cases['incorrect_short']['exit']!=0
 if version.endswith('+petalos1'):
  assert all(cases[n]['exit']==0 and cases[n]['blue_page_rendered'] for n in ('correct_127','correct_truncated_128','correct_truncated_1024'))
  assert all(cases[n]['exit']>0 and not cases[n]['crashed'] for n in ('incorrect_short','incorrect_long'))
finally:
 plain.unlink(missing_ok=True);encrypted.unlink(missing_ok=True)
