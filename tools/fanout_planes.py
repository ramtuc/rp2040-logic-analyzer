"""
GND / +3V3 の SMD パッドに、部品の外側へ向けたスタブ＋ビアを付けて内層ベタ（In1 = GND・In2 = +3V3）へ落とす。
KiCad 同梱の python で実行すること:

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools\\fanout_planes.py --input <基板> --output <基板> [--report <md>] [--lock-existing]

やること
    1. --lock-existing: 既存の全 segment / via を locked にする（人間の配線を freerouting から守る）
    2. ベタ配線ネット（GND / +3V3）の SMD パッドのうち、ビアにも THT パッドにも繋がっていないものを列挙する
    3. 各パッドから部品の外側へ短いスタブを出し、その先にビアを置く。位置は候補（真っ直ぐ → 斜め 45° → 横）を
       順に試し、他ネットの銅箔・穴・基板端・隣接ピンの直進レーンとぶつからない最初の候補を採る
       - ビア径 / 穴径・クリアランスはそのネットのネットクラスの値（.kicad_pro）。スタブ幅はクラス幅をパッド幅で頭打ち
       - 追加したスタブ / ビアは locked
    4. ベタ配線ネットの配線で端が浮いているもの（人間が「ここにビア」と残した端）にはその場でビアを置く
    5. 置けなかったパッドは理由付きで報告（freerouting に任せる）

DRC の代わりにはならない。出力後に kicad-cli pcb drc --refill-zones で error 0 を確認すること。
"""

import argparse
import fnmatch
import json
import math
import os
import sys

try:
    import wx
    wx.DisableAsserts()          # pcbnew の assert ダイアログを人間の画面に出さない（層引数無しの GetWidth など）
except Exception:
    pass

import pcbnew

PLANE_NETS = ("GND", "+3V3")
MIN_CLEARANCE = 0.15            # 基板の最小クリアランス（.kicad_pro rules.min_clearance）
HOLE_CLEARANCE = 0.25           # 穴 ↔ 他ネット銅箔（rules.min_hole_clearance）
HOLE_TO_HOLE = 0.25             # 穴 ↔ 穴（rules.min_hole_to_hole）
EDGE_CLEARANCE = 0.3            # 銅箔 ↔ 基板端（rules.min_copper_edge_clearance）
GAPS = [0.30, 0.40, 0.50, 0.60, 0.75, 0.90, 1.05, 1.20, 1.40, 1.60]     # パッド端 → ビア端
LANE_LEN = 1.0                  # 隣接ピン（他ネット）の直進レーンを塞がないようにする長さ

MM = pcbnew.FromMM
TOMM = pcbnew.ToMM


def V(x, y):
    return pcbnew.VECTOR2I(int(round(MM(x))), int(round(MM(y))))


# 手で決める例外: ref または (ref, pad) → 試す方向の優先順（"out" = 部品中心から外向き、"+x" "-x" "+y" "-y"、"diag" = 外向き 45°）
DIRECTION_OVERRIDE = {
    "D1": ["+y"], "D2": ["+y"], "D3": ["+y"],                 # LED カソード: 抵抗側でなく下へ
    "SW2": ["+y"], "SW3": ["+y"],                             # タクトスイッチ GND: 隣のスイッチとぶつからないよう下へ
    ("X1", "2"): ["+y", "+x"], ("X1", "4"): ["-y", "-x"],     # 水晶 GND: XIN/XOUT の通り道（右）を避ける
}
for _c in ("C6", "C9", "C21", "C22", "C10", "C8"):            # 右辺のパスコン列（2.4 ピッチ・横向き）: 横は隣とぶつかるので上下へ
    DIRECTION_OVERRIDE[(_c, "1")] = ["-y", "+y"]
    DIRECTION_OVERRIDE[(_c, "2")] = ["+y", "-y"]

# QFN は部品中心へ向かう「内側」を先に試す（パッド列と EP の間の 1.4 mm の環にビアを置く = 外側のエスケープ路を塞がない）
INWARD_FIRST = {"U1"}

