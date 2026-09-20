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
* locked の配線 / ビアは DSN で (type protect) になり freerouting は触らない（結果を照合する）。--lock-existing で
  既存の全 segment / via を先に locked にできる（人間の手配線を守る）
* 内層ベタ (plane) は既定で DSN に残す。freerouting 2.2.4 の Structure.java は plane を
  insert_conduction_area(..., is_obstacle=false, ...) で入れるので、他ネットのビアが plane を貫いても衝突にならない。
  GND/+3V3 のパッドは tools/fanout_planes.py で先にビア→ベタへ落としてあるので、freerouting はこれらを配線しない
  （第 2 工程で plane を外していたのは、-inc が効かず GND/+3V3 が配線されたときの回避策。今は不要）
* KiCad が書く DSN には freerouting 2.2.4 / 2.4.1 が正しく読めない箇所が 2 つあり、書き出し後に直してから渡す（実測 2026-09-20）:
  (1) ルールエリア（配線禁止）は (wire_keepout "" (polygon ...)) で出るが、freerouting はこのキーワードを知らず、
      スコープ読み飛ばしが後続の (via "Via[0-3]_450:250_um" ...) 宣言まで巻き込む → 使えるビアが 0 個になり、
      基板全体で 1 個もビアを打てなくなる（第 2 工程で「B.Cu をほとんど使わない」「未配線 37」だった真因）。
      → (wire_keepout ...) を DSN から外す（KiCad 側のルールエリアは残るので DRC は今までどおり）
  (2) 配線 / ビアの座標を 1 µm に丸めて書くのに、パッド位置は 0.1 µm 精度（QFN の 3437.5 など）で書く。
      パッド中心から出した locked 配線が freerouting には 0.5 µm 離れて見えて「未接続」扱いになり、
      埋めようとして NullPointerException（Polyline: must contain at least 2 different points）を連発する。
      → (wiring ...) を基板の segment / via から 0.1 µm 精度で作り直す
* freerouting は必ず --gui.enabled=false（ヘッドレス）で回す。GUI モードは -de/-do でも Swing の窓を開き、配線後に
  プロファイル設定ダイアログ（BoardMenuBar.showProfileDialog → WindowUserSettings）が出ることがあって、人間が閉じるまで
  .ses を書かない（第 2 工程の「JVM が終了しない」の正体。jstack で確認 2026-09-20）
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

try:
    import wx
    wx.DisableAsserts()          # pcbnew の assert ダイアログ（層引数無しの PCB_VIA::GetWidth 等）を人間の画面に出さない
except Exception:
    pass

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
    """locked な (segment …) の (start, end, width, layer, net) と (via …) の (at, size, drill, net) の集合（子要素の順序は問わない）"""
    text = open(path, encoding="utf-8").read()
    out = set()
    for block in re.findall(r"\(segment\n(.*?)\n\t\)", text, flags=re.S):
        if "(locked yes)" not in block:
            continue
        g = lambda key: re.search(r"\(%s ([^)]*)\)" % key, block).group(1)
        out.add(("segment", g("start"), g("end"), g("width"), g("layer"), g("net")))
    for block in re.findall(r"\(via\n(.*?)\n\t\)", text, flags=re.S):
        if "(locked yes)" not in block:
            continue
        g = lambda key: re.search(r"\(%s ([^)]*)\)" % key, block).group(1)
        out.add(("via", g("at"), g("size"), g("drill"), g("net")))
    return out


def strip_scopes(text, keyword):
    """DSN から (keyword ...) スコープを括弧の対応を見て取り除く"""
    out = []
    i = 0
    token = "(" + keyword
    while True:
        j = text.find(token, i)
        if j < 0 or not text[j + len(token)].isspace():
            if j < 0:
                out.append(text[i:])
                break
            out.append(text[i:j + len(token)])
            i = j + len(token)
            continue
        out.append(text[i:j])
        depth = 0
        k = j
        while k < len(text):
            if text[k] == "(":
                depth += 1
            elif text[k] == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        i = k + 1
        if i < len(text) and text[i] == "\n":
            i += 1
    return "".join(out)


def _um(v_mm):
    s = "%.3f" % (v_mm * 1000.0)
    return s.rstrip("0").rstrip(".") if "." in s else s


def _dsn_name(name):
    return '"%s"' % name if (name == "" or any(c in name for c in ' ()"')) else name


