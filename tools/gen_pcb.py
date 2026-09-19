# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""
RP2040 16ch ロジックアナライザ — KiCad 10 基板ジェネレータ（配置まで・配線は freerouting）

    uv run tools/verify_netlist.py                 # 先にネットリスト（hardware/out/*.net）を出す
    uv run tools/gen_pcb.py                        # hardware/out/placed/ と hardware/ に配置済み・未配線の基板を生成
    uv run tools/gen_pcb.py --fanout               # 実験用: GND/+3V3 のファンアウトビア付き（freerouting -inc と組で使う）
    uv run tools/gen_pcb.py --check                # 既存出力と一致するか（冪等性）

やること
  * kicadsexpr ネットリストから部品とネットを読み、標準 footprints / lib/lcsc/lcsc.pretty の
    .kicad_mod を埋め込んでパッドにネットを付ける（KiCad 10 形式 version 20260206）
  * Board Setup: KIT §3.1 のスタックアップ（JLC04161H-7628・4 層 1.6mm）は .kicad_pcb に、
    §3.2 の DRC 値と §3.3 のネットクラスは .kicad_pro に（gen_schematic.py が書く）
  * 外形 65×45mm（SPEC §8.3）。配置は SPEC §8.2 の制約に沿った決め打ち（下の PLACE 表）
  * 内層: In1.Cu = GND ベタ、In2.Cu = +3V3 ベタ（layer type = power なので freerouting は配線しない）。B.Cu の GND ベタは配線後（route_pcb.py）
  * USB 差動（USB_DP / USB_DM）は J1 → U8 → R19/R20 → U1 を手配線（locked・幅 0.30mm、QFN 側 1.5mm は 0.2mm）
  * RP2040 の EP に GND ビア 4 個。ほかの配線は無し（人間が GUI で配線する。2026-09-20 決定）
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_schematic import HW, LIBDIR, PROJECT, S, Sym, Y, dump, find, find1, parse  # noqa: E402

STD_FP_DIR = Path(os.environ.get("KICAD10_FOOTPRINT_DIR", r"C:\Program Files\KiCad\10.0\share\kicad\footprints"))
PCB_VERSION = 20260206
NS = uuid.UUID("2b7e0c4a-5d1f-4a83-9c0d-7e6f1b2a3c4d")
OUT_DIR = HW / "out" / "placed"

ORIGIN = (100.0, 100.0)          # 基板左上のシート座標
BOARD_W, BOARD_H = 65.0, 45.0    # SPEC §8.3

# --------------------------------------------------------------------------------------
# 配置（基板左上原点・mm・回転は KiCad の正方向 = 画面上で反時計回り）
# --------------------------------------------------------------------------------------

J2_X0, J2_Y = 12.0, 4.44         # J2 ピン 1 の位置（rot 90 で偶数列が上=外側、奇数列が y=4.44）
TXU_Y = 13.6


def txu_x(k: int) -> float:
    return J2_X0 + 2.54 * (4 * k + 1.5)


