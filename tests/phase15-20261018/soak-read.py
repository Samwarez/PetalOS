from pathlib import Path
import json
r=json.loads(Path('/run/petalos-phase15/soak.json').read_text());print(json.dumps(r))
