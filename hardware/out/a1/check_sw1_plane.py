"""
A1 の SW1 まわりの In2（+3V3 プレーン）の充填を KiCad 同梱の python（pcbnew）で検算する。

    "C:/Program Files/KiCad/10.0/bin/python.exe" hardware/out/a1/check_sw1_plane.py hardware/rp2040-logic-analyzer.kicad_pcb

見るもの
  - SW1 pad1〜4 のネット名と座標
  - In2 の +3V3 ゾーンの充填ポリゴンが、各パッドの周り（半径 0.95mm＝パッド半径 0.762 ＋ サーマルギャップ 0.3 の内側）に
    銅を持つか: pad1（+3V3）はサーマルスポークの方向だけ銅がある／pad2（VREF）・pad3・pad4 は一周すべて銅なし（アンチパッド）
  - 半径 1.3mm では全パッドとも一周銅がある（プレーンの連続性）
"""

import math
import sys

import pcbnew

board = pcbnew.LoadBoard(sys.argv[1])
board.BuildConnectivity()
sw1 = board.FindFootprintByReference("SW1")
zone = next(z for z in board.Zones() if z.GetNetname() == "+3V3" and z.IsOnLayer(pcbnew.In2_Cu))
poly = zone.GetFilledPolysList(pcbnew.In2_Cu)
print("zone:", zone.GetZoneName(), zone.GetNetname(), "filled polygons:", poly.OutlineCount())


def ring(cx, cy, r_mm, n=72):
    hits = []
    for k in range(n):
        a = 2 * math.pi * k / n
        p = pcbnew.VECTOR2I(int(cx + pcbnew.FromMM(r_mm * math.cos(a))), int(cy + pcbnew.FromMM(r_mm * math.sin(a))))
        hits.append(poly.Contains(p))
    return hits


def runs(hits):
    """True の連続区間の数（円周上なので先頭と末尾が繋がっていれば 1 つに数える）"""
    n = sum(1 for i in range(len(hits)) if hits[i] and not hits[i - 1])
    return n


print("| pad | net | x,y [mm] | r=0.95 銅あり点数/72 | スポーク本数 | r=1.3 銅あり点数/72 |")
print("|:--|:--|:--|--:|--:|--:|")
for num in ("1", "2", "3", "4"):
    pad = sw1.FindPadByNumber(num)
    pos = pad.GetPosition()
    inner = ring(pos.x, pos.y, 0.95)
    outer = ring(pos.x, pos.y, 1.3)
    print(f"| {num} | {pad.GetNetname()} | {pcbnew.ToMM(pos.x):.3f},{pcbnew.ToMM(pos.y):.3f} | {sum(inner)} | {runs(inner)} | {sum(outer)} |")