PLACE: dict[str, tuple[float, float, int]] = {
    # --- プローブヘッダ（上辺） ---
    "J2": (J2_X0, J2_Y, 90),
    # --- MCU（右辺 = ADC/VREG/USB/QSPI、左辺 = XIN/XOUT/SWD/RUN、上辺 = GPIO0-11、下辺 = GPIO18-29） ---
    "U1": (31.0, 27.0, 270),
    # RP2040 の +3V3 ピンは直線で逃がして L3 ベタへビア（fanout_u1）。パスコンはベタ経由で効くので周囲の空きに置く
    "C1": (36.0, 22.2, 90),      # IOVDD pin 1 用（上辺右）
    "C2": (27.6, 21.6, 0),       # IOVDD pin 10 用（上辺左）
    "C12": (23.0, 21.6, 0),      # 予備 100nF（+3V3）
    "C3": (25.0, 28.9, 90),      # IOVDD pin 22 用（左辺・下）
    "C7": (26.3, 29.4, 90),      # DVDD pin 23（左辺・下）
    "C4": (28.6, 33.6, 0),       # IOVDD pin 33 用（下辺左）
    "C5": (32.6, 33.6, 0),       # IOVDD pin 42 用（下辺右）
    # 右辺の電源ピン用パスコンは 1 列（2.4 ピッチ）。ファンアウトビアは上下に出す（FANOUT_OVERRIDE）
    "C6": (36.8, 32.1, 0),       # IOVDD pin 49 用
    "C9": (39.2, 32.1, 0),       # USB_VDD pin 48 用
    "C21": (41.6, 32.1, 0),      # VREG_VIN pin 44 1µF
    "C22": (44.0, 32.1, 0),      # VREG_VOUT pin 45 1µF（DVDD）
    "C10": (46.4, 32.1, 0),      # ADC_AVDD pin 43 用
    "C8": (48.8, 32.1, 0),       # DVDD pin 50
    "R19": (38.0, 27.8, 180),    # USB D+ 27Ω（pad 2 = MCU 側が左）
    "R20": (40.0, 28.4, 180),    # USB D- 27Ω
    "X1": (21.4, 26.4, 0), "C23": (21.4, 23.5, 0), "C24": (21.4, 29.3, 0), "R21": (24.0, 31.5, 0),
    "U2": (44.5, 24.8, 0),       # QSPI フラッシュ（右辺の QSPI ピンの正面）
    "C11": (50.0, 22.6, 90), "R22": (51.0, 25.3, 90), "R23": (52.3, 25.3, 90),
    "SW2": (12.0, 41.5, 0), "SW3": (20.5, 41.5, 0),
    "R27": (26.0, 41.5, 0), "D3": (29.5, 41.5, 0),
    "R24": (12.0, 19.0, 90),
    "J4": (57.0, 41.5, 90),
    # --- USB / 電源（右辺） ---
    "J1": (61.85, 22.0, 90), "U8": (53.5, 29.5, 0), "R17": (58.0, 30.5, 0), "R18": (55.0, 18.0, 0),
    "U7": (56.0, 36.0, 0), "C25": (49.5, 36.0, 90), "C26": (62.5, 36.0, 90),
    # --- VREF セレクタ / EXT / 表示 LED（左辺） ---
    "SW1": (7.35, 13.0, 270), "C27": (10.5, 10.0, 90), "J3": (2.0, 22.0, 0),
    "R25": (3.0, 32.0, 0), "D1": (6.0, 32.0, 0), "R26": (3.0, 35.0, 0), "D2": (6.0, 35.0, 0),
}
for k in range(4):
    x = txu_x(k)
    PLACE[f"U{3 + k}"] = (x, TXU_Y, 270)
    PLACE[f"C{13 + 2 * k}"] = (x + 4.0, 10.6, 90)     # VCCA 100nF（ピン 1 = 右上）
    PLACE[f"C{14 + 2 * k}"] = (x + 4.0, 16.4, 90)     # VCCB 100nF（ピン 14 = 右下）
for n in range(16):
    PLACE[f"R{n + 1}"] = (J2_X0 + 2.54 * n, 7.6, 90)   # ヘッダ奇数ピンの真下（縦）
for i in range(9):
    PLACE[f"TP{i + 1}"] = (34.0 + 2.5 * i, 41.5, 0)

# --------------------------------------------------------------------------------------
# ネットリスト
# --------------------------------------------------------------------------------------

def load_netlist(path: Path):
    root = parse(path.read_text(encoding="utf-8"))[0]
    comps = {}
    for c in find(find1(root, "components"), "comp"):
        ref = find1(c, "ref")[1]
        props = {}
        for p in find(c, "property"):
            v = find1(p, "value")
            props[find1(p, "name")[1]] = v[1] if v else ""
        fields = {}
        fl = find1(c, "fields")
        if fl:
            for f in find(fl, "field"):
                fields[find1(f, "name")[1]] = f[2] if len(f) > 2 and isinstance(f[2], str) else ""
        comps[ref] = {
            "value": find1(c, "value")[1],
            "footprint": (find1(c, "footprint") or [None, ""])[1],
            "description": (find1(c, "description") or [None, ""])[1],
            "datasheet": (find1(c, "datasheet") or [None, ""])[1],
            "lcsc": props.get("LCSC Part #", ""),
            "dnp": "dnp" in props,
            "tstamp": (find1(c, "tstamps") or [None, ""])[1],
            "sheetfile": props.get("Sheetfile", ""),
        }
    pin_net = {}
    nets = {}
    for n in find(find1(root, "nets"), "net"):
        name = find1(n, "name")[1]
        nodes = []
        for x in find(n, "node"):
            ref, pin = find1(x, "ref")[1], find1(x, "pin")[1]
            pin_net[(ref, pin)] = name
            nodes.append((ref, pin))
        nets[name] = nodes
    return comps, nets, pin_net


# --------------------------------------------------------------------------------------
# フットプリント
# --------------------------------------------------------------------------------------

class FpLib:
    def __init__(self):
        self.dirs = {"lcsc": LIBDIR / "lcsc" / "lcsc.pretty", "logicana": LIBDIR / "logicana.pretty"}

    def load(self, fpid: str) -> list:
        nick, name = fpid.split(":", 1)
        d = self.dirs.get(nick, STD_FP_DIR / f"{nick}.pretty")
        p = d / f"{name}.kicad_mod"
        if not p.exists():
            raise FileNotFoundError(f"フットプリントが無い: {fpid} -> {p}")
        return parse(p.read_text(encoding="utf-8"))[0]


def uid(*parts) -> str:
    return str(uuid.uuid5(NS, "|".join(str(p) for p in parts)))


