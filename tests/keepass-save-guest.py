#!/usr/bin/python3 -I
"""Actual disposable database lifecycle under the production offline profile.

Never opens an existing database. The fixture password protects test data only;
all fixture files are removed inside the sandbox before it exits.
"""
import json
import subprocess
import sys

sys.path.insert(0, '/usr/local/lib/portable')
import compartments as c

probe = '''from pathlib import Path
import json,secrets,socket,subprocess
p=Path.home()/'Documents'/('petalos-save-fixture-'+secrets.token_hex(12)+'.kdbx')
assert not p.exists()
password=b'public-disposable-fixture-only\\n'
result={}
try:
 r=subprocess.run(['/usr/bin/keepassxc-cli','db-create','-p',str(p)],input=password*2,capture_output=True,timeout=25)
 result['create']=r.returncode==0 and p.is_file()
 if result['create']:
  r=subprocess.run(['/usr/bin/keepassxc-cli','db-info',str(p)],input=password,capture_output=True,timeout=25)
  result['reopen']=r.returncode==0
  r=subprocess.run(['/usr/bin/keepassxc-cli','mkdir',str(p),'Public fixture group'],input=password,capture_output=True,timeout=25)
  result['update']=r.returncode==0
  r=subprocess.run(['/usr/bin/keepassxc-cli','ls',str(p)],input=password,capture_output=True,timeout=25)
  result['updated_group_readable']=r.returncode==0 and b'Public fixture group' in r.stdout
 for family,key in ((socket.AF_INET,'ipv4_denied'),(socket.AF_INET6,'ipv6_denied')):
  try:s=socket.socket(family);s.close();result[key]=False
  except PermissionError:result[key]=True
 print(json.dumps(result))
finally:p.unlink(missing_ok=True)
'''
c.storage_setup('offline-keepassxc')
result = subprocess.run(c.sandbox('offline-keepassxc', [
    '/usr/bin/aa-exec', '-p', 'petalos_offline_keepassxc', '--',
    '/usr/bin/python3', '-I', '-c', probe]), capture_output=True, text=True, timeout=110)
assert result.returncode == 0, 'Database fixture failed; raw output suppressed.'
report = json.loads(result.stdout)
print(json.dumps(report, sort_keys=True))
assert len(report) == 6 and all(report.values()), 'Database lifecycle or network isolation failed.'
