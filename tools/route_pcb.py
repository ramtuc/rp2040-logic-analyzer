"""
freerouting で自動配線する（GUI なし）。KiCad 同梱の python で実行すること:

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools\\route_pcb.py [--input <基板>] [--passes N] [--timeout SEC]
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools\\route_pcb.py --pours-only --input <配線済み基板>   # ベタ追加だけ

流れ（KiCad の freerouting アドオンがダイアログ内でやることをスクリプトで）:
    hardware/rp2040-logic-analyzer.kicad_pcb（配置済み・gen_pcb.py の出力）
      → hardware/out/route/ にコピー
      → pcbnew.ExportSpecctraDSN → java -jar freerouting.jar -de … -do … → pcbnew.ImportSpecctraSES
      → hardware/out/route/rp2040-logic-analyzer.kicad_pcb（配線済み）
      → hardware/rp2040-logic-analyzer.kicad_pcb に上書き（配置済み版は hardware/out/placed/ に残る）

* 内層 In1/In2 は layer type = power なので DSN で (type power) になり freerouting は配線しない
* locked の USB 差動配線は DSN で (type protect) になり freerouting は触らない（結果を照合する）
* kicad-cli に DSN 書き出しは無い（memory: astra-kicad-trial/run_freerouting.md）
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HW = os.path.join(ROOT, "hardware")
PROJECT = "rp2040-logic-analyzer"
RUN = os.path.join(HW, "out", "route")

PLUGIN_JAR_DIR = os.path.join(os.path.expanduser("~"), "Documents", "KiCad", "10.0", "3rdparty", "plugins",
                              "app_freerouting_kicad-plugin", "jar")


def find_jar():
    env = os.environ.get("FREEROUTING_JAR")
    if env and os.path.exists(env):
        return env
    if os.path.isdir(PLUGIN_JAR_DIR):
        jars = sorted(f for f in os.listdir(PLUGIN_JAR_DIR) if f.endswith(".jar"))
        if jars:
            return os.path.join(PLUGIN_JAR_DIR, jars[-1])
    return None


def locked_segments(path):
    """(segment … (locked yes) …) の (start, end, layer, net) 集合（子要素の順序は問わない）"""
    text = open(path, encoding="utf-8").read()
    out = set()
    for block in re.findall(r"\(segment\n(.*?)\n\t\)", text, flags=re.S):
        if "(locked yes)" not in block:
            continue
        g = lambda key: re.search(r"\(%s ([^)]*)\)" % key, block).group(1)
        out.add((g("start"), g("end"), g("layer"), g("net")))
    return out


def add_bottom_gnd_zone(board, pcbnew):
    """KIT §3.1 L4 = 信号 + GND ベタ。配線後に B.Cu へ GND ゾーンを足して全ゾーンを塗る"""
    net = board.FindNet("GND")
    if net is None:
        sys.exit("GND net not found")
    bbox = board.GetBoardEdgesBoundingBox()
    zone = pcbnew.ZONE(board)
    zone.SetNet(net)
    zone.SetLayer(pcbnew.B_Cu)
    zone.SetZoneName("GND_L4")
    zone.SetLocalClearance(pcbnew.FromMM(0.2))
    zone.SetMinThickness(pcbnew.FromMM(0.25))
    zone.SetThermalReliefGap(pcbnew.FromMM(0.3))
    zone.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.3))
    zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_AREA)
    zone.SetMinIslandArea(pcbnew.FromMM(10) * pcbnew.FromMM(1))
    outline = zone.Outline()
    outline.NewOutline()
    x0, y0, x1, y1 = bbox.GetLeft(), bbox.GetTop(), bbox.GetRight(), bbox.GetBottom()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        outline.Append(int(x), int(y))
    board.Add(zone)
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    return zone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--passes", type=int, default=20, help="freerouting -mp（最適化パス上限）")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--source", "--input", dest="source", default=os.path.join(HW, "out", "placed", PROJECT + ".kicad_pcb"),
                    help="配線する基板（既定: hardware/out/placed/ の配置済み版。人間が GUI で直した版を渡してよい）")
    ap.add_argument("--pours-only", action="store_true",
                    help="配線せず、--source の基板に B.Cu の GND ベタを足して全ゾーンを塗り、hardware/ に保存するだけ")
    ap.add_argument("--inner-signal", dest="inner_signal", action="store_true",
                    help="DSN の内層を signal に書き換える（実験用。freerouting が内層に配線してしまう）")
    ap.add_argument("--keep-planes", dest="strip_planes", action="store_false",
                    help="DSN の plane（内層ベタ）を残す（既定は外す）")
    ap.add_argument("--ignore-classes", default="Plane_GND,Plane_3V3",
                    help="freerouting に無視させるネットクラス（-inc）。ベタで配るネットはファンアウトビアで繋いである")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    try:
        import pcbnew
    except ImportError:
        sys.exit('pcbnew が import できない。KiCad 同梱の python で実行: "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools\\route_pcb.py')

    if args.pours_only:
        board = pcbnew.LoadBoard(args.source)
        add_bottom_gnd_zone(board, pcbnew)
        dest = os.path.join(HW, PROJECT + ".kicad_pcb")
        board.Save(dest)
        print("B.Cu GND zone added and all zones filled ->", dest)
        return 0

    jar = find_jar()
    if not jar:
        sys.exit("freerouting の jar が見つからない（KiCad アドオン app_freerouting_kicad-plugin を入れるか FREEROUTING_JAR を設定）")
    java = shutil.which("java")
    if not java:
        sys.exit("java が無い（freerouting 2.2.4 は Java 25 以上）")

    os.makedirs(RUN, exist_ok=True)
    pcb = os.path.join(RUN, PROJECT + ".kicad_pcb")
    shutil.copy2(args.source, pcb)
    for suffix in (".kicad_pro",):
        src = os.path.join(HW, PROJECT + suffix)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(RUN, PROJECT + suffix))
    dsn = os.path.join(RUN, PROJECT + ".dsn")
    ses = os.path.join(RUN, PROJECT + ".ses")
    log = os.path.join(RUN, "freerouting.log")

    board = pcbnew.LoadBoard(pcb)
    before = len(board.GetTracks())
    if not pcbnew.ExportSpecctraDSN(board, dsn):
        sys.exit("ExportSpecctraDSN failed")
    dsn_text = open(dsn, encoding="utf-8", errors="replace").read()
    if args.strip_planes:
        # 内層ベタ（plane）を DSN から外す。GND/+3V3 は -inc で無視させるので freerouting に plane は不要。
        # 残しておくと freerouting は「他ネットのビアが plane を貫く」のを衝突と見て、ビアを 1 個も打てなくなる
        # （実測: B.Cu に配線がほぼ無く 141 ネット中 61 未配線）
        dsn_text = re.sub(r"\(plane [^\n]*\n[^\n]*\)\)\n", "", dsn_text)
        with open(dsn, "w", encoding="utf-8", newline="\n") as f:
            f.write(dsn_text)
    if args.inner_signal:
        # KiCad は power 層を (type power) で書くが、freerouting はその層のベタへビアを落とさない（GND/+3V3 が全部未配線になる）。
        # signal に書き換えると、ベタは「同ネットの導体面」になってビアで繋がり、他ネットには障害物になる（= 内層に配線は入らない）
        dsn_text = re.sub(r"(\(layer In\d\.Cu\s*\(type )power\)", r"\1signal)", dsn_text)
        with open(dsn, "w", encoding="utf-8", newline="\n") as f:
            f.write(dsn_text)
    print("dsn: %d bytes, power layers: %s, planes: %d, fixed wires: %d" % (
        len(dsn_text), re.findall(r'\(layer (In\d\.Cu)\s*\(type power\)', dsn_text), dsn_text.count("(plane "),
        dsn_text.count("(type fix)")))

    cmd = [java, "-jar", jar, "-de", dsn, "-do", ses, "-host", "KiCad", "-mp", str(args.passes)]
    if args.ignore_classes:
        cmd += ["-inc", args.ignore_classes]
    started = time.time()
    # freerouting は .ses を書いた後に JVM が終了しないことがある（実測）→ .ses が書かれて 15 秒動かなければ止める
    with open(log, "w", encoding="utf-8", newline="\n") as lf:
        lf.write(" ".join(cmd) + "\n\n")
        proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        ses_seen = None
        rc = None
        while True:
            rc = proc.poll()
            if rc is not None:
                break
            if os.path.exists(ses):
                mtime = os.path.getmtime(ses)
                if ses_seen is None or mtime != ses_seen:
                    ses_seen = mtime
                    ses_stable = time.time()
                elif time.time() - ses_stable > 15:
                    proc.kill()
                    rc = "killed-after-ses"
                    break
            if time.time() - started > args.timeout:
                proc.kill()
                sys.exit("freerouting timeout (%ds)" % args.timeout)
            time.sleep(1)
    elapsed = time.time() - started
    output = open(log, encoding="utf-8", errors="replace").read()

    class _P:
        returncode = rc
    proc = _P()
    for line in output.splitlines():
        if any(k in line for k in ("Auto-router", "unrouted", "ERROR", "incomplete", "Routing")):
            print("  " + line.split("INFO")[-1].strip()[:160])
    if not os.path.exists(ses):
        sys.exit("freerouting が .ses を出さなかった (rc=%s) — %s" % (proc.returncode, log))
    if not pcbnew.ImportSpecctraSES(board, ses):
        sys.exit("ImportSpecctraSES failed")
    add_bottom_gnd_zone(board, pcbnew)
    board.Save(pcb)
    after = len(board.GetTracks())

    # locked（手配線 USB）が変わっていないことを確認
    kept = locked_segments(pcb)
    orig = locked_segments(args.source)
    same = kept == orig
    summary = {"seconds": round(elapsed, 1), "returncode": proc.returncode, "tracks_before": before, "tracks_after": after,
               "locked_segments_original": len(orig), "locked_segments_after": len(kept), "locked_unchanged": same,
               "jar": jar, "passes": args.passes}
    with open(os.path.join(RUN, "run.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    dest = os.path.join(HW, PROJECT + ".kicad_pcb")
    shutil.copy2(pcb, dest)
    print("routed board ->", dest)
    return 0 if same else 2


if __name__ == "__main__":
    sys.exit(main())
