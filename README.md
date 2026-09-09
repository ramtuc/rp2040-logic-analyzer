# RP2040 16ch ロジックアナライザ基板

**ロジックアナライザを持っていないので、自分で作る。** RP2040 と JLCPCB の PCBA で 16ch のロジックアナライザ基板を起こし、PulseView（sigrok）から使えるところまで持っていくプロジェクト。

- 入力は **1.8V 〜 5V 対応**。TXU0104（Schmitt 入力・内蔵プルダウン）で受けるので、1.8V ロジックも 5V ロジックもそのまま掴める
- ファームは **sigrok-pico を主、μLA を保険**。GP0〜15 に並べたので 3 つのファームが無改造で動く
- 基板は **4 層・16ch・2×16 のプローブヘッダ（内側が信号 / 外側が全部 GND）**

設計・製造・立ち上げの過程は electwork.net で記事にする（全 3 本の予定）。**基板は JLCPCB から提供を受ける**ので、記事には景表法のステマ規制に基づく PR 表記を入れる。**ただし編集権は当方にあり、うまくいかなかった点もそのまま書く。**

---

## 読む順番

| # | ファイル | 中身 |
|--:|:---|:---|
| 1 | **[SPEC.md](SPEC.md)** | **何を作るのか。** ファーム選定・IC 選定・入力フロントエンド・ピン割り当て・レイアウト制約・BOM・費用見積り・実機チェックリスト・記事プラン・決定事項 |
| 2 | **[KICAD-KIT.md](KICAD-KIT.md)** | **どう描き始めるか。** 部品ライブラリの所在表・JLCPCB 向け BOM/CPL の出し方・4 層の DRC とスタックアップ・ネット名とシート構成・回路図チェックリスト |

**先に SPEC.md の §14（決定事項）を読むと速い。** 何がもう決まっていて、何がまだ決まっていないかが 1 画面で分かる。

---

## いまの状態

| 工程 | 状態 |
|:---|:---|
| 仕様の確定 | **完了**（SPEC §14 の 11 項目中、未決はプローブケーブルの商品選定のみ） |
| KiCad の準備 | **完了**（KICAD-KIT.md ＋ `lib/`） |
| 回路図 | **これから**（人間が KiCad 10 で描く） |
| レイアウト | 未着手 |
| 発注 | 未着手（**JLCPCB のクーポン発行前に注文を確定しない**） |

---

## リポジトリの構成

```
SPEC.md              仕様書
KICAD-KIT.md         KiCad 着手キット
lib/
  logicana.kicad_sym TXU0104PWR のシンボル（自作・追跡対象）
  lcsc/              LCSC から取り込んだライブラリ（.gitignore・下記参照）
```

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
| C318884 | タクトスイッチ | SW2 / SW3 のフットプリント（**必須**） |
| C393948 | スライドスイッチ SK13D07VG5 | SW1 のフットプリント（**必須**） |
| C2286 | LED 赤 0603 | 照合用（**任意** — 標準の `LED_SMD:LED_0603_1608Metric` を使う） |
| C165948 | USB-C 16P | 照合用（**任意** — 標準の `Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12` を使う） |

生成したら **KiCad 10 の形式に上げる**（easyeda2kicad が書くのは KiCad 5 時代の形式）。

```
kicad-cli fp  upgrade <repo>/lib/lcsc/lcsc.pretty
kicad-cli sym upgrade <repo>/lib/lcsc/lcsc.kicad_sym
```

登録先とニックネームは [KICAD-KIT.md §1.4](KICAD-KIT.md) を参照。**`lib/logicana.kicad_sym`（TXU0104PWR）はリポジトリに入っているので、生成し直す必要はない。**

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
