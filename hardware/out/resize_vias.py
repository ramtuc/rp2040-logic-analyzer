"""Prepare 0.3 mm minimum drilled vias in an isolated board copy."""
import collections
import json
import pathlib
import shutil
import pcbnew as p
import wx

wx.DisableAsserts()
root = pathlib.Path(__file__).resolve().parent.parent
out = root / 'out' / 'via-0p3'
out.mkdir(exist_ok=True)
name = 'rp2040-logic-analyzer'
for ext in ('.kicad_pcb', '.kicad_pro', '.kicad_sch'):
    backup = out / ('original' + ext)
    if not backup.exists():
        shutil.copy2(root / (name + ext), backup)
board = p.LoadBoard(str(out / 'original.kicad_pcb'))
vias = [t for t in board.GetTracks() if t.Type() == p.PCB_VIA_T]
before = collections.Counter((round(p.ToMM(t.GetDrillValue()), 4), round(p.ToMM(t.GetWidth()), 4)) for t in vias)
changed = []
for via in vias:
    if via.GetDrillValue() < p.FromMM(.3):
        changed.append(str(via.m_Uuid.AsString()))
        via.SetDrill(p.FromMM(.3))
        via.SetWidth(max(via.GetWidth(), p.FromMM(.45)))
board.Save(str(out / (name + '.kicad_pcb')))
pro = json.loads((out / 'original.kicad_pro').read_text(encoding='utf-8'))
rules = pro['board']['design_settings']['rules']
rules['min_through_hole_diameter'] = .3
rules['min_via_diameter'] = .45
rules['min_via_annular_width'] = .075
for nc in pro['net_settings']['classes']:
    nc['via_drill'] = max(nc['via_drill'], .3)
    nc['via_diameter'] = round(max(nc['via_diameter'], nc['via_drill'] + .15), 4)
for size in pro['board']['design_settings'].get('via_dimensions', []):
    if size.get('drill', 0) > 0:
        size['drill'] = max(size['drill'], .3)
        size['diameter'] = round(max(size['diameter'], size['drill'] + .15), 4)
(out / (name + '.kicad_pro')).write_text(json.dumps(pro, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
shutil.copy2(out / 'original.kicad_sch', out / (name + '.kicad_sch'))
print('Original via counts (drill, diameter):', dict(before))
print('Resized:', len(changed), 'of', len(vias))
print('Candidate:', out / (name + '.kicad_pcb'))