def rot_xy(x: float, y: float, deg: float) -> tuple[float, float]:
    """KiCad の RotatePoint と同じ（正の角度で画面上反時計回り、y は下向き正）"""
    a = math.radians(deg)
    return (x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a))


def r4(v: float) -> float:
    return round(v + 0.0, 4)


class Board:
    def __init__(self, comps, nets, pin_net):
        self.comps, self.nets, self.pin_net = comps, nets, pin_net
        self.lib = FpLib()
        self.footprints: list[list] = []
        self.pads_abs: dict[tuple[str, str], list[tuple[float, float]]] = {}   # (ref, pin) -> [abs positions]
        self.items: list[list] = []      # segments, vias, zones, graphics
        self.pad_shape: dict[tuple[str, str], tuple[float, float]] = {}
        self.pad_is_smd: dict[tuple[str, str], bool] = {}
        self.fp_center: dict[str, tuple[float, float]] = {}
        self.fp_rot: dict[str, int] = {}

    # ---- footprint ----
    def place(self, ref: str, x: float, y: float, rot: int):
        c = self.comps[ref]
        fp = self.lib.load(c["footprint"])
        ax, ay = ORIGIN[0] + x, ORIGIN[1] + y
        self.fp_center[ref] = (ax, ay)
        self.fp_rot[ref] = rot
        node = S("footprint", c["footprint"], S("layer", "F.Cu"), S("uuid", uid("fp", ref)), S("at", r4(ax), r4(ay), rot))
        # descr / tags は元のまま
        for key in ("descr", "tags"):
            n = find1(fp, key)
            if n:
                node.append(copy.deepcopy(n))

        lib_props = {p[1]: p for p in find(fp, "property")}

        def prop(name, val, layer, hide, i):
            base = lib_props.get(name)
            if base is not None and name in ("Reference", "Value"):
                n = copy.deepcopy(base)
                n[2] = val
                at = find1(n, "at")
                at[3] = r4((float(at[3]) if len(at) > 3 else 0) + rot)
                if len(at) == 3:
                    at.append(r4(rot))
                if not find1(n, "uuid"):
                    n.insert(3 + (1 if find1(n, "layer") is None else 0), S("uuid", uid("prop", ref, name)))
                if hide and not find1(n, "hide"):
                    n.insert(2, S("hide", Y(True)))
                # KiCad は property の順序を at/layer/hide/uuid/effects で書く
                return _reorder_prop(n, uid("prop", ref, name))
            n = S("property", name, val, S("at", 0, 0, rot), S("layer", layer))
            if hide:
                n.append(S("hide", Y(True)))
            n.append(S("uuid", uid("prop", ref, name)))
            n.append(S("effects", S("font", S("size", 1, 1), S("thickness", 0.15))))
            return n

        node.append(prop("Reference", ref, "F.SilkS", False, 0))
        node.append(prop("Value", c["value"], "F.Fab", False, 1))
        node.append(prop("Footprint", c["footprint"], "F.Fab", True, 2))
        node.append(prop("Datasheet", c["datasheet"], "F.Fab", True, 3))
        node.append(prop("Description", c["description"], "F.Fab", True, 4))
        node.append(prop("LCSC Part #", c["lcsc"], "F.Fab", True, 5))
        for name, p in lib_props.items():
            if name in ("Reference", "Value", "Footprint", "Datasheet", "Description"):
                continue
            n = _reorder_prop(copy.deepcopy(p), uid("prop", ref, name))
            at = find1(n, "at")
            if at is not None:
                if len(at) == 3:
                    at.append(0)
                at[3] = r4(float(at[3]) + rot)
            node.append(n)
        node.append(S("path", "/" + c["tstamp"]))
        node.append(S("sheetname", "/"))
        node.append(S("sheetfile", c["sheetfile"] or f"{PROJECT}.kicad_sch"))
        attr = find1(fp, "attr")
        attr = copy.deepcopy(attr) if attr else S("attr", Sym("smd"))
        if c["dnp"] and Sym("dnp") not in attr:
            attr.append(Sym("dnp"))
        node.append(attr)
        dup = find1(fp, "duplicate_pad_numbers_are_jumpers")
        node.append(copy.deepcopy(dup) if dup else S("duplicate_pad_numbers_are_jumpers", Y(False)))

        gi = 0
        pi = 0
        for ch in fp:
            if not isinstance(ch, list):
                continue
            head = ch[0]
            if head in ("fp_line", "fp_rect", "fp_circle", "fp_arc", "fp_poly", "fp_text"):
                n = copy.deepcopy(ch)
                if head == "fp_text":
                    at = find1(n, "at")
                    if len(at) == 3:
                        at.append(0)
                    at[3] = r4(float(at[3]) + rot)
                if not find1(n, "uuid"):
                    n.append(S("uuid", uid("gfx", ref, gi)))
                gi += 1
                node.append(n)
            elif head == "pad":
                n = copy.deepcopy(ch)
                at = find1(n, "at")
                px, py = float(at[1]), float(at[2])
                pang = float(at[3]) if len(at) > 3 else 0.0
                if len(at) == 3:
                    at.append(0)
                at[3] = r4(pang + rot)
                number = n[1]
                net = self.pin_net.get((ref, number)) if number else None
                if net:
                    # (net "...") は layers の後・uuid の前
                    idx = next((i for i, k in enumerate(n) if isinstance(k, list) and k and k[0] == "uuid"), len(n))
                    n.insert(idx, S("net", net))
                if not find1(n, "uuid"):
                    n.append(S("uuid", uid("pad", ref, pi)))
                pi += 1
                node.append(n)
                dx, dy = rot_xy(px, py, rot)
                self.pads_abs.setdefault((ref, number), []).append((r4(ax + dx), r4(ay + dy)))
                sz = find1(n, "size")
                self.pad_shape[(ref, number)] = (float(sz[1]), float(sz[2]))
                self.pad_is_smd[(ref, number)] = (str(n[2]) == "smd")
            elif head == "model":
                n = copy.deepcopy(ch)
                n[1] = n[1].replace("${KIPRJMOD}/lib/", "${KIPRJMOD}/../lib/")   # プロジェクトは hardware/ 配下
                node.append(n)
        node.append(S("embedded_fonts", Y(False)))
        self.footprints.append(node)

    def pad(self, ref: str, pin) -> tuple[float, float]:
        return self.pads_abs[(ref, str(pin))][0]

    # ---- primitives ----
    def segment(self, p1, p2, width: float, net: str, layer="F.Cu", locked=False):
        n = S("segment", S("start", r4(p1[0]), r4(p1[1])), S("end", r4(p2[0]), r4(p2[1])), S("width", width),
              S("layer", layer))
        if locked:
            n.append(S("locked", Y(True)))
        n.append(S("net", net))
        n.append(S("uuid", uid("seg", len(self.items), p1, p2)))
        self.items.append(n)

    def route(self, pts, width, net, layer="F.Cu", locked=False):
        for a, b in zip(pts, pts[1:]):
            self.segment(a, b, width, net, layer, locked)

    def via(self, p, net: str, size=0.45, drill=0.25):
        self.items.append(S("via", S("at", r4(p[0]), r4(p[1])), S("size", size), S("drill", drill),
                            S("layers", "F.Cu", "B.Cu"), S("net", net), S("uuid", uid("via", len(self.items), p))))

    def zone(self, net: str, layer: str, name: str, priority: int = 0):
        x0, y0 = ORIGIN
        pts = [(x0, y0), (x0 + BOARD_W, y0), (x0 + BOARD_W, y0 + BOARD_H), (x0, y0 + BOARD_H)]
        self.items.append(S("zone", S("net", net), S("layers", layer), S("uuid", uid("zone", name)), S("name", name),
                            S("hatch", Sym("edge"), 0.5), S("priority", priority),
                            S("connect_pads", S("clearance", 0.2)), S("min_thickness", 0.25),
                            S("filled_areas_thickness", Y(False)),
                            S("fill", Y(True), S("thermal_gap", 0.3), S("thermal_bridge_width", 0.3), S("island_removal_mode", 1),
                              S("island_area_min", 10)),
                            S("polygon", S("pts", *[S("xy", r4(x), r4(y)) for x, y in pts]))))

    def keepout_tracks(self, layers: list[str], name: str):
        """ルールエリア: 指定層に配線禁止（ビア・パッド・ベタは許可）。KIT §3.1 の「L2 は切らない」を DRC で守らせる"""
        x0, y0 = ORIGIN
        pts = [(x0, y0), (x0 + BOARD_W, y0), (x0 + BOARD_W, y0 + BOARD_H), (x0, y0 + BOARD_H)]
        self.items.append(S("zone", S("net", 0), S("net_name", ""), S("layers", *layers), S("uuid", uid("keepout", name)),
                            S("name", name), S("hatch", Sym("edge"), 0.5), S("connect_pads", S("clearance", 0)),
                            S("min_thickness", 0.25), S("filled_areas_thickness", Y(False)),
                            S("keepout", S("tracks", Sym("not_allowed")), S("vias", Sym("allowed")), S("pads", Sym("allowed")),
                              S("copperpour", Sym("allowed")), S("footprints", Sym("allowed"))),
                            S("fill", S("thermal_gap", 0.5), S("thermal_bridge_width", 0.5)),
                            S("polygon", S("pts", *[S("xy", r4(x), r4(y)) for x, y in pts]))))

    def edge(self):
        x0, y0 = ORIGIN
        self.items.append(S("gr_rect", S("start", r4(x0), r4(y0)), S("end", r4(x0 + BOARD_W), r4(y0 + BOARD_H)),
                            S("stroke", S("width", 0.05), S("type", Sym("default"))), S("fill", Y(False)),
                            S("layer", "Edge.Cuts"), S("uuid", uid("edge"))))

    def text(self, s: str, x: float, y: float, layer="F.SilkS", size=1.0, rot=0):
        self.items.append(S("gr_text", s, S("at", r4(ORIGIN[0] + x), r4(ORIGIN[1] + y), rot), S("layer", layer),
                            S("uuid", uid("text", s)),
                            S("effects", S("font", S("size", size, size), S("thickness", 0.15)), S("justify", Sym("left")))))


