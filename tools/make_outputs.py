# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""
配線済み基板（hardware/rp2040-logic-analyzer.kicad_pcb）から製造データとレビュー用画像を出す。

    uv run tools/make_outputs.py

出力（hardware/out/）
    drc.json / drc.rpt / drc-summary.md      kicad-cli pcb drc --severity-all --refill-zones
    gerbers/                                  Gerber（Protel 拡張子・X2）＋ Excellon（PTH/NPTH 分離・mm・decimal・長穴は route 記法）＋ map
    rp2040-logic-analyzer-gerbers.zip         JLCPCB アップロード用
    pos-kicad.csv / cpl-jlcpcb.csv            位置ファイル（KiCad 生・THT/DNP 込み）と JLCPCB 列名の CPL（SMD 実装対象のみ・回転補正済み）
    cpl-rotation-report.md                    回転補正の根拠（Fabrication Toolkit の transformations.csv と同じ規則）と CPL から除外した参照子
    bom-flat.csv / bom-grouped.csv            回路図の BOM（kicad-cli sch export bom。1 行 1 部品／Value+Footprint+LCSC+DNP でまとめ・範囲表記なし）
    bom-jlcpcb.csv                            JLCPCB 列名の BOM（DNP 除外・LCSC 空の汎用 R/C は LCSC_FILL で補完・LCSC が無い TP/ヘッダは除外）
    bom-cpl-check.md                          BOM ／ CPL ／ THT ／ DNP ／ TP の照合表（回路図の全参照子が漏れなくどれかに入ること）
    render-top.png / render-bottom.png        3D レンダ（人間レビュー用）
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_schematic import HW, KICAD_CLI, PROJECT  # noqa: E402

OUT = HW / "out"
PCB = HW / f"{PROJECT}.kicad_pcb"
SCH = HW / f"{PROJECT}.kicad_sch"
LAYERS = "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"

# JLCPCB の部品向きに合わせる回転補正（bennymeg/Fabrication-Toolkit plugins/transformations.csv・Apache-2.0 と同じ規則。
# フットプリント名（ライブラリ名を除く）の先頭一致。ここに無いものは補正 0 ＝ 発注画面の 3D プレビューで人間が確認する）
ROTATION_DB = [
    (r"^QFN-", 90),
    (r"^SOT-223", 180),
    (r"^SOT-23", 180),
    (r"^SOIC-", 270),
    (r"^TSSOP-", 270),
    (r"^SOP-(?!18_)", 270),
    (r"^SSOP-", 270),
    (r"^MSOP-", 270),
    (r"^DFN-", 270),
    (r"^LQFP-", 270),
    (r"^TQFP-", 270),
]

# 回路図の `LCSC Part #` が空の汎用部品（SPEC §10 で「汎用 Basic」としか決めていない R/C）に BOM 出力時だけ入れる JLCPCB 番号。
# キーは (Value, フットプリント名)。2026-09-20 に JLCPCB の部品 API（cart.jlcpcb.com/shoppingCart/smtGood/getComponentDetail）で
# componentLibraryType（base = Basic）・仕様・在庫を確認した。27Ω 0402 だけは Basic が 1 件も無い（412 件すべて expand）ので Extended。
# 発注時は JLCPCB の部品照合画面で在庫と区分を再確認する（回路図は変えない・ここを書き換えれば BOM に反映される）
LCSC_FILL = {
    ("100nF", "C_0402_1005Metric"): "C1525",    # Samsung CL05B104KO5NNNC 100nF 16V X7R ±10%   base 在庫 28,078,814
    ("1µF", "C_0402_1005Metric"): "C52923",     # Samsung CL05A105KA5NQNC 1µF 25V X5R ±10%     base 在庫 7,879,905
    ("15pF", "C_0402_1005Metric"): "C1548",     # FH 0402CG150J500NT 15pF 50V C0G ±5%          base 在庫 1,539,852
    ("10µF", "C_0805_2012Metric"): "C15850",    # Samsung CL21A106KAYNNNE 10µF 25V X5R ±10%    base 在庫 6,154,988
    ("100Ω", "R_0402_1005Metric"): "C25076",    # UNI-ROYAL 0402WGF1000TCE 100Ω ±1%             base 在庫 2,925,326
    ("5.1kΩ", "R_0402_1005Metric"): "C25905",   # UNI-ROYAL 0402WGF5101TCE 5.1kΩ ±1%            base 在庫 6,840,501
    ("27Ω", "R_0402_1005Metric"): "C25100",     # UNI-ROYAL 0402WGF270JTCE 27Ω ±1%   ★expand（Basic 無し）在庫 81,952
    ("1kΩ", "R_0402_1005Metric"): "C11702",     # UNI-ROYAL 0402WGF1001TCE 1kΩ ±1%              base 在庫 10,670,360
    ("10kΩ", "R_0402_1005Metric"): "C25744",    # UNI-ROYAL 0402WGF1002TCE 10kΩ ±1%             base 在庫 26,111,398
}


