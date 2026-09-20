"""Read-only schematic audit; generated evidence is confined to out/review."""
import hashlib
import json
import pathlib
import subprocess
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'tools'))
import gen_schematic as g
import check_kit5 as kit
import verify_netlist as verify
hw=pathlib.Path(__file__).resolve().parent.parent
out=hw/'out'/'review';out.mkdir(exist_ok=True)
sch=hw/'rp2040-logic-analyzer.kicad_sch'
def cli(*args):
    result=subprocess.run([str(g.KICAD_CLI),*map(str,args)],capture_output=True,text=True,encoding='utf-8',errors='replace')
    print(result.stdout.strip())
    if result.returncode:print(result.stderr);raise SystemExit(result.returncode)
cli('sch','erc','--severity-all','--format','json','-o',out/'erc.json',sch)
cli('sch','export','netlist','--format','kicadsexpr','-o',out/'current.net',sch)
comps,nets=kit.load(out/'current.net')
expected=verify.expected();fail=[]
for name,nodes in expected.items():
    actual={q for q in nets.get(name,set()) if not q[0].startswith('#')}
    if actual!=nodes:fail.append(dict(net=name,missing=sorted(nodes-actual),extra=sorted(actual-nodes)))
details={}
for ref,c in comps.items():
    c['pins']={pin:name for name,nodes in nets.items() for r,pin in nodes if r==ref}
    details[ref]=c
erc=json.loads((out/'erc.json').read_text(encoding='utf-8'))
print('ERC',[(s['path'],len(s['violations'])) for s in erc['sheets']])
print('Expected nets',len(expected),'mismatches',fail)
print('Parts',len(comps))
class ReviewPaths:
    def __truediv__(self, key):
        if key != 'out':
            raise ValueError(key)
        return out

# Reuse the existing 17 checks against this freshly exported netlist, while
# redirecting all evidence output into this review's directory.
kit.HW = ReviewPaths()
kit.PROJECT = 'current'
kit_status = kit.main()
for ref in ['U1','U2','U3','U7','U8','SW1','SW2','SW3','C21','C22','C25','C26','R24','J4']:
    print(ref,json.dumps(details[ref],ensure_ascii=False))
(out/'audit.json').write_text(json.dumps(dict(schematic_sha256=hashlib.sha256(sch.read_bytes()).hexdigest(),expected_nets=len(expected),mismatches=fail,components=details,nets={k:sorted(v) for k,v in nets.items()}),ensure_ascii=False,indent=2),encoding='utf-8')
if fail or kit_status or any(s['violations'] for s in erc['sheets']):
    raise SystemExit(1)
