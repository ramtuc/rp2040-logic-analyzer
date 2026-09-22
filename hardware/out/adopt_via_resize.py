"""Verify isolated via changes, then adopt into the working KiCad project."""
import collections
import hashlib
import json
import pathlib
import shutil
import pcbnew as p
import wx
wx.DisableAsserts()

root = pathlib.Path(__file__).resolve().parent.parent
out = root / 'out' / 'via-0p3'
name = 'rp2040-logic-analyzer'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
for ext in ('.kicad_pcb', '.kicad_pro', '.kicad_sch'):
    assert sha(root / (name + ext)) == sha(out / ('original' + ext)), 'Source changed: ' + ext
assert not (root / (name + '.kicad_dru')).exists(), 'Preserve existing custom rules'
old = p.LoadBoard(str(out / 'original.kicad_pcb'))
new = p.LoadBoard(str(out / (name + '.kicad_pcb')))
pos = lambda pt: (pt.x, pt.y)
def track_state(board):
    return {t.m_Uuid.AsString(): (t.Type(), t.GetNetname(), pos(t.GetStart()), pos(t.GetEnd()),
            t.GetFrontWidth() if t.Type() == p.PCB_VIA_T else t.GetWidth(), t.GetLayer(), t.IsLocked()) for t in board.GetTracks()}
def footprint_state(board):
    return {f.m_Uuid.AsString(): (f.GetReference(), pos(f.GetPosition()), f.GetOrientationDegrees(),
            tuple(sorted((q.GetNumber(), q.GetNetname(), pos(q.GetPosition()), pos(q.GetSize()),
                          pos(q.GetDrillSize())) for q in f.Pads()))) for f in board.GetFootprints()}
assert track_state(old) == track_state(new), 'Track geometry or via position/diameter changed'
assert footprint_state(old) == footprint_state(new), 'Footprint or pad changed'
old_vias = {v.m_Uuid.AsString(): v for v in old.GetTracks() if v.Type() == p.PCB_VIA_T}
counts = collections.Counter()
for v in new.GetTracks():
    if v.Type() != p.PCB_VIA_T:
        continue
    assert v.GetDrillValue() == max(p.FromMM(.3), old_vias[v.m_Uuid.AsString()].GetDrillValue())
    counts[(round(p.ToMM(v.GetDrillValue()), 4), round(p.ToMM(v.GetFrontWidth()), 4))] += 1
drc = json.loads((out / (name + '.drc.json')).read_text(encoding='utf-8'))
assert not drc['unconnected_items']
assert not any(v['severity'] == 'error' for key in ('violations', 'schematic_parity') for v in drc.get(key, []))
for ext in ('.kicad_pcb', '.kicad_pro', '.kicad_dru'):
    shutil.copy2(out / (name + ext), root / (name + ext))
print('Adopted. Via counts (drill, diameter):', dict(counts))
print('Track geometry, via positions/diameters, footprint positions and pad nets preserved.')
