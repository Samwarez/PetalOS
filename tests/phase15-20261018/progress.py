from pathlib import Path
import json,subprocess
out={}
for name in ('soak','soak-load'):
 p=Path('/run/petalos-phase15')/(name+'.json');r=json.loads(p.read_text());out[name]={'phase':r['phase'],'last_sample':r['samples'][-1] if r['samples'] else None,'stress_workers_reaped':r.get('stress_workers_reaped',False)}
print(json.dumps(out))
