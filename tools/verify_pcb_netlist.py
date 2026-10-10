# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""
基板（hardware/rp2040-logic-analyzer.kicad_pcb）のパッドのネットを、回路図のネットリストと突き合わせる。

    uv run tools/verify_netlist.py        # 先に hardware/out/rp2040-logic-analyzer.net を出す
    uv run tools/verify_pcb_netlist.py    # → hardware/out/pcb-netlist-check.md（ネット別の照合表と SW1 のパッド表）

回路図の全ノード (参照子, ピン) について、基板の同じ (参照子, パッド) が同じネット名を持つことを見る。
`unconnected-` ネット（no_connect）は名前が基板側と一致しないことがあるので「基板側も未接続か空」で判定する。
基板側だけにあるネット付きパッドも列挙する（回路図に無い接続＝誤配線の候補）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_schematic import HW, PROJECT, find, find1, parse  # noqa: E402

PCB = HW / f"{PROJECT}.kicad_pcb"
NET = HW / "out" / f"{PROJECT}.net"
OUT = HW / "out" / "pcb-netlist-check.md"


def pcb_pads(text: str) -> dict[tuple[str, str], str]:
    pads = {}
    for blk in text.split('\n\t(footprint "')[1:]:
        ref = re.search(r'\(property "Reference" "([^"]+)"', blk).group(1)
        for m in re.finditer(r'\(pad "([^"]*)" \w+ \w+\n(.*?)\n\t\t\)', blk, re.S):
            net = re.search(r'\(net "([^"]*)"\)', m.group(2))
            pads[(ref, m.group(1))] = net.group(1) if net else ""
    return pads


def sch_nodes(text: str) -> dict[tuple[str, str], str]:
    root = parse(text)[0]
    nodes = {}
    for net in find(find1(root, "nets"), "net"):
        name = find1(net, "name")[1]
        for n in find(net, "node"):
            nodes[(find1(n, "ref")[1], find1(n, "pin")[1])] = name
    return nodes


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    pads = pcb_pads(PCB.read_text(encoding="utf-8"))
    nodes = sch_nodes(NET.read_text(encoding="utf-8"))
    is_nc = lambda n: n == "" or n.startswith("unconnected-")

    per_net: dict[str, list[int]] = {}      # net -> [期待ノード, 一致]
    bad = []
    for (ref, pin), net in sorted(nodes.items()):
        got = pads.get((ref, pin))
        if got is None:
            bad.append((ref, pin, net, "基板にパッドが無い"))
            continue
        if is_nc(net):
            ok = is_nc(got)
        else:
            ok = got == net
            per_net.setdefault(net, [0, 0])
            per_net[net][0] += 1
            per_net[net][1] += ok
        if not ok:
            bad.append((ref, pin, net, f"基板は {got!r}"))
    extra = sorted((k, v) for k, v in pads.items() if not is_nc(v) and k not in nodes)

    named = {n for n in nodes.values() if not is_nc(n)}
    ok_nets = sum(1 for n, (e, g) in per_net.items() if e == g)
    lines = ["# 基板パッド ↔ 回路図ネットリスト 照合", "",
             f"- 基板: `{PCB.relative_to(HW.parent)}`／ネットリスト: `{NET.relative_to(HW.parent)}`",
             f"- 回路図の名前付きネット: **{len(named)}**／全ノード一致したネット: **{ok_nets}**／ノード不一致: **{len(bad)}**／"
             f"基板だけにあるネット付きパッド: **{len(extra)}**", "",
             "| ネット | 回路図ノード | 基板で一致 | 判定 |", "|:--|--:|--:|:--|"]
    for net in sorted(per_net, key=lambda s: (not s.startswith("+"), s)):
        e, g = per_net[net]
        lines.append(f"| `{net}` | {e} | {g} | {'OK' if e == g else '**NG**'} |")
    if bad:
        lines += ["", "## 不一致", ""] + [f"- {r}.{p}: 回路図 `{n}` — {why}" for r, p, n, why in bad]
    if extra:
        lines += ["", "## 基板だけにあるネット付きパッド", ""] + [f"- {r}.{p}: `{n}`" for (r, p), n in extra]
    lines += ["", "## SW1（SK13D07VG5）のパッド", "", "| pad | 回路図 | 基板 | 役割 |", "|:--|:--|:--|:--|"]
    role = {"1": "接点（スライダ位置 1）", "2": "コモン", "3": "接点（位置 2）", "4": "接点（位置 3）", "5": "固定ラグ", "6": "固定ラグ"}
    for p in ("1", "2", "3", "4", "5", "6"):
        lines.append(f"| {p} | `{nodes.get(('SW1', p), '')}` | `{pads.get(('SW1', p), '')}` | {role[p]} |")
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text)
    print("wrote", OUT)
    return 1 if bad or extra else 0


if __name__ == "__main__":
    sys.exit(main())
