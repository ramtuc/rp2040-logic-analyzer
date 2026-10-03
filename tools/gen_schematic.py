# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""
RP2040 16ch ロジックアナライザ — KiCad 10 回路図ジェネレータ

SPEC.md §3〜§7・§10 と KICAD-KIT.md §1・§2・§4 の確定値から、KiCad 10 の
`.kicad_sch`（S 式・version 20260306）を直接生成する。GUI も IPC API も使わない。

    uv run tools/gen_schematic.py             # hardware/ に出力
    uv run tools/gen_schematic.py --check     # 出力せず、hardware/ の既存ファイルと一致するか確認（冪等性）
    uv run tools/gen_schematic.py --selftest  # 回転行列の実測（kicad-cli netlist でピン位置を検算）

生成物（すべて hardware/ 配下）
    rp2040-logic-analyzer.kicad_pro   最小プロジェクト（KIT §3.3 のネットクラス入り）
    rp2040-logic-analyzer.kicad_sch   平面 1 シート（電源／MCU／FE×4／コネクタ の 4 領域）
    sym-lib-table / fp-lib-table      ../lib/ をプロジェクト相対で登録（KIT §1.4）

設計方針
  * シンボルは KiCad 10 標準ライブラリと lib/logicana.kicad_sym から読み、`extends` を
    平坦化して lib_symbols に埋め込む（KiCad が GUI で保存する形と同じ）。
  * 結線はピン端からの短いスタブ＋ローカルラベル（KIT §4.1 のネット名そのまま）。
    電源レールは電源シンボル（+5V / +3V3 / GND / VREF）。
  * UUID は uuid5（固定名前空間 + 論理名）なので、再実行しても同じ出力になる。
  * 座標は 1.27mm グリッド単位の整数で書く（`G(x, y)`）。見た目の整形は人間が GUI で行う。
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