def _reorder_prop(n: list, u: str) -> list:
    """(property "N" "V" (at) (layer) [(hide)] (uuid) (effects)) の順に整える"""
    name, val = n[1], n[2]
    parts = {c[0]: c for c in n[3:] if isinstance(c, list)}
    out = S("property", name, val)
    for key in ("at", "unlocked", "layer", "hide"):
        if key in parts:
            out.append(parts[key])
    out.append(parts.get("uuid") or S("uuid", u))
    if "effects" in parts:
        out.append(parts["effects"])
    return out


# --------------------------------------------------------------------------------------
# Board Setup（KIT §3）
# --------------------------------------------------------------------------------------

def layers_node() -> list:
    return S("layers",
             S(0, "F.Cu", Sym("signal")),
             S(4, "In1.Cu", Sym("power")),      # L2 = GND ベタ（power 型 → freerouting は配線しない。ベタ接続はファンアウトビアで）
             S(6, "In2.Cu", Sym("power")),      # L3 = +3V3 ベタ
             S(2, "B.Cu", Sym("signal")),
             S(9, "F.Adhes", Sym("user"), "F.Adhesive"), S(11, "B.Adhes", Sym("user"), "B.Adhesive"),
             S(13, "F.Paste", Sym("user")), S(15, "B.Paste", Sym("user")),
             S(5, "F.SilkS", Sym("user"), "F.Silkscreen"), S(7, "B.SilkS", Sym("user"), "B.Silkscreen"),
             S(1, "F.Mask", Sym("user")), S(3, "B.Mask", Sym("user")),
             S(17, "Dwgs.User", Sym("user"), "User.Drawings"), S(19, "Cmts.User", Sym("user"), "User.Comments"),
             S(21, "Eco1.User", Sym("user"), "User.Eco1"), S(23, "Eco2.User", Sym("user"), "User.Eco2"),
             S(25, "Edge.Cuts", Sym("user")), S(27, "Margin", Sym("user")),
             S(31, "F.CrtYd", Sym("user"), "F.Courtyard"), S(29, "B.CrtYd", Sym("user"), "B.Courtyard"),
             S(35, "F.Fab", Sym("user")), S(33, "B.Fab", Sym("user")))


