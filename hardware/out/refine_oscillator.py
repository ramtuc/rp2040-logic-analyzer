import pathlib
import re
import sys
import shutil
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import manual_complete as m
src,dst=sys.argv[1:3]
text=pathlib.Path(src).read_text(encoding='utf-8')
def remove(match):
    block=match.group(0)
    return '' if any('(net "'+n+'")' in block for n in ['/XIN','/XOUT','/XTAL_DRV']) and '(locked yes)' not in block else block
text=re.sub(r'\n\t\((?:segment|via)\n.*?\n\t\)',remove,text,flags=re.S)
clean=pathlib.Path(dst).with_name('oscillator-clean.kicad_pcb');clean.write_text(text,encoding='utf-8')
shutil.copy2('rp2040-logic-analyzer.kicad_pro',str(clean.with_suffix('.kicad_pro')))
b=m.p.LoadBoard(str(clean));router=m.Router(b)
pads={(f.GetReference(),q.GetNumber()):q for f in b.GetFootprints() for q in f.Pads()}
for a,z in [(('U1','21'),('R21','1')),(('U1','20'),('X1','1')),(('C23','1'),('X1','1')),(('R21','2'),('X1','3')),(('C24','1'),('X1','3'))]:
    assert pads[a].GetNetname()==pads[z].GetNetname(),(a,z,pads[a].GetNetname(),pads[z].GetNetname())
    router.route(pads[a],pads[z])
b.Save(dst);shutil.copy2('rp2040-logic-analyzer.kicad_pro',str(pathlib.Path(dst).with_suffix('.kicad_pro')))