# --------------------------------------------------------------------------------------
# 定数
# --------------------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
HW = ROOT / "hardware"
LIBDIR = ROOT / "lib"
PROJECT = "rp2040-logic-analyzer"
STD_SYM_DIR = Path(os.environ.get("KICAD10_SYMBOL_DIR", r"C:\Program Files\KiCad\10.0\share\kicad\symbols"))
KICAD_CLI = Path(os.environ.get("KICAD_CLI", r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"))

SCH_VERSION = 20260306        # KiCad 10.0 が書く .kicad_sch のフォーマット版
GENERATOR_VERSION = "10.0"
NS = uuid.UUID("6f1a7d6e-3c0b-4b5e-9f0e-2a9d7c0e5a11")   # uuid5 名前空間（固定）
GRID = 1.27                    # mm。KiCad 既定の 50mil グリッド

# 各シンボルに載せる JLCPCB 用フィールド名（KIT §2.1: 公式記事と Fabrication Toolkit の両方で通る名前）
LCSC_FIELD = "LCSC Part #"

FP = {
    "R0402": "Resistor_SMD:R_0402_1005Metric",
    "C0402": "Capacitor_SMD:C_0402_1005Metric",
    "C0805": "Capacitor_SMD:C_0805_2012Metric",
    "LED0603": "LED_SMD:LED_0603_1608Metric",
    "XTAL": "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
    "USBC": "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
    "H2x16": "Connector_PinHeader_2.54mm:PinHeader_2x16_P2.54mm_Vertical",
    "H1x03": "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
    "TP": "TestPoint:TestPoint_Pad_1.0x1.0mm",
    "QFN56": "Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm",
    "SOIC8": "Package_SO:SOIC-8_5.3x5.3mm_P1.27mm",
    "TSSOP14": "Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
    "SOT223": "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
    "SOT23-6": "Package_TO_SOT_SMD:SOT-23-6",
    "SW1": "lcsc:SW-TH_SK13D07VG5",
    "TACT": "lcsc:SW-SMD_4P-L5.1-W5.1-P3.70-LS6.5-TL_H1.5",
}


# --------------------------------------------------------------------------------------
# S 式
# --------------------------------------------------------------------------------------

class Sym(str):
    """クォート無しのトークン（yes / no / passive など）"""
    __slots__ = ()


_TOK = re.compile(r'\s*(?:(\()|(\))|("(?:[^"\\]|\\.)*")|([^\s()"]+))', re.S)


def parse(text: str) -> list:
    pos, n = 0, len(text)
    stack: list[list] = [[]]
    while pos < n:
        m = _TOK.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise ValueError("S 式の構文エラー: %r" % text[pos:pos + 40])
        pos = m.end()
        if m.group(1):
            stack.append([])
        elif m.group(2):
            lst = stack.pop()
            stack[-1].append(lst)
        elif m.group(3):
            s = m.group(3)[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            stack[-1].append(s)
        else:
            stack[-1].append(Sym(m.group(4)))
    if len(stack) != 1:
        raise ValueError("括弧が閉じていない")
    return stack[0]


def find(node: list, name: str) -> list[list]:
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def find1(node: list, name: str):
    r = find(node, name)
    return r[0] if r else None


def num(v) -> str:
    if isinstance(v, int):
        return str(v)
    if abs(v) < 1e-9:
        return "0"
    return f"{v:.4f}".rstrip("0").rstrip(".")


def atom(a) -> str:
    if isinstance(a, Sym):
        return str(a)
    if isinstance(a, str):
        return '"' + a.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(a, (int, float)):
        return num(a)
    raise TypeError(repr(a))


def dump(node: list, depth: int = 0) -> str:
    """KiCad 風の整形（タブ字下げ・1 行 1 子要素。`pts` の xy だけ横並び）"""
    ind = "\t" * depth
    head = node[0]
    atoms, lists = [], []
    for c in node[1:]:
        (lists if isinstance(c, list) else atoms).append(c)
    first = "(" + atom(head) + "".join(" " + atom(a) for a in atoms)
    if not lists:
        return ind + first + ")"
    if head == "pts":
        inner = " ".join(dump(c, 0) for c in lists)
        return ind + first + "\n" + ind + "\t" + inner + "\n" + ind + ")"
    out = [ind + first]
    for c in lists:
        out.append(dump(c, depth + 1))
    out.append(ind + ")")
    return "\n".join(out)


def S(*items) -> list:
    """(head ...) を組み立てる糖衣。先頭要素は Sym にする"""
    head, *rest = items
    return [Sym(head), *rest]


def Y(v: bool) -> Sym:
    return Sym("yes") if v else Sym("no")


# --------------------------------------------------------------------------------------
# ライブラリ読み込みと平坦化
# --------------------------------------------------------------------------------------

class LibCache:
    def __init__(self, std_dir: Path, project_libs: dict[str, Path]):
        self.std_dir = std_dir
        self.project_libs = project_libs
        self._roots: dict[str, dict[str, list]] = {}

    def _symbols(self, nick: str) -> dict[str, list]:
        if nick not in self._roots:
            path = self.project_libs.get(nick, self.std_dir / f"{nick}.kicad_sym")
            if not path.exists():
                raise FileNotFoundError(f"シンボルライブラリが無い: {nick} -> {path}")
            root = parse(path.read_text(encoding="utf-8"))[0]
            self._roots[nick] = {s[1]: s for s in find(root, "symbol")}
        return self._roots[nick]

    def flattened(self, lib_id: str) -> list:
        """`extends` を解決した（KiCad の LIB_SYMBOL::Flatten 相当）シンボル。名前は "nick:name"。"""
        nick, name = lib_id.split(":", 1)
        syms = self._symbols(nick)
        if name not in syms:
            raise KeyError(f"シンボルが無い: {lib_id}")
        flat = self._flatten(syms, name)
        flat[1] = lib_id
        return flat

    def _flatten(self, syms: dict[str, list], name: str) -> list:
        s = syms[name]
        ext = find1(s, "extends")
        if ext is None:
            return copy.deepcopy(s)
        pname = ext[1]
        base = self._flatten(syms, pname)          # 既に deepcopy 済み
        base[1] = name
        for sub in find(base, "symbol"):
            if sub[1].startswith(pname + "_"):
                sub[1] = name + sub[1][len(pname):]
        child_props = [copy.deepcopy(p) for p in find(s, "property")]
        child_names = {p[1] for p in child_props}
        parent_props = [p for p in find(base, "property") if p[1] not in child_names]
        first = next(i for i, c in enumerate(base) if isinstance(c, list) and c and c[0] == "property")
        rest = [c for c in base if not (isinstance(c, list) and c and c[0] == "property")]
        return rest[:first] + child_props + parent_props + rest[first:]


def lib_pins(flat: list) -> list[dict]:
    """平坦化済みシンボルの全ピン。座標はライブラリ系（y 上向き）。"""
    out = []
    for sub in find(flat, "symbol"):
        for p in find(sub, "pin"):
            at = find1(p, "at")
            out.append({
                "number": find1(p, "number")[1],
                "name": find1(p, "name")[1],
                "type": str(p[1]),
                "x": float(at[1]), "y": float(at[2]), "angle": float(at[3]),
                "length": float(find1(p, "length")[1]),
            })
    return out


# --------------------------------------------------------------------------------------
# 幾何
# --------------------------------------------------------------------------------------

# KiCad の SCH_SYMBOL 変換行列。ライブラリ座標 (px, py) → シート座標のオフセット。
# 0°: (px, -py)   90°: (-py, -px)   180°: (-px, py)   270°: (py, px)
# `--selftest` が kicad-cli のネットリストで実測して確認する。
ROT = {
    0: ((1, 0), (0, -1)),
    90: ((0, -1), (-1, 0)),
    180: ((-1, 0), (0, 1)),
    270: ((0, 1), (1, 0)),
}

UP, DOWN, LEFT, RIGHT = (0, -1), (0, 1), (-1, 0), (1, 0)   # シート座標の向き（y は下向き正）


def G(x: float, y: float) -> tuple[float, float]:
    """グリッド単位（1.27mm）→ mm"""
    return (round(x * GRID, 4), round(y * GRID, 4))


def add(p, dx, dy):
    return (round(p[0] + dx * GRID, 4), round(p[1] + dy * GRID, 4))


def key(p) -> tuple[float, float]:
    return (round(p[0], 3), round(p[1], 3))


def power_rot(net: str, direction) -> int:
    """電源シンボルの記号が `direction` の側に伸びる回転角。GND だけ記号が下側（ライブラリ -y）にある"""
    if net == "GND":
        return {DOWN: 0, UP: 180, LEFT: 270, RIGHT: 90}[direction]
    return {UP: 0, DOWN: 180, LEFT: 90, RIGHT: 270}[direction]


def label_rot(direction) -> int:
    return {RIGHT: 0, LEFT: 180, UP: 90, DOWN: 270}[direction]


# --------------------------------------------------------------------------------------
# 回路図ビルダー
# --------------------------------------------------------------------------------------

class Placed:
    def __init__(self, ref: str, lib_id: str, at, rot: int, pins: list[dict]):
        self.ref, self.lib_id, self.at, self.rot = ref, lib_id, at, rot
        self._pins = {}
        for p in pins:
            self._pins.setdefault(p["number"], p)
        self.pins = pins

    def pin(self, number) -> tuple[float, float]:
        """ピンの接続点（シート座標 mm）"""
        p = self._pins[str(number)]
        m = ROT[self.rot]
        x = self.at[0] + m[0][0] * p["x"] + m[0][1] * p["y"]
        y = self.at[1] + m[1][0] * p["x"] + m[1][1] * p["y"]
        return (round(x, 4), round(y, 4))

    def outward(self, number) -> tuple[int, int]:
        """ピンから外へ向かう単位ベクトル（シート座標）"""
        p = self._pins[str(number)]
        a = int(p["angle"]) % 360
        lib_dir = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}[a]   # 本体へ向かう向き（ライブラリ系）
        m = ROT[self.rot]
        dx = m[0][0] * lib_dir[0] + m[0][1] * lib_dir[1]
        dy = m[1][0] * lib_dir[0] + m[1][1] * lib_dir[1]
        return (-dx, -dy)


class Sch:
    def __init__(self, libs: LibCache):
        self.libs = libs
        self.lib_symbols: dict[str, list] = {}
        self.symbols: list[list] = []
        self.wires: list[tuple] = []
        self.labels: list[list] = []
        self.ncs: list[list] = []
        self.texts: list[list] = []
        self.refs: set[str] = set()
        self.pin_points: list[tuple] = []      # (point, ref, pin)
        self.label_points: list[tuple] = []
        self.nc_points: set = set()
        self.root_uuid = str(uuid.uuid5(NS, "root-sheet"))
        self._pwr_n = 0
        self._flg_n = 0
        self._wire_n = 0

    def uid(self, *parts) -> str:
        return str(uuid.uuid5(NS, "|".join(str(p) for p in parts)))

    # ---- symbols ----
    def _lib(self, lib_id: str) -> list:
        if lib_id not in self.lib_symbols:
            self.lib_symbols[lib_id] = self.libs.flattened(lib_id)
        return self.lib_symbols[lib_id]

    def place(self, lib_id: str, ref: str, at, rot: int = 0, value: str | None = None,
              footprint: str | None = None, lcsc: str | None = None, dnp: bool = False,
              description: str | None = None, extra: dict | None = None) -> Placed:
        if ref in self.refs:
            raise ValueError(f"参照子の重複: {ref}")
        self.refs.add(ref)
        flat = self._lib(lib_id)
        pins = lib_pins(flat)
        placed = Placed(ref, lib_id, at, rot, pins)
        for p in pins:
            self.pin_points.append((key(placed.pin(p["number"])), ref, p["number"]))

        libprops = {p[1]: p for p in find(flat, "property")}
        m = ROT[rot]

        def prop_at(name):
            """ライブラリのフィールド位置・角度をシンボルの回転に合わせて変換（KiCad の配置時と同じ）"""
            lp = libprops.get(name)
            if lp is None:
                return at[0], at[1], 0
            a = find1(lp, "at")
            px, py, ang = float(a[1]), float(a[2]), int(float(a[3]))
            return (round(at[0] + m[0][0] * px + m[0][1] * py, 4), round(at[1] + m[1][0] * px + m[1][1] * py, 4), ang)   # 角度はシンボル基準（KiCad が回転を加味して描く）

        def prop(name, val, hide, pos=None):
            x, y, ang = (pos[0], pos[1], 0) if pos else prop_at(name)
            node = S("property", name, val, S("at", x, y, ang), S("show_name", Y(False)), S("do_not_autoplace", Y(False)))
            if hide:
                node.insert(3, S("hide", Y(True)))
            node.append(S("effects", S("font", S("size", 1.27, 1.27))))
            return node

        def libval(name, default=""):
            lp = libprops.get(name)
            return lp[2] if lp is not None else default

        is_power = ref.startswith("#")
        props = [
            prop("Reference", ref, hide=is_power),
            prop("Value", value if value is not None else libval("Value"), hide=False),
            prop("Footprint", footprint if footprint is not None else libval("Footprint"), hide=True),
            prop("Datasheet", libval("Datasheet"), hide=True),
            prop("Description", description if description is not None else libval("Description"), hide=True),
        ]
        if not is_power:
            props.append(prop(LCSC_FIELD, lcsc or "", hide=True, pos=at))
        for k, v in (extra or {}).items():
            props.append(prop(k, v, hide=True, pos=at))

        node = S("symbol",
                 S("lib_id", lib_id),
                 S("at", at[0], at[1], rot),
                 S("unit", 1),
                 S("body_style", 1),
                 S("exclude_from_sim", Y(False)),
                 S("in_bom", Y(True)),
                 S("on_board", Y(True)),
                 S("in_pos_files", Y(True)),
                 S("dnp", Y(dnp)),
                 S("fields_autoplaced", Y(True)),
                 S("uuid", self.uid("sym", ref)),
                 *props)
        seen = set()
        for p in pins:
            if p["number"] in seen:
                continue
            seen.add(p["number"])
            node.append(S("pin", p["number"], S("uuid", self.uid("pin", ref, p["number"]))))
        node.append(S("instances", S("project", PROJECT, S("path", "/" + self.root_uuid, S("reference", ref), S("unit", 1)))))
        self.symbols.append(node)
        return placed

    # ---- primitives ----
    def wire(self, p1, p2):
        p1, p2 = key(p1), key(p2)
        if p1 == p2:
            raise ValueError("長さ 0 のワイヤ")
        if p1[0] != p2[0] and p1[1] != p2[1]:
            raise ValueError(f"斜めワイヤ: {p1} -> {p2}")
        self._wire_n += 1
        self.wires.append((p1, p2, self.uid("wire", self._wire_n, p1, p2)))

    def route(self, *pts):
        """折れ線（L 字・コ字）を順に結ぶ"""
        for a, b in zip(pts, pts[1:]):
            self.wire(a, b)

    def label(self, name: str, at, rot: int = 0):
        just = ("left", "bottom") if rot in (0, 90) else ("right", "bottom")
        at = key(at)
        self.labels.append(S("label", name, S("at", at[0], at[1], rot),
                             S("effects", S("font", S("size", 1.27, 1.27)), S("justify", *[Sym(j) for j in just])),
                             S("uuid", self.uid("label", name, at))))
        self.label_points.append((at, name))

    def nc(self, at):
        at = key(at)
        self.ncs.append(S("no_connect", S("at", at[0], at[1]), S("uuid", self.uid("nc", at))))
        self.nc_points.add(at)

    def text(self, s: str, at, size: float = 1.27):
        at = key(at)
        self.texts.append(S("text", s, S("exclude_from_sim", Y(False)), S("at", at[0], at[1], 0),
                            S("effects", S("font", S("size", size, size)), S("justify", Sym("left"), Sym("bottom"))),
                            S("uuid", self.uid("text", s, at))))

    def power(self, net: str, at, direction=UP) -> Placed:
        """電源シンボル。接続点が at、記号は direction の側へ。VREF は自作（logicana）"""
        self._pwr_n += 1
        lib_id = "logicana:VREF" if net == "VREF" else f"power:{net}"
        return self.place(lib_id, f"#PWR{self._pwr_n:03d}", at, power_rot(net, direction))

    def flag(self, at, direction=UP) -> Placed:
        self._flg_n += 1
        return self.place("power:PWR_FLAG", f"#FLG{self._flg_n:02d}", at, power_rot("PWR_FLAG", direction))

    # ---- 便利関数 ----
    def stub(self, placed: Placed, pin, length: int = 2):
        """ピンから外向きに length グリッドのワイヤを引き、その端点を返す"""
        p = placed.pin(pin)
        d = placed.outward(pin)
        q = add(p, d[0] * length, d[1] * length)
        self.wire(p, q)
        return q

    def pin_label(self, placed: Placed, pin, net: str, length: int = 2):
        """スタブ ＋ ラベル（外向きに文字が伸びる）"""
        q = self.stub(placed, pin, length)
        self.label(net, q, label_rot(placed.outward(pin)))
        return q

    def pin_power(self, placed: Placed, pin, net: str, length: int = 2):
        """スタブ ＋ 電源シンボル（記号は外向き）"""
        q = self.stub(placed, pin, length)
        self.power(net, q, placed.outward(pin))
        return q

    # ---- ジャンクション自動付与 ----
    def _junctions(self) -> list[list]:
        ends: dict[tuple, int] = {}
        segs = []
        for p1, p2, _ in self.wires:
            ends[p1] = ends.get(p1, 0) + 1
            ends[p2] = ends.get(p2, 0) + 1
            segs.append((p1, p2))
        pins: dict[tuple, int] = {}
        for pt, ref, _ in self.pin_points:
            if ref.startswith("#"):
                continue
            pins[pt] = pins.get(pt, 0) + 1
        out = []
        for pt in sorted(set(ends) | set(pins)):
            n = ends.get(pt, 0) + pins.get(pt, 0)
            on_interior = any(_interior(pt, a, b) for a, b in segs)
            if n >= 3 or (on_interior and n >= 1):
                out.append(S("junction", S("at", pt[0], pt[1]), S("diameter", 0), S("color", 0, 0, 0, 0),
                             S("uuid", self.uid("junction", pt))))
        return out

    # ---- 生成側でできる範囲の検査 ----
    def check(self):
        """全ピンが ワイヤ端 / ラベル / 未接続フラグ のどれかに載っているか。ラベル・電源シンボルはワイヤ端にあるか"""
        ends = set()
        for p1, p2, _ in self.wires:
            ends.add(p1)
            ends.add(p2)
        labels = {pt for pt, _ in self.label_points}
        problems = []
        for pt, ref, pin in self.pin_points:
            if pt in ends or pt in labels or pt in self.nc_points:
                continue
            problems.append(f"{ref} pin {pin} が何にも繋がっていない {pt}")
        for pt, name in self.label_points:
            if pt not in ends:
                problems.append(f"ラベル {name} がワイヤ端に無い {pt}")
        if problems:
            raise SystemExit("生成側チェック失敗:\n  " + "\n  ".join(problems))

    # ---- 出力 ----
    def render(self, paper: str, title_block: list | None) -> str:
        libs = [self.lib_symbols[k] for k in sorted(self.lib_symbols)]
        node = S("kicad_sch",
                 S("version", SCH_VERSION),
                 S("generator", "eeschema"),
                 S("generator_version", GENERATOR_VERSION),
                 S("uuid", self.root_uuid),
                 S("paper", paper))
        if title_block is not None:
            node.append(title_block)
        node.append(S("lib_symbols", *libs))
        node.extend(self._junctions())
        node.extend(self.ncs)
        for p1, p2, u in self.wires:
            node.append(S("wire", S("pts", S("xy", p1[0], p1[1]), S("xy", p2[0], p2[1])),
                          S("stroke", S("width", 0), S("type", Sym("default"))), S("uuid", u)))
        node.extend(self.texts)
        node.extend(self.labels)
        node.extend(self.symbols)
        node.append(S("sheet_instances", S("path", "/", S("page", "1"))))
        node.append(S("embedded_fonts", Y(False)))
        return dump(node) + "\n"


def _interior(pt, a, b) -> bool:
    """pt が線分 ab の内部（端点を除く）にあるか"""
    if pt == a or pt == b:
        return False
    if a[0] == b[0] == pt[0]:
        return min(a[1], b[1]) < pt[1] < max(a[1], b[1])
    if a[1] == b[1] == pt[1]:
        return min(a[0], b[0]) < pt[0] < max(a[0], b[0])
    return False


# --------------------------------------------------------------------------------------
# 部品の共通設定（SPEC §10 BOM）
# --------------------------------------------------------------------------------------

def R(sch, ref, at, value, rot=0, dnp=False, desc=None):
    return sch.place("Device:R", ref, at, rot, value=value, footprint=FP["R0402"], dnp=dnp,
                     description=desc or f"{value} 1% 0402 (SPEC §10)")


def C(sch, ref, at, value, rot=0, desc=None, size="C0402"):
    return sch.place("Device:C", ref, at, rot, value=value, footprint=FP[size], description=desc)


def is_rail(name: str) -> bool:
    return name.startswith("+") or name in ("VREF", "GND")


def led_chain(sch, x, y, src, r_ref, d_ref, d_desc):
    """[src] ── R(1kΩ) ── LED(A→K) ── GND を横一列で。src は電源名かラベル名"""
    p0 = G(x, y)
    if is_rail(src):
        sch.power(src, p0)
    else:
        sch.label(src, p0, 180)
    r = R(sch, r_ref, G(x + 5, y), "1kΩ", rot=90, desc="1kΩ 0402 LED current limit (SPEC §10 #21)")
    sch.wire(p0, r.pin(1))
    d = sch.place("Device:LED", d_ref, G(x + 13, y), 180, value="LED RED", footprint=FP["LED0603"], lcsc="C2286", description=d_desc)
    sch.wire(r.pin(2), d.pin(2))          # A
    k = d.pin(1)
    sch.route(k, add(k, 2, 0), add(k, 2, 2))
    sch.power("GND", add(k, 2, 2), DOWN)


def cap_to_rails(sch, ref, x, y, value, top, desc, size="C0402"):
    """縦置きコンデンサ。pin1 を上のレール（電源名またはラベル）、pin2 を GND へ"""
    c = C(sch, ref, G(x, y), value, desc=desc, size=size)
    p1, p2 = c.pin(1), c.pin(2)
    q1 = add(p1, 0, -2)
    sch.wire(p1, q1)
    if is_rail(top):
        sch.power(top, q1, UP)
    else:
        sch.label(top, q1, 90)
    q2 = add(p2, 0, 2)
    sch.wire(p2, q2)
    sch.power("GND", q2, DOWN)
    return c


# --------------------------------------------------------------------------------------
# 回路本体
# --------------------------------------------------------------------------------------

def build(sch: Sch):
    # ================================================================================
    # 領域 1: USB-C / ESD / LDO / VREF セレクタ / 表示 LED   （左上）
    # ================================================================================
    sch.text("1. POWER / USB", G(10, 12), 2.0)
    sch.text("J1 -> U8 (ESD) -> +5V -> U7 (LDO) -> +3V3 ; SW1 selects VREF = +3V3 / EXT / +5V", G(10, 15), 1.27)

    # --- J1 USB-C 16P（標準シンボル・フットプリントは C165948 そのもの）
    j1 = sch.place("Connector:USB_C_Receptacle_USB2.0_16P", "J1", G(30, 62), 0,
                   value="TYPE-C-31-M-12", footprint=FP["USBC"], lcsc="C165948",
                   description="USB-C receptacle 16P, USB 2.0 (SPEC §10 #7, HRO TYPE-C-31-M-12)")
    # VBUS（A4/A9/B4/B9 は同一点に重なる）→ +5V。PWR_FLAG で ERC の電源駆動を宣言
    vb = j1.pin("A4")
    sch.route(vb, add(vb, 6, 0), add(vb, 12, 0))
    sch.power("+5V", add(vb, 6, 0))
    sch.flag(add(vb, 12, 0), UP)
    # CC1 / CC2 → 各 5.1kΩ で GND（独立）。抵抗はラベル経由で下に置く
    sch.pin_label(j1, "A5", "CC1", 4)
    sch.pin_label(j1, "B5", "CC2", 4)
    # D- : A7 / B7 を結んでから USB_DM、D+ : A6 / B6 を結んで USB_DP（KIT §4.1: コネクタ側の名前）
    a7, b7 = j1.pin("A7"), j1.pin("B7")
    sch.route(a7, add(a7, 4, 0), add(b7, 4, 0), b7)
    sch.wire(add(a7, 4, 0), add(a7, 8, 0))
    sch.label("USB_DM", add(a7, 8, 0), 0)
    a6, b6 = j1.pin("A6"), j1.pin("B6")
    sch.route(a6, add(a6, 4, 0), add(b6, 4, 0), b6)
    sch.wire(add(b6, 4, 0), add(b6, 8, 0))
    sch.label("USB_DP", add(b6, 8, 0), 0)
    # SBU は未使用
    sch.nc(j1.pin("A8"))
    sch.nc(j1.pin("B8"))
    # GND（A1/A12/B1/B12 重なり）と SHIELD → GND。GND にも PWR_FLAG
    g, sh = j1.pin("A1"), j1.pin("SH")
    sch.route(sh, add(sh, 0, 4), add(g, 0, 4))
    sch.route(g, add(g, 0, 4), add(g, 0, 6))
    sch.power("GND", add(g, 0, 6), DOWN)
    sch.wire(add(g, 0, 4), add(g, 4, 4))
    sch.flag(add(g, 4, 4), UP)

    # --- CC プルダウン（SPEC §4.5 / KIT §5-8: 各 1 本・独立）
    for ref, net, x in (("R17", "CC1", 78), ("R18", "CC2", 84)):
        r = R(sch, ref, G(x, 84), "5.1kΩ", desc="5.1kΩ 1% 0402 USB-C CC pull-down (SPEC §10 #15)")
        sch.pin_label(r, 1, net)
        sch.pin_power(r, 2, "GND")

    # --- U8 USBLC6-2SC6（J1 直近・順序 J1 → ESD → 27Ω → RP2040）
    u8 = sch.place("Power_Protection:USBLC6-2SC6", "U8", G(60, 96), 0, footprint=FP["SOT23-6"], lcsc="C7519",
                   description="USB 2.0 ESD protection, SOT-23-6 (SPEC §10 #5)")
    sch.pin_label(u8, "1", "USB_DP", 4)     # I/O1（J1 側）
    sch.pin_label(u8, "3", "USB_DM", 4)     # I/O2（J1 側）
    sch.pin_power(u8, "5", "+5V")
    sch.pin_power(u8, "2", "GND")
    # --- R19 / R20 27Ω 直列終端。U8 の流し出し側（pin 6 / 4）から直結 → RP2040 側は *_MCU（KIT §4.1）
    p6, p4 = u8.pin("6"), u8.pin("4")
    r19 = R(sch, "R19", add(p6, 8, 0), "27Ω", rot=90, desc="27Ω 1% 0402 USB D+ series termination, place next to RP2040 (SPEC §10 #16)")
    sch.wire(p6, r19.pin(1))
    sch.label("USB_DP", r19.pin(1), 180)          # U8 の 1/6 はシンボル上は別ピン。ラベルで同じネットにする
    sch.pin_label(r19, 2, "USB_DP_MCU")
    r20 = R(sch, "R20", add(p4, 8, 4), "27Ω", rot=90, desc="27Ω 1% 0402 USB D- series termination, place next to RP2040 (SPEC §10 #16)")
    sch.route(p4, add(p4, 2, 0), add(p4, 2, 4), r20.pin(1))
    sch.label("USB_DM", r20.pin(1), 180)
    sch.pin_label(r20, 2, "USB_DM_MCU")

    # --- U7 AMS1117-3.3 ＋ 10µF ×2
    u7 = sch.place("Regulator_Linear:AMS1117-3.3", "U7", G(60, 116), 0, footprint=FP["SOT223"], lcsc="C6186",
                   description="LDO 3.3V 1A SOT-223 (SPEC §10 #4)")
    vi, vo = u7.pin("3"), u7.pin("2")
    sch.route(vi, add(vi, -4, 0), add(vi, -8, 0))
    sch.power("+5V", add(vi, -8, 0))
    c25 = C(sch, "C25", add(vi, -4, 3), "10µF", desc="10µF X5R 16V 0805 LDO input (SPEC §10 #26)", size="C0805")
    sch.pin_power(c25, 2, "GND")
    sch.route(vo, add(vo, 4, 0), add(vo, 8, 0))
    sch.power("+3V3", add(vo, 8, 0))
    c26 = C(sch, "C26", add(vo, 4, 3), "10µF", desc="10µF X5R 16V 0805 LDO output (SPEC §10 #26)", size="C0805")
    sch.pin_power(c26, 2, "GND")
    sch.pin_power(u7, "1", "GND")

    # --- SW1 VREF セレクタ（ピン 2 = コモン、1 = +3V3 / 3 = EXT / 4 = +5V：KIT §1.2.3 shorting 対策。コモンは実物の導通確認で pin 2・2026-10-04）
    sw1 = sch.place("logicana:SW_SP3T_SK13D07VG5", "SW1", G(60, 138), 0, value="SK13D07VG5", footprint=FP["SW1"], lcsc="C393948",
                    description="SP3T slide switch, THT right-angle, SHORTING type. Contact order +3V3 / EXT / +5V so +3V3 and +5V never bridge (SPEC §5.4, KIT §1.2.3)")
    com = sw1.pin(2)
    sch.route(com, add(com, -4, 0), add(com, -6, 0), add(com, -10, 0))
    sch.power("VREF", add(com, -4, 0))
    sch.flag(add(com, -10, 0), UP)
    # C27: VREF レールのバルク 1µF（SW1 コモン直近・Manager 判断 2026-09-20 Q2=(b)・SPEC §5.4）
    c27 = C(sch, "C27", add(com, -6, 3), "1µF", desc="1µF X5R 0402, VREF bulk next to SW1 common (SPEC §5.4, Manager 2026-09-20)")
    sch.pin_power(c27, 2, "GND")
    p2, p3, p4 = sw1.pin(1), sw1.pin(3), sw1.pin(4)   # p2 = 上段の接点（ピン番号 1）
    sch.wire(p2, add(p2, 6, 0))
    sch.power("+3V3", add(p2, 6, 0))
    sch.wire(p3, add(p3, 4, 0))
    sch.label("VREF_EXT", add(p3, 4, 0), 0)
    sch.wire(p4, add(p4, 10, 0))
    sch.power("+5V", add(p4, 10, 0), DOWN)
    sch.nc(sw1.pin(5))
    sch.nc(sw1.pin(6))

    # --- J3 VREF EXT 入力（1×3・中央 = EXT、両端 GND）。90° 回転でピンを下向きに
    j3 = sch.place("Connector_Generic:Conn_01x03", "J3", G(60, 150), 90, value="VREF_EXT", footprint=FP["H1x03"],
                   description="Pin header 1x3 2.54mm, VREF EXT input (SPEC §6: EXT + GND x2). Pin 2 = EXT, pins 1/3 = GND")
    sch.pin_label(j3, 2, "VREF_EXT", 5)
    sch.pin_power(j3, 1, "GND")
    sch.pin_power(j3, 3, "GND")

    # --- 表示 LED：D1 = +3V3、D2 = VREF（KIT §5-14）
    led_chain(sch, 82, 128, "+3V3", "R25", "D1", "LED red 0603, +3V3 power indicator (SPEC §6 D1)")
    led_chain(sch, 82, 134, "VREF", "R26", "D2", "LED red 0603, VREF indicator: dark when SW1 is not set (SPEC §6 D2)")

    # ================================================================================
    # 領域 2: RP2040 / フラッシュ / 水晶 / BOOT・RUN / テストパッド     （中央）
    # ================================================================================
    sch.text("2. MCU", G(112, 12), 2.0)
    sch.text("U1 RP2040 + U2 W25Q128 (QSPI) + X1 12MHz ; 100nF x10 (C1-C10) + 1uF x2 (C21/C22) ; BOOT = SW2, RUN = SW3 ; SWD on TP8/TP9", G(112, 15), 1.27)

    u1 = sch.place("MCU_RaspberryPi:RP2040", "U1", G(160, 92), 0, footprint=FP["QFN56"], lcsc="C2040",
                   description="Raspberry Pi RP2040, QFN-56 7x7mm (SPEC §10 #1)")
    # 右側 GPIO（GPIO0..7 = pin 2..9、GPIO8..15 = pin 11..18）
    for i in range(16):
        sch.pin_label(u1, str(2 + i + (1 if i >= 8 else 0)), f"D{i}", 4)
    gp = {16: "27", 17: "28", 18: "29", 19: "30", 20: "31", 21: "32", 22: "34", 23: "35", 24: "36", 25: "37",
          26: "38", 27: "39", 28: "40", 29: "41"}
    for n in range(16, 23):
        sch.pin_label(u1, gp[n], f"GP{n}", 4)
    sch.pin_label(u1, gp[23], "TXU_OE", 4)
    sch.nc(u1.pin(gp[24]))
    sch.pin_label(u1, gp[25], "LED_STATUS", 4)
    sch.pin_label(u1, gp[26], "GP26_ADC0", 4)
    sch.pin_label(u1, gp[27], "GP27_ADC1", 4)
    sch.pin_label(u1, gp[28], "GP28_ADC2", 4)
    sch.nc(u1.pin(gp[29]))
    # 左側
    sch.pin_power(u1, "19", "GND", 3)                # TESTEN: データシート「Ground on user boards」
    sch.pin_label(u1, "26", "RUN", 4)
    sch.pin_label(u1, "46", "USB_DM_MCU", 4)
    sch.pin_label(u1, "47", "USB_DP_MCU", 4)
    sch.pin_label(u1, "56", "QSPI_SS_N", 4)
    sch.pin_label(u1, "52", "QSPI_SCLK", 4)
    sch.pin_label(u1, "53", "QSPI_SD0", 4)
    sch.pin_label(u1, "55", "QSPI_SD1", 4)
    sch.pin_label(u1, "54", "QSPI_SD2", 4)
    sch.pin_label(u1, "51", "QSPI_SD3", 4)
    sch.pin_label(u1, "20", "XIN", 4)
    sch.pin_label(u1, "21", "XOUT", 4)
    sch.pin_label(u1, "24", "SWCLK", 4)              # KIT §5-15: SWD を出す（TP8 / TP9・Manager 2026-09-20）
    sch.pin_label(u1, "25", "SWDIO", 4)
    # 上側 電源。IOVDD(1,10,22,33,42,49) と DVDD(23,50) はシンボル上で同一点に重なる
    sch.pin_power(u1, "43", "+3V3", 3)               # ADC_AVDD
    sch.pin_power(u1, "48", "+3V3", 5)               # USB_VDD
    sch.pin_power(u1, "1", "+3V3", 3)                # IOVDD ×6
    sch.pin_power(u1, "44", "+3V3", 5)               # VREG_VIN
    vout, dvdd = u1.pin("45"), u1.pin("23")
    sch.route(vout, add(vout, 0, -3), add(dvdd, 0, -3), dvdd)
    sch.label("DVDD", add(vout, 0, -3), 90)
    # 下側 GND（EP = 57）
    sch.pin_power(u1, "57", "GND")

    # --- デカップリング（KIT §5-1: 電源ピン 1 本に 100nF 1 個 = 10 個。C11 = U2、C12 = 予備）
    row, x = 30, 118
    for i in range(1, 7):
        cap_to_rails(sch, f"C{i}", x, row, "100nF", "+3V3", f"100nF X7R 16V 0402, RP2040 IOVDD pin {[1, 10, 22, 33, 42, 49][i - 1]} (KIT §5-1)")
        x += 6
    cap_to_rails(sch, "C9", x, row, "100nF", "+3V3", "100nF X7R 16V 0402, RP2040 USB_VDD pin 48 (KIT §5-1)"); x += 6
    cap_to_rails(sch, "C10", x, row, "100nF", "+3V3", "100nF X7R 16V 0402, RP2040 ADC_AVDD pin 43 (KIT §5-1)"); x += 6
    cap_to_rails(sch, "C12", x, row, "100nF", "+3V3", "100nF X7R 16V 0402, spare (SPEC §10 #22 予備)"); x += 6
    cap_to_rails(sch, "C21", x, row, "1µF", "+3V3", "1µF X5R 0402, RP2040 VREG_VIN pin 44 (KIT §5-2, 公式指定)"); x += 8
    cap_to_rails(sch, "C7", x, row, "100nF", "DVDD", "100nF X7R 16V 0402, RP2040 DVDD pin 23 (KIT §5-1)"); x += 6
    cap_to_rails(sch, "C8", x, row, "100nF", "DVDD", "100nF X7R 16V 0402, RP2040 DVDD pin 50 (KIT §5-1)"); x += 6
    cap_to_rails(sch, "C22", x, row, "1µF", "DVDD", "1µF X5R 0402, RP2040 VREG_VOUT pin 45 (KIT §5-2, 公式指定)"); x += 8
    cap_to_rails(sch, "C11", x, row, "100nF", "+3V3", "100nF X7R 16V 0402, U2 flash VCC - place at U2 pin 8 (KIT §5-1)")

    # --- U2 W25Q128JVSIQ（QSPI 直結）
    u2 = sch.place("Memory_Flash:W25Q128JVS", "U2", G(118, 82), 0, value="W25Q128JVSIQ", footprint=FP["SOIC8"], lcsc="C97521",
                   description="128Mbit QSPI flash, SOIC-8 208mil (SPEC §10 #2)")
    sch.pin_label(u2, "1", "QSPI_SS_N", 4)
    sch.pin_label(u2, "6", "QSPI_SCLK", 4)
    sch.pin_label(u2, "5", "QSPI_SD0", 4)     # DI / IO0
    sch.pin_label(u2, "2", "QSPI_SD1", 4)     # DO / IO1
    sch.pin_label(u2, "3", "QSPI_SD2", 4)     # WP / IO2
    sch.pin_label(u2, "7", "QSPI_SD3", 4)     # HOLD / IO3
    sch.pin_power(u2, "8", "+3V3")
    sch.pin_power(u2, "4", "GND")

    # --- R23 10kΩ DNF（QSPI_SS プルアップ）─ R22 1kΩ（BOOTSEL）─ SW2 / SW3
    r23 = R(sch, "R23", G(92, 74), "10kΩ", dnp=True, desc="10kΩ 0402 QSPI_SS pull-up, DNF (SPEC §4.2 / KIT §5-5)")
    sch.pin_power(r23, 1, "+3V3")
    r22 = R(sch, "R22", G(92, 84), "1kΩ", desc="1kΩ 0402 BOOTSEL series (SPEC §4.2 / KIT §5-6)")
    mid = add(r23.pin(2), 0, 2)
    sch.route(r23.pin(2), mid, r22.pin(1))
    sch.label("QSPI_SS_N", mid, 0)
    sch.pin_label(r22, 2, "USB_BOOT")
    for ref, y, net, desc in (("SW2", 104, "USB_BOOT", "Tactile switch, BOOTSEL: pulls QSPI_SS low via R22 (SPEC §6 SW2)"),
                              ("SW3", 112, "RUN", "Tactile switch, RESET: pulls RUN low, no external parts (SPEC §6 SW3, KIT §5 RUN)")):
        sw = sch.place("logicana:SW_Push_TS1187A", ref, G(92, y), 0, value="TS-1187A-B-A-B", footprint=FP["TACT"], lcsc="C318884", description=desc)
        sch.pin_label(sw, 1, net, 3)
        p = sw.pin(3)
        sch.route(p, add(p, 2, 0), add(p, 2, 2))
        sch.power("GND", add(p, 2, 2), DOWN)

    # --- 水晶（KIT §5-3/5-4: 15pF ×2、1kΩ は XOUT 側、XIN は直結）
    x1 = sch.place("Device:Crystal_GND24", "X1", G(112, 108), 0, value="ABM8-272-T3 12MHz", footprint=FP["XTAL"], lcsc="C20625731",
                   description="Crystal 12MHz 3225 4-pin, CL 10pF, ESR <= 50Ω (SPEC §4.3, Raspberry Pi 公式推奨品)")
    p1, p3 = x1.pin(1), x1.pin(3)
    sch.wire(p1, add(p1, -3, 0))
    sch.label("XIN", add(p1, -3, 0), 180)
    sch.wire(p3, add(p3, 3, 0))
    sch.label("XTAL_DRV", add(p3, 3, 0), 0)
    sch.pin_power(x1, "2", "GND")
    c23 = C(sch, "C23", add(p1, -3, 3), "15pF", desc="15pF NP0 0402 crystal load, XIN side (KIT §5-3)")
    sch.pin_power(c23, 2, "GND")
    c24 = C(sch, "C24", add(p3, 3, 3), "15pF", desc="15pF NP0 0402 crystal load, XOUT/XTAL_DRV side (KIT §5-3)")
    sch.pin_power(c24, 2, "GND")
    r21 = R(sch, "R21", G(128, 126), "1kΩ", rot=90, desc="1kΩ 0402 crystal damping, XOUT side (SPEC §4.3 / KIT §5-4)")
    sch.pin_label(r21, 1, "XOUT")
    sch.pin_label(r21, 2, "XTAL_DRV")

    # --- ステータス LED（GP25）
    led_chain(sch, 104, 142, "LED_STATUS", "R27", "D3", "LED red 0603, status on GP25 (SPEC §6 D3)")

    # --- TXU_OE プルアップ 10kΩ → +3V3（KIT §5-10: VREF ではない）
    r24 = R(sch, "R24", G(204, 136), "10kΩ", desc="10kΩ 0402 TXU0104 OE pull-up to +3V3 (SPEC §5.3 / KIT §5-10)")
    sch.pin_power(r24, 1, "+3V3")
    sch.pin_label(r24, 2, "TXU_OE")

    # --- テストパッド GP16〜GP22（SPEC §6 J5。TestPoint シンボルは TP 参照子）
    tps = [(f"TP{i + 1}", f"GP{n}", f"Test pad 1.0mm, GP{n} (SPEC §6 J5 test pads for dgatf UART/config)") for i, n in enumerate(range(16, 23))]
    tps += [("TP8", "SWCLK", "Test pad 1.0mm, SWCLK (KIT §5-15: SWD brought out, Manager 2026-09-20)"),
            ("TP9", "SWDIO", "Test pad 1.0mm, SWDIO (KIT §5-15: SWD brought out, Manager 2026-09-20)")]
    for i, (ref, net, desc) in enumerate(tps):
        tp = sch.place("Connector:TestPoint", ref, G(136 + 5 * i, 144), 0, value=net, footprint=FP["TP"], description=desc)
        sch.pin_label(tp, 1, net, 2)

    # --- J4 アナログ 3ch（DNF）
    j4 = sch.place("Connector_Generic:Conn_01x03", "J4", G(190, 152), 0, value="ADC 1x3 (DNF)", footprint=FP["H1x03"], dnp=True,
                   description="Pin header 1x3 2.54mm, GP26/27/28 analog, DNF (SPEC §6 J4)")
    sch.pin_label(j4, 1, "GP26_ADC0", 4)
    sch.pin_label(j4, 2, "GP27_ADC1", 4)
    sch.pin_label(j4, 3, "GP28_ADC2", 4)

    # ================================================================================
    # 領域 3: フロントエンド ×4（U3〜U6・100Ω ×16・100nF ×8）     （右）
    # ================================================================================
    sch.text("3. FRONT END x4", G(216, 12), 2.0)
    sch.text("CHn_IN -> 100R -> TXU0104 (A: VREF, B: +3V3) -> Dn ; OE = TXU_OE", G(216, 15), 1.27)
    for k in range(4):
        ux, uy = 246, 40 + 40 * k
        u = sch.place("logicana:TXU0104PWR", f"U{3 + k}", G(ux, uy), 0, footprint=FP["TSSOP14"], lcsc="C2938871",
                      description=f"4-bit level translator A->B, Schmitt inputs, CH{4 * k}-CH{4 * k + 3} (SPEC §10 #3)")
        for ch in range(4):
            n = 4 * k + ch
            a_pin = u.pin(str(2 + ch))
            r = R(sch, f"R{n + 1}", add(a_pin, -6 if ch % 2 == 0 else -11, 0), "100Ω", rot=90,
                  desc=f"100Ω 1% 0402 input series CH{n} (SPEC §5.3 / KIT §5-13)")
            sch.wire(r.pin(2), a_pin)
            sch.label(f"CH{n}_A", r.pin(2), 0)
            sch.pin_label(r, 1, f"CH{n}_IN")
            sch.pin_label(u, str(13 - ch), f"D{n}", 4)          # B1Y..B4Y = pin 13..10
        sch.pin_label(u, "8", "TXU_OE", 4)
        sch.nc(u.pin("6"))
        sch.nc(u.pin("9"))
        va, vb = u.pin("1"), u.pin("14")
        sch.route(va, add(va, 0, -3), add(va, -4, -3))
        sch.power("VREF", add(va, -4, -3))
        sch.route(vb, add(vb, 0, -3), add(vb, 4, -3))
        sch.power("+3V3", add(vb, 4, -3))
        sch.pin_power(u, "7", "GND")
        cap_to_rails(sch, f"C{13 + 2 * k}", ux + 22, uy - 8, "100nF", "VREF", f"100nF X7R 16V 0402, U{3 + k} VCCA (KIT §5-11)")
        cap_to_rails(sch, f"C{14 + 2 * k}", ux + 28, uy - 8, "100nF", "+3V3", f"100nF X7R 16V 0402, U{3 + k} VCCB (KIT §5-11)")

    # ================================================================================
    # 領域 4: プローブヘッダ J2（内側 = CH、外側 = GND）     （右端）
    # ================================================================================
    sch.text("4. PROBE HEADER", G(292, 12), 2.0)
    sch.text("J2 2x16: odd = CH0-CH15, even = GND", G(292, 15), 1.27)
    j2 = sch.place("Connector_Generic:Conn_02x16_Odd_Even", "J2", G(308, 60), 0, value="PROBE 2x16", footprint=FP["H2x16"],
                   description="Pin header 2x16 2.54mm probe header: odd row = CH0..CH15, even row = GND (SPEC §6 J2)")
    for n in range(16):
        sch.pin_label(j2, str(2 * n + 1), f"CH{n}_IN", 4)
    bus_x = add(j2.pin(2), 2, 0)[0]
    for n in range(16):
        p = j2.pin(str(2 * n + 2))
        sch.wire(p, (bus_x, p[1]))
    top, bottom = (bus_x, j2.pin(2)[1]), (bus_x, j2.pin(32)[1])
    sch.wire(top, bottom)
    sch.wire(bottom, add(bottom, 0, 2))
    sch.power("GND", add(bottom, 0, 2), DOWN)

    # ================================================================================
    # 注記
    # ================================================================================
    notes = [
        "Generated by tools/gen_schematic.py from SPEC.md / KICAD-KIT.md (2026-09-20). Placement is functional only; tidy in the GUI.",
        "SW1 (SK13D07VG5) is a SHORTING slide switch: +3V3 (pin 1) and +5V (pin 4) are never adjacent; EXT (pin 3) sits between. Do not slide with EXT connected.",
        "USB path: J1 -> U8 (USBLC6) -> R19/R20 27R -> RP2040. No external pull-ups (RP2040 internal). CC1/CC2: 5.1k each to GND.",
        "Crystal: 1k damping on the XOUT side (R21), XIN direct. 15pF x2 at the crystal pins. RP2040 TESTEN tied to GND (datasheet).",
        "DNF: R23 (10k QSPI_SS pull-up), J4 (analog header). SWD on test pads TP8 (SWCLK) / TP9 (SWDIO). C27 = 1uF bulk on VREF.",
    ]
    for i, t in enumerate(notes):
        sch.text(t, G(10, 200 + 3 * i), 1.5)


# --------------------------------------------------------------------------------------
# プロジェクトファイル・ライブラリテーブル
# --------------------------------------------------------------------------------------

def _netclass(name, track, clearance, via, drill, priority, dp_w=0.2, dp_gap=0.25):
    return {"bus_width": 12, "clearance": clearance, "diff_pair_gap": dp_gap, "diff_pair_via_gap": 0.25, "diff_pair_width": dp_w,
            "line_style": 0, "microvia_diameter": 0.3, "microvia_drill": 0.1, "name": name, "pcb_color": "rgba(0, 0, 0, 0.000)",
            "priority": priority, "schematic_color": "rgba(0, 0, 0, 0.000)", "track_width": track, "tuning_profile": "",
            "via_diameter": via, "via_drill": drill, "wire_width": 6}


# .kicad_pro に入れる DRC 値（KIT §3.2）
DESIGN_RULES = {
    "max_error": 0.005,
    "min_clearance": 0.15,
    "min_connection": 0.0,
    "min_copper_edge_clearance": 0.3,
    "min_groove_width": 0.0,
    "min_hole_clearance": 0.25,
    "min_hole_to_hole": 0.25,
    "min_microvia_diameter": 0.2,
    "min_microvia_drill": 0.1,
    "min_resolved_spokes": 2,
    "min_silk_clearance": 0.0,
    "min_text_height": 0.8,
    "min_text_thickness": 0.15,
    "min_through_hole_diameter": 0.25,      # KiCad はビアドリルもこの値で見る（KIT §3.2 ビア 0.45/0.25）。THT の実穴は全部 0.7 以上
    "min_track_width": 0.15,
    "min_via_annular_width": 0.1,
    "min_via_diameter": 0.45,
    "solder_mask_to_copper_clearance": 0.0,
    "use_height_for_length_calcs": True,
}
DESIGN_DEFAULTS = {
    "apply_defaults_to_fp_barcodes": False, "apply_defaults_to_fp_dimensions": False, "apply_defaults_to_fp_fields": False,
    "apply_defaults_to_fp_shapes": False, "apply_defaults_to_fp_text": False,
    "board_outline_line_width": 0.05, "copper_line_width": 0.2, "copper_text_italic": False,
    "copper_text_size_h": 1.5, "copper_text_size_v": 1.5, "copper_text_thickness": 0.3, "copper_text_upright": False,
    "courtyard_line_width": 0.05, "dimension_precision": 4, "dimension_units": 3,
    "dimensions": {"arrow_length": 1270000, "extension_offset": 500000, "keep_text_aligned": True, "suppress_zeroes": True,
                   "text_position": 0, "units_format": 0},
    "fab_line_width": 0.1, "fab_text_italic": False, "fab_text_size_h": 1.0, "fab_text_size_v": 1.0,
    "fab_text_thickness": 0.15, "fab_text_upright": False,
    "other_line_width": 0.1, "other_text_italic": False, "other_text_size_h": 1.0, "other_text_size_v": 1.0,
    "other_text_thickness": 0.15, "other_text_upright": False,
    "pads": {"drill": 0.8, "height": 1.27, "width": 2.54},
    "silk_line_width": 0.15, "silk_text_italic": False, "silk_text_size_h": 1.0, "silk_text_size_v": 1.0,
    "silk_text_thickness": 0.15, "silk_text_upright": False,
    "zones": {"border_display_style": 2, "border_hatch_pitch": 0.5, "corner_radius": 0.0, "corner_smoothing": 0,
              "fill_mode": 0, "hatch_gap": 1.5, "hatch_orientation": 0.0, "hatch_smoothing_level": 0,
              "hatch_smoothing_value": 0.1, "hatch_thickness": 1.0, "min_clearance": 0.2, "min_island_area": 10.0,
              "min_thickness": 0.25, "pad_connection": 1, "remove_islands": 1, "thermal_relief_gap": 0.3,
              "thermal_relief_spoke_width": 0.3},
}
RULE_SEVERITIES = {
    "annular_width": "error", "clearance": "error", "connection_width": "warning", "copper_edge_clearance": "error",
    "copper_sliver": "warning", "courtyards_overlap": "error", "creepage": "error", "diff_pair_gap_out_of_range": "error",
    "diff_pair_uncoupled_length_too_long": "error", "drill_out_of_range": "error", "duplicate_footprints": "warning",
    "extra_footprint": "warning", "footprint": "error", "footprint_filters_mismatch": "ignore",
    "footprint_symbol_field_mismatch": "warning", "footprint_symbol_mismatch": "warning", "footprint_type_mismatch": "ignore",
    "hole_clearance": "error", "hole_to_hole": "warning", "holes_co_located": "warning", "invalid_outline": "error",
    "isolated_copper": "warning", "item_on_disabled_layer": "error", "items_not_allowed": "error",
    "length_out_of_range": "error", "lib_footprint_issues": "warning", "lib_footprint_mismatch": "warning",
    "malformed_courtyard": "error", "microvia_drill_out_of_range": "error", "mirrored_text_on_front_layer": "warning",
    "missing_courtyard": "ignore", "missing_footprint": "warning", "missing_tuning_profile": "warning",
    "net_conflict": "warning", "nonmirrored_text_on_back_layer": "warning", "npth_inside_courtyard": "error",
    "padstack": "warning", "pth_inside_courtyard": "error", "shorting_items": "error", "silk_edge_clearance": "warning",
    "silk_over_copper": "warning", "silk_overlap": "warning", "skew_out_of_range": "error", "solder_mask_bridge": "error",
    "starved_thermal": "error", "text_height": "warning", "text_on_edge_cuts": "error", "text_thickness": "warning",
    "through_hole_pad_without_hole": "error", "too_many_vias": "error", "track_angle": "error", "track_dangling": "warning",
    "track_segment_length": "error", "unconnected_items": "error", "unresolved_variable": "error",
    "via_dangling": "warning", "zones_intersect": "error",
}


def board_design_settings() -> dict:
    """基板側の Board Setup（KIT §3.2 の DRC 値ほか）。.kicad_pro の board.design_settings に入る"""
    ds = {}
    ds["defaults"] = DESIGN_DEFAULTS
    ds["diff_pair_dimensions"] = [{"gap": 0.15, "via_gap": 0.25, "width": 0.3}]      # KIT §3.4 USB 90Ω
    ds["drc_exclusions"] = []
    ds["meta"] = {"version": 2}
    ds["rule_severities"] = RULE_SEVERITIES
    ds["rules"] = DESIGN_RULES
    ds["track_widths"] = [0.0, 0.2, 0.3, 0.5]
    ds["via_dimensions"] = [{"diameter": 0.0, "drill": 0.0}, {"diameter": 0.45, "drill": 0.25}, {"diameter": 0.65, "drill": 0.35}]
    ds["zones_allow_external_fillets"] = False
    return ds



def kicad_pro() -> str:
    pro = {
        "board": {"3dviewports": [], "design_settings": board_design_settings(),
                  "ipc2581": {"bom_rev": "", "dist": "", "distpn": "", "internal_id": "", "mfg": "", "mpn": "", "sch_revision": ""},
                  "layer_pairs": [], "layer_presets": [], "viewports": []},
        "boards": [],
        "component_class_settings": {"assignments": [], "meta": {"version": 0}, "sheet_component_classes": {"enabled": False}},
        "cvpcb": {"equivalence_files": []},
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": f"{PROJECT}.kicad_pro", "version": 3},
        "net_settings": {
            # KIT §3.3 のネットクラス（値はそのまま）。Default は最低優先
            "classes": [
                _netclass("Default", 0.2, 0.15, 0.45, 0.25, 2147483647),
                _netclass("Power", 0.5, 0.2, 0.65, 0.35, 0),
                _netclass("USB", 0.3, 0.15, 0.45, 0.25, 1, dp_w=0.3, dp_gap=0.15),
                _netclass("Signal_D", 0.2, 0.15, 0.45, 0.25, 2),
                _netclass("QSPI", 0.2, 0.15, 0.45, 0.25, 3),
            ],
            "meta": {"version": 5},
            "net_colors": None,
            "netclass_assignments": None,
            "netclass_patterns": [
                {"netclass": "Power", "pattern": "+5V"}, {"netclass": "Power", "pattern": "+3V3"},
                {"netclass": "Power", "pattern": "VREF"}, {"netclass": "Power", "pattern": "/DVDD"},
                {"netclass": "USB", "pattern": "/USB_DP"}, {"netclass": "USB", "pattern": "/USB_DM"},
                {"netclass": "Signal_D", "pattern": "/D?"}, {"netclass": "Signal_D", "pattern": "/D??"},
                {"netclass": "QSPI", "pattern": "/QSPI_*"},
            ],
        },
        "pcbnew": {"last_paths": {"idf": "", "netlist": "", "plot": "", "specctra_dsn": "", "vrml": ""}, "page_layout_descr_file": ""},
        "schematic": {"bus_aliases": {}, "legacy_lib_dir": "", "legacy_lib_list": [], "top_level_sheets": []},
        "sheets": [],
        "text_variables": {},
        "tuning_profiles": {"meta": {"version": 0}, "tuning_profiles_impedance_geometric": []},
    }
    return json.dumps(pro, indent=2, ensure_ascii=False) + "\n"


SYM_LIB_TABLE = '''(sym_lib_table
  (version 7)
  (lib (name "logicana")(type "KiCad")(uri "${KIPRJMOD}/../lib/logicana.kicad_sym")(options "")(descr "self-drawn, tracked: TXU0104PWR / SW_SP3T_SK13D07VG5 / SW_Push_TS1187A / VREF"))
  (lib (name "lcsc")(type "KiCad")(uri "${KIPRJMOD}/../lib/lcsc/lcsc.kicad_sym")(options "")(descr "easyeda2kicad imports, gitignored (see README)"))
)
'''

FP_LIB_TABLE = '''(fp_lib_table
  (version 7)
  (lib (name "lcsc")(type "KiCad")(uri "${KIPRJMOD}/../lib/lcsc/lcsc.pretty")(options "")(descr "easyeda2kicad imports: SW1 / SW2 / SW3 footprints, gitignored (see README)"))
)
'''


# --------------------------------------------------------------------------------------
# 生成・検算
# --------------------------------------------------------------------------------------

def new_sch() -> Sch:
    libs = LibCache(STD_SYM_DIR, {"logicana": LIBDIR / "logicana.kicad_sym", "lcsc": LIBDIR / "lcsc" / "lcsc.kicad_sym"})
    return Sch(libs)


def generate() -> dict[str, str]:
    sch = new_sch()
    build(sch)
    sch.check()
    tb = S("title_block", S("title", "RP2040 16ch Logic Analyzer"), S("date", "2026-09-20"), S("rev", "A0"),
           S("company", "electwork.net"), S("comment", 1, "Generated by tools/gen_schematic.py from SPEC.md / KICAD-KIT.md. CERN-OHL-P-2.0"))
    return {
        f"{PROJECT}.kicad_sch": sch.render("A3", tb),
        f"{PROJECT}.kicad_pro": kicad_pro(),
        "sym-lib-table": SYM_LIB_TABLE,
        "fp-lib-table": FP_LIB_TABLE,
    }


def netlist_nets(sch_path: Path) -> dict[str, set[tuple[str, str]]]:
    """kicad-cli で kicadsexpr ネットリストを出し、{ネット名: {(ref, pin)}} にする"""
    out = sch_path.with_suffix(".net")
    subprocess.run([str(KICAD_CLI), "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(out), str(sch_path)],
                   check=True, capture_output=True)
    root = parse(out.read_text(encoding="utf-8"))[0]
    nets = {}
    for net in find(find1(root, "nets"), "net"):
        name = find1(net, "name")[1]
        nets[name] = {(find1(n, "ref")[1], find1(n, "pin")[1]) for n in find(net, "node")}
    return nets


def selftest() -> int:
    """回転 0/90/180/270 の抵抗にラベルを付け、kicad-cli のネットリストで ROT 行列を実測する"""
    sch = new_sch()
    expect = {}
    for i, rot in enumerate((0, 90, 180, 270)):
        r = sch.place("Device:R", f"R{i + 1}", G(20 + 20 * i, 40), rot, value="1k", footprint=FP["R0402"])
        for pin in (1, 2):
            net = f"ROT{rot}_P{pin}"
            sch.pin_label(r, pin, net, 3)
            expect[net] = {(f"R{i + 1}", str(pin))}
    # 電源シンボルの向きも同時に確認（記号の向きは目視用。接続点だけ検算）
    c = sch.place("Device:C", "C1", G(120, 40), 0, value="100n", footprint=FP["C0402"])
    sch.pin_power(c, 1, "+3V3")
    sch.pin_power(c, 2, "GND")
    expect["+3V3"] = {("C1", "1")}
    expect["GND"] = {("C1", "2")}
    sch.check()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "selftest.kicad_sch"
        p.write_text(sch.render("A4", None), encoding="utf-8")
        nets = netlist_nets(p)
    ok = True
    for net, nodes in expect.items():
        got = nets.get(net) or nets.get("/" + net) or set()
        flag = "OK " if got == nodes else "NG "
        ok &= got == nodes
        print(flag, net, sorted(got))
    print("selftest", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="RP2040 logic analyzer: KiCad 10 schematic generator")
    ap.add_argument("--check", action="store_true", help="書き込まず、既存出力と一致するか確認する（冪等性）")
    ap.add_argument("--selftest", action="store_true", help="回転行列を kicad-cli のネットリストで実測する")
    ap.add_argument("--out", type=Path, default=HW, help="出力ディレクトリ（既定: hardware/）")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if args.selftest:
        return selftest()
    files = generate()
    if args.check:
        bad = [n for n, body in files.items() if not (args.out / n).exists() or (args.out / n).read_text(encoding="utf-8") != body]
        print("一致" if not bad else "不一致: " + ", ".join(bad))
        return 1 if bad else 0
    args.out.mkdir(parents=True, exist_ok=True)
    for n, body in files.items():
        (args.out / n).write_text(body, encoding="utf-8", newline="\n")
        print("wrote", args.out / n, len(body), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
