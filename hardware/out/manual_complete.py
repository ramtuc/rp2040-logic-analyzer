"""Deterministic two-outer-layer maze routing for residual KiCad connections.

No design rules are disabled. Result must pass KiCad DRC before adoption.
"""
import heapq
import json
import math
import pathlib
import shutil
import sys
import time
import numpy as np
import pcbnew as p
import wx
wx.DisableAsserts()

STEP=.05
X0,Y0=100.,100.
NX,NY=1301,901
LAYERS=[p.F_Cu,p.B_Cu]
MM=p.FromMM
V=lambda x,y:p.VECTOR2I(MM(x),MM(y))
xy=lambda q:(p.ToMM(q.x),p.ToMM(q.y))
grid=lambda x,y:(int(round((x-X0)/STEP)),int(round((y-Y0)/STEP)))
world=lambda x,y:(X0+x*STEP,Y0+y*STEP)

def power(net): return net in ['+3V3','+5V','VREF','/DVDD']

class Router:
    def __init__(self,b):
        self.b=b
        self.pads=[q for f in b.GetFootprints() for q in f.Pads()]
        self.tracks=list(b.GetTracks())
        self.lookup={q.m_Uuid.AsString():q for q in self.pads+self.tracks}

    def masks(self,net,width):
        masks=np.zeros((3,NY,NX),dtype=np.bool_)
        def rect(layer,x0,y0,x1,y1,r):
            a=max(0,int((x0-r-X0)/STEP)-1);c=min(NX,int((x1+r-X0)/STEP)+2)
            b=max(0,int((y0-r-Y0)/STEP)-1);d=min(NY,int((y1+r-Y0)/STEP)+2)
            if a>=c or b>=d:return
            xx=X0+np.arange(a,c)[None,:]*STEP;yy=Y0+np.arange(b,d)[:,None]*STEP
            dx=np.maximum(np.maximum(x0-xx,xx-x1),0);dy=np.maximum(np.maximum(y0-yy,yy-y1),0)
            masks[layer,b:d,a:c] |= dx*dx+dy*dy <= r*r
        def line(layer,x0,y0,x1,y1,r):
            a=max(0,int((min(x0,x1)-r-X0)/STEP)-1);c=min(NX,int((max(x0,x1)+r-X0)/STEP)+2)
            b=max(0,int((min(y0,y1)-r-Y0)/STEP)-1);d=min(NY,int((max(y0,y1)+r-Y0)/STEP)+2)
            if a>=c or b>=d:return
            xx=X0+np.arange(a,c)[None,:]*STEP;yy=Y0+np.arange(b,d)[:,None]*STEP
            dx=x1-x0;dy=y1-y0; length=dx*dx+dy*dy
            t=np.clip(((xx-x0)*dx+(yy-y0)*dy)/length,0,1) if length else 0
            masks[layer,b:d,a:c] |= (xx-x0-t*dx)**2+(yy-y0-t*dy)**2<=r*r
        for q in self.pads:
            ls=[i for i,l in enumerate(LAYERS) if q.IsOnLayer(l)]
            if not ls:continue
            bb=q.GetBoundingBox();x0,y0=xy(bb.GetOrigin());x1,y1=xy(bb.GetEnd())
            other=q.GetNetname()!=net
            clear=.2 if power(net) or power(q.GetNetname()) else .15
            if other:
                for i in ls:rect(i,x0,y0,x1,y1,clear+width/2+.008)
                rect(2,x0,y0,x1,y1,max(clear+.225,.25+.125)+.008)
            if q.GetAttribute() in (p.PAD_ATTRIB_PTH,p.PAD_ATTRIB_NPTH):
                x,y=xy(q.GetPosition());ds=xy(q.GetDrillSize());rr=max(ds)/2
                rect(2,x,y,x,y,rr+.125+.25+.008)
        for q in self.tracks:
            via=q.Type()==p.PCB_VIA_T
            other=q.GetNetname()!=net
            x0,y0=xy(q.GetStart());x1,y1=xy(q.GetEnd())
            rr=p.ToMM(q.GetFrontWidth() if via else q.GetWidth())/2
            clear=.2 if power(net) or power(q.GetNetname()) else .15
            if other:
                ls=range(2) if via else [i for i,l in enumerate(LAYERS) if q.GetLayer()==l]
                for i in ls:line(i,x0,y0,x1,y1,rr+width/2+clear+.008)
                line(2,x0,y0,x1,y1,rr+max(clear+.225,.375)+.008)
            if via:
                line(2,x0,y0,x0,y0,p.ToMM(q.GetDrillValue())/2+.125+.25+.008)
        for i in range(3):
            margin=.3+(width/2 if i<2 else .225)+.01
            k=int(math.ceil(margin/STEP))
            masks[i,:k,:]=True;masks[i,-k:,:]=True;masks[i,:,:k]=True;masks[i,:,-k:]=True
        return masks

    def component(self,item):
        conn=self.b.GetConnectivity();seen={};stack=[item]
        while stack:
            q=stack.pop();uid=q.m_Uuid.AsString()
            if uid in seen:continue
            seen[uid]=q
            stack.extend(conn.GetConnectedTracks(q));stack.extend(conn.GetConnectedPads(q))
        return list(seen.values())

    def points(self,items):
        out={}
        for q in items:
            if q.Type()==p.PCB_TRACE_T:
                a=xy(q.GetStart());b=xy(q.GetEnd());ls=[LAYERS.index(q.GetLayer())] if q.GetLayer() in LAYERS else []
                n=max(1,int(math.dist(a,b)/STEP))
                pts=[(a[0]+(b[0]-a[0])*t/n,a[1]+(b[1]-a[1])*t/n) for t in range(n+1)]
            else:
                pts=[xy(q.GetPosition())]
                ls=[i for i,l in enumerate(LAYERS) if q.IsOnLayer(l)]
            for pt in pts:
                x,y=grid(*pt)
                if 0<=x<NX and 0<=y<NY:
                    for z in ls:out[(z,y,x)]=pt
        return out

    def route(self,a,b,width=.15):
        net=a.GetNetname();started=time.time()
        source=self.points(self.component(a));target=self.points(self.component(b))
        if set(source)&set(target):return True
        masks=self.masks(net,width)
        source={q:v for q,v in source.items() if not masks[q]}
        target={q:v for q,v in target.items() if not masks[q]}
        if not source or not target:
            print('blocked terminal',net,len(source),len(target),flush=True);return False
        # A bounding-box distance is an admissible lower bound to a complex target.
        tx0=min(q[2] for q in target);tx1=max(q[2] for q in target)
        ty0=min(q[1] for q in target);ty1=max(q[1] for q in target)
        def heuristic(q):
            z,y,x=q;dx=max(tx0-x,0,x-tx1);dy=max(ty0-y,0,y-ty1)
            return max(dx,dy)+.41421356*min(dx,dy)
        dist={q:0. for q in source};parent={q:None for q in source}
        heap=[(heuristic(q),0.,q) for q in source];heapq.heapify(heap)
        moves=[(dx,dy,math.hypot(dx,dy)) for dx,dy in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]]
        visits=0;end=None
        while heap:
            _,cost,q=heapq.heappop(heap)
            if cost!=dist.get(q):continue
            if q in target:end=q;break
            visits+=1
            if visits%50000==0 and time.time()-started>65:break
            z,y,x=q
            for dx,dy,dc in moves:
                xx=x+dx;yy=y+dy
                if not (0<=xx<NX and 0<=yy<NY) or masks[z,yy,xx]:continue
                if dx and dy and (masks[z,y,xx] or masks[z,yy,x]):continue
                nq=(z,yy,xx);nc=cost+dc
                if nc<dist.get(nq,float('inf')):
                    dist[nq]=nc;parent[nq]=q;heapq.heappush(heap,(nc+heuristic(nq)*1.12,nc,nq))
            if net not in ['/XOUT','/XIN','/XTAL_DRV'] and not masks[2,y,x] and not masks[1-z,y,x]:
                nq=(1-z,y,x);nc=cost+80
                if nc<dist.get(nq,float('inf')):
                    dist[nq]=nc;parent[nq]=q;heapq.heappush(heap,(nc+heuristic(nq)*1.12,nc,nq))
        if end is None:
            print('no path',net,visits,round(time.time()-started,1),flush=True);return False
        path=[];q=end
        while q is not None:path.append(q);q=parent[q]
        path.reverse()
        def track(start,end,layer):
            if math.dist(start,end)<.00001:return
            q=p.PCB_TRACK(self.b);q.SetStart(V(*start));q.SetEnd(V(*end));q.SetLayer(LAYERS[layer]);q.SetWidth(MM(width));q.SetNet(a.GetNet());self.b.Add(q);self.tracks.append(q)
        z,y,x=path[0];last=world(x,y);track(source[path[0]],last,z)
        for j in range(1,len(path)):
            zz,yy,xx=path[j];prev=path[j-1];pt=world(xx,yy)
            if zz!=prev[0]:
                track(last,pt,prev[0]);q=p.PCB_VIA(self.b);q.SetPosition(V(*pt));q.SetWidth(MM(.45));q.SetDrill(MM(.25));q.SetViaType(p.VIATYPE_THROUGH);q.SetLayerPair(p.F_Cu,p.B_Cu);q.SetNet(a.GetNet());self.b.Add(q);self.tracks.append(q);last=pt
            elif j==len(path)-1 or (path[j+1][0]!=zz) or (xx-prev[2],yy-prev[1])!=(path[j+1][2]-xx,path[j+1][1]-yy):
                track(last,pt,zz);last=pt
        track(last,target[end],end[0])
        self.b.BuildConnectivity()
        print('routed',net,'length cost',round(dist[end]*STEP,2),'visited',visits,'seconds',round(time.time()-started,1),flush=True)
        return True

if __name__=='__main__':
    src,report,dst=sys.argv[1:4]
    b=p.LoadBoard(src);r=Router(b)
    data=json.loads(pathlib.Path(report).read_text(encoding='utf-8'))
    connections=sorted(data['unconnected_items'], key=lambda v: 0 if '/GP22' in v['items'][0]['description'] else 1 if '/XOUT' in v['items'][0]['description'] else 2)
    for v in connections:
        a,c=[r.lookup.get(i['uuid']) for i in v['items'][:2]]
        if a is not None and c is not None:r.route(a,c)
    b.Save(dst)
    shutil.copy2('rp2040-logic-analyzer.kicad_pro',str(pathlib.Path(dst).with_suffix('.kicad_pro')))
