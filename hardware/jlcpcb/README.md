# JLCPCB 製造データ

このフォルダの直下は **A1 の製造データ**（2026-10-10・SW1 の配線を回路図に合わせて修正した版）です。`../out/` の kicad-cli 出力（`uv run tools/make_outputs.py`）をそのまま置いたもので、発注にはこのフォルダのファイルを使います。**A1 はまだ製造していません**（筆者はこのデータでの発注を行っていません）。

## 中身（A1）

| パス | 何か | 出どころ |
|:---|:---|:---|
| `gerbers/`（16 ファイル） | A1 の Gerber・ドリル・`.gbrjob`。KiCad 10.0.3 の kicad-cli 出力（2026-10-10）。長穴 6 か所（USB-C シェルの脚 4 × 0.6mm、SW1 の固定脚 2 × 0.8mm）は KiCad の「Use route command」記法（`G00`/`M15`/`G01`/`M16`）。A0 の注文で製造に使われたドリルファイルと同じ記法です | `../out/gerbers/` と同一 |
| `bom-jlcpcb.csv` / `cpl-jlcpcb.csv` | JLCPCB 形式の BOM（19 行）と CPL（SMD 68 部品） | `../out/` の同名ファイルと同一。**A0 の注文に使ったものと同一**（部品・配置は変えていない） |

筆者が注文した A0 からの変更は SW1 まわりだけです（pad1 = 3.3V・pad2 = VREF の入れ替えと VREF 配線の引き直し。経緯はリポジトリ直下の README の「既知の問題」）。部品・配置・穴の数と径（0.30 ×148・0.35 ×33・0.914 ×4・1.0 ×38・NPTH 0.65 ×2・長穴 6）は A0 と同じで、BOM / CPL は A0 の注文に使ったものと同一です。A0 の注文では USB-C（J1）が在庫切れで、注文画面の部品照合で実装から外しました。

## 同梱していないもの

- JLCPCB 内部の CAM 出力（ダウンロードの `ok/` フォルダ。注文番号付きのアーカイブと層ごとの中間ファイル）
- 解析用 JSON（`4te.json` など。JLCPCB 社内のパスや期限付き URL を含む）

---

# JLCPCB manufacturing data

The top level of this folder holds the **Rev A1** manufacturing data (2026-10-10; SW1 pad assignment fixed to match the schematic): the kicad-cli output from `../out/` (`uv run tools/make_outputs.py`), stored as-is. **A1 has not been manufactured yet.**

- `gerbers/`: the 16 Gerber / drill / `.gbrjob` files for A1 (KiCad 10.0.3 kicad-cli export). The six oval slots use KiCad's "route command" encoding (`G00`/`M15`/`G01`/`M16`), the same encoding as the drill files used for the A0 production run.
- `bom-jlcpcb.csv` / `cpl-jlcpcb.csv`: JLCPCB-format BOM (19 lines) and CPL (68 SMD parts), identical to the A0 files (no part or placement changes).
- A1 differs from the A0 boards the author ordered only around SW1: two pad nets swapped (pad1 = 3.3 V, pad2 = VREF) and the VREF trace re-routed to pad2 (see "Known issue" in the top-level README). Parts, placement, hole count and sizes are unchanged. In the A0 order the USB-C connector (J1) was deselected at the parts-matching step because it was out of stock.
- Not included: JLCPCB's internal CAM output and analysis JSON files.