def _layer(name, ltype, **kw):
    n = S("layer", name, S("type", ltype))
    for k, v in kw.items():
        n.append(S(k, v))
    return n


def setup_node() -> list:
    # KIT §3.1: JLC04161H-7628（銅 0.035 / 7628 0.2104 εr4.4 / 0.0152 / コア 1.065 εr4.6 / 0.0152 / 7628 / 0.035）
    stack = S("stackup",
              _layer("F.SilkS", "Top Silk Screen"),
              _layer("F.Paste", "Top Solder Paste"),
              _layer("F.Mask", "Top Solder Mask", thickness=0.01),
              _layer("F.Cu", "copper", thickness=0.035),
              _layer("dielectric 1", "prepreg", thickness=0.2104, material="7628", epsilon_r=4.4, loss_tangent=0.02),
              _layer("In1.Cu", "copper", thickness=0.0152),
              _layer("dielectric 2", "core", thickness=1.065, material="FR4", epsilon_r=4.6, loss_tangent=0.02),
              _layer("In2.Cu", "copper", thickness=0.0152),
              _layer("dielectric 3", "prepreg", thickness=0.2104, material="7628", epsilon_r=4.4, loss_tangent=0.02),
              _layer("B.Cu", "copper", thickness=0.035),
              _layer("B.Mask", "Bottom Solder Mask", thickness=0.01),
              _layer("B.Paste", "Bottom Solder Paste"),
              _layer("B.SilkS", "Bottom Silk Screen"),
              S("copper_finish", "HAL lead-free"),
              S("dielectric_constraints", Y(False)))
    plot = S("pcbplotparams",
             S("layerselection", Sym("0x00000000_00000000_55555555_5755f5ff")),
             S("plot_on_all_layers_selection", Sym("0x00000000_00000000_00000000_00000000")),
             S("disableapertmacros", Y(False)), S("usegerberextensions", Y(True)), S("usegerberattributes", Y(True)),
             S("usegerberadvancedattributes", Y(True)), S("creategerberjobfile", Y(True)),
             S("dashed_line_dash_ratio", 12), S("dashed_line_gap_ratio", 3), S("svgprecision", 4),
             S("plotframeref", Y(False)), S("mode", 1), S("useauxorigin", Y(False)),
             S("pdf_front_fp_property_popups", Y(True)), S("pdf_back_fp_property_popups", Y(True)), S("pdf_metadata", Y(True)),
             S("pdf_single_document", Y(False)), S("dxfpolygonmode", Y(True)), S("dxfimperialunits", Y(True)),
             S("dxfusepcbnewfont", Y(True)), S("psnegative", Y(False)), S("psa4output", Y(False)),
             S("plot_black_and_white", Y(True)), S("sketchpadsonfab", Y(False)), S("plotpadnumbers", Y(False)),
             S("hidednponfab", Y(False)), S("sketchdnponfab", Y(True)), S("crossoutdnponfab", Y(True)),
             S("subtractmaskfromsilk", Y(True)), S("outputformat", 1), S("mirror", Y(False)), S("drillshape", 0),
             S("scaleselection", 1), S("outputdirectory", "out/gerbers/"))
    return S("setup", stack,
             S("pad_to_mask_clearance", 0),
             S("solder_mask_min_width", 0.1),          # KIT §3.2 マスクダム 0.10
             S("allow_soldermask_bridges_in_footprints", Y(False)),
             S("tenting", S("front", Y(True)), S("back", Y(True))),
             S("covering", S("front", Y(False)), S("back", Y(False))),
             S("plugging", S("front", Y(False)), S("back", Y(False))),
             S("capping", Y(False)), S("filling", Y(False)),
             plot)


