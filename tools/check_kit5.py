# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""
KICAD-KIT.md §5 の 15 項目（ERC では見つからない「繋がっているが間違っている」）を、
kicad-cli のネットリスト（hardware/out/rp2040-logic-analyzer.net）から機械的に検査する。

    uv run tools/verify_netlist.py      # 先にネットリストを出す
    uv run tools/check_kit5.py          # 合否表を hardware/out/kit5-check.md に書く
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_schematic import HW, PROJECT, find, find1, parse  # noqa: E402


def load(net_path: Path):
    root = parse(net_path.read_text(encoding="utf-8"))[0]
    comps = {}
    for c in find(find1(root, "components"), "comp"):
        ref = find1(c, "ref")[1]
        props = {}
        for p in find(c, "property"):
            v = find1(p, "value")
            props[find1(p, "name")[1]] = v[1] if v else ""
        comps[ref] = {"value": find1(c, "value")[1], "footprint": (find1(c, "footprint") or [None, ""])[1],
                      "dnp": "dnp" in props, "lcsc": props.get("LCSC Part #", "")}
    nets = {}
    for n in find(find1(root, "nets"), "net"):
        nets[find1(n, "name")[1]] = {(find1(x, "ref")[1], find1(x, "pin")[1]) for x in find(n, "node")}
    return comps, nets


def net_of(nets, ref, pin):
    for name, nodes in nets.items():
        if (ref, str(pin)) in nodes:
            return name
    return None


