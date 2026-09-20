"""Routing work helper; run with KiCad's bundled Python."""
import json
import pathlib
import sys
import pcbnew
import wx
wx.DisableAsserts()
import shutil
import re

def render(src, dst):
    from PIL import Image, ImageDraw, ImageFont
    b=pcbnew.LoadBoard(src)
    scale=30
    xy=lambda v: (round((pcbnew.ToMM(v.x)-98)*scale),round((pcbnew.ToMM(v.y)-98)*scale))
    im=Image.new('RGB',(2070,1470),'#141c25'); d=ImageDraw.Draw(im)
    for layer,color in [(pcbnew.B_Cu,'#426cb0'),(pcbnew.F_Cu,'#d15b53')]:
        for t in b.GetTracks():
            if t.Type()!=pcbnew.PCB_VIA_T and t.GetLayer()==layer:
                d.line([xy(t.GetStart()),xy(t.GetEnd())],fill=color,width=max(1,round(pcbnew.ToMM(t.GetWidth())*scale)))
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
    for f in b.GetFootprints():
        for p in f.Pads():
            if p.IsOnLayer(pcbnew.F_Cu):
                bb=p.GetBoundingBox(); d.rectangle([xy(bb.GetOrigin()),xy(bb.GetEnd())],fill='#b6a75b')
        pos=xy(f.GetPosition()); d.text((pos[0]+8,pos[1]+8),f.GetReference(),fill='white',font=font)
    for t in b.GetTracks():
        if t.Type()==pcbnew.PCB_VIA_T:
            x,y=xy(t.GetPosition());r=pcbnew.ToMM(t.GetFrontWidth())*scale/2
            d.ellipse((x-r,y-r,x+r,y+r),fill='#b6a75b');d.ellipse((x-2,y-2,x+2,y+2),fill='#141c25')
    d.rectangle((60,60,2010,1410),outline='white',width=2)
    im.save(dst)

def prepare(src, dst):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'tools'))
    from fanout_planes import Fanout, load_classes, INWARD_FIRST
    b=pcbnew.LoadBoard(src)
    classes,patterns=load_classes('rp2040-logic-analyzer.kicad_pro')
    fan=Fanout(b,classes,patterns)
    INWARD_FIRST.add('U1')
    for f in b.GetFootprints():
        for p in f.Pads():
            if (f.GetReference()=='U1' and p.GetNetname()=='/DVDD') or (f.GetReference() in ['J1','U8'] and p.GetNetname()=='+5V'):
                if not fan.has_plane_link(p):
                    print(f.GetReference(),p.GetNumber(),p.GetNetname(),fan.try_pad(p))
    print('skipped',fan.skipped)
    pathlib.Path(dst).parent.mkdir(parents=True,exist_ok=True)
    b.Save(dst)
    shutil.copy2('rp2040-logic-analyzer.kicad_pro',str(pathlib.Path(dst).with_suffix('.kicad_pro')))

def escape(src,dst):
    sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2] / 'tools'))
    import fanout_planes as mod
    b=pcbnew.LoadBoard(src)
    classes,patterns=mod.load_classes('rp2040-logic-analyzer.kicad_pro')
    for c in classes.values():
        c['via_diameter']=0.45;c['via_drill']=0.25
    mod.GAPS=[0.05,0.1,0.15,0.2,0.25,0.3,0.4,0.5,0.6,0.75,0.9,1.1,1.3,1.5]
    fan=mod.Fanout(b,classes,patterns)
    fan.stub_width=lambda p,n:0.15
    fan.lane_conflict=lambda *a:None
    targets={'U1':['23','24','27','31','32','34','50'],'J1':['A5','A4','B9'],'U8':['5']}
    for f in b.GetFootprints():
        for p in f.Pads():
            if p.GetNumber() in targets.get(f.GetReference(),[]) and not fan.has_plane_link(p):
                print(f.GetReference(),p.GetNumber(),fan.try_pad(p))
    print('placed',fan.placed); print('skipped',fan.skipped)
    b.Save(dst)
    shutil.copy2('rp2040-logic-analyzer.kicad_pro',str(pathlib.Path(dst).with_suffix('.kicad_pro')))

def snapshot(path):
    b = pcbnew.LoadBoard(str(path))
    xy = lambda v: [pcbnew.ToMM(v.x), pcbnew.ToMM(v.y)]
    fps = {}
    for f in b.GetFootprints():
        fps[f.GetReference()] = dict(uuid=f.m_Uuid.AsString(), pos=xy(f.GetPosition()), angle=f.GetOrientationDegrees(), pads=[dict(number=p.GetNumber(), net=p.GetNetname(), pos=xy(p.GetPosition()), size=xy(p.GetSize())) for p in f.Pads()])
    tracks=[]
    for t in b.GetTracks():
        via=t.Type()==pcbnew.PCB_VIA_T
        tracks.append(dict(uuid=t.m_Uuid.AsString(), net=t.GetNetname(), start=xy(t.GetStart()), end=xy(t.GetEnd()), layer=b.GetLayerName(t.GetLayer()), width=pcbnew.ToMM(t.GetFrontWidth() if via else t.GetWidth()), via=via, locked=t.IsLocked()))
    print(json.dumps(dict(footprints=fps,tracks=tracks,zones=[dict(net=z.GetNetname(),layer=b.GetLayerName(z.GetLayer()),rule=z.GetIsRuleArea()) for z in b.Zones()])))

if __name__=='__main__':
    if sys.argv[1]=='prepare': prepare(*sys.argv[2:])
    elif sys.argv[1]=='render': render(*sys.argv[2:])
    elif sys.argv[1]=='escape': escape(*sys.argv[2:])
    else: snapshot(sys.argv[1])
