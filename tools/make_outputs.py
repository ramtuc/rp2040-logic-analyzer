# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""
配線済み基板（hardware/rp2040-logic-analyzer.kicad_pcb）から製造データとレビュー用画像を出す。

    uv run tools/make_outputs.py

出力（hardware/out/）
    drc.json / drc.rpt / drc-summary.md      kicad-cli pcb drc --severity-all --refill-zones
    gerbers/                                  Gerber（Protel 拡張子・X2）＋ Excellon（PTH/NPTH 分離・mm・decimal）＋ map
    rp2040-logic-analyzer-gerbers.zip         JLCPCB アップロード用
    pos-kicad.csv / cpl-jlcpcb.csv            位置ファイル（KiCad 生）と JLCPCB 列名の CPL（回転補正済み）
    cpl-rotation-report.md                    回転補正の根拠（Fabrication Toolkit の transformations.csv と同じ規則）
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
    run([KICAD_CLI, "pcb", "export", "drill", "-o", str(gdir) + "/", "--format", "excellon", "--excellon-separate-th",
         "--excellon-units", "mm", "--excellon-zeros-format", "decimal", "--drill-origin", "absolute",
         "--generate-map", "--map-format", "gerberx2", PCB])
    zpath = OUT / f"{PROJECT}-gerbers.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(gdir.iterdir()):
            if f.is_file():
                z.write(f, f.name)
    return sorted(f.name for f in gdir.iterdir())


def cpl():
    pos = OUT / "pos-kicad.csv"
    run([KICAD_CLI, "pcb", "export", "pos", "-o", pos, "--format", "csv", "--units", "mm", "--side", "front",
         "--exclude-dnp", "--exclude-fp-th", PCB])
    rows = list(csv.DictReader(pos.open(encoding="utf-8")))
    out_rows, report = [], []
    for r in rows:
        ref, pkg = r["Ref"], r["Package"]
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
             "KiCad の位置ファイル（`pos-kicad.csv`・Y 上向き正・mm・DNP と THT を除外）に、Fabrication Toolkit の "
             "`transformations.csv` と同じ規則（フットプリント名の先頭一致）で回転を足した。補正 0 のものは JLCPCB 側の部品向きと"
             "一致する保証が無いので、注文画面の 3D プレビューで確認する（KIT §2.3）。", "",
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
    (OUT / "cpl-rotation-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(out_rows)


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
    n = cpl()
    print("cpl rows:", n)
    render()
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
