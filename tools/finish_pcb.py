"""
freerouting の結果を仕上げる（KiCad 同梱 python で実行）:

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools\\finish_pcb.py --input <配線済み基板> --output <基板> [--report <md>] [--stitch-pitch 8] [--no-stitch]

1. SES 取り込みの副産物を消す: 長さ 0.01 mm 未満の unlocked segment（freerouting が 0.5 µm の丸めズレを埋めようとした欠片）と、
   同じネットのパッドの中に完全に収まる unlocked segment（EP の中のビア→パッド中心の線など）
2. B.Cu に GND ベタを足す（KIT §3.1 L4 = 信号 + GND ベタ。island は ALWAYS で除去 = 浮き銅を残さない）
3. GND のビアスティッチ: 基板外周に沿って一定ピッチで候補を置き、他ネットの銅箔・穴・基板端とぶつからない所だけ打つ
   （径 / 穴はネットクラス Default の 0.45/0.25。QFN の EP は既にビア 4 個、TXU 周りはファンアウトのビアで足りている）
4. 全ゾーンを塗って保存。DRC は別途 kicad-cli で
"""

import argparse
import json
import math
import os
import sys

try:
    import wx
    wx.DisableAsserts()
except Exception:
    pass

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fanout_planes import Fanout, load_classes, MM, TOMM, V  # noqa: E402

STITCH_INSET = 1.0        # 基板端からビア中心まで（銅箔 ↔ 基板端 0.3 に余裕）


def find_artifacts(board):
    """消すべき unlocked segment の uuid（読み取りだけ。KiCad 10.0.3 の python は board.Remove() の後で SWIG のラップが壊れ、
    Drawings() 等が生の SwigPyObject を返すようになるので、削除はテキストで行う）"""
    conn = board.GetConnectivity()
    removed = {"sliver": 0, "inside_pad": 0}
    uuids = []
    for t in list(board.GetTracks()):
        if t.Type() != pcbnew.PCB_TRACE_T or t.IsLocked():
            continue
        a, b = t.GetStart(), t.GetEnd()
        length = math.hypot(TOMM(a.x - b.x), TOMM(a.y - b.y))
        if length < 0.01:
            uuids.append(t.m_Uuid.AsString())
            removed["sliver"] += 1
            continue
        for p in conn.GetConnectedPads(t):
            if p.GetNetname() == t.GetNetname() and p.HitTest(a) and p.HitTest(b):
                uuids.append(t.m_Uuid.AsString())
                removed["inside_pad"] += 1
                break
    return removed, uuids


def drop_segments_by_uuid(src_path, dst_path, uuids):
    import re
    text = open(src_path, encoding="utf-8").read()
    want = set(uuids)
    pat = re.compile(chr(10) + chr(9) + r"\(segment" + chr(10) + r".*?" + chr(10) + chr(9) + r"\)", re.S)
    def repl(m):
        u = re.search(r'\(uuid "([^"]+)"\)', m.group(0)).group(1)
        return "" if u in want else m.group(0)
    text = pat.sub(repl, text)
    with open(dst_path, "w", encoding="utf-8", newline=chr(10)) as f:
        f.write(text)


def add_bottom_gnd_zone(board, edge_mm):
    net = board.FindNet("GND")
    zone = pcbnew.ZONE(board)
    zone.SetNet(net)
    zone.SetLayer(pcbnew.B_Cu)
    zone.SetZoneName("GND_L4")
    zone.SetLocalClearance(MM(0.2))
    zone.SetMinThickness(MM(0.25))
    zone.SetThermalReliefGap(MM(0.3))
    zone.SetThermalReliefSpokeWidth(MM(0.3))
    zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    # KiCad 10.0.3 の Python では zone.Outline() が shared_ptr プロキシで NewOutline を持たない → 作って SetOutline
    outline = pcbnew.SHAPE_POLY_SET()
    outline.NewOutline()
    x0, y0, x1, y1 = edge_mm
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        outline.Append(V(x, y))
    zone.SetOutline(outline)
    outline.thisown = 0          # 所有権は zone へ（Python 側が解放すると Save で二重解放 → segfault）
    board.Add(zone)
    return zone


