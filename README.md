# RP2040 16ch ロジックアナライザ基板

RP2040 と TI の TXU0104（レベル変換 ×4）で作った、**16ch のロジックアナライザ基板**です。1.8V〜5V のロジックをそのまま受け、[sigrok-pico](https://github.com/pico-coder/sigrok-pico) のファームを書くと **PulseView（sigrok）から I2C・SPI・UART をデコード**できます。4 層・65 × 45mm で、部品実装は JLCPCB の PCBA に任せています。

![A0 基板（部品をすべて実装した状態）](docs/images/board-a0.jpg)

| 項目 | 内容 |
|:---|:---|
| ch 数 | 16ch（GP0〜GP15） |
| 入力 | 1.8V〜5V のロジック（最大 5.5V）。TXU0104 のシュミット入力・内蔵プルダウン |
| しきい値の基準 | VREF をスライドスイッチ SW1 で選ぶ（3.3V／EXT／5V） |
| ファーム | sigrok-pico `pico_dig26.uf2`（PulseView nightly の `raspberrypi-pico` ドライバ） |
| 基板 | 4 層（L1 信号／L2 GND／L3 電源／L4 信号）・65 × 45mm・1.6mm |
| 製造 | JLCPCB（PCB＋Economic PCBA） |

---

## 状態（2026-10-10）

- **A0 基板の検証は第3回（実戦投入）で一区切りです。** 第2回で立ち上げ（3.3V レール 3.303V・水晶 12MHz・RP2040 内蔵 LDO 1.096V・PulseView で I2C をデコード）、第3回でしきい値・サンプリング上限・時間窓を実測し、SPI／UART／サーボ PWM をデコードしました。第3回の実測値（A0・SW1 改修済み・`pico_dig26.uf2`）:
  - **1.8V ロジックは EXT で読めます。** VREF = 1.806V（EXT）で VT+ 1.399V／VT− 0.732V。雑音を抑えた入力で測り直した 3.3V 位置は VT+ 2.401V／VT− 1.395V、5V 位置は VT+ 3.290V／VT− 2.138V（0.05V 刻みの掃引）。VT+ は TXU0104 データシートの近い VCCA 行の上限より高めで、原因は未特定です
  - **サンプリングレートの上限は 120MS/s です。** PulseView の一覧には 150M〜240M も出ますが、選ぶと取り込みに失敗します。12MHz・24MHz の矩形波は 120／60MS/s で正しく読め、20MS/s では 12MHz が 8MHz に化けます（エイリアス）
  - **16ch・120MS/s で一度に取れるのは 10 万サンプル（約 0.84ms）までです。** それ以上を指定すると、エラーなしで約 0.45ms に打ち切られます
  - SPI（74HC595 への 1 バイト・shiftOut とハードウェア SPI 1MHz）、UART（115200／9600bps）、サーボ PWM（50Hz・パルス幅 0.5〜2.4ms）を PulseView のデコーダで読めました
- **次版 A1 の基板データを作りました（2026-10-10）。** SW1 の pad1／pad2 のネットを回路図に合わせて入れ替え（pad1 = 3.3V・pad2 = VREF）、VREF の配線を pad2 へ引き直したものです。DRC エラー 0・未配線 0、基板と回路図のネット照合は 88 ネットすべて一致。`hardware/jlcpcb/` の製造データは A1 に更新してあります。**A1 はまだ製造していません。** 手元で検証した基板は A0 を改修したものです

### 既知の問題（A0）：SW1 のコモンはピン 2（A1 で修正済み）

筆者が注文した A0 の基板にあった問題です。VREF 切替スイッチ SW1（SK13D07VG5・C393948）のコモンは**ピン 2**（孤立したピン 1 の隣）ですが、A0 の基板は pad1 をコモン（VREF）として配線していました。改修前の A0 では、

- 「5V」位置で LDO の 3.3V 出力と USB の 5V が直結します
- 「EXT」位置で J3 に 3.3V が出ます

A0 の基板は、改修を済ませるまで **SW1 を 1 番目の位置（3.3V）から動かさないでください**。

**A0 の基板を使う場合の改修方法（部品側）**: pad2（3.3V）は内層の電源プレーンに直結でパターンを切れないため、スイッチのピン 1 とピン 2 を基板の穴から切り離し、**スイッチのピン 2（コモン）→ pad1（VREF）、スイッチのピン 1 → pad2（3.3V）**をジャンパ線で交差させます。改修後の VREF は「3.3V」3.303V／「EXT」0V（J3 未接続）／「5V」4.895V でした。改修の手順と写真は[第2回の記事](https://electwork.net/posts/jlcpcb-rp2040-logic-analyzer-02-bringup-first-i2c-decode/)にあります。

回路図と自作シンボル（`lib/logicana.kicad_sym`）は 2026-10-04 に、**PCB と製造データは A1（2026-10-10）で訂正済み**です（[SPEC.md §17](SPEC.md)）。A1 は pad1 = 3.3V・pad2 = VREF（コモン）で、改修なしで「3.3V／EXT／5V」の 3 位置が正しく切り替わります。A1 の基板はまだ製造していません。

---

## 製造データ

| 置き場所 | 中身 | 扱い |
|:---|:---|:---|
| **[hardware/jlcpcb/](hardware/jlcpcb/)** | **A1** の製造データ（Gerber 16 ファイル・BOM・CPL）。`hardware/out/` の kicad-cli 出力をそのまま置いたもの | **発注に使う正規データ**。**A1 はまだ製造していません**（筆者はこのデータでの発注を行っていません） |
| [hardware/out/](hardware/out/) | KiCad（kicad-cli）から出力した現行（A1）の Gerber・ドリル・BOM（`bom-jlcpcb.csv`）・CPL（`cpl-jlcpcb.csv`）・DRC・照合表 | 設計側の出力。`uv run tools/make_outputs.py` で再生成 |
| [hardware/out/a1/](hardware/out/a1/) | A1 の出力一式のスナップショット（Gerber zip・BOM・CPL・DRC・照合表・レンダ）と、A0 → A1 の修正スクリプト `apply_sw1_fix.py`・検算スクリプト | 記録 |

- **A1 と A0 の違いは SW1 まわりだけ**です。SW1 の pad1／pad2 のネットの入れ替え（pad1 = 3.3V・pad2 = VREF）、VREF の配線（表面 0.5mm）を pad1 から pad2 へ引き直し、内層 L3 の 3.3V プレーンの再充填、表シルク「RP2040 LA A1」、裏シルクに「CERN-OHL-P v2」。部品・配置・ほかの配線・穴（数と径）・BOM・CPL は A0 と同じです
- A0 の発注では、**USB-C（J1）は注文時に部品が入手できなかったため、実装から外して手はんだ**にしました。BOM / CPL のファイルには J1（C165948）が入ったままで、注文画面の部品照合で実装から外しています。A1 の BOM / CPL は A0 と同一で、J1 も入ったままです（在庫があれば実装に含めて構いません）
- SW1 とピンヘッダ J2・J3 は THT 部品なので、設計段階から手はんだの予定です

---

## JLCPCB で発注する手順

A1 の基板は、`hardware/jlcpcb/` の製造データでそのまま発注できます。以下は A0 の注文（2026 年 9 月）で実際に選んだ項目で、A1 でも同じです（A1 のデータでの発注は、筆者はまだ行っていません）。JLCPCB の画面の項目名や並びは更新で変わることがあるので、見当たらないときは同じ意味の項目を探してください。発注の流れの一般的な説明は[第1回の記事](https://electwork.net/posts/jlcpcb-rp2040-logic-analyzer-01-design-and-order/)に、この基板での選び方は[第3回の記事](https://electwork.net/posts/jlcpcb-rp2040-logic-analyzer-03-field-test/)にもあります。

> [!NOTE]
> **`hardware/jlcpcb/` は A1（SW1 の配線を直したデータ）です。** A0 からの変更は SW1 まわり（2 パッドのネットと VREF の配線 1 本）だけで、A1 の基板はスイッチの改修なしで使えますが、**A1 の実機はまだありません**。

### 手順

1. **Gerber を zip にしてアップロード**: `hardware/jlcpcb/gerbers/` の 16 ファイルを 1 つの zip にまとめ（`hardware/out/rp2040-logic-analyzer-gerbers.zip` が同じ内容の zip です）、注文ページでアップロードします。層数 4・外形 65 × 45mm と読み取られれば、外形とドリルまで入っています
2. **基板の仕様を選ぶ**: 下の表の項目が設計の前提に関わります。それ以外（表面処理・レジスト色など）は好みで構いません（A0 は HASL・緑）

   | 項目 | 選ぶ値 | 理由 |
   |:---|:---|:---|
   | 層数 | 4（自動認識） | 4 層設計 |
   | 板厚 | 1.6mm | スタックアップの前提 |
   | スタックアップ（インピーダンス制御の層構成） | **JLC04161H-7628** | USB 差動ペアの線幅 0.30mm／間隔 0.15mm はこの層構成で計算しています |
   | 最小ビア（穴径／外径） | **0.3mm/(0.4/0.45mm)** | 設計のビアは穴 0.30mm・外径 0.45mm |
   | 枚数 | 5 | A0 と同じ。段取り費が固定なので 2 枚と 5 枚の差は小さいです |

3. **PCB Assembly を ON**: **Economic**・実装面 **Top**・枚数 **5**。SMD 部品はすべて表面なので、片面実装で足ります
4. **BOM と CPL をアップロード**: `hardware/jlcpcb/bom-jlcpcb.csv`（19 行・全行に JLCPCB 部品番号入り）と `hardware/jlcpcb/cpl-jlcpcb.csv`（SMD 68 部品の座標・回転・面）
5. **部品の照合**: 19 行がすべて JLCPCB の部品に当たり、在庫があるかを見ます
   - 区分は Basic 12 種・Extended 6 種（RP2040・TXU0104・USB-C・USBLC6・水晶 ABM8-272-T3・27Ω）。Economic PCBA では Extended 1 種類ごとに段取り費がかかります
   - **在庫切れの行は、実装から外して手はんだに回します。** A0 の注文では USB-C（J1・C165948）が在庫切れで、この方法にしました。在庫があれば、そのまま実装に含めて構いません
   - 汎用の抵抗・コンデンサが在庫切れなら、同じ値・同じサイズ（0402／0805）の Basic 品に差し替えます
   - SW1（C393948）は BOM にありますが CPL にはなく（THT・手はんだの予定）、JLCPCB 側では未実装扱いになります
6. **配置プレビューで向きを確認**: CPL の回転が合っているかは、ここで目で確かめます。見るところは RP2040（U1）の 1 番ピン、TXU0104（U3〜U6）、SOT-223 の LDO（U7）のタブ、USB-C（J1）、LED（D1〜D3）の極性です。ずれていれば、その画面で回転を直します（CPL の回転補正の記録は `hardware/out/cpl-rotation-report.md`）
7. **カートへ**: 配送方法を選んで注文します。A0 は DHL Express で、注文確定から 5 日で届きました

### 届いたら手はんだする部品

| 部品 | 種類 | 備考 |
|:---|:---|:---|
| J1 USB-C（TYPE-C-31-M-12・C165948） | SMD・0.5mm ピッチ | PCBA で在庫がなく外した場合だけ |
| SW1 スライドスイッチ（SK13D07VG5・C393948） | THT・ライトアングル | JLCPCB では実装されないので別に用意する。A1 の基板は改修不要。A0 の基板は取り付けと同時に上の改修をする |
| J2 2×16 ピンヘッダ（2.54mm） | THT | プローブ入力。BOM に含めていないので別に用意する |
| J3 1×3 ピンヘッダ（2.54mm） | THT | 外部 VREF（EXT）。同上 |

手はんだが終わったら、下の「ファーム」の手順で `pico_dig26.uf2` を書き込みます。

### 費用の目安

A0（5 枚・USB-C 実装なし）の実際の注文額は、製品代 $73.10（PCB＋Economic PCBA・1 枚あたり $14.62）＋送料 $17.04（DHL Express）＝ **$90.14**（2026 年 9 月）でした。部品の価格と在庫、Extended の種類数、配送方法で変わります。手はんだ用の SW1・ピンヘッダは別にかかります。

---

## ファーム

1. sigrok-pico の [release フォルダ](https://github.com/pico-coder/sigrok-pico/tree/main/pico_sdk_sigrok/release)から **`pico_dig26.uf2`** を取得する
2. BOOT ボタン（SW2）を押しながら USB を挿す（またはリセットする）と、PC に RPI-RP2 ドライブが現れる。フラッシュが空なら自動でこの状態になる
3. `pico_dig26.uf2` を RPI-RP2 ドライブにコピーする → COM ポート（VID 2E8A / PID 000A）が現れる

- **`pico_baseline.uf2` は書かないでください。** GP0 を UART の送信ピンとして出力にするため、CH0 の TXU0104 の出力とぶつかります（[SPEC.md §2.3](SPEC.md)）
- PulseView は**リリース版 0.4.2 では使えません**（`raspberrypi-pico` ドライバが未収録）。[sigrok Downloads](https://sigrok.org/wiki/Downloads) から nightly 版を入れ、Connect to Device でドライバ **RaspberryPI PICO (raspberrypi-pico)** と COM ポートを選んでスキャンします
- **PulseView のチャンネル名は D2 から始まります。** 基板の **CH n は PulseView の D(n+2)**（CH0 = D2、CH15 = D17）です（sigrok-pico release の README にある PulseView 側の仕様）

---

## 使い方（最小）

### VREF の選び方

TXU0104 の入力しきい値は、入力側電源 VREF（VCCA）に応じて変わります。**測る相手の電源電圧に VREF を合わせます。**

| 測る相手 | SW1 | 備考 |
|:---|:---|:---|
| 3.3V ロジック | 3.3V | 基板内の LDO 出力 |
| 5V ロジック | 5V | USB の VBUS |
| 1.8V などそれ以外 | EXT | J3 に相手の電源電圧を入れる。**VREF 3.3V のままでは 1.8V ロジックの High を安定して読めません** |

- **J3（外部 VREF）を外してから SW1 を切り替えてください。** SW1 は shorting 型で、切り替えの途中で外部電源と内蔵電源が一瞬つながります
- EXT 位置で J3 に何もつないでいないと、**全 ch が反応しません**（VREF = 0V で TXU0104 の出力が Hi-Z）。VREF の LED（D2）が消えていれば、この状態です

### プローブヘッダ J2

2×16 ピン（2.54mm）。**内側 1 列が CH0〜CH15、外側 1 列はすべて GND** です。1ch ごとに隣の GND を使えます。

### 注意

- プローブ入力と EXT は **0〜5.5V** まで。過電圧・負電圧の保護回路はありません（直列 100Ω のみ）
- しきい値付近の信号は、入力の雑音がヒステリシスを超えるとトグルします。配線を短くし、GND をしっかり取ってください

---

## ディレクトリ構成

```
README.md            この文書
SPEC.md              仕様書（ファーム選定・IC 選定・入力回路・ピン割り当て・BOM・実機チェックリスト・改版メモ）
KICAD-KIT.md         KiCad の作業メモ（ライブラリ・BOM/CPL の出し方・4 層の DRC とスタックアップ・回路図チェックリスト）
docs/images/         README 用の写真
hardware/            KiCad 10 プロジェクト
  rp2040-logic-analyzer.kicad_pro / .kicad_sch / .kicad_pcb
  sym-lib-table / fp-lib-table      logicana / lcsc の登録（${KIPRJMOD}/../lib/...）
  out/                              kicad-cli の出力（schematic.pdf・Gerber・BOM / CPL・DRC・照合表・review/）と、配線作業で使った補助スクリプト（*.py）
    a1/                             A1 の出力のスナップショットと A0 → A1 の修正スクリプト（apply_sw1_fix.py）・プレーンの検算（check_sw1_plane.py）
  jlcpcb/                           A1 の製造データ（Gerber・BOM・CPL・未製造）
tools/
  gen_schematic.py   回路図の生成スクリプト（Python 3.12・標準ライブラリのみ）
  verify_netlist.py  kicad-cli のネットリストを期待表と照合
  verify_pcb_netlist.py
                     基板の全パッドのネットを回路図のネットリストと照合（→ hardware/out/pcb-netlist-check.md）
  check_kit5.py      回路図チェックリストをネットリストから機械検査
  gen_pcb.py         配置済み・未配線の基板を生成（配線は freerouting と手作業）
  fanout_planes.py / route_pcb.py / finish_pcb.py
                     GND・3V3 のファンアウト／freerouting の自動配線／ベタとビアスティッチの仕上げ（KiCad 同梱の python で実行）
  make_outputs.py    配線済み基板から製造データ（Gerber zip・BOM・CPL・DRC）とレビュー用画像を出力
  uno-r4-clock/      Arduino UNO R4 WiFi の GPT で 12／16／24／1MHz の矩形波を D6 に出すスケッチ（サンプリング上限テストの信号源。README あり）
  uno-r4-spi-uart/   UNO R4 WiFi から 74HC595 へ SPI（shiftOut／ハードウェア SPI 1MHz）を送り、同時に Serial1 から UART を出すスケッチ（第3回の SPI／UART 測定用）
  uno-r4-servo/      UNO R4 WiFi の D9 からサーボ PWM（0°→90°→180° を 2 秒ごと）を出すスケッチ（第3回のサーボ測定用）
lib/
  logicana.kicad_sym 自作シンボル 4 個（TXU0104PWR / SW_SP3T_SK13D07VG5 / SW_Push_TS1187A / VREF）
  lcsc/              LCSC 由来のライブラリ（リポジトリに含めない・下記で各自生成）
```

回路図は [hardware/out/schematic.pdf](hardware/out/schematic.pdf)（A3・1 ページ）で見られます。

---

## 回路図の再現手順

回路図は手描きではなく `tools/gen_schematic.py` の出力です。部品の位置・結線・ネット名はすべてスクリプトに書いてあり、再実行すると同じファイルになります（UUID は固定名前空間の uuid5）。前提は `uv`（cpython 3.12）と KiCad 10（`kicad-cli`）。

```
uv run tools/gen_schematic.py                # hardware/ に .kicad_sch / .kicad_pro / sym-lib-table / fp-lib-table を出力
uv run tools/gen_schematic.py --check        # 既存出力と一致するか（冪等性の確認）
uv run tools/gen_schematic.py --selftest     # 回転ごとのピン位置を kicad-cli のネットリストで実測
kicad-cli sch erc --severity-all --format report -o hardware/out/erc.rpt hardware/rp2040-logic-analyzer.kicad_sch
uv run tools/verify_netlist.py               # → hardware/out/netlist-check.md
uv run tools/check_kit5.py                   # → hardware/out/kit5-check.md
uv run tools/verify_pcb_netlist.py           # → hardware/out/pcb-netlist-check.md（基板の全パッド ↔ 回路図のネット）
kicad-cli sch export pdf -o hardware/out/schematic.pdf hardware/rp2040-logic-analyzer.kicad_sch
uv run tools/make_outputs.py                 # → hardware/out/（DRC・Gerber zip・BOM・CPL・照合表・レンダ）
```

KiCad 標準ライブラリと `lib/logicana.kicad_sym` からシンボルを読み、`extends` を平坦化して `lib_symbols` に埋め込みます。結線はピン端のスタブ＋ローカルラベル、電源レールは電源シンボルです。ネットが変わる変更はスクリプト側に入れて再生成します。

### LCSC 由来のライブラリ（clone した人がやること）

`lib/lcsc/` はリポジトリに含めていません（LCSC / EasyEDA 由来で、再配布できるライセンスか確認できなかったため）。次のコマンドで各自の環境に生成し、KiCad 10 の形式に上げます。

```
py -m pip install --user easyeda2kicad
py -m easyeda2kicad --full --project-relative --lcsc_id C318884 --output <repo>/lib/lcsc/lcsc --overwrite
py -m easyeda2kicad --full --project-relative --lcsc_id C393948 --output <repo>/lib/lcsc/lcsc --overwrite
py -m easyeda2kicad --full --project-relative --lcsc_id C2286   --output <repo>/lib/lcsc/lcsc --overwrite
py -m easyeda2kicad --full --project-relative --lcsc_id C165948 --output <repo>/lib/lcsc/lcsc --overwrite
kicad-cli fp  upgrade <repo>/lib/lcsc/lcsc.pretty
kicad-cli sym upgrade <repo>/lib/lcsc/lcsc.kicad_sym
```

| LCSC | 部品 | 用途 |
|:---|:---|:---|
| C318884 | タクトスイッチ | SW2 / SW3 のフットプリント（必須） |
| C393948 | スライドスイッチ SK13D07VG5 | SW1 のフットプリント（必須） |
| C2286 | LED 赤 0603 | 照合用（任意・標準の `LED_SMD:LED_0603_1608Metric` を使う） |
| C165948 | USB-C 16P | 照合用（任意・標準の `Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12` を使う） |

---

## 記事（electwork.net）

- 第1回 設計と発注: https://electwork.net/posts/jlcpcb-rp2040-logic-analyzer-01-design-and-order/
- 第2回 立ち上げ: https://electwork.net/posts/jlcpcb-rp2040-logic-analyzer-02-bringup-first-i2c-decode/
- 第3回 実戦投入（しきい値・サンプリング上限・時間窓の実測、SPI／UART／サーボのデコード、発注の手順）: https://electwork.net/posts/jlcpcb-rp2040-logic-analyzer-03-field-test/

---

## 提供

この基板の製造と部品実装は、JLCPCB の提供を受けています（PR）。JLCPCB: https://jlcpcb.com/jp?from=RamTuckeyPCB

---

## ライセンス

| 対象 | ライセンス |
|:---|:---|
| **ハードウェア設計データ** — `hardware/`（KiCad プロジェクト・製造データ・`out/` の出力）・`lib/logicana.kicad_sym`・`SPEC.md`・`KICAD-KIT.md` | **CERN-OHL-P-2.0**（[LICENSE](LICENSE)）。寛容型（permissive）で、改変版や製品に同じライセンスでの公開義務はありません |
| **ソフトウェア** — `tools/` の Python スクリプトと Arduino スケッチ、`hardware/out/` の Python スクリプト | **MIT**（[LICENSE-MIT](LICENSE-MIT)） |
| 記事（electwork.net）の文章・画像、`docs/images/` の写真 | 上記の対象外（All rights reserved） |

SPDX 識別子: ハードウェア `CERN-OHL-P-2.0`／ソフトウェア `MIT`。

ハードウェア設計データの表示（CERN-OHL-P-2.0 の Notice）:

> Copyright 2026 ramtuc (electwork.net).
> This source describes Open Hardware and is licensed under the CERN-OHL-P v2.
> You may redistribute and modify this documentation and make products using it under the terms of the CERN-OHL-P v2 (https://ohwr.org/cern_ohl_p_v2.txt). This documentation is distributed WITHOUT ANY EXPRESS OR IMPLIED WARRANTY, INCLUDING OF MERCHANTABILITY, SATISFACTORY QUALITY AND FITNESS FOR A PARTICULAR PURPOSE. Please see the CERN-OHL-P v2 for applicable conditions.
> Source Location: https://github.com/ramtuc/rp2040-logic-analyzer

### 第三者のもの

| 対象 | ライセンス・扱い |
|:---|:---|
| ファーム（sigrok-pico） | GPL-3.0。別のプロジェクトで、このリポジトリには含めていません |
| LCSC / EasyEDA 由来のライブラリ（`lib/lcsc/` など） | 同梱しません（`.gitignore` で除外。上の手順で各自生成） |
| KiCad 標準ライブラリ | 同梱しません |
| [gusmanb/logicanalyzer](https://github.com/gusmanb/logicanalyzer)（GPL-3.0） | 回路図・レイアウトは流用していません。TXU0104 採用という部品選定の事実のみ参考にしました |

---

## English summary

A 16-channel logic analyzer board based on the Raspberry Pi RP2040 and four TI TXU0104 level translators. It accepts 1.8 V to 5 V logic (max 5.5 V) with a selectable reference voltage (VREF: 3.3 V / external / 5 V via slide switch SW1), and works with PulseView (sigrok) through the [sigrok-pico](https://github.com/pico-coder/sigrok-pico) firmware `pico_dig26.uf2` (requires a PulseView nightly build; channel CH n appears as D(n+2) in PulseView). 4-layer, 65 x 45 mm, assembled by JLCPCB PCBA.

- **Status (2026-10-10):** Rev A0 is verified through Part 3 of the article series. Measured on A0 (SW1 reworked, `pico_dig26.uf2`): 1.8 V logic is readable with VREF = EXT (VT+ 1.399 V / VT− 0.732 V at VREF 1.806 V); with a low-noise input the 3.3 V position reads VT+ 2.401 V / VT− 1.395 V and the 5 V position VT+ 3.290 V / VT− 2.138 V (VT+ came out above the upper limit of the nearest TXU0104 datasheet row; cause not identified). The usable sample-rate ceiling is 120 MS/s (150 MS/s and above fail to capture); 12 MHz and 24 MHz square waves are read correctly at 120 and 60 MS/s, and 12 MHz aliases to 8 MHz at 20 MS/s. With 16 channels at 120 MS/s a single capture holds up to 100k samples (about 0.84 ms); larger settings are silently cut to about 0.45 ms. SPI (74HC595), UART (115200 / 9600 bps) and servo PWM (50 Hz, 0.5–2.4 ms) were decoded in PulseView. **Rev A1 board data (2026-10-10)** fixes the SW1 pad assignment (pad1 = 3.3 V, pad2 = VREF/common, VREF trace re-routed to pad2) with DRC 0 errors / 0 unconnected and a full PCB-vs-schematic net match (88/88 nets). **A1 has not been manufactured yet.**
- **Known issue (A0):** The common pin of SW1 (SK13D07VG5) is pin 2, not pin 1. The A0 PCB routes it incorrectly; A0 boards need a jumper rework on the switch side (switch pin 2 → pad1/VREF, switch pin 1 → pad2/3.3V). The schematic and symbol were corrected on 2026-10-04 and the PCB in Rev A1 (2026-10-10); A1 boards need no rework. **On an A0 board, until the rework is done, keep SW1 in position 1 (3.3 V): position 3 (5 V) shorts the 3.3 V LDO output to USB 5 V, and position 2 (EXT) puts 3.3 V on J3.**
- **Manufacturing data:** `hardware/jlcpcb/` holds the Rev A1 files (16 Gerber/drill files, BOM, CPL; kicad-cli output, not yet ordered by the author). `hardware/out/` contains the current KiCad outputs. A1 differs from A0 only around SW1 (two pad nets, one VREF trace, the L3 3.3 V plane refill, silkscreen "A1" and a "CERN-OHL-P v2" mark on the back); parts, placement, holes, BOM and CPL are identical. The BOM/CPL files still contain the USB-C connector J1 (C165948); for the A0 order it was deselected at the parts-matching step because it was out of stock, and hand-soldered.
- **Ordering from JLCPCB** (the choices actually made for the A0 order, September 2026; UI labels may change):
  1. Zip the 16 files in `hardware/jlcpcb/gerbers/` and upload them. The board should be recognized as 4 layers, 65 x 45 mm.
  2. PCB options: 4 layers, 1.6 mm, stackup **JLC04161H-7628** (the USB pair 0.30 / 0.15 mm was calculated for it), minimum via **0.3 mm/(0.4/0.45 mm)**, quantity 5. Surface finish and color do not affect the design (A0: HASL, green).
  3. PCB Assembly: **Economic**, **Top** side, 5 boards.
  4. Upload `bom-jlcpcb.csv` (19 lines, all with JLCPCB part numbers) and `cpl-jlcpcb.csv` (68 SMD parts).
  5. Parts matching: 12 Basic and 6 Extended types (RP2040, TXU0104, USB-C, USBLC6, crystal ABM8-272-T3, 27 Ω); each Extended type adds a feeder fee. If a line is out of stock, deselect it and hand-solder it (this is what happened to J1 for A0); replace generic R/C with a Basic part of the same value and size. SW1 is in the BOM but has no CPL entry (THT), so JLCPCB treats it as not assembled.
  6. Check orientation in the placement preview: U1 pin 1, U3–U6, the U7 (SOT-223) tab, J1 and LED polarity. Fix rotation there if needed.
  7. Choose shipping and order. A0: DHL Express, delivered 5 days after order confirmation. Actual A0 cost: $73.10 for 5 boards (PCB + Economic PCBA, USB-C not assembled) + $17.04 shipping = $90.14.
  - Hand-soldered parts: SW1 (SK13D07VG5, C393948, THT, buy separately; no rework needed on A1), J2 (2x16 header), J3 (1x3 header), and J1 only if it was not assembled.
- Do not flash `pico_baseline.uf2` (it drives GP0 as UART TX and conflicts with CH0).
- The boards were provided by JLCPCB (sponsored).
- **License:** Hardware design data (`hardware/`, `lib/logicana.kicad_sym`, `SPEC.md`, `KICAD-KIT.md`) is licensed under **CERN-OHL-P-2.0** ([LICENSE](LICENSE)). Software (`tools/` Python scripts and Arduino sketches, Python scripts in `hardware/out/`) is licensed under **MIT** ([LICENSE-MIT](LICENSE-MIT)). The article text and images on electwork.net and the photos in `docs/images/` are not covered by either license. Source location: https://github.com/ramtuc/rp2040-logic-analyzer
- Articles (Japanese): [Part 1](https://electwork.net/posts/jlcpcb-rp2040-logic-analyzer-01-design-and-order/), [Part 2](https://electwork.net/posts/jlcpcb-rp2040-logic-analyzer-02-bringup-first-i2c-decode/), [Part 3](https://electwork.net/posts/jlcpcb-rp2040-logic-analyzer-03-field-test/)