def rebuild_wiring(board, pcbnew, dsn_text):
    """(wiring ...) を基板の segment / via から作り直す（座標 0.1 µm 精度・locked は (type fix)）。
    使うビアの padstack が (library ...) に無ければ足す"""
    copper = [board.GetLayerName(l) for l in board.GetEnabledLayers().CuStack()]
    lines = []
    padstacks = set()
    for t in board.GetTracks():
        net = _dsn_name(t.GetNetname())
        fixed = "(type fix)" if t.IsLocked() else ""
        if t.Type() == pcbnew.PCB_VIA_T:
            size = int(round(pcbnew.ToMM(t.GetFrontWidth()) * 1000))
            drill = int(round(pcbnew.ToMM(t.GetDrillValue()) * 1000))
            name = "Via[0-%d]_%d:%d_um" % (len(copper) - 1, size, drill)
            padstacks.add((name, size))
            p = t.GetPosition()
            lines.append('    (via "%s"  %s %s (net %s)%s)' % (name, _um(pcbnew.ToMM(p.x)), _um(-pcbnew.ToMM(p.y)), net, fixed))
        elif t.Type() == pcbnew.PCB_TRACE_T:
            a, b = t.GetStart(), t.GetEnd()
            lines.append("    (wire (path %s %d  %s %s  %s %s)(net %s)%s)" % (
                board.GetLayerName(t.GetLayer()), int(round(pcbnew.ToMM(t.GetWidth()) * 1000)),
                _um(pcbnew.ToMM(a.x)), _um(-pcbnew.ToMM(a.y)), _um(pcbnew.ToMM(b.x)), _um(-pcbnew.ToMM(b.y)), net, fixed))
    new_wiring = "  (wiring\n" + "\n".join(lines) + "\n  )\n"
    m = re.search(r"\n  \(wiring\n.*?\n  \)\n", dsn_text, flags=re.S)
    if m:
        dsn_text = dsn_text[:m.start() + 1] + new_wiring + dsn_text[m.end():]
    else:
        dsn_text = dsn_text.rstrip()[:-1] + new_wiring + ")\n"
    for name, size in sorted(padstacks):
        if ('(padstack "%s"' % name) in dsn_text:
            continue
        block = '    (padstack "%s"\n' % name + "".join("      (shape (circle %s %d))\n" % (l, size) for l in copper) + "      (attach off)\n    )\n"
        k = dsn_text.find("  (library\n")
        end = dsn_text.find("\n  )\n", k)
        dsn_text = dsn_text[:end + 1] + block + dsn_text[end + 1:]
    return dsn_text, len(lines)


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
    # KiCad 10.0.3 の Python では zone.Outline() が shared_ptr プロキシで NewOutline を持たない → 作って SetOutline
    outline = pcbnew.SHAPE_POLY_SET()
    outline.NewOutline()
    x0, y0, x1, y1 = bbox.GetLeft(), bbox.GetTop(), bbox.GetRight(), bbox.GetBottom()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        outline.Append(int(x), int(y))
    zone.SetOutline(outline)
    outline.thisown = 0          # 所有権は zone へ（Python 側が解放すると Save で二重解放 → segfault）
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
    ap.add_argument("--strip-planes", dest="strip_planes", action="store_true",
                    help="DSN から plane（内層ベタ）を外す（第 2 工程の回避策。既定は残す＝GND/+3V3 はベタ経由で接続済みと見なされる）")
    ap.add_argument("--ignore-classes", default="",
                    help="freerouting に無視させるネットクラス（-inc）。空なら渡さない")
    ap.add_argument("--lock-existing", action="store_true",
                    help="DSN 書き出しの前に既存の全 segment / via を locked にする（人間の手配線を freerouting から守る）")
    ap.add_argument("--run-dir", default=RUN, help="中間ファイル（.dsn/.ses/log/run.json）と配線済み基板の置き場")
    ap.add_argument("--dest", default=os.path.join(HW, PROJECT + ".kicad_pcb"),
                    help="配線済み基板のコピー先（既定: hardware/ の基板を上書き。段階検証中は別パスを渡す）")
    ap.add_argument("--no-pour", action="store_true", help="SES 取り込み後の B.Cu GND ベタ追加をしない（--pours-only を後で別に回す）")
    ap.add_argument("--fr-args", default="--gui.enabled=false",
                    help="freerouting に追加で渡す引数（空白区切り）。既定はヘッドレス実行。GUI モードだと配線後に "
                         "ユーザー設定ダイアログ（WindowUserSettings）が出て人間がクリックするまで .ses を書かず止まる（jstack で確認）")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    run_dir = args.run_dir

    try:
        import pcbnew
    except ImportError:
        sys.exit('pcbnew が import できない。KiCad 同梱の python で実行: "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools\\route_pcb.py')

    if args.pours_only:
        board = pcbnew.LoadBoard(args.source)
        add_bottom_gnd_zone(board, pcbnew)
        board.Save(args.dest)
        print("B.Cu GND zone added and all zones filled ->", args.dest)
        return 0

    jar = find_jar()
    if not jar:
        sys.exit("freerouting の jar が見つからない（KiCad アドオン app_freerouting_kicad-plugin を入れるか FREEROUTING_JAR を設定）")
    java = shutil.which("java")
    if not java:
        sys.exit("java が無い（freerouting 2.2.4 は Java 25 以上）")

    os.makedirs(run_dir, exist_ok=True)
    pcb = os.path.join(run_dir, PROJECT + ".kicad_pcb")
    shutil.copy2(args.source, pcb)
    for name in (PROJECT + ".kicad_pro", "fp-lib-table"):
        src = os.path.join(HW, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(run_dir, name))
    dsn = os.path.join(run_dir, PROJECT + ".dsn")
    ses = os.path.join(run_dir, PROJECT + ".ses")
    log = os.path.join(run_dir, "freerouting.log")

    board = pcbnew.LoadBoard(pcb)
    locked_now = 0
    if args.lock_existing:
        for t in board.GetTracks():
            if not t.IsLocked():
                t.SetLocked(True)
                locked_now += 1
        board.Save(pcb)
        shutil.copy2(pcb, os.path.join(run_dir, PROJECT + "-locked-input.kicad_pcb"))
    before = len(board.GetTracks())
    if not pcbnew.ExportSpecctraDSN(board, dsn):
        sys.exit("ExportSpecctraDSN failed")
    dsn_text = open(dsn, encoding="utf-8", errors="replace").read()
    # (1) wire_keepout を外す（freerouting が読めず、後続の via 宣言まで失ってビアを 1 個も打てなくなる）
    n_keepout = dsn_text.count("(wire_keepout")
    dsn_text = strip_scopes(dsn_text, "wire_keepout")
    # (2) 配線 / ビアを 0.1 µm 精度で書き直す（0.5 µm の丸めズレで locked 配線が未接続に見えるのを防ぐ）
    dsn_text, n_wiring = rebuild_wiring(board, pcbnew, dsn_text)
    with open(dsn, "w", encoding="utf-8", newline="\n") as f:
        f.write(dsn_text)
    print("dsn fixed: wire_keepout removed: %d, wiring rebuilt: %d items" % (n_keepout, n_wiring))
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
    if args.fr_args.strip():
        cmd += args.fr_args.split()
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
    if not args.no_pour:
        add_bottom_gnd_zone(board, pcbnew)
    board.Save(pcb)
    after = len(board.GetTracks())

    # locked（人間の手配線・USB・ファンアウト）が変わっていないことを確認（--lock-existing のときは lock 後の入力と比べる）
    kept = locked_segments(pcb)
    orig = locked_segments(os.path.join(run_dir, PROJECT + "-locked-input.kicad_pcb") if args.lock_existing else args.source)
    same = kept == orig
    unrouted = None
    for line in output.splitlines()[::-1]:
        m = re.search(r"\((\d+) unrouted\)", line)
        if m:
            unrouted = int(m.group(1))
            break
    summary = {"seconds": round(elapsed, 1), "returncode": proc.returncode, "tracks_before": before, "tracks_after": after,
               "locked_now": locked_now, "locked_items_original": len(orig), "locked_items_after": len(kept), "locked_unchanged": same,
               "freerouting_last_unrouted": unrouted, "jar": jar, "passes": args.passes, "strip_planes": args.strip_planes,
               "inner_signal": args.inner_signal, "ignore_classes": args.ignore_classes}
    with open(os.path.join(run_dir, "run.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    shutil.copy2(pcb, args.dest)
    # pcbnew の Save は隣の .kicad_pro をネットクラス無しで書き換えるので、本物の .kicad_pro を run_dir と dest の隣に置き直す
    for d in (os.path.join(run_dir, PROJECT + ".kicad_pro"), os.path.splitext(args.dest)[0] + ".kicad_pro"):
        shutil.copy2(os.path.join(HW, PROJECT + ".kicad_pro"), d)
    print("routed board ->", args.dest)
    return 0 if same else 2


if __name__ == "__main__":
    sys.exit(main())