# --------------------------------------------------------------------------------------
# USB 差動の手配線（J1 → U8 → R19/R20 → U1）
# --------------------------------------------------------------------------------------

USB_W = 0.30   # KIT §3.3 USB クラス


def route_usb(b: Board):
    dp, dm = "/USB_DP", "/USB_DM"
    # J1: A6/B6 = D+、A7/B7 = D-（0.5mm ピッチで交互）。D+ は左（基板内側）、D- は右（コネクタ内側）で結ぶ
    a6, b6, a7, b7 = b.pad("J1", "A6"), b.pad("J1", "B6"), b.pad("J1", "A7"), b.pad("J1", "B7")
    xl = a6[0] - 1.05
    xr = a6[0] + 1.20
    b.route([b6, (xl, b6[1]), (xl, a6[1]), a6], USB_W, dp, locked=True)
    b.route([a7, (xr, a7[1]), (xr, b7[1]), b7], USB_W, dm, locked=True)
    # J1 → U8（pin 6 = I/O1 = D+、pin 4 = I/O2 = D-）
    p6, p4, p1, p3 = b.pad("U8", "6"), b.pad("U8", "4"), b.pad("U8", "1"), b.pad("U8", "3")
    xp = p6[0] + 0.76
    xm = xp + 0.80
    b.route([(xl, a6[1]), (xp, a6[1]), (xp, p6[1]), p6], USB_W, dp, locked=True)
    b.route([b7, (xm, b7[1]), (xm, p4[1]), p4], USB_W, dm, locked=True)
    # U8 の流し込み（6→1、4→3 はパッケージ内で導通。銅でも結ぶ）
    b.segment(p6, p1, USB_W, dp, locked=True)
    b.segment(p4, p3, USB_W, dm, locked=True)
    # U8 → R19/R20 pad 1（USB_DP / USB_DM 側。rot 180 なので右側のパッド）。D+ は R20 の上を 0.15 以上離して通す
    r19u, r20u, r19m, r20m = b.pad("R19", "1"), b.pad("R20", "1"), b.pad("R19", "2"), b.pad("R20", "2")
    yp = r19u[1] - 0.4                                    # 27.4: U2 の下パッド（27.03）と R20 のパッド上端（28.09）の間
    b.route([r19u, (r19u[0] + 0.4, yp), (r19u[0] + 4.5, yp), (r19u[0] + 4.5 + (p1[1] - yp), p1[1]), p1], USB_W, dp, locked=True)
    b.route([r20u, (r20u[0] + 1.5, r20u[1]), (r20u[0] + 1.5 + (p3[1] - r20u[1]), p3[1]), p3], USB_W, dm, locked=True)
    # R19/R20 pad 2 → U1 47 / 46（右辺）。QFN のパッド幅 0.2 に合わせて 0.2 幅（隣ピン・隣線との 0.2 クリアランス。1.5mm なので特性インピーダンスには効かない）
    u47, u46 = b.pad("U1", "47"), b.pad("U1", "46")
    b.route([u47, (r19m[0] - 0.6, u47[1]), r19m], 0.2, "/USB_DP_MCU", locked=True)     # 28.0 → 27.8 の小さな斜め
    b.route([u46, r20m], 0.2, "/USB_DM_MCU", locked=True)                                 # 28.4 で一直線


# --------------------------------------------------------------------------------------
# ベタ（GND / +3V3）への接続 = ファンアウトビア。freerouting はこの 2 ネットを無視する（-inc Plane_GND,Plane_3V3）
# --------------------------------------------------------------------------------------

