# RP2040 16ch ロジックアナライザ基板

**ロジックアナライザを持っていないので、自分で作る。** RP2040 と JLCPCB の PCBA で 16ch のロジックアナライザ基板を起こし、PulseView（sigrok）から使えるところまで持っていくプロジェクト。

- 入力は **1.8V 〜 5V 対応**。TXU0104（Schmitt 入力・内蔵プルダウン）で受けるので、1.8V ロジックも 5V ロジックもそのまま掴める
- ファームは **sigrok-pico を主、μLA を保険**。GP0〜15 に並べたので 3 つのファームが無改造で動く。**書き込むのは `pico_dig26.uf2`。`pico_baseline.uf2` は GP0 を UART TX 出力にして CH0 と衝突するので書かない**（SPEC §2.3）
- 基板は **4 層・16ch・2×16 のプローブヘッダ（内側が信号 / 外側が全部 GND）**

設計・製造・立ち上げの過程は electwork.net で記事にする（全 3 本の予定）。**基板は JLCPCB から提供を受ける**ので、記事には景表法のステマ規制に基づく PR 表記を入れる。**ただし編集権は当方にあり、うまくいかなかった点もそのまま書く。**

---

## 読む順番

| # | ファイル | 中身 |
|--:|:---|:---|
| 1 | **[SPEC.md](SPEC.md)** | **何を作るのか。** ファーム選定・IC 選定・入力フロントエンド・ピン割り当て・レイアウト制約・BOM・費用見積り・実機チェックリスト・記事プラン・決定事項 |
| 2 | **[KICAD-KIT.md](KICAD-KIT.md)** | **どう描き始めるか。** 部品ライブラリの所在表・JLCPCB 向け BOM/CPL の出し方・4 層の DRC とスタックアップ・ネット名とシート構成・回路図チェックリスト |
| 3 | **[hardware/out/schematic.pdf](hardware/out/schematic.pdf)** | **回路図**（A3・1 ページ・kicad-cli 出力）。ソースは `hardware/rp2040-logic-analyzer.kicad_sch`、生成元は `tools/gen_schematic.py`（下記「回路図の再現手順」） |
| 4 | **[hardware/out/](hardware/out/)** | **製造データ一式**（Gerber / ドリルの zip・JLCPCB 向け BOM / CPL・DRC・照合表・レンダ画像）。回路図レビューとその回答は `hardware/out/review/`（`REVIEW.md` / `RESPONSE.md`） |

**先に SPEC.md の §14（決定事項）を読むと速い。** 何がもう決まっていて、何がまだ決まっていないかが 1 画面で分かる。

---

## いまの状態

| 工程 | 状態 |
|:---|:---|
| 仕様の確定 | **完了**（SPEC §14 の 12 項目中、未決はプローブケーブルの商品選定のみ） |
| KiCad の準備 | **完了**（KICAD-KIT.md ＋ `lib/`） |
| 回路図 | **完了**（2026-09-20・TP8/TP9 = SWD・C27 1µF 反映済み・kicad-cli 10.0.3 の ERC = error 0 / warning 0・期待ネット 88/88・KICAD-KIT §5 の 17 項目 PASS）。**回路図レビュー（`hardware/out/review/REVIEW.md`・2026-09-20）を受けて文書のみ更新し、回路は変えていない**（回答: `hardware/out/review/RESPONSE.md`） |
| レイアウト | **配線完了**（2026-09-20・4 層・DRC error 0・未配線 0・commit 9e2cc98） |
| 製造データ | **一式あり**（`hardware/out/`・commit 70e5a8e）: Gerber / ドリルの zip・JLCPCB BOM（19 行・全行 LCSC 付き）・CPL（68 行）・照合表 `bom-cpl-check.md` |
| 発注 | **JLCPCB アップロード待ち**（**クーポン発行前に注文を確定しない**）。届いたら書き込むのは `pico_dig26.uf2`（baseline は不可・SPEC §2.3）、立ち上げ手順は SPEC §11 |

---

## リポジトリの構成

