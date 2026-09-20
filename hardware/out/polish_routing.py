"""Restore useful route widths with geometric copper/hole clearance checks."""
import math
import pathlib
import shutil
import sys
import pcbnew as p
import wx
wx.DisableAsserts()
src,dst=sys.argv[1:3]
b=p.LoadBoard(src)
MM=p.FromMM
power=lambda n:n in ['+3V3','+5V','VREF','/DVDD']
tracks=list(b.GetTracks());pads=[q for f in b.GetFootprints() for q in f.Pads()]
changes=[]
for t in tracks:
    if t.Type()!=p.PCB_TRACE_T or t.IsLocked():continue
    old=p.ToMM(t.GetWidth());net=t.GetNetname();layer=t.GetLayer()
    widths=[.5,.4,.3,.25,.2,.15] if power(net) else [.2,.15]
    if net in ['/USB_DP','/USB_DM']:widths=[.3,.2,.15]
    if old>=widths[0]:continue
    bb=t.GetBoundingBox();bb.Inflate(MM(1.0))
    obs=[]
    for q in pads+tracks:
        if q.GetNetname()==net or not q.IsOnLayer(layer) or not bb.Intersects(q.GetBoundingBox()):continue
        clear=.2 if power(net) or power(q.GetNetname()) else .15
        obs.append((q.GetEffectiveShape(layer),MM(clear)+2000))
        if q.Type()==p.PCB_VIA_T:
            obs.append((p.SHAPE_CIRCLE(q.GetPosition(),q.GetDrillValue()//2),MM(.25)+2000))
    chosen=None
    for width in widths:
        if width<old and old>=.15:break
        shape=p.SHAPE_SEGMENT(t.GetStart(),t.GetEnd(),MM(width))
        if all(not (s.Collide(shape.GetSeg(),c+MM(width)//2) if isinstance(s,p.SHAPE_CIRCLE) else s.Collide(shape,c)) for s,c in obs):chosen=width;break
    if chosen is not None and chosen!=old:
        t.SetWidth(MM(chosen));changes.append((net,old,chosen,round(p.ToMM(t.GetLength()),3)))
    elif old<.15:
        t.SetWidth(MM(.15));changes.append((net,old,.15,'minimum width; DRC required'))
print('width changes',len(changes))
b.Save(dst)
shutil.copy2('rp2040-logic-analyzer.kicad_pro',str(pathlib.Path(dst).with_suffix('.kicad_pro')))