def stitch_perimeter(board, fan, pitch):
    """外周リング上に pitch 間隔で GND ビア候補を置き、衝突しない所だけ打つ"""
    x0, y0, x1, y1 = fan.edge
    x0, y0, x1, y1 = x0 + STITCH_INSET, y0 + STITCH_INSET, x1 - STITCH_INSET, y1 - STITCH_INSET
    pts = []
    def walk(ax, ay, bx, by):
        L = math.hypot(bx - ax, by - ay)
        n = max(1, int(round(L / pitch)))
        for i in range(n):
            pts.append((ax + (bx - ax) * i / n, ay + (by - ay) * i / n))
    walk(x0, y0, x1, y0); walk(x1, y0, x1, y1); walk(x1, y1, x0, y1); walk(x0, y1, x0, y0)
    c = fan.cls("GND")
    dia, drill = c["via_diameter"], c["via_drill"]
    placed, skipped = [], []
    for (x, y) in pts:
        x, y = round(x, 3), round(y, 3)
        shape = pcbnew.SHAPE_CIRCLE(V(x, y), MM(dia / 2))
        why = fan.collides(shape, "GND", drill / 2, (x - 1, y - 1, x + 1, y + 1))
        if why:
            skipped.append((x, y, why))
            continue
        fan.add_stub_via(None, (x, y), (x, y), 0.0, "GND", dia, drill, "stitch")
        placed.append((x, y))
    return placed, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--project")
    ap.add_argument("--report")
    ap.add_argument("--stitch-pitch", type=float, default=8.0)
    ap.add_argument("--no-stitch", action="store_true")
    ap.add_argument("--scan-only", action="store_true", help="（内部用）欠片の uuid を JSON で出すだけ")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    pro = args.project or os.path.splitext(args.input)[0] + ".kicad_pro"
    classes, patterns = load_classes(pro)
    if args.scan_only:
        board = pcbnew.LoadBoard(args.input)
        removed, uuids = find_artifacts(board)
        print(json.dumps({"removed": removed, "uuids": uuids}))
        return 0
    # 1 プロセスで基板を 2 回 LoadBoard すると segfault するので、欠片の走査は子プロセスで
    import subprocess
    out = subprocess.run([sys.executable, os.path.abspath(__file__), "--input", args.input, "--output", args.output,
                          "--project", pro, "--scan-only"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    scan = json.loads([l for l in out.stdout.splitlines() if l.startswith("{")][-1])
    removed, uuids = scan["removed"], scan["uuids"]
    cleaned = os.path.splitext(args.output)[0] + "-cleaned.kicad_pcb"
    drop_segments_by_uuid(args.input, cleaned, uuids)
    board = pcbnew.LoadBoard(cleaned)
    fan = Fanout(board, classes, patterns)
    zone = add_bottom_gnd_zone(board, fan.edge)
    stitched, skipped = [], []
    if not args.no_stitch:
        stitched, skipped = stitch_perimeter(board, fan, args.stitch_pitch)
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    board.Save(args.output)
    # pcbnew の Save は隣の .kicad_pro をネットクラス無しの空に近い内容で書き換える → 本物を隣に置き直す（DRC が既定値で走るのを防ぐ）
    import shutil
    shutil.copy2(pro, os.path.splitext(args.output)[0] + ".kicad_pro")
    n_tracks = sum(1 for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T)
    n_vias = sum(1 for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T)
    print("removed:", removed, "/ stitch vias:", len(stitched), "(skipped %d)" % len(skipped), "/ tracks:", n_tracks, "vias:", n_vias, "->", args.output)
    if args.report:
        lines = ["# 仕上げ（アーティファクト除去・B.Cu GND ベタ・ビアスティッチ）", "",
                 "- 入力: `%s`" % os.path.basename(args.input),
                 "- 消した unlocked segment: 欠片（<0.01 mm）%d・同ネットパッド内 %d" % (removed["sliver"], removed["inside_pad"]),
                 "- B.Cu GND ベタ: 基板全面・クリアランス 0.2・最小幅 0.25・サーマル 0.3/0.3・島は常に除去",
                 "- ビアスティッチ（GND 0.45/0.25・外周 %.0f mm 内側・ピッチ %.0f mm）: **%d 個**（候補 %d・不可 %d）" % (
                     STITCH_INSET, args.stitch_pitch, len(stitched), len(stitched) + len(skipped), len(skipped)),
                 "- 配線 %d 本 / ビア %d 個" % (n_tracks, n_vias), ""]
        if stitched:
            lines += ["| # | X | Y |", "|--:|--:|--:|"] + ["| %d | %.3f | %.3f |" % (i + 1, x, y) for i, (x, y) in enumerate(stitched)]
        if skipped:
            lines += ["", "打てなかった候補:", ""] + ["- (%.3f, %.3f): %s" % s for s in skipped]
        with open(args.report, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