```
SPEC.md              仕様書
KICAD-KIT.md         KiCad 着手キット
hardware/            KiCad 10 プロジェクト（回路図・配線済み PCB・製造データ）
  rp2040-logic-analyzer.kicad_pro   最小プロジェクト（KICAD-KIT §3.3 のネットクラス 5 種入り）
  rp2040-logic-analyzer.kicad_sch   回路図（平面 1 シート A3・生成スクリプトの出力）
  sym-lib-table / fp-lib-table      logicana / lcsc の登録（${KIPRJMOD}/../lib/...）
  out/                              schematic.pdf・Gerber zip・JLCPCB BOM / CPL・DRC・照合表・review/（回路図レビューと回答）
tools/
  gen_schematic.py   回路図の生成スクリプト（Python 3.12・標準ライブラリのみ）
  verify_netlist.py  kicad-cli のネットリストを KICAD-KIT §4.1 の期待表と照合
  check_kit5.py      KICAD-KIT §5 の 15 項目をネットリストから機械検査
lib/
  logicana.kicad_sym 自作シンボル 4 個（TXU0104PWR / SW_SP3T_SK13D07VG5 / SW_Push_TS1187A / VREF・追跡対象）
  lcsc/              LCSC から取り込んだライブラリ（.gitignore・下記参照）
```

---

## 回路図の再現手順

回路図は手描きではなく `tools/gen_schematic.py` の出力。**部品の位置・結線・ネット名はすべてスクリプトに書いてあり、再実行すると同じファイルになる**（UUID は固定名前空間の uuid5）。前提は `uv`（cpython 3.12 を自動で使う）と KiCad 10.0.3（`kicad-cli` は `C:\Program Files\KiCad\10.0\bin\kicad-cli.exe`）。

```
cd <repo>
uv run tools/gen_schematic.py                # hardware/ に .kicad_sch / .kicad_pro / sym-lib-table / fp-lib-table を出力
uv run tools/gen_schematic.py --check        # 既存出力と一致するか（冪等性の確認）
uv run tools/gen_schematic.py --selftest     # R と電源シンボルを 0/90/180/270° で置き、ピン位置を kicad-cli のネットリストで実測 → PASS 10/10
kicad-cli sch erc --severity-all --format report -o hardware/out/erc.rpt hardware/rp2040-logic-analyzer.kicad_sch
uv run tools/verify_netlist.py               # → hardware/out/netlist-check.md（KICAD-KIT §4.1 の期待表と照合。第 1 版 de18d95 は 86 OK / NG 0。TP8/TP9 反映後は 88 本）
uv run tools/check_kit5.py                   # → hardware/out/kit5-check.md（KICAD-KIT §5 の 15 項目。第 1 版は PASS 15 / FAIL 0 / 要決定 1（SWD）→ TP8/TP9・C27 反映後は要決定 0）
kicad-cli sch export pdf -o hardware/out/schematic.pdf hardware/rp2040-logic-analyzer.kicad_sch
kicad-cli sch export bom --fields "Reference,Value,Footprint,LCSC Part #,QUANTITY,DNP" --labels "Designator,Comment,Footprint,LCSC Part #,Qty,DNP" --group-by "Value,Footprint,LCSC Part #,DNP" -o hardware/out/bom-grouped.csv hardware/rp2040-logic-analyzer.kicad_sch
```

生成の要点: KiCad 標準ライブラリと `lib/logicana.kicad_sym` からシンボルを読み、`extends` を KiCad の Flatten と同じ規則で平坦化して `lib_symbols` に埋め込む（ERC の lib_symbol_issues = 0 が「ライブラリと一致」の判定）。結線はピン端のスタブ＋ローカルラベル（KICAD-KIT §4.1 の名前そのまま）、電源レールは電源シンボル。**部品を GUI で動かしても接続はラベルで決まるので変わらない。** ネットが変わる変更（TP8/TP9・C27 など）はスクリプト側に入れて再生成する。

---

## ライブラリの取り込み（clone した人がやること）

