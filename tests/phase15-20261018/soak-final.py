from pathlib import Path
import collections,json,subprocess,time
root=Path('/run/petalos-phase15');out={}
for name in ('soak','soak-load'):
 r=json.loads((root/(name+'.json')).read_text());out[name]=r
logs=subprocess.check_output(['journalctl','-b','-k','--no-pager','-o','cat'],text=True)
patterns={'oom':'out of memory','killed_process':'killed process','I_O_error':'i/o error','segfault':'segfault','kernel_bug':'bug:'}
out['kernel_error_counts']={k:logs.lower().count(s) for k,s in patterns.items()}
out['failed_services']=subprocess.check_output(['systemctl','--failed','--no-legend','--plain'],text=True).splitlines()
out['journal_RAM_usage_bytes']=sum(p.stat().st_size for p in Path('/run/log/journal').rglob('*') if p.is_file())
import base64,zlib
print(json.dumps({'compressed_public_metadata':base64.b64encode(zlib.compress(json.dumps(out).encode())).decode()}))
