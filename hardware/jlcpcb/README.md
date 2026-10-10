# JLCPCB 製造データ

このフォルダの直下は **A1 の製造データ**（2026-10-10・SW1 の配線を回路図に合わせて修正した版）です。`../out/` の kicad-cli 出力（`uv run tools/make_outputs.py`）をそのまま置いたもので、発注にはこのフォルダのファイルを使います。**A1 はまだ製造していません**（筆者はこのデータでの発注を行っていません）。A0 の注文に実際に使ったデータは `a0/` に残しています。

## 中身（A1）

| パス | 何か | 出どころ |
|:---|:---|:---|
| `gerbers/`（16 ファイル） | A1 の Gerber・ドリル・`.gbrjob`。KiCad 10.0.3 の kicad-cli 出力（2026-10-10）。長穴 6 か所（USB-C シェルの脚 4 × 0.6mm、SW1 の固定脚 2 × 0.8mm）は KiCad の「Use route command」記法（`G00`/`M15`/`G01`/`M16`）で、A0 の注文で製造に使われたドリルファイルと日付以外同一 | `../out/gerbers/` と同一 |
| `bom-jlcpcb.csv` / `cpl-jlcpcb.csv` | JLCPCB 形式の BOM（19 行）と CPL（SMD 68 部品） | `../out/` の同名ファイルと同一。**A0 の注文に使ったものと同一**（部品・配置は変えていない） |

A1 と A0 の違いは SW1 まわりだけです: SW1 の pad1／pad2 のネットの入れ替え（pad1 = 3.3V・pad2 = VREF）、VREF の表面配線を pad2 へ引き直し、内層 L3 の 3.3V プレーンの再充填、表シルク「RP2040 LA A1」、裏シルク「CERN-OHL-P v2」。穴の数と径（0.30 ×148・0.35 ×33・0.914 ×4・1.0 ×38・NPTH 0.65 ×2・長穴 6）は A0 と同じです。

## a0/ — A0 の注文（2026-09-26）に実際に使ったデータ

| パス | 何か | 出どころ |
|:---|:---|:---|
| `a0/gerbers/`（16 ファイル） | A0 の注文で製造に使われた Gerber・ドリル・`.gbrjob`。KiCad 10.0.3 の GUI 出力（2026-09-21 22:40 JST） | 注文ページ「Production file」の `yg/` フォルダ |
| `a0/jlcpcb-render-top.png` / `a0/jlcpcb-render-bottom.png` | アップロードした Gerber から JLCPCB 側が自動生成したプレビュー（表はシルクとパッド、裏はパッドのみ） | 同上 |
| `a0/bom-jlcpcb.csv` / `a0/cpl-jlcpcb.csv` | A0 の注文でアップロードした BOM と CPL | 注文に使ったファイルそのもの |

- A0 の注文では、USB-C（J1）を部品が入手できなかったため実装から外しています。`a0/` のデータは、その状態の注文のものです
- **A0 の PCB は SW1 のコモンの配線が誤っています**（コモンはピン 2）。`a0/` のデータで作った基板は改修が要ります。改修方法はリポジトリ直下の README の「既知の問題」を参照してください

## 同梱していないもの

- JLCPCB 内部の CAM 出力（ダウンロードの `ok/` フォルダ。注文番号付きのアーカイブと層ごとの中間ファイル）
- 解析用 JSON（`4te.json` など。JLCPCB 社内のパスや期限付き URL を含む）

---

# JLCPCB manufacturing data

The top level of this folder holds the **Rev A1** manufacturing data (2026-10-10; SW1 pad assignment fixed to match the schematic): the kicad-cli output from `../out/` (`uv run tools/make_outputs.py`), stored as-is. **A1 has not been manufactured yet.** The files actually used for the A0 order are kept in `a0/`.

- `gerbers/`: the 16 Gerber / drill / `.gbrjob` files for A1 (KiCad 10.0.3 kicad-cli export). The six oval slots use KiCad's "route command" encoding (`G00`/`M15`/`G01`/`M16`); the drill files are identical to the A0 production files except for the dates.
- `bom-jlcpcb.csv` / `cpl-jlcpcb.csv`: JLCPCB-format BOM (19 lines) and CPL (68 SMD parts), identical to the A0 files (no part or placement changes).
- A1 differs from A0 only around SW1: two pad nets swapped (pad1 = 3.3 V, pad2 = VREF), the VREF trace re-routed to pad2, the L3 3.3 V plane refilled, silkscreen "RP2040 LA A1" and "CERN-OHL-P v2" on the back. Hole count and sizes are unchanged.
- `a0/`: the data used for the A0 order (2026-09-26): Gerbers downloaded from the JLCPCB order page (KiCad 10.0.3 GUI export, 2026-09-21 22:40 JST), the BOM / CPL as uploaded, and JLCPCB's preview renders. In the A0 order the USB-C connector (J1) was excluded from assembly because the part was unavailable. The A0 PCB wires SW1's common incorrectly (the common is pin 2); boards made from `a0/` need the rework described under "Known issues" in the top-level README.
- Not included: JLCPCB's internal CAM output and analysis JSON files.