# 隣接 2 ピンを 1 個のビアに合流させる: (ref, [pads]) → (junction, mid, via)
# 43+44 は人間の 48+49（外向き）と違って内側の環へ。外側を DVDD(45)/QSPI の逃げ道として空けるため
MERGE = [
    ("U1", ["44", "43"], (134.4375, 129.4), (133.9, 129.4), (133.3, 129.4)),
]


def board_edge_mm(board):
    """Edge.Cuts の外接矩形（mm）。GetBoardEdgesBoundingBox() は import 経路によって未ラップの SwigPyObject が返ることが
    あった（finish_pcb.py から呼ぶと GetLeft が無い）ので、Edge.Cuts の図形から直接求める"""
    xs, ys = [], []
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        bb = d.GetBoundingBox()
        try:
            xs += [TOMM(bb.GetLeft()), TOMM(bb.GetRight())]
            ys += [TOMM(bb.GetTop()), TOMM(bb.GetBottom())]
        except AttributeError:
            a, b = d.GetStart(), d.GetEnd()
            xs += [TOMM(a.x), TOMM(b.x)]
            ys += [TOMM(a.y), TOMM(b.y)]
    return (min(xs), min(ys), max(xs), max(ys))


def load_classes(pro_path):
    """.kicad_pro のネットクラス（名前 → dict）とパターン割り当て"""
    with open(pro_path, encoding="utf-8") as f:
        pro = json.load(f)
    ns = pro["net_settings"]
    classes = {c["name"]: c for c in ns["classes"]}
    patterns = [(p["pattern"], p["netclass"]) for p in ns.get("netclass_patterns", [])]
    return classes, patterns


