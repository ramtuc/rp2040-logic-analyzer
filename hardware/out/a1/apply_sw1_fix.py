# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
A0 → A1: SW1（SK13D07VG5）の pad ネットを回路図（2026-10-04 修正・COM = pad2）に合わせる基板データの修正。

    py -3 hardware/out/a1/apply_sw1_fix.py hardware/rp2040-logic-analyzer.kicad_pcb

変更（これ以外は触らない）
  1. SW1 pad1: VREF → +3V3（In2 の +3V3 プレーンに THT バレルで接続・サーマル）
     SW1 pad2: +3V3 → VREF
  2. pad1 に来ていた VREF の F.Cu 0.5mm 配線 (108.5492,110.1992)→(107.35,109) を削除し、
     同じ分岐点から pad2 (107.35,113) へ 45°＋垂直の 2 本 (0.5mm・F.Cu・VREF) を追加
  3. 表シルク "RP2040 LA A0" → "RP2040 LA A1"、タイトルブロック rev A0 → A1・date → 2026-10-10
  4. 裏シルクに "CERN-OHL-P v2" を 1 行追加（B.SilkS・ミラー・基板下辺中央）

実行後は kicad-cli pcb drc --refill-zones --save-board でゾーンを再充填して保存する
（pad1/pad2 のネットが入れ替わるので In2 プレーンのサーマル／アンチパッドが変わる）。
"""

from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path

NS = uuid.UUID("3b4d5e6f-a1a1-4a1a-9a1a-5a1a6a1a7a1a")   # A1 修正で足す要素の uuid5 名前空間（再実行で同じ ID になる）
REMOVED_SEG = "8fd9686e-cdd4-4471-9ef3-6ef33ef865fa"      # (108.5492 110.1992)→(107.35 109) VREF 0.5 F.Cu
JUNCTION = ("108.5492", "110.1992")
CORNER = ("107.35", "111.3984")                            # 分岐点から 45° で x=107.35 に乗る点
PAD2 = ("107.35", "113")


def seg(start, end, name) -> str:
    return ("\t(segment\n"
            f"\t\t(start {start[0]} {start[1]})\n"
            f"\t\t(end {end[0]} {end[1]})\n"
            "\t\t(width 0.5)\n"
            "\t\t(layer \"F.Cu\")\n"
            "\t\t(net \"VREF\")\n"
            f"\t\t(uuid \"{uuid.uuid5(NS, name)}\")\n"
            "\t)\n")


def main(path: Path) -> int:
    raw = path.read_bytes()
    crlf = b"\r\n" in raw                                  # pcbnew（Windows）の保存は CRLF。改行は元のまま保つ
    text = raw.decode("utf-8").replace("\r\n", "\n")
    orig = text

    # 1. SW1 の pad1 / pad2 のネット（SW1 フットプリントのブロック内だけを書き換える）
    i = text.index('(property "Reference" "SW1"')
    start = text.rfind("\n\t(footprint ", 0, i)
    end = text.index("\n\t(footprint ", i)
    blk = text[start:end]
    n1 = blk.count('(pad "1" thru_hole circle')
    n2 = blk.count('(pad "2" thru_hole circle')
    assert n1 == 1 and n2 == 1, (n1, n2)
    blk2 = re.sub(r'(\(pad "1" thru_hole circle\n(?:\t\t\t[^\n]*\n)*?\t\t\t\(net )"VREF"\)', r'\1"+3V3")', blk, count=1)
    blk2 = re.sub(r'(\(pad "2" thru_hole circle\n(?:\t\t\t[^\n]*\n)*?\t\t\t\(net )"\+3V3"\)', r'\1"VREF")', blk2, count=1)
    assert blk2 != blk and blk2.count('(net "VREF")') == 1 and blk2.count('(net "+3V3")') == 1
    text = text[:start] + blk2 + text[end:]

    # 2. pad1 への VREF 配線を外し、pad2 への 2 本を同じ場所に入れる
    m = re.search(r'\t\(segment\n(?:\t\t[^\n]*\n)*?\t\t\(uuid "' + REMOVED_SEG + r'"\)\n\t\)\n', text)
    assert m, "removed segment not found"
    old = m.group(0)
    assert "(start 108.5492 110.1992)" in old and "(end 107.35 109)" in old and '(net "VREF")' in old, old
    new = seg(JUNCTION, CORNER, "A1 VREF seg1 junction->corner") + seg(CORNER, PAD2, "A1 VREF seg2 corner->SW1 pad2")
    text = text[:m.start()] + new + text[m.end():]

    # 3. 表シルクの版表記・タイトルブロック
    assert text.count('(gr_text "RP2040 LA A0"') == 1
    text = text.replace('(gr_text "RP2040 LA A0"', '(gr_text "RP2040 LA A1"')
    assert text.count('(rev "A0")') == 1 and text.count('(date "2026-09-20")') == 1
    text = text.replace('(rev "A0")', '(rev "A1")').replace('(date "2026-09-20")', '(date "2026-10-10")')

    # 4. 裏シルクにライセンス表記（基板外形 (100,100)-(165,145) の下辺中央・裏面は部品なし・THT パッドから離れた位置）
    anchor = '(gr_text "electwork.net"'
    j = text.index(anchor)
    j0 = text.rfind("\n\t(gr_text ", 0, j + 1)
    j1 = text.index("\n\t)\n", j0) + len("\n\t)\n")
    lic = ("\t(gr_text \"CERN-OHL-P v2\"\n"
           "\t\t(at 132.5 142 0)\n"
           "\t\t(layer \"B.SilkS\")\n"
           f"\t\t(uuid \"{uuid.uuid5(NS, 'A1 B.SilkS CERN-OHL-P v2')}\")\n"
           "\t\t(effects\n"
           "\t\t\t(font\n"
           "\t\t\t\t(size 1 1)\n"
           "\t\t\t\t(thickness 0.15)\n"
           "\t\t\t)\n"
           "\t\t\t(justify mirror)\n"
           "\t\t)\n"
           "\t)\n")
    text = text[:j1] + lic + text[j1:]

    assert text != orig
    out = text.replace("\n", "\r\n") if crlf else text
    path.write_bytes(out.encode("utf-8"))
    print(f"wrote {path} ({len(raw)} -> {len(out.encode('utf-8'))} bytes, {'CRLF' if crlf else 'LF'})")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
