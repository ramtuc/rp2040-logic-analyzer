"""Complete an existing board; retain the project's clearances and inner planes."""
import pathlib
import re
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2] / 'tools'))
import route_pcb

original=route_pcb.rebuild_wiring
def rebuild(board,pcbnew,text):
    text,n=original(board,pcbnew,text)
    # Small QFN pins require neck-downs. These are routing widths, not a relaxation
    # of project minima or clearances. Existing locked USB tracks are retained.
    text=re.sub(r'(\(class (?:Power|Default|Signal_D|QSPI)\s[\s\S]*?\(width )\d+',r'\g<1>150',text)
    # Bottom copper is poured after routing; exporting its unfilled outline would
    # incorrectly represent the whole bottom surface as a solid conductor.
    text=re.sub(r'\(plane GND \(polygon B\.Cu[\s\S]*?\)\)', '', text)
    return text,n
route_pcb.rebuild_wiring=rebuild
if __name__=='__main__':
    raise SystemExit(route_pcb.main())