class Fanout:
    def __init__(self, board, classes, patterns):
        self.b = board
        self.classes = classes
        self.patterns = patterns
        self.conn = board.GetConnectivity()
        self.new_items = []          # (shape, net, hole_r or None, kind)
        self.placed = []
        self.skipped = []
        self.edge = board_edge_mm(board)
        self.skip_refs = set()
        self.no_merge = False
        self.pads = []
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                self.pads.append(pad)
        self.tracks = list(board.GetTracks())

    # --- ネットクラス値 ---------------------------------------------------------------
    def cls(self, netname):
        name = "Default"
        for pat, nc in self.patterns:
            if fnmatch.fnmatchcase(netname, pat):
                name = nc
                break
        return self.classes[name]

    def clearance(self, net_a, net_b):
        ca = self.cls(net_a)["clearance"] if net_a else MIN_CLEARANCE
        cb = self.cls(net_b)["clearance"] if net_b else MIN_CLEARANCE
        return max(ca, cb, MIN_CLEARANCE)

    # --- 接続状態 ------------------------------------------------------------------------
    def has_plane_link(self, pad):
        """パッドの繋がりの中にビアか THT パッドがあるか（= 既にベタへ落ちている）"""
        seen = set()
        stack = [pad]
        while stack:
            it = stack.pop()
            key = it.m_Uuid.AsString()
            if key in seen:
                continue
            seen.add(key)
            if it.Type() == pcbnew.PCB_VIA_T:
                return True
            if it.Type() == pcbnew.PCB_PAD_T and it.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                return True
            for t in self.conn.GetConnectedTracks(it):
                stack.append(t)
            for p in self.conn.GetConnectedPads(it):
                stack.append(p)
        return False

    # --- 衝突判定 ------------------------------------------------------------------------
    def collides(self, shape, net, hole_r, bbox_mm, ignore=()):
        """shape（SHAPE_CIRCLE / SHAPE_SEGMENT, F.Cu）が他の銅箔とぶつかるか。理由文字列 or None"""
        x0, y0, x1, y1 = bbox_mm
        R = 3.0
        ignore_ids = {p.m_Uuid.AsString() for p in ignore}
        for pad in self.pads:
            if pad.m_Uuid.AsString() in ignore_ids:
                continue
            pnet = pad.GetNetname()
            pos = pad.GetPosition()
            px, py = TOMM(pos.x), TOMM(pos.y)
            if px < x0 - R or px > x1 + R or py < y0 - R or py > y1 + R:
                continue
            is_pth = pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)
            if not is_pth and not pad.IsOnLayer(pcbnew.F_Cu):
                continue
            same = (pnet == net) and pnet != ""
            if not same:
                cl = self.clearance(net, pnet) if pnet else MIN_CLEARANCE
                if pad.GetEffectiveShape(pcbnew.F_Cu).Collide(shape, MM(cl)):
                    return "pad %s-%s [%s]" % (pad.GetParentFootprint().GetReference(), pad.GetNumber(), pnet)
                if hole_r is not None:
                    # 自分の穴 ↔ 相手の銅箔
                    if pad.GetEffectiveShape(pcbnew.F_Cu).Collide(shape, MM(HOLE_CLEARANCE + hole_r - self._shape_r(shape))):
                        return "hole clearance to pad %s-%s" % (pad.GetParentFootprint().GetReference(), pad.GetNumber())
            if is_pth and hole_r is not None:
                d = pad.GetDrillSize()
                pr = TOMM(max(d.x, d.y)) / 2
                c = self._shape_center(shape)
                if c is not None and math.hypot(c[0] - px, c[1] - py) < pr + hole_r + HOLE_TO_HOLE:
                    return "hole-to-hole pad %s-%s" % (pad.GetParentFootprint().GetReference(), pad.GetNumber())
        for t in self.tracks:
            tnet = t.GetNetname()
            is_via = t.Type() == pcbnew.PCB_VIA_T
            if not is_via and t.GetLayer() != pcbnew.F_Cu and hole_r is None:
                continue                                   # 裏面配線とはスタブ（F.Cu）は当たらない
            same = tnet == net
            if not same:
                cl = self.clearance(net, tnet)
                if t.GetEffectiveShape(pcbnew.F_Cu).Collide(shape, MM(cl)):
                    return "track/via [%s] at (%.3f, %.3f)" % (tnet, TOMM(t.GetStart().x), TOMM(t.GetStart().y))
            if is_via and hole_r is not None:
                c = self._shape_center(shape)
                vr = TOMM(t.GetDrillValue()) / 2
                if c is not None and math.hypot(c[0] - TOMM(t.GetPosition().x), c[1] - TOMM(t.GetPosition().y)) < vr + hole_r + HOLE_TO_HOLE:
                    return "hole-to-hole via [%s]" % tnet
        # この実行で置いたスタブ / ビア（SWIG の SHAPE_CIRCLE.Collide は SHAPE* を受けないので自前の幾何で）
        g = self._geom(shape)
        for shp, nnet, nh, kind, g2 in self.new_items:
            cl = self.clearance(net, nnet)
            if self._dist(g, g2) < cl:
                return "new %s [%s]" % (kind, nnet)
            if hole_r is not None and nh is not None and g[0] == "c" and g2[0] == "c":
                if math.hypot(g[1] - g2[1], g[2] - g2[2]) < nh + hole_r + HOLE_TO_HOLE:
                    return "hole-to-hole new via [%s]" % nnet
        return None

    @staticmethod
    def _geom(shape):
        """pcbnew の SHAPE → ("c", x, y, r) / ("s", x1, y1, x2, y2, half_w)（mm）"""
        if isinstance(shape, pcbnew.SHAPE_CIRCLE):
            c = shape.GetCenter()
            return ("c", TOMM(c.x), TOMM(c.y), TOMM(shape.GetRadius()))
        seg = shape.GetSeg()
        return ("s", TOMM(seg.A.x), TOMM(seg.A.y), TOMM(seg.B.x), TOMM(seg.B.y), TOMM(shape.GetWidth()) / 2)

    @staticmethod
    def _pt_seg(px, py, x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
        return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

    @classmethod
    def _dist(cls, a, b):
        """2 つの幾何（円 / 太い線分）の銅箔端どうしの距離（負 = 重なり）"""
        if a[0] == "c" and b[0] == "c":
            return math.hypot(a[1] - b[1], a[2] - b[2]) - a[3] - b[3]
        if a[0] == "c":
            a, b = b, a
        if b[0] == "c":                       # a = seg, b = circle
            return cls._pt_seg(b[1], b[2], a[1], a[2], a[3], a[4]) - a[5] - b[3]
        # seg-seg: 端点 ↔ 相手線分の最短（線分が交差する場合は 0 扱い）
        d = min(cls._pt_seg(a[1], a[2], b[1], b[2], b[3], b[4]), cls._pt_seg(a[3], a[4], b[1], b[2], b[3], b[4]),
                cls._pt_seg(b[1], b[2], a[1], a[2], a[3], a[4]), cls._pt_seg(b[3], b[4], a[1], a[2], a[3], a[4]))
        if cls._intersect(a[1:5], b[1:5]):
            d = 0.0
        return d - a[5] - b[5]

    @staticmethod
    def _intersect(s1, s2):
        def ccw(ax, ay, bx, by, cx, cy):
            return (cx - ax) * (by - ay) - (bx - ax) * (cy - ay)
        x1, y1, x2, y2 = s1
        x3, y3, x4, y4 = s2
        d1 = ccw(x3, y3, x4, y4, x1, y1); d2 = ccw(x3, y3, x4, y4, x2, y2)
        d3 = ccw(x1, y1, x2, y2, x3, y3); d4 = ccw(x1, y1, x2, y2, x4, y4)
        return (d1 * d2 < 0) and (d3 * d4 < 0)

    @staticmethod
    def _shape_center(shape):
        if isinstance(shape, pcbnew.SHAPE_CIRCLE):
            c = shape.GetCenter()
            return (TOMM(c.x), TOMM(c.y))
        return None

    @staticmethod
    def _shape_r(shape):
        if isinstance(shape, pcbnew.SHAPE_CIRCLE):
            return TOMM(shape.GetRadius())
        return 0.0

    def edge_ok(self, x, y, r):
        x0, y0, x1, y1 = self.edge
        m = EDGE_CLEARANCE + r + 0.05
        return x0 + m <= x <= x1 - m and y0 + m <= y <= y1 - m

    def lane_conflict(self, pad, vx, vy, r, net):
        """同じ部品の隣接他ネットパッドが部品外向きに真っ直ぐ LANE_LEN 逃げるレーンとぶつからないか"""
        fp = pad.GetParentFootprint()
        n_pads = len(list(fp.Pads()))
        if n_pads <= 4:
            return None
        for other in fp.Pads():
            onet = other.GetNetname()
            if other is pad or onet == net or onet == "":
                continue
            if other.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            opos = other.GetPosition()
            ox, oy = TOMM(opos.x), TOMM(opos.y)
            if math.hypot(ox - vx, oy - vy) > LANE_LEN + 2.0:
                continue
            ux, uy, half_along, half_across = self.outward(other)
            bb = other.GetBoundingBox()
            lane_w = TOMM(bb.GetWidth()) if abs(uy) > abs(ux) else TOMM(bb.GetHeight())
            start = (ox + ux * half_along, oy + uy * half_along)
            end = (ox + ux * (half_along + LANE_LEN), oy + uy * (half_along + LANE_LEN))
            cl = self.clearance(net, onet)
            if self._dist(("s", start[0], start[1], end[0], end[1], lane_w / 2), ("c", vx, vy, r)) < cl:
                return "lane of %s-%s [%s]" % (fp.GetReference(), other.GetNumber(), onet)
        return None

    # --- 幾何 ---------------------------------------------------------------------------
    def outward(self, pad):
        """部品中心から見た外向きの単位ベクトル（軸方向）と、その方向 / 直交方向のパッド半寸法"""
        fp = pad.GetParentFootprint()
        c = fp.GetPosition()
        p = pad.GetPosition()
        dx, dy = TOMM(p.x - c.x), TOMM(p.y - c.y)
        bb = pad.GetBoundingBox()
        w, h = TOMM(bb.GetWidth()), TOMM(bb.GetHeight())
        if abs(dx) >= abs(dy):
            return (1 if dx >= 0 else -1), 0, w / 2, h / 2
        return 0, (1 if dy >= 0 else -1), h / 2, w / 2

    def directions(self, pad):
        fp = pad.GetParentFootprint()
        ux, uy, _, _ = self.outward(pad)
        ov = DIRECTION_OVERRIDE.get((fp.GetReference(), pad.GetNumber())) or DIRECTION_OVERRIDE.get(fp.GetReference())
        c = fp.GetPosition()
        p = pad.GetPosition()
        dx, dy = TOMM(p.x - c.x), TOMM(p.y - c.y)
        sx = 1 if dx >= 0 else -1
        sy = 1 if dy >= 0 else -1
        named = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1), "out": (ux, uy)}
        dirs = []
        if ov:
            for d in ov:
                dirs.append(named[d])
        if fp.GetReference() in INWARD_FIRST:
            dirs.append((-ux, -uy))
        dirs.append((ux, uy))
        # 外向き 45°（列端のピンはこれで隣のレーンを避ける）
        if ux != 0:
            dirs += [(ux, sy), (ux, -sy)]
        else:
            dirs += [(sx, uy), (-sx, uy)]
        # 直交方向（部品中心から遠ざかる側を先に）
        if ux != 0:
            dirs += [(0, sy), (0, -sy)]
        else:
            dirs += [(sx, 0), (-sx, 0)]
        out = []
        for d in dirs:
            if d not in out:
                out.append(d)
        return out

    def stub_width(self, pad, net):
        bb = pad.GetBoundingBox()
        w = min(TOMM(bb.GetWidth()), TOMM(bb.GetHeight()))
        cw = self.cls(net)["track_width"]
        if net == "GND":
            cw = max(cw, 0.3)                    # GND のスタブは 0.3（クラス最小 0.2 以上・パッド幅で頭打ち）
        return round(max(0.2, min(cw, w)), 3)

    # --- 配置 ---------------------------------------------------------------------------
    def try_pad(self, pad):
        fp = pad.GetParentFootprint()
        ref, num = fp.GetReference(), pad.GetNumber()
        net = pad.GetNetname()
        c = self.cls(net)
        dia, drill = c["via_diameter"], c["via_drill"]
        r, hr = dia / 2, drill / 2
        w = self.stub_width(pad, net)
        pos = pad.GetPosition()
        px, py = TOMM(pos.x), TOMM(pos.y)
        bb = pad.GetBoundingBox()
        hw, hh = TOMM(bb.GetWidth()) / 2, TOMM(bb.GetHeight()) / 2
        reasons = []
        for (dx, dy) in self.directions(pad):
            n = math.hypot(dx, dy)
            ex, ey = dx / n, dy / n
            # パッド端までの距離（矩形 bbox と方向から）
            tx = hw / abs(ex) if ex else 1e9
            ty = hh / abs(ey) if ey else 1e9
            half = min(tx, ty)
            for gap in GAPS:
                d = half + gap + r
                vx, vy = round(px + ex * d, 4), round(py + ey * d, 4)
                if not self.edge_ok(vx, vy, r):
                    reasons.append("edge")
                    continue
                via_shape = pcbnew.SHAPE_CIRCLE(V(vx, vy), MM(r))
                stub_shape = pcbnew.SHAPE_SEGMENT(V(px, py), V(vx, vy), MM(w))
                box = (min(px, vx) - r, min(py, vy) - r, max(px, vx) + r, max(py, vy) + r)
                why = self.collides(via_shape, net, hr, box, ignore=(pad,))
                if why is None:
                    why = self.collides(stub_shape, net, None, box, ignore=(pad,))
                if why is None:
                    why = self.lane_conflict(pad, vx, vy, r, net)
                if why is None:
                    self.add_stub_via(pad, (px, py), (vx, vy), w, net, dia, drill, "%+d%+d gap %.2f" % (dx, dy, gap))
                    return True
                reasons.append(why)
        self.skipped.append((ref, num, net, sorted(set(reasons))[:6]))
        return False

    def add_stub_via(self, pad, p0, p1, w, net, dia, drill, note):
        netinfo = self.b.FindNet(net)
        if math.hypot(p1[0] - p0[0], p1[1] - p0[1]) > 0.001:
            t = pcbnew.PCB_TRACK(self.b)
            t.SetStart(V(*p0))
            t.SetEnd(V(*p1))
            t.SetWidth(MM(w))
            t.SetLayer(pcbnew.F_Cu)
            t.SetNet(netinfo)
            t.SetLocked(True)
            self.b.Add(t)
            self.new_items.append((pcbnew.SHAPE_SEGMENT(V(*p0), V(*p1), MM(w)), net, None, "stub", ("s", p0[0], p0[1], p1[0], p1[1], w / 2)))
        v = pcbnew.PCB_VIA(self.b)
        v.SetPosition(V(*p1))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetWidth(MM(dia))
        v.SetDrill(MM(drill))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNet(netinfo)
        v.SetLocked(True)
        self.b.Add(v)
        self.new_items.append((pcbnew.SHAPE_CIRCLE(V(*p1), MM(dia / 2)), net, drill / 2, "via", ("c", p1[0], p1[1], dia / 2)))
        ref = pad.GetParentFootprint().GetReference() if pad is not None else "-"
        num = pad.GetNumber() if pad is not None else "-"
        self.placed.append((ref, num, net, p1[0], p1[1], dia, drill, w, round(math.hypot(p1[0] - p0[0], p1[1] - p0[1]), 3), note))

    def merge_pins(self):
        """MERGE: 隣接ピンをパッド列に沿って結び、1 本のスタブで 1 個のビアへ"""
        for ref, pads, junction, mid, via_xy in MERGE:
            fp = self.b.FindFootprintByReference(ref)
            pad_objs = [p for p in fp.Pads() if p.GetNumber() in pads]
            if any(self.has_plane_link(p) for p in pad_objs):
                continue
            net = pad_objs[0].GetNetname()
            c = self.cls(net)
            dia, drill = c["via_diameter"], c["via_drill"]
            r, hr = dia / 2, drill / 2
            checks = [(pcbnew.SHAPE_CIRCLE(V(*via_xy), MM(r)), hr),
                      (pcbnew.SHAPE_SEGMENT(V(*junction), V(*mid), MM(0.3)), None),
                      (pcbnew.SHAPE_SEGMENT(V(*mid), V(*via_xy), MM(0.3)), None)]
            def col_start(p):
                # パッド中心からジャンクション側へ 0.05 寄せた点（0.2 幅の丸端が隣ピンへ 0.2 ぴったりにならないよう余裕を取る）
                pp = p.GetPosition()
                x, y = TOMM(pp.x), TOMM(pp.y)
                return (x, y + (0.05 if junction[1] > y else -0.05)) if abs(junction[0] - x) < 1e-6 else (x + (0.05 if junction[0] > x else -0.05), y)
            for p in pad_objs:
                checks.append((pcbnew.SHAPE_SEGMENT(V(*col_start(p)), V(*junction), MM(0.2)), None))
            box = (min(junction[0], via_xy[0]) - 1, min(junction[1], via_xy[1]) - 1, max(junction[0], via_xy[0]) + 1, max(junction[1], via_xy[1]) + 1)
            bad = None
            for shp, hole in checks:
                bad = self.collides(shp, net, hole, box, ignore=tuple(pad_objs))
                if bad:
                    break
            if bad:
                self.skipped.append((ref, "+".join(pads), net, ["merge: " + bad]))
                continue
            netinfo = self.b.FindNet(net)
            def seg(a, b_, w):
                t = pcbnew.PCB_TRACK(self.b)
                t.SetStart(V(*a)); t.SetEnd(V(*b_)); t.SetWidth(MM(w)); t.SetLayer(pcbnew.F_Cu); t.SetNet(netinfo); t.SetLocked(True)
                self.b.Add(t)
                self.new_items.append((pcbnew.SHAPE_SEGMENT(V(*a), V(*b_), MM(w)), net, None, "stub", ("s", a[0], a[1], b_[0], b_[1], w / 2)))
            for p in pad_objs:
                seg(col_start(p), junction, 0.2)
            seg(junction, mid, 0.3)
            self.add_stub_via(pad_objs[0], mid, via_xy, 0.3, net, dia, drill, "merge %s" % "+".join(pads))
            self.placed[-1] = self.placed[-1][:1] + ("+".join(pads),) + self.placed[-1][2:]

    def dangling_ends(self):
        """ベタ配線ネットの配線で、何にも繋がっていない端 → そこにビア"""
        for t in list(self.tracks):
            if t.Type() != pcbnew.PCB_TRACE_T or t.GetNetname() not in PLANE_NETS:
                continue
            for end in (t.GetStart(), t.GetEnd()):
                touched = False
                for o in self.conn.GetConnectedTracks(t):
                    same = lambda a: a.x == end.x and a.y == end.y
                    if o.Type() == pcbnew.PCB_VIA_T:
                        if same(o.GetPosition()):
                            touched = True
                    elif same(o.GetStart()) or same(o.GetEnd()):
                        touched = True
                for p in self.conn.GetConnectedPads(t):
                    if p.HitTest(end):
                        touched = True
                if touched:
                    continue
                net = t.GetNetname()
                c = self.cls(net)
                dia, drill = c["via_diameter"], c["via_drill"]
                x, y = TOMM(end.x), TOMM(end.y)
                shape = pcbnew.SHAPE_CIRCLE(V(x, y), MM(dia / 2))
                why = self.collides(shape, net, drill / 2, (x - 1, y - 1, x + 1, y + 1))
                if why is None and not self.edge_ok(x, y, dia / 2):
                    why = "edge"
                if why:
                    self.skipped.append(("dangling", "%.3f,%.3f" % (x, y), net, [why]))
                    continue
                self.add_stub_via(None, (x, y), (x, y), 0.0, net, dia, drill, "dangling end of %.1f-wide track" % TOMM(t.GetWidth()))

    def run(self):
        self.dangling_ends()
        if not self.no_merge:
            self.merge_pins()
        self.b.BuildConnectivity()                 # 浮き端のビア・合流スタブを接続判定に反映
        self.conn = self.b.GetConnectivity()
        # 2 パス: 1 回目は「他の部品のパッドと既に配線で繋がっている U1 ピン」を飛ばす（人間が pin 1 → C1、pin 10 → C2 と
        # 引いた線の先のパスコン側にビアを置けば足りる）。2 回目で残りを拾う
        for pass_no in (1, 2):
            targets = []
            for pad in self.pads:
                if pad.GetNetname() not in PLANE_NETS or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                    continue
                if self.has_plane_link(pad):
                    continue
                if pad.GetParentFootprint().GetReference() in self.skip_refs:
                    continue
                if pass_no == 1 and pad.GetParentFootprint().GetReference() == "U1" and self.linked_to_other_footprint(pad):
                    continue
                targets.append(pad)
            # 一番窮屈な U1（QFN）を先に、同じ部品の中ではビア径の大きい方（+3V3）を先に置く
            targets.sort(key=lambda p: (0 if p.GetParentFootprint().GetReference() == "U1" else 1, p.GetParentFootprint().GetReference(),
                                        0 if p.GetNetname() == "+3V3" else 1, p.GetNumber()))
            for pad in targets:
                if self.pad_now_linked(pad):
                    continue                            # 同じパス内で合流 / 重なりパッド（J1 の A1/B12）に付いた
                self.try_pad(pad)
            self.b.BuildConnectivity()
            self.conn = self.b.GetConnectivity()
        return self.placed, self.skipped

    def linked_to_other_footprint(self, pad):
        ref = pad.GetParentFootprint().GetReference()
        seen = set()
        stack = [pad]
        while stack:
            it = stack.pop()
            key = it.m_Uuid.AsString()
            if key in seen:
                continue
            seen.add(key)
            if it.Type() == pcbnew.PCB_PAD_T and it.GetParentFootprint().GetReference() != ref:
                return True
            for t in self.conn.GetConnectedTracks(it):
                stack.append(t)
            for p in self.conn.GetConnectedPads(it):
                stack.append(p)
        return False

    def pad_now_linked(self, pad):
        """MERGE で結んだピンなど、この実行中に付けたスタブがパッドに触れているか"""
        shp = pad.GetEffectiveShape(pcbnew.F_Cu)
        for s, nnet, hole, kind, _g in self.new_items:
            if nnet == pad.GetNetname() and kind == "stub" and shp.Collide(s, 0):
                return True
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--project", help=".kicad_pro（既定: --input と同名）")
    ap.add_argument("--report")
    ap.add_argument("--lock-existing", action="store_true", help="先に既存の全 segment / via を locked にする")
    ap.add_argument("--skip-refs", default="", help="ファンアウトしない部品（カンマ区切り。例: U1 = QFN のピンは freerouting に任せる）")
    ap.add_argument("--no-merge", action="store_true", help="MERGE（隣接ピンの合流ビア）をしない")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    board = pcbnew.LoadBoard(args.input)
    pro = args.project or os.path.splitext(args.input)[0] + ".kicad_pro"
    classes, patterns = load_classes(pro)
    locked = 0
    if args.lock_existing:
        for t in board.GetTracks():
            if not t.IsLocked():
                t.SetLocked(True)
                locked += 1
    f = Fanout(board, classes, patterns)
    f.skip_refs = {r.strip() for r in args.skip_refs.split(",") if r.strip()}
    f.no_merge = args.no_merge
    placed, skipped = f.run()
    board.Save(args.output)
    print("locked existing: %d / placed vias: %d / skipped: %d -> %s" % (locked, len(placed), len(skipped), args.output))
    lines = ["# ファンアウト（GND / +3V3 → 内層ベタ）", "",
             "- 入力: `%s`" % os.path.basename(args.input), "- 既存配線を locked にした本数: %d" % locked,
             "- 置いたビア: **%d**（GND %d / +3V3 %d）" % (len(placed), sum(p[2] == "GND" for p in placed), sum(p[2] == "+3V3" for p in placed)),
             "- 置けなかったパッド: %d" % len(skipped), "",
             "| Ref | Pad | Net | via X | via Y | 径/穴 | スタブ幅 | スタブ長 | 位置の決め方 |", "|:--|:--|:--|--:|--:|:--|--:|--:|:--|"]
    for ref, num, net, x, y, dia, drill, w, length, note in placed:
        lines.append("| %s | %s | %s | %.3f | %.3f | %.2f/%.2f | %.2f | %.2f | %s |" % (ref, num, net, x, y, dia, drill, w, length, note))
    if skipped:
        lines += ["", "## 置けなかったパッド（freerouting に任せる）", "", "| Ref | Pad | Net | 当たった相手（候補ごと・先頭 6 件） |", "|:--|:--|:--|:--|"]
        for ref, num, net, reasons in skipped:
            lines.append("| %s | %s | %s | %s |" % (ref, num, net, "; ".join(reasons)))
    if args.report:
        with open(args.report, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
    for s in skipped:
        print("  skipped:", s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