def main() -> int:
    comps, nets = load(HW / "out" / f"{PROJECT}.net")
    parts = lambda name: sorted({r for r, _ in nets.get(name, set()) if not r.startswith("#")})
    rows = []

    def item(no, title, ok, detail):
        rows.append((no, title, "PASS" if ok is True else ("FAIL" if ok is False else "要決定"), detail))

    # 1. RP2040 の 100nF ×10
    cap10 = [f"C{i}" for i in range(1, 11)]
    ok = all(comps[c]["value"] == "100nF" for c in cap10)
    on33 = [c for c in cap10 if net_of(nets, c, 1) == "+3V3" and net_of(nets, c, 2) == "GND"]
    ondv = [c for c in cap10 if net_of(nets, c, 1) == "/DVDD" and net_of(nets, c, 2) == "GND"]
    ok = ok and len(on33) == 8 and len(ondv) == 2
    item(1, "RP2040 の 100nF が 10 個（IOVDD×6・USB_VDD・ADC_AVDD → +3V3、DVDD×2）", ok,
         f"+3V3–GND: {on33}（8） / DVDD–GND: {ondv}（2）。C11 = U2 用、C12 = 予備（+3V3）")

    # 2. 内蔵レギュレータ
    dv = nets.get("/DVDD", set())
    ok = (comps["C21"]["value"] == "1µF" and net_of(nets, "C21", 1) == "+3V3"
          and comps["C22"]["value"] == "1µF" and net_of(nets, "C22", 1) == "/DVDD"
          and {("U1", "45"), ("U1", "23"), ("U1", "50")} <= dv and ("U1", "23") not in nets["+3V3"])
    item(2, "VREG_VIN / VREG_VOUT に 1µF 各 1・VREG_VOUT→DVDD(23,50)・DVDD は +3V3 と別ネット", ok,
         f"C21→{net_of(nets,'C21',1)} / C22→{net_of(nets,'C22',1)} / DVDD ノード: {sorted(dv)}")

    # 3. 水晶負荷容量
    ok = (comps["C23"]["value"] == "15pF" and comps["C24"]["value"] == "15pF"
          and net_of(nets, "C23", 1) == "/XIN" and net_of(nets, "C24", 1) == "/XTAL_DRV"
          and net_of(nets, "C23", 2) == "GND" and net_of(nets, "C24", 2) == "GND")
    item(3, "15pF ×2（XIN 側・XOUT 側）", ok, f"C23: {net_of(nets,'C23',1)} / C24: {net_of(nets,'C24',1)}（水晶側 = XTAL_DRV）")

    # 4. ダンピング抵抗は XOUT 側
    xin = parts("/XIN")
    ok = (comps["R21"]["value"] == "1kΩ" and {net_of(nets, "R21", 1), net_of(nets, "R21", 2)} == {"/XOUT", "/XTAL_DRV"}
          and xin == ["C23", "U1", "X1"])
    item(4, "1kΩ は XOUT と水晶の間・XIN は直結", ok, f"R21: {net_of(nets,'R21',1)}↔{net_of(nets,'R21',2)} / XIN ネット: {xin}")

    # 5. QSPI_SS プルアップ DNF
    ok = (comps["R23"]["value"] == "10kΩ" and comps["R23"]["dnp"] and comps["R23"]["lcsc"] == ""
          and {net_of(nets, "R23", 1), net_of(nets, "R23", 2)} == {"+3V3", "/QSPI_SS_N"})
    item(5, "R23 10kΩ は DNP・LCSC 空・QSPI_SS_N↔+3V3 にフットプリントだけ置く", ok,
         f"dnp={comps['R23']['dnp']} LCSC='{comps['R23']['lcsc']}' {net_of(nets,'R23',1)}↔{net_of(nets,'R23',2)}")

    # 6. BOOTSEL
    ok = (comps["R22"]["value"] == "1kΩ" and {net_of(nets, "R22", 1), net_of(nets, "R22", 2)} == {"/QSPI_SS_N", "/USB_BOOT"}
          and parts("/USB_BOOT") == ["R22", "SW2"] and net_of(nets, "SW2", 3) == "GND")
    item(6, "SW2 → R22(1kΩ) → QSPI_SS_N", ok, f"USB_BOOT: {parts('/USB_BOOT')} / SW2 pin3→{net_of(nets,'SW2',3)}")

    # 7. USB 27Ω・プルアップ無し
    ok = (comps["R19"]["value"] == "27Ω" and comps["R20"]["value"] == "27Ω"
          and {net_of(nets, "R19", 1), net_of(nets, "R19", 2)} == {"/USB_DP", "/USB_DP_MCU"}
          and {net_of(nets, "R20", 1), net_of(nets, "R20", 2)} == {"/USB_DM", "/USB_DM_MCU"}
          and parts("/USB_DP_MCU") == ["R19", "U1"] and parts("/USB_DM_MCU") == ["R20", "U1"]
          and parts("/USB_DP") == ["J1", "R19", "U8"] and parts("/USB_DM") == ["J1", "R20", "U8"])
    item(7, "USB_DP/DM に 27Ω 各 1・プルアップ/ダウン無し", ok,
         f"USB_DP: {parts('/USB_DP')} → R19 → USB_DP_MCU: {parts('/USB_DP_MCU')}")

    # 8. CC
    ok = (comps["R17"]["value"] == "5.1kΩ" and comps["R18"]["value"] == "5.1kΩ"
          and parts("/CC1") == ["J1", "R17"] and parts("/CC2") == ["J1", "R18"]
          and net_of(nets, "R17", 2) == "GND" and net_of(nets, "R18", 2) == "GND")
    item(8, "CC1 / CC2 に 5.1kΩ 各 1・独立に GND", ok, f"CC1: {parts('/CC1')} / CC2: {parts('/CC2')}")

    # 9. ESD の位置（J1 → USBLC6 → 27Ω → RP2040）
    ok = ("U8" in parts("/USB_DP") and "U8" in parts("/USB_DM") and "U8" not in parts("/USB_DP_MCU")
          and net_of(nets, "U8", 5) == "+5V" and net_of(nets, "U8", 2) == "GND")
    item(9, "USBLC6 はコネクタ側ネット（27Ω の外側）・VBUS/GND 接続", ok,
         f"U8 pins: 1→{net_of(nets,'U8',1)} 6→{net_of(nets,'U8',6)} 3→{net_of(nets,'U8',3)} 4→{net_of(nets,'U8',4)} 5→{net_of(nets,'U8',5)}")

    # 10. TXU OE → +3V3
    ok = (comps["R24"]["value"] == "10kΩ" and {net_of(nets, "R24", 1), net_of(nets, "R24", 2)} == {"+3V3", "/TXU_OE"}
          and {("U1", "35")} <= nets["/TXU_OE"] and all((f"U{k}", "8") in nets["/TXU_OE"] for k in (3, 4, 5, 6)))
    item(10, "TXU_OE = GP23 ＋ 10kΩ プルアップは +3V3（VREF ではない）", ok,
         f"R24: {net_of(nets,'R24',1)}↔{net_of(nets,'R24',2)} / TXU_OE: {parts('/TXU_OE')}")

    # 11. TXU 未使用入力・パスコン・NC
    ok = True
    det = []
    for k in (3, 4, 5, 6):
        ca, cb = f"C{13 + 2 * (k - 3)}", f"C{14 + 2 * (k - 3)}"
        ok &= (comps[ca]["value"] == "100nF" and net_of(nets, ca, 1) == "VREF" and comps[cb]["value"] == "100nF" and net_of(nets, cb, 1) == "+3V3")
        ok &= net_of(nets, f"U{k}", 1) == "VREF" and net_of(nets, f"U{k}", 14) == "+3V3" and net_of(nets, f"U{k}", 7) == "GND"
        ok &= net_of(nets, f"U{k}", 6).startswith("unconnected-") and net_of(nets, f"U{k}", 9).startswith("unconnected-")
        det.append(f"U{k}: VCCA←{ca}({net_of(nets, ca, 1)}) VCCB←{cb}({net_of(nets, cb, 1)}) NC6/9 未接続")
    for n in range(16):
        ok &= parts(f"/CH{n}_A") == [f"R{n + 1}", f"U{3 + n // 4}"]     # 外付けプルダウン無し
    item(11, "VCCA/VCCB に 100nF 各 1 ×4（C13–C20）・A 入力に外付け無し・NC(6,9) 未接続", ok, " / ".join(det))

    # 12. SW1 の並び
    sw = {p: net_of(nets, "SW1", p) for p in (1, 2, 3, 4, 5, 6)}
    ok = sw[1] == "VREF" and sw[2] == "+3V3" and sw[3] == "/VREF_EXT" and sw[4] == "+5V"
    item(12, "SW1: ピン1 = VREF(コモン)・2 = +3V3・3 = EXT・4 = +5V（+3V3 と +5V が隣接しない）", ok,
         f"SW1 {sw}（5/6 = 固定ラグ・未接続）")

    # 13. 入力直列抵抗 100Ω
    ok = True
    for n in range(16):
        r = f"R{n + 1}"
        ok &= comps[r]["value"] == "100Ω" and {net_of(nets, r, 1), net_of(nets, r, 2)} == {f"/CH{n}_IN", f"/CH{n}_A"}
        ok &= ("J2", str(2 * n + 1)) in nets[f"/CH{n}_IN"]
    item(13, "R1–R16 = 100Ω、J2 と TXU0104 A ピンの間（1kΩ ではない）", ok, "R1–R16 すべて 100Ω・CHn_IN(J2 奇数ピン)↔CHn_A")

    # 14. LED 3 個
    def chain(rr, dd):
        return (comps[rr]["value"] == "1kΩ" and net_of(nets, rr, 2) == net_of(nets, dd, 2) and net_of(nets, dd, 1) == "GND", net_of(nets, rr, 1))
    c1, c2, c3 = chain("R25", "D1"), chain("R26", "D2"), chain("R27", "D3")
    ok = c1[0] and c2[0] and c3[0] and c1[1] == "+3V3" and c2[1] == "VREF" and c3[1] == "/LED_STATUS" and ("U1", "37") in nets["/LED_STATUS"]
    item(14, "D1 = +3V3、D2 = VREF、D3 = LED_STATUS(GP25)、各 1kΩ", ok, f"D1←{c1[1]} / D2←{c2[1]} / D3←{c3[1]}")

    # 15. SWD
    swclk, swdio = net_of(nets, "U1", 24), net_of(nets, "U1", 25)
    item(15, "SWD を出すか決める（SPEC §6 に無い）", None,
         f"SWCLK→{swclk} / SWDIO→{swdio}。未決のため no_connect で明示。テストパッド 2 点の追加は handoff で提案")

    # 補: RUN に外付け無し
    ok = parts("/RUN") == ["SW3", "U1"] and net_of(nets, "SW3", 3) == "GND"
    item("補", "RUN(26) に外付け部品なし（SW3 で GND に落とすだけ）", ok, f"RUN: {parts('/RUN')}")

    lines = ["| # | 項目 | 判定 | 根拠（ネットリスト） |", "|--:|:---|:---|:---|"]
    for no, title, st, detail in rows:
        lines.append(f"| {no} | {title} | **{st}** | {detail} |")
    n_pass = sum(1 for r in rows if r[2] == "PASS")
    n_fail = sum(1 for r in rows if r[2] == "FAIL")
    lines.append("")
    lines.append(f"PASS {n_pass} / FAIL {n_fail} / 要決定 {len(rows) - n_pass - n_fail}")
    text = "\n".join(lines) + "\n"
    (HW / "out" / "kit5-check.md").write_text(text, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