def run(args: list[str], **kw) -> subprocess.CompletedProcess:
    print("$", " ".join(str(a) for a in args))
    return subprocess.run([str(a) for a in args], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


def drc() -> dict:
    run([KICAD_CLI, "pcb", "drc", "--severity-all", "--refill-zones", "--format", "json", "-o", OUT / "drc.json", PCB])
    run([KICAD_CLI, "pcb", "drc", "--severity-all", "--refill-zones", "--format", "report", "-o", OUT / "drc.rpt", PCB])
    d = json.loads((OUT / "drc.json").read_text(encoding="utf-8"))
    counts = Counter((v["severity"], v["type"]) for v in d.get("violations", []))
    unconnected = d.get("unconnected_items", [])
    by_net = Counter()
    for v in unconnected:
        m = re.search(r"\[([^\]]+)\]", v["items"][0]["description"])
        by_net[m.group(1) if m else "?"] += 1
    lines = ["# DRC（kicad-cli pcb drc --severity-all --refill-zones）", "",
             f"- 基板: `{PCB.relative_to(HW.parent)}`", f"- 未配線: **{len(unconnected)}**", ""]
    lines.append("| severity | type | 件数 |")
    lines.append("|:--|:--|--:|")
    for (sev, typ), n in sorted(counts.items()):
        lines.append(f"| {sev} | {typ} | {n} |")
    if by_net:
        lines += ["", "未配線の内訳（ネット別）:", ""] + [f"- `{k}`: {v}" for k, v in by_net.most_common()]
    errors = [v for v in d.get("violations", []) if v["severity"] == "error"]
    if errors:
        lines += ["", "エラー一覧:", ""]
        for v in errors[:80]:
            items = " / ".join(i["description"] for i in v.get("items", []))
            lines.append(f"- {v['type']}: {v['description']} — {items}")
    (OUT / "drc-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"errors": sum(n for (s, _), n in counts.items() if s == "error"),
            "warnings": sum(n for (s, _), n in counts.items() if s == "warning"), "unconnected": len(unconnected)}


def gerbers():
    gdir = OUT / "gerbers"
    gdir.mkdir(exist_ok=True)
    for old in gdir.iterdir():
        if old.is_file():
            old.unlink()
    run([KICAD_CLI, "pcb", "export", "gerbers", "-o", str(gdir) + "/", "--layers", LAYERS, "--subtract-soldermask",
         "--check-zones", "--precision", "6", PCB])
    # 長穴（USB-C シェルの脚 ×4・SW1 の固定脚 ×2）の記法は route（G00/M15/G01/M16 = GUI の「Use route command (recommended)」）。
    # A0 の注文に使った GUI 出力と同じ記法で、JLCPCB で製造済み（実測 2026-10-10: kicad-cli 10.0.3 の既定 alternate は G85 スロット指令。
    # JLCPCB の KiCad 手順は alternate を案内しているが、製造実績のある route に合わせる）
    run([KICAD_CLI, "pcb", "export", "drill", "-o", str(gdir) + "/", "--format", "excellon", "--excellon-separate-th",
         "--excellon-units", "mm", "--excellon-zeros-format", "decimal", "--excellon-oval-format", "route",
         "--drill-origin", "absolute", "--generate-map", "--map-format", "gerberx2", PCB])
    zpath = OUT / f"{PROJECT}-gerbers.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(gdir.iterdir()):
            if f.is_file():
                z.write(f, f.name)
    return sorted(f.name for f in gdir.iterdir())


def footprint_kinds() -> dict[str, str]:
    """基板の全フットプリントを参照子 → 区分に分ける。区分は CPL/BOM の照合に使う。
    smd = SMD 実装（CPL に載せる）／tht = THT（手はんだ・CPL に載せない）／dnp = 未実装／tp = テストパッド（exclude_from_pos_files）"""
    kinds = {}
    for blk in PCB.read_text(encoding="utf-8").split('\n\t(footprint "')[1:]:
        ref = re.search(r'\(property "Reference" "([^"]+)"', blk).group(1)
        m = re.search(r"\n\t\t\(attr ([^)]*)\)", blk)
        attr = set(m.group(1).split()) if m else set()
        if "dnp" in attr:
            kinds[ref] = "dnp"
        elif "exclude_from_pos_files" in attr:
            kinds[ref] = "tp"
        elif "through_hole" in attr:
            kinds[ref] = "tht"
        else:
            kinds[ref] = "smd"          # attr smd（attr 無しの「未指定」も SMD 扱い＝CPL に載せて 3D で確認）
    return kinds


def cpl(kinds: dict[str, str]) -> list[str]:
    """位置ファイルは THT/DNP も含めて出し（--exclude-fp-th を付けると THT の固定ピンを持つ USB-C J1 が落ちる）、
    スクリプト側で kinds == smd だけを CPL にする。テストパッドは KiCad が exclude_from_pos_files で既に落としている"""
    pos = OUT / "pos-kicad.csv"
    run([KICAD_CLI, "pcb", "export", "pos", "-o", pos, "--format", "csv", "--units", "mm", "--side", "front", PCB])
    rows = list(csv.DictReader(pos.open(encoding="utf-8")))
    pos_refs = {r["Ref"] for r in rows}
    missing = sorted(ref for ref, k in kinds.items() if k == "smd" and ref not in pos_refs)
    if missing:
        raise SystemExit(f"SMD 実装対象なのに位置ファイルに無い: {missing}")
    excluded = [(r["Ref"], kinds.get(r["Ref"], "?")) for r in rows if kinds.get(r["Ref"]) != "smd"]
    out_rows, report = [], []
    for r in rows:
        ref, pkg = r["Ref"], r["Package"]
        if kinds.get(ref) != "smd":
            continue
        name = pkg.split(":", 1)[-1]
        off = next((rot for pat, rot in ROTATION_DB if re.match(pat, name)), 0)
        rot = (float(r["Rot"]) + off) % 360.0
        out_rows.append({"Designator": ref, "Mid X": f"{float(r['PosX']):.4f}mm", "Mid Y": f"{float(r['PosY']):.4f}mm",
                         "Layer": "Top" if r["Side"].lower().startswith("top") else "Bottom", "Rotation": f"{rot:.1f}"})
        report.append((ref, pkg, float(r["Rot"]), off, rot))
    with (OUT / "cpl-jlcpcb.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        w.writeheader()
        w.writerows(out_rows)
    lines = ["# CPL 回転補正（JLCPCB 列名 Designator / Mid X / Mid Y / Layer / Rotation）", "",
             "KiCad の位置ファイル（`pos-kicad.csv`・Y 上向き正・mm・原点は KiCad のページ原点＝Gerber と同じ絶対原点）から "
             "SMD 実装対象だけを取り、Fabrication Toolkit（bennymeg/Fabrication-Toolkit master `plugins/transformations.csv`・51 行）"
             "と同じ規則（フットプリント名の先頭一致）で回転を足した。補正 0 のものは JLCPCB 側の部品向きと"
             "一致する保証が無いので、注文画面の 3D プレビューで確認する（KIT §2.3）。", "",
             "- **Mid Y が負**なのは KiCad の pos 規約（Y 上向き正・基板がページ原点より下にある）。JLCPCB の公式手順"
             "（help「How To Export BOM and CPL Files From KiCad 10」2026-09-09 更新）は KiCad の .pos の列名を Designator/Mid X/Mid Y/"
             "Rotation/Layer に**改名するだけ**で座標変換を求めておらず、推奨の Fabrication Toolkit も `mid_y = (y − aux_origin.y) × −1`"
             "（process.py）で同じ符号を出す。JLCPCB は Gerber と同じ原点で相対位置を見るので負の値のままで受け付ける",
             "- **USB-C J1（`USB_C_Receptacle_HRO_TYPE-C-31-M-12`）は transformations.csv に規則が無い**（USB/Type-C/HRO の行は 0 件）"
             "ので補正 0＝KiCad の回転そのまま。位置は KiCad のアンカー（Fabrication Toolkit 既定の「パッド外接矩形の中心」とは "
             "局所 Y で 1.46mm ずれる。THT 固定穴まで含めた矩形なので機械的中心とも一致しない）。**3D プレビューで基板端からの張り出しと"
             "向きを目視**", "",
             "| Designator | Footprint | KiCad rot | 補正 | CPL rot | 備考 |", "|:--|:--|--:|--:|--:|:--|"]
    for ref, pkg, kr, off, rot in report:
        note = ""
        n = pkg.split(":", 1)[-1]
        if n.startswith("LED_"):
            note = "★極性: 3D プレビューで目視（DB に規則なし）"
        elif "USB_C" in n:
            note = "★原点/向き: 3D プレビューで目視（DB に規則なし）"
        elif n.startswith("SOT-223"):
            note = "タブの向き: 3D プレビューで目視（DB 規則 +180）"
        elif n.startswith("QFN-"):
            note = "1 番ピン位置を 3D プレビューで目視（DB 規則 +90）"
        elif pkg.startswith("lcsc:") or n.startswith("Crystal"):
            note = "DB に規則なし（0）"
        lines.append(f"| {ref} | `{pkg}` | {kr:.0f} | {off:+d} | {rot:.0f} | {note} |")
    kind_ja = {"tht": "THT（手はんだ）", "dnp": "DNP（未実装）", "tp": "テストパッド"}
    lines += ["", f"## CPL から除外した参照子（位置ファイルにはあるが SMD 実装対象でない・{len(excluded)} 件）", ""]
    lines += [f"- {ref}: {kind_ja.get(k, k)}" for ref, k in excluded]
    lines += ["- TP1〜TP9: exclude_from_pos_files なので位置ファイル自体に出ない（部品なし）"]
    (OUT / "cpl-rotation-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [r["Designator"] for r in out_rows]


BOM_FIELDS = "Reference,Value,Footprint,LCSC Part #"
BOM_LABELS = "Designator,Comment,Footprint,LCSC Part #"


def bom() -> tuple[list[dict], list[tuple[str, str]]]:
    """BOM は回路図から出す（基板側フットプリントの LCSC も同じく空なので、基板から出しても埋まらない）。
    bom-flat.csv = 1 行 1 部品（照合の母集団）／bom-grouped.csv = まとめ（DNP 込み）／bom-jlcpcb.csv = JLCPCB 用（DNP 除外・LCSC 補完）。
    参照子は `--ref-range-delimiter ""` で範囲表記（C1-C20）にせずカンマ区切り。DNP は `${DNP}` でまとめ分けしないと R23/R24 が同じ行になる"""
    run([KICAD_CLI, "sch", "export", "bom", "-o", OUT / "bom-flat.csv", "--fields", BOM_FIELDS + ",${DNP},Description",
         "--labels", BOM_LABELS + ",DNP,Description", "--ref-range-delimiter", "", SCH])
    run([KICAD_CLI, "sch", "export", "bom", "-o", OUT / "bom-grouped.csv", "--fields", BOM_FIELDS + ",${QUANTITY},${DNP}",
         "--labels", BOM_LABELS + ",Qty,DNP", "--group-by", "Value,Footprint,LCSC Part #,${DNP}", "--ref-range-delimiter", "", SCH])
    rows, dropped = [], []
    for r in csv.DictReader((OUT / "bom-grouped.csv").open(encoding="utf-8")):
        if r["DNP"]:
            continue                                        # DNP（R23・J4）は JLCPCB に渡さない
        lcsc = r["LCSC Part #"] or LCSC_FILL.get((r["Comment"], r["Footprint"].split(":", 1)[-1]), "")
        if not lcsc:                                        # TP（部品なし）・ヘッダ J2/J3（要選定・手はんだ）
            dropped += [(ref, r["Comment"]) for ref in r["Designator"].split(",")]
            continue
        rows.append({"Designator": r["Designator"], "Comment": r["Comment"], "Footprint": r["Footprint"], "JLCPCB Part #": lcsc})
    with (OUT / "bom-jlcpcb.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Designator", "Comment", "Footprint", "JLCPCB Part #"], quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)
    return rows, dropped


def check(kinds: dict[str, str], cpl_refs: list[str], bom_rows: list[dict], dropped: list[tuple[str, str]]) -> int:
    """回路図の全参照子（bom-flat.csv）が BOM ／ CPL ／ THT ／ DNP ／ TP のどれかに漏れなく入るかを照合して bom-cpl-check.md に書く"""
    flat = {r["Designator"]: r for r in csv.DictReader((OUT / "bom-flat.csv").open(encoding="utf-8"))}
    bom_of = {ref: r for r in bom_rows for ref in r["Designator"].split(",")}
    cpl_set, ng = set(cpl_refs), []
    kind_ja = {"smd": "SMD 実装", "tht": "THT（手はんだ）", "dnp": "DNP（未実装）", "tp": "テストパッド"}
    lines = ["# BOM / CPL 照合（回路図の全参照子 → JLCPCB BOM・CPL・THT・DNP・TP）", "",
             f"- 回路図の部品: **{len(flat)}**（bom-flat.csv）／基板のフットプリント: **{len(kinds)}**",
             f"- CPL（SMD 実装対象）: **{len(cpl_set)}**／JLCPCB BOM の参照子: **{len(bom_of)}**（行数 {len(bom_rows)}・全行に JLCPCB Part # あり: "
             f"{'はい' if all(r['JLCPCB Part #'] for r in bom_rows) else 'いいえ'}）", "",
             "| Ref | Comment | 区分（基板 attr） | BOM | CPL | JLCPCB Part # |", "|:--|:--|:--|:--|:--|:--|"]
    for ref in sorted(set(flat) | set(kinds), key=lambda s: (re.match(r"[A-Z]+", s).group(0), int(re.search(r"\d+", s).group(0)))):
        k = kinds.get(ref)
        in_bom, in_cpl = ref in bom_of, ref in cpl_set
        expect_bom = k in ("smd", "tht") and ref not in dict(dropped)
        if ref not in flat or k is None or in_cpl != (k == "smd") or in_bom != expect_bom:
            ng.append(ref)
        lines.append(f"| {ref} | {flat.get(ref, {}).get('Comment', '—')} | {kind_ja.get(k, '基板に無い')} | {'○' if in_bom else '—'} | "
                     f"{'○' if in_cpl else '—'} | {bom_of[ref]['JLCPCB Part #'] if in_bom else ''} |")
    by_kind = Counter(kinds.values())
    lines += ["", "## 集計", "",
              f"- 回路図 {len(flat)} ＝ CPL {by_kind['smd']} ＋ THT {by_kind['tht']}（{', '.join(sorted(r for r, k in kinds.items() if k == 'tht'))}）"
              f" ＋ DNP {by_kind['dnp']}（{', '.join(sorted(r for r, k in kinds.items() if k == 'dnp'))}）＋ TP {by_kind['tp']}"
              f" → {by_kind['smd'] + by_kind['tht'] + by_kind['dnp'] + by_kind['tp']}",
              f"- JLCPCB BOM {len(bom_of)} ＝ CPL {len(cpl_set)} ＋ CPL に無い BOM 行 {sorted(set(bom_of) - cpl_set)}（THT・JLCPCB 側で未実装扱い）",
              f"- BOM から落とした参照子（LCSC 無し）: {', '.join(f'{r}（{c}）' for r, c in dropped)}",
              f"- **不整合: {len(ng)} 件**" + (f" → {ng}" if ng else "")]
    (OUT / "bom-cpl-check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(ng)


def render():
    for side in ("top", "bottom"):
        run([KICAD_CLI, "pcb", "render", "--side", side, "--width", "1800", "--height", "1250", "--quality", "basic",
             "--background", "opaque", "-o", OUT / f"render-{side}.png", PCB])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(exist_ok=True)
    d = drc()
    print("DRC:", d)
    files = gerbers()
    print("gerbers:", len(files), "files")
    kinds = footprint_kinds()
    cpl_refs = cpl(kinds)
    print("cpl rows:", len(cpl_refs))
    bom_rows, dropped = bom()
    print("bom rows:", len(bom_rows), "dropped:", [r for r, _ in dropped])
    ng = check(kinds, cpl_refs, bom_rows, dropped)
    print("bom/cpl check NG:", ng)
    render()
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
