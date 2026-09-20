"""Run KiCad DRC and summarize without suppressing errors or warnings."""
import json
import pathlib
import subprocess
import sys
from collections import Counter
board=pathlib.Path(sys.argv[1]).resolve()
report=board.with_suffix('.drc.json')
args=[r'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe','pcb','drc','--refill-zones','--format','json','-o',str(report)]
if '--parity' in sys.argv: args.append('--schematic-parity')
if '--save' in sys.argv: args.append('--save-board')
args.append(str(board))
result=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace')
print(result.stdout)
if result.returncode:
    print(result.stderr)
    raise SystemExit(result.returncode)
d=json.loads(report.read_text(encoding='utf-8'))
for k in ['violations','unconnected_items','schematic_parity']:
    items=d.get(k,[])
    print(k,len(items),dict(Counter((v['severity'],v['type']) for v in items)))
    for v in items:
        if v['severity']=='error':
            print(v['type'],v['description'])
            for i in v['items']: print(' ',i['description'],i['pos'],i['uuid'])