PLANE_NETS = {"GND": 0.3, "+3V3": 0.3}      # ネット → スタブ幅
FANOUT_GAP = 0.45                            # パッド端からビア端まで
VIA_R = 0.225

# 手で決める例外: (ref, pad) → (dx, dy) ビア中心のパッドからのオフセット、None = ビアを打たない
FANOUT_OVERRIDE: dict[tuple[str, str], tuple[float, float] | None] = {
    ("J1", "A1"): (-0.4, 0.85),      # 下側 GND パッド: シールド THT と D- 縦線を避けて斜め下
    ("J1", "A12"): (-0.4, -0.85),    # 上側 GND パッド
    ("D1", "1"): (0, 1.0), ("D2", "1"): (0, 1.0), ("D3", "1"): (0, 1.0),   # LED カソード: 抵抗側でなく下へ
    ("SW2", "3"): (0, 1.05), ("SW2", "4"): (0, 1.05), ("SW3", "3"): (0, 1.05), ("SW3", "4"): (0, 1.05),   # 隣のスイッチとぶつからないよう下へ
}
for _c in ("C6", "C9", "C21", "C22", "C10", "C8"):
    FANOUT_OVERRIDE[(_c, "1")] = (0, -0.995)
    FANOUT_OVERRIDE[(_c, "2")] = (0, 0.995)


def fanout_u1(b: Board):
    """RP2040 の +3V3 ピンと TESTEN(GND): 0.2 幅で真っ直ぐ逃がしてビア。隣接する 2 本は 1 個のビアに合流させる（0.4 ピッチにビアは 1 個ずつ置けない）"""
    def esc(pin, via_xy, mid=None, net="+3V3"):
        p = b.pad("U1", pin)
        pts = [p] + ([mid] if mid else []) + [via_xy]
        b.route(pts, 0.2, net, locked=True)
    ox, oy = ORIGIN
    A = lambda x, y: (ox + x, oy + y)
    # 上辺: pin 1（右端）、pin 10
    esc("1", A(33.9, 22.3), mid=A(33.6, 22.9)); b.via(A(33.9, 22.3), "+3V3")
    esc("10", A(30.0, 21.9)); b.via(A(30.0, 21.9), "+3V3")
    # 左辺: pin 22、TESTEN(19) → GND
    esc("22", A(25.7, 27.2)); b.via(A(25.7, 27.2), "+3V3")
    esc("19", A(25.3, 26.0), net="GND"); b.via(A(25.3, 26.0), "GND")
    # 下辺: pin 33、pin 42
    esc("33", A(30.0, 32.0)); b.via(A(30.0, 32.0), "+3V3")
    esc("42", A(33.6, 32.0)); b.via(A(33.6, 32.0), "+3V3")
    # 右辺: 48+49 → 1 個、43+44 → 1 個
    esc("49", A(36.4, 27.4), mid=A(35.8, 27.2)); esc("48", A(36.4, 27.4), mid=A(35.8, 27.6)); b.via(A(36.4, 27.4), "+3V3")
    esc("44", A(36.4, 29.4), mid=A(35.8, 29.2)); esc("43", A(36.4, 29.4), mid=A(35.8, 29.6)); b.via(A(36.4, 29.4), "+3V3")


def fanout_pads(b: Board) -> list[tuple[str, str, float, float]]:
    """U1 以外の GND / +3V3 の SMD パッドに、部品の外側へ向けたスタブ＋ビアを付ける"""
    done_xy = set()
    placed = []
    for (ref, pin), positions in sorted(b.pads_abs.items()):
        if ref == "U1":
            continue
        net = b.pin_net.get((ref, pin))
        if net not in PLANE_NETS:
            continue
        if not b.pad_is_smd.get((ref, pin)):
            continue                                   # THT はスルーホールでベタに繋がる
        for pos in positions:
            key = (round(pos[0], 3), round(pos[1], 3))
            if key in done_xy:
                continue                               # 同じ位置に重なるパッド（J1 の A1/B12 など）
            done_xy.add(key)
            ov = FANOUT_OVERRIDE.get((ref, pin), "auto")
            if ov is None:
                continue
            if ov == "auto":
                cx, cy = b.fp_center[ref]
                dx, dy = pos[0] - cx, pos[1] - cy
                sx, sy = b.pad_shape[(ref, pin)]
                rot = b.fp_rot[ref]
                if abs(dx) >= abs(dy):
                    ux, uy = (1 if dx >= 0 else -1), 0
                    half = (sx if rot % 180 == 0 else sy) / 2
                else:
                    ux, uy = 0, (1 if dy >= 0 else -1)
                    half = (sy if rot % 180 == 0 else sx) / 2
                d = half + FANOUT_GAP + VIA_R
                vx, vy = pos[0] + ux * d, pos[1] + uy * d
            else:
                vx, vy = pos[0] + ov[0], pos[1] + ov[1]
            b.segment(pos, (vx, vy), PLANE_NETS[net], net, locked=True)
            b.via((vx, vy), net)
            placed.append((ref, pin, r4(vx - ORIGIN[0]), r4(vy - ORIGIN[1])))
    return placed


