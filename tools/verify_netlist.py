# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""
生成した回路図のネットリストを KICAD-KIT.md §4.1 / SPEC.md §7 の期待表と突き合わせる。

    uv run tools/verify_netlist.py            # kicad-cli でネットリストを出して照合、Markdown 表を stdout に

期待表は KIT §4.1 のネット名と接続先を (参照子, ピン番号) の集合に落としたもの。
電源シンボル（#PWR）と PWR_FLAG（#FLG）は照合対象から外す（存在は ERC が見る）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_schematic import HW, PROJECT, netlist_nets  # noqa: E402

# RP2040 のピン番号（KiCad シンボル MCU_RaspberryPi:RP2040 = データシート Table 621）
GPIO = {0: "2", 1: "3", 2: "4", 3: "5", 4: "6", 5: "7", 6: "8", 7: "9", 8: "11", 9: "12", 10: "13", 11: "14", 12: "15",
        13: "16", 14: "17", 15: "18", 16: "27", 17: "28", 18: "29", 19: "30", 20: "31", 21: "32", 22: "34", 23: "35",
        24: "36", 25: "37", 26: "38", 27: "39", 28: "40", 29: "41"}
TXU_A = {0: "2", 1: "3", 2: "4", 3: "5"}          # A1..A4
TXU_B = {0: "13", 1: "12", 2: "11", 3: "10"}      # B1Y..B4Y


def expected() -> dict[str, set[tuple[str, str]]]:
    e: dict[str, set] = {}
    for n in range(16):
        u = f"U{3 + n // 4}"
        ch = n % 4
        e[f"/CH{n}_IN"] = {("J2", str(2 * n + 1)), (f"R{n + 1}", "1")}
        e[f"/CH{n}_A"] = {(f"R{n + 1}", "2"), (u, TXU_A[ch])}
        e[f"/D{n}"] = {(u, TXU_B[ch]), ("U1", GPIO[n])}
    e["+5V"] = {("J1", "A4"), ("J1", "A9"), ("J1", "B4"), ("J1", "B9"), ("U8", "5"), ("U7", "3"), ("SW1", "4"), ("C25", "1")}
    e["+3V3"] = ({("U7", "2"), ("U2", "8"), ("SW1", "2"), ("R23", "1"), ("R24", "1"), ("R25", "1"), ("C26", "1"), ("C11", "1")}
                 | {("U1", p) for p in ("1", "10", "22", "33", "42", "49", "43", "44", "48")}
                 | {(f"U{k}", "14") for k in (3, 4, 5, 6)}
                 | {(f"C{k}", "1") for k in (1, 2, 3, 4, 5, 6, 9, 10, 12, 21, 14, 16, 18, 20)})
    e["VREF"] = {("SW1", "1"), ("R26", "1")} | {(f"U{k}", "1") for k in (3, 4, 5, 6)} | {(f"C{k}", "1") for k in (13, 15, 17, 19)}
    e["/DVDD"] = {("U1", "45"), ("U1", "23"), ("U1", "50"), ("C7", "1"), ("C8", "1"), ("C22", "1")}
    e["/USB_DP"] = {("J1", "A6"), ("J1", "B6"), ("U8", "1"), ("U8", "6"), ("R19", "1")}
    e["/USB_DP_MCU"] = {("R19", "2"), ("U1", "47")}
    e["/USB_DM"] = {("J1", "A7"), ("J1", "B7"), ("U8", "3"), ("U8", "4"), ("R20", "1")}
    e["/USB_DM_MCU"] = {("R20", "2"), ("U1", "46")}
    e["/CC1"] = {("J1", "A5"), ("R17", "1")}
    e["/CC2"] = {("J1", "B5"), ("R18", "1")}
    e["/XIN"] = {("U1", "20"), ("X1", "1"), ("C23", "1")}
    e["/XOUT"] = {("U1", "21"), ("R21", "1")}
    e["/XTAL_DRV"] = {("R21", "2"), ("X1", "3"), ("C24", "1")}
    e["/QSPI_SS_N"] = {("U1", "56"), ("U2", "1"), ("R22", "1"), ("R23", "2")}
    e["/QSPI_SCLK"] = {("U1", "52"), ("U2", "6")}
    e["/QSPI_SD0"] = {("U1", "53"), ("U2", "5")}
    e["/QSPI_SD1"] = {("U1", "55"), ("U2", "2")}
    e["/QSPI_SD2"] = {("U1", "54"), ("U2", "3")}
    e["/QSPI_SD3"] = {("U1", "51"), ("U2", "7")}
    e["/USB_BOOT"] = {("R22", "2"), ("SW2", "1"), ("SW2", "2")}
    e["/RUN"] = {("U1", "26"), ("SW3", "1"), ("SW3", "2")}
    e["/TXU_OE"] = {("U1", GPIO[23]), ("R24", "2")} | {(f"U{k}", "8") for k in (3, 4, 5, 6)}
    e["/LED_STATUS"] = {("U1", GPIO[25]), ("R27", "1")}
    for n in range(16, 23):
        e[f"/GP{n}"] = {("U1", GPIO[n]), (f"TP{n - 15}", "1")}
    e["/GP26_ADC0"] = {("U1", GPIO[26]), ("J4", "1")}
    e["/GP27_ADC1"] = {("U1", GPIO[27]), ("J4", "2")}
    e["/GP28_ADC2"] = {("U1", GPIO[28]), ("J4", "3")}
    e["/VREF_EXT"] = {("SW1", "3"), ("J3", "2")}
    e["GND"] = ({("J1", p) for p in ("A1", "A12", "B1", "B12", "SH")}
                | {("U8", "2"), ("U7", "1"), ("U1", "19"), ("U1", "57"), ("U2", "4"), ("X1", "2"), ("X1", "4"),
                   ("R17", "2"), ("R18", "2"), ("D1", "1"), ("D2", "1"), ("D3", "1"),
                   ("SW2", "3"), ("SW2", "4"), ("SW3", "3"), ("SW3", "4"), ("J3", "1"), ("J3", "3")}
                | {(f"U{k}", "7") for k in (3, 4, 5, 6)}
                | {(f"C{k}", "2") for k in range(1, 27)}
                | {("J2", str(2 * n + 2)) for n in range(16)})
    # LED の中間ネット（名前は KiCad 自動）: 抵抗 pin2 と LED アノード
    e["Net-(D1-A)"] = {("D1", "2"), ("R25", "2")}
    e["Net-(D2-A)"] = {("D2", "2"), ("R26", "2")}
    e["Net-(D3-A)"] = {("D3", "2"), ("R27", "2")}
    return e