**`lib/lcsc/` はリポジトリに入っていない。** 中身が LCSC / EasyEDA 由来で、再配布できるライセンスかどうかを確認できなかったため。次のコマンドで各自の環境に生成する。

```
py -m pip install --user easyeda2kicad

py -m easyeda2kicad --full --project-relative --lcsc_id C318884 --output <repo>/lib/lcsc/lcsc --overwrite
py -m easyeda2kicad --full --project-relative --lcsc_id C393948 --output <repo>/lib/lcsc/lcsc --overwrite
py -m easyeda2kicad --full --project-relative --lcsc_id C2286   --output <repo>/lib/lcsc/lcsc --overwrite
py -m easyeda2kicad --full --project-relative --lcsc_id C165948 --output <repo>/lib/lcsc/lcsc --overwrite
```

| LCSC | 部品 | 何に要るか |
|:---|:---|:---|
| C318884 | タクトスイッチ | SW2 / SW3 のフットプリント（**必須**。シンボルは `logicana:SW_Push_TS1187A` を使う） |
| C393948 | スライドスイッチ SK13D07VG5 | SW1 のフットプリント（**必須**。シンボルは `logicana:SW_SP3T_SK13D07VG5` を使う） |
| C2286 | LED 赤 0603 | 照合用（**任意** — 標準の `LED_SMD:LED_0603_1608Metric` を使う） |
| C165948 | USB-C 16P | 照合用（**任意** — 標準の `Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12` を使う） |

生成したら **KiCad 10 の形式に上げる**（easyeda2kicad が書くのは KiCad 5 時代の形式）。

```
kicad-cli fp  upgrade <repo>/lib/lcsc/lcsc.pretty
kicad-cli sym upgrade <repo>/lib/lcsc/lcsc.kicad_sym
```

登録は `hardware/sym-lib-table` / `hardware/fp-lib-table` に入っている（`${KIPRJMOD}/../lib/...`・[KICAD-KIT.md §1.4](KICAD-KIT.md)）ので、生成したらそのまま `hardware/rp2040-logic-analyzer.kicad_pro` を開けば通る。**`lib/logicana.kicad_sym`（TXU0104PWR・スイッチ 2 種・VREF の自作シンボル 4 個）はリポジトリに入っているので、生成し直す必要はない。**

---

## ライセンス

**この 2 つは別物なので混ぜないこと。**

| 対象 | ライセンス |
|:---|:---|
| **この基板の設計データ**（回路図・レイアウト・Gerber・BOM・CPL・`lib/logicana.kicad_sym`・SPEC.md・KICAD-KIT.md） | **CERN-OHL-P-2.0** |
| **ファームウェア**（sigrok-pico） | **GPL-3.0** — 別のプロジェクト。ここには含まれない。UF2 を焼いて使うだけなら基板設計に義務は及ばないが、**改変して配布するならソースを GPL-3.0 で公開する必要がある** |

**CERN-OHL-P**（permissive）を選んだのは、読者が追体験して部分流用できることが企画の柱だから。改変版に同じライセンスでの公開義務が及ばない。

**この選択には前提条件がある。** ハードウェアが一番よくできている [gusmanb/logicanalyzer](https://github.com/gusmanb/logicanalyzer) は **KiCad ファイルを含めて GPL-3.0** なので、**回路図もレイアウトも流用していない**。参考にしたのは「TXU0104 を 6 個載せて 100Msps で出荷している」という部品選定の事実だけで、回路は TI のデータシートから自分で起こしている（SPEC §15 / §16）。流用していたら permissive では出せなかった。

その他の出典:

| 対象 | ライセンス | 扱い |
|:---|:---|:---|
| KiCad 標準ライブラリ | CC-BY-SA 4.0 ＋ 例外条項 | 設計に使うのは自由。**ライブラリ自体は再配布しない**（コピーを同梱していない） |
| Hardware design with RP2040（文書） | CC BY-ND 4.0 | **引用は可、改変版の再配布は不可。** 図は自分で描く |
| easyeda2kicad.py | AGPL-3.0 | ツールとして実行するだけ |