# --------------------------------------------------------------------------------------
# 生成
# --------------------------------------------------------------------------------------

def build(fanout: bool = False) -> tuple[str, Board]:
    comps, nets, pin_net = load_netlist(HW / "out" / f"{PROJECT}.net")
    missing = sorted(set(comps) - set(PLACE))
    extra = sorted(set(PLACE) - set(comps))
    if missing or extra:
        raise SystemExit(f"配置表とネットリストが合わない: 未配置 {missing} / 余分 {extra}")
    b = Board(comps, nets, pin_net)
    for ref in sorted(comps, key=_ref_key):
        x, y, rot = PLACE[ref]
        b.place(ref, x, y, rot)
    b.edge()
    b.zone("GND", "In1.Cu", "GND_L2")
    b.zone("+3V3", "In2.Cu", "P3V3_L3")
    b.keepout_tracks(["In1.Cu", "In2.Cu"], "no_tracks_on_plane_layers")
    # B.Cu の GND ベタ（KIT §3.1 L4）は配線後に route_pcb.py が足す。
    # 配線前に置くと freerouting が B.Cu を「他ネット進入禁止の導体面」と見て実質 1 層配線になる（実測: 200 ネット中 91 未配線）
    # RP2040 EP → L2 GND（SPEC §8.2-2）
    cx, cy = ORIGIN[0] + PLACE["U1"][0], ORIGIN[1] + PLACE["U1"][1]
    for dx, dy in ((-0.8, -0.8), (0.8, -0.8), (-0.8, 0.8), (0.8, 0.8)):
        b.via((cx + dx, cy + dy), "GND")
    route_usb(b)
    b.fanout = []
    if fanout:
        # 実験用: GND/+3V3 の SMD パッドにベタ接続用のビアを付け、freerouting に -inc Plane_GND,Plane_3V3 で無視させる構成。
        # 2026-09-20 の人間判断で配線は GUI で行うことになったので既定では入れない（ネットクラスも KIT §3.3 のまま）
        fanout_u1(b)
        b.fanout = fanout_pads(b)
    # シルク
    b.text("RP2040 LA A0", 5.0, 24.5, size=0.8)
    b.text("electwork.net", 5.0, 26.0, size=0.8)
    b.text("VREF 3V3/EXT/5V  IN MAX 5.5V", 33.5, 43.9, size=0.8)
    b.text("CH0", 6.6, 4.9, size=0.8)
    b.text("CH15", 52.2, 4.9, size=0.8)
    b.text("GND", 52.2, 2.4, size=0.8)

    node = S("kicad_pcb", S("version", PCB_VERSION), S("generator", "pcbnew"), S("generator_version", "10.0"),
             S("general", S("thickness", 1.6), S("legacy_teardrops", Y(False))),
             S("paper", "A4"),
             S("title_block", S("title", "RP2040 16ch Logic Analyzer"), S("date", "2026-09-20"), S("rev", "A0"),
               S("company", "electwork.net"), S("comment", 1, "Generated by tools/gen_pcb.py. CERN-OHL-P-2.0")),
             layers_node(), setup_node())
    node.extend(b.footprints)
    node.extend(b.items)
    node.append(S("embedded_fonts", Y(False)))
    return dump(node) + "\n", b


def _ref_key(ref: str):
    i = 0
    while i < len(ref) and not ref[i].isdigit():
        i += 1
    return (ref[:i], int(ref[i:] or 0))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="RP2040 logic analyzer: KiCad 10 PCB generator (placement)")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--fanout", action="store_true", help="GND/+3V3 の SMD パッドにファンアウトビアを付ける（実験用・既定は付けない）")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    text, b = build(fanout=args.fanout)
    files = {f"{PROJECT}.kicad_pcb": text}
    if args.check:
        bad = [n for n, body in files.items() if not (args.out / n).exists() or (args.out / n).read_text(encoding="utf-8") != body]
        print("一致" if not bad else "不一致: " + ", ".join(bad))
        return 1 if bad else 0
    args.out.mkdir(parents=True, exist_ok=True)
    for n, body in files.items():
        (args.out / n).write_text(body, encoding="utf-8", newline="\n")
        print("wrote", args.out / n, len(body), "bytes")
    # プロジェクト直下にも同じ配置済み基板を置く（route_pcb.py が配線後に上書きする）
    if args.out == OUT_DIR:
        (HW / f"{PROJECT}.kicad_pcb").write_text(text, encoding="utf-8", newline="\n")
        print("wrote", HW / f"{PROJECT}.kicad_pcb")
    print(f"footprints {len(b.footprints)} / items {len(b.items)} / fanout vias {len(b.fanout)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