def main() -> int:
    sch = HW / f"{PROJECT}.kicad_sch"
    nets = netlist_nets(sch)
    (HW / "out").mkdir(exist_ok=True)
    src = sch.with_suffix(".net")
    dst = HW / "out" / f"{PROJECT}.net"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    src.unlink()

    strip = lambda s: {n for n in s if not n[0].startswith("#")}
    actual = {k: strip(v) for k, v in nets.items()}
    exp = expected()
    rows, ng = [], 0
    for name in exp:
        got = actual.get(name)
        if got is None:
            rows.append((name, "NG", "ネットが無い", len(exp[name]), 0))
            ng += 1
            continue
        missing = exp[name] - got
        extra = got - exp[name]
        if not missing and not extra:
            rows.append((name, "OK", "", len(exp[name]), len(got)))
        else:
            ng += 1
            rows.append((name, "NG", f"不足 {sorted(missing)} / 余分 {sorted(extra)}", len(exp[name]), len(got)))
    extra_nets = sorted(set(actual) - set(exp))
    unconnected = [n for n in extra_nets if n.startswith("unconnected-")]     # no_connect フラグ 1 個につき 1 本できる
    unexpected = [n for n in extra_nets if not n.startswith("unconnected-")]
    lines = ["| ネット | 判定 | 期待ノード数 | 実ノード数 | 備考 |", "|:---|:---|--:|--:|:---|"]
    for name, st, note, ne, na in rows:
        lines.append(f"| `{name}` | {st} | {ne} | {na} | {note} |")
    lines.append("")
    lines.append(f"期待ネット {len(exp)} / 実ネット {len(actual)} / NG {ng} / 期待表に無いネット {len(unexpected)}: {unexpected}")
    lines.append(f"no_connect による unconnected ネット {len(unconnected)}: " + ", ".join(f"`{n}`" for n in unconnected))
    text = "\n".join(lines) + "\n"
    out = HW / "out" / "netlist-check.md"
    out.write_text(text, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    print("wrote", out)
    return 1 if ng or unexpected else 0


if __name__ == "__main__":
    sys.exit(main())
