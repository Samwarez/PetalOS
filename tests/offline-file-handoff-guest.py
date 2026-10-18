#!/usr/bin/python3 -I
"""Selected-file handoff using public RAM fixtures only, without content logs."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
sys.path.insert(0,'/usr/local/lib/portable')
import compartments as c
from offline_files import opened_as_petal, delegate
assert os.geteuid()==0
base=Path(tempfile.mkdtemp(prefix='petalos-public-handoff-',dir='/run'));base.chmod(0o755)
fds=[]
try:
    selected=base/'selected.txt';selected.write_text('public-selected-fixture');selected.chmod(0o644)
    neighbor=base/'neighbor.txt';neighbor.write_text('public-neighbor-fixture');neighbor.chmod(0o644)
    restricted=base/'restricted.txt';restricted.write_text('public-permission-fixture');restricted.chmod(0o600)
    report={}
    private_selection=base/'private-selection.txt';private_selection.write_text('public-selected-fixture');os.chown(private_selection,1000,1000);private_selection.chmod(0o600)
    try:
        fd=opened_as_petal(restricted);os.close(fd);report['root_permissions_not_used']=False
    except RuntimeError:report['root_permissions_not_used']=True
    link=base/'link.txt';link.symlink_to(selected)
    try:
        fd=opened_as_petal(link);os.close(fd);report['symlink_leaf_rejected']=False
    except RuntimeError:report['symlink_leaf_rejected']=True
    fifo=base/'fifo';os.mkfifo(fifo)
    try:
        fd=opened_as_petal(fifo);os.close(fd);report['nonregular_item_rejected']=False
    except RuntimeError:report['nonregular_item_rejected']=True
    args,binds,fds=delegate([str(selected)],'geany')
    inode=selected.stat().st_ino
    selected.rename(base/'original.txt');selected.write_text('public-replacement-fixture');selected.chmod(0o644)
    report['authorized_inode_pinned_across_rename']=os.fstat(fds[0]).st_ino==inode
    probe='''import json,os
from pathlib import Path
p=Path(SELECTED)
r={'selected_file_readable':p.read_text()=='public-selected-fixture','neighbor_not_exposed':not Path(NEIGHBOR).exists()}
try:p.write_text('public-write-attempt');r['selected_file_read_only']=False
except OSError:r['selected_file_read_only']=True
print(json.dumps(r))
'''.replace('SELECTED',repr(args[0])).replace('NEIGHBOR',repr(str(neighbor)))
    result=subprocess.run(c.sandbox('offline-geany',['/usr/bin/aa-exec','-p','petalos_offline_geany','--','/usr/bin/python3','-I','-c',probe],extra_binds=binds),pass_fds=tuple(fds),capture_output=True,text=True,timeout=20)
    assert result.returncode==0,'File handoff fixture failed; raw output suppressed.'
    report.update(json.loads(result.stdout))
    for fd in fds:os.close(fd)
    fds=[]
    args,binds,fds=delegate([str(private_selection)],'geany')
    report['private_selection_original_permissions_preserved']=private_selection.stat().st_uid==1000 and private_selection.stat().st_mode & 0o777==0o600
    result=subprocess.run(c.sandbox('offline-geany',['/usr/bin/aa-exec','-p','petalos_offline_geany','--','/usr/bin/python3','-I','-c',probe.replace('/run/petalos-opened/item-1.txt',args[0])],extra_binds=binds),pass_fds=tuple(fds),capture_output=True,text=True,timeout=20)
    assert result.returncode==0,'Private-mode selected-file fixture failed; raw output suppressed.'
    report['mode_0600_selection_readable_as_ram_snapshot']=all(json.loads(result.stdout).values())
    print(json.dumps(report,sort_keys=True));assert all(report.values())
finally:
    for fd in fds:os.close(fd)
    shutil.rmtree(base)
