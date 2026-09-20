# 回路図レビュー（2026-09-20）への回答

対象: [REVIEW.md](REVIEW.md)（回路図レビュー・2026-09-20）。4 点すべてを一次ソースで再検証し、**回路図・PCB・BOM・生成ツールは変更しない**と決めた（人間決定・2026-09-20）。反映先は文書（SPEC.md・KICAD-KIT.md・README.md）のみ。回答日 2026-09-20。

| # | 指摘 | 検証した一次（取得日 2026-09-20） | 判断 | 反映先 |
|--:|:---|:---|:---|:---|
| 1 | **`pico_baseline` と CH0 が出力衝突する**（優先度高） | `pico_sdk_sigrok/sr_device.h`（main）: baseline = `PICO_MODE 0` → `GPIO_D_MASK 0x7FFFFC`（GP2〜22）・**`UART_EN 1`**。dig26 = `PICO_MODE 1` → `0x1C7FFFFF`（GP0〜22 ＋ 26〜28）・`UART_EN 0`。`pico_sdk_sigrok.c` `main()`: `#if (UART_EN == 1)` で `uart_init(uart0, 115200)`・`gpio_set_function(0, GPIO_FUNC_UART)`・`gpio_set_function(1, GPIO_FUNC_UART)`。同ファイルは baseline / dig26 とも GP23 を SIO 出力 High に駆動（OE = 有効で一致）。配布 `release/pico_baseline.uf2` のフラッシュイメージに `Uart Char %d` / `UART OVRFLW` の文字列あり（`UART_EN 1` ビルドの傍証）。`release/pico_dig26.uf2` SHA-256 `3a10298a00f21d74bd963b95baa381e238212a863fd4645908a676c21647f953`（100,352 B）。https://github.com/pico-coder/sigrok-pico/blob/main/pico_sdk_sigrok/sr_device.h ／ …/pico_sdk_sigrok.c ／ …/release/README.md | **指摘のとおり。** GP0 は「ch にならない」ではなく UART TX として出力駆動され、U3 の B1Y 出力と衝突する。→ **配布 `pico_baseline.uf2` はこの基板に書き込み禁止。標準ファームは `pico_dig26.uf2`**。アナログ 3ch が要る場合は `UART_EN 0` の自前ビルドのみ可。`PIN_TEST_MODE` 等、測定ピンを出力にするテストビルドも禁止。採用 UF2 は SHA-256 で版を固定。**回路側で CH0 を切り離す変更はしない**（初版は 16ch デジタル専用でよい） | SPEC §2.1（アナログ行）・§2.2（3 項）・**§2.3（表の baseline 行を「✗ 使用禁止」に変更＋根拠ブロック）**・§5.3（GP23 の駆動）・§6（J4 行）・§6.1 #2/#3・§7（表ヘッダ・GP0 行）・§11 #11（書き込むのは dig26）・#14（応答文字列を `SRPICO,A001D26,02` に）・§14 #11/#12。README（ファーム行・いまの状態）・KICAD-KIT §7 |
| 2 | **AMS1117 ＋ 10µF セラミックの安定性が未確認**（優先度中） | AMS `ds1117.pdf`（http://www.advanced-monolithic.com/pdf/ds1117.pdf ）。LCSC C6186 のデータシート（https://datasheet.lcsc.com/datasheet/pdf/e6935943fc6b1bbf350a1a0f3e90dc4a.pdf?productCode=C6186 ）と SHA-256 `189a2651878a87d590b768eaa9b44217a3fdf460352ce6ecaff127221282a3f0`（95,151 B・8 ページ）が一致 = 同一ファイル。Stability 節の全文は「出力コンデンサはデバイスの周波数補償の一部として必要」「**22µF 固体タンタルを出力に付ければ全動作条件で安定**」「ADJ をバイパスしないなら（固定電圧版）より小さい容量でも同等に使える」「安定性と過渡応答を上げるにはより大きい容量」の 4 文。特性表の条件も全て `C_OUT = 22µF Tantalum`。**セラミック 10µF の安定性は規定なし・禁止もなし・ESR 下限もなし。** SPEC §4.4 の「入出力に 10µF」は RP2040 公式 Minimal design example の NCP1117 の値で、AMS1117 の規定ではない | **指摘のとおり「設計保証が無い」。ただし初回 5 枚は C25 / C26 = 10µF X5R（C15850）のまま発注する**（人間決定）。理由: 発注前に LDO を差し替えるとフットプリント（SOT-223 → SOT-23-5 等）から変わり、配線済み PCB と製造データを作り直すことになる。代わりに **実機で 3V3 レールをオシロ（OWON VDS3102L）で観測**し、無負荷相当・RP2040 動作時・全入力トグル時の 3 条件で発振・リンギングが無いことを確定する。発振が見えたら **C26 の 0805 パッドに 22µF タンタル（3528 B ケース）を手はんだ**、または **C26 と直列に 0.5〜1Ω**。次リビジョンではセラミック安定を明記した LDO（例 AP2112K-3.3・SOT-23-5・C51118・ピン非互換）を検討 | **SPEC §4.4（表の備考＋「出力コンデンサ C26 の既知リスク」ブロック）**・**§11 フェーズ 2 #5a（新設）**・§10 #26（備考）・§14 #12。KICAD-KIT §7 |
| 3 | **外部 VREF をつないだまま SW1 を切り替えない**（使用条件） | KICAD-KIT §1.2.3（SK13D07VG5 データシート図面の `SCHEMATIC (SHORTING)`・2026-09-09 確認）。レビューの指摘どおり、3.3V ― EXT ― 5V の並びは LDO 出力と VBUS の直結を防ぐだけで、**EXT 接続中の切替では途中で外部電源と内蔵電源が一時的に直結**し、外部電源への逆流も防げない。スイッチ原図の再取得はしていない（根拠はリポジトリ内の記録のまま） | **指摘のとおり。初版は回路を変えず運用制約で回避する**（人間決定）。手順を **「J3 の EXT ケーブルを外す → SW1 で位置を選ぶ → 接続する」** と定め、SPEC の「使い方」節（新設 §6.1）に格上げ。§11 #7 / #19 の手順にも組み込んだ。通電中の切替を許容するなら次リビジョンで non-shorting 型か逆流防止（ダイオード / 理想ダイオード）を検討 | **SPEC §6.1（新設・使い方 #1）**・§5.4（SW1 の項に追記）・§11 #7 / #19・§14 #12。KICAD-KIT §1.2.3（追記）・§7 |
| 4 | **dgatf の設定ピン説明が逆**（軽微） | dgatf/logic_analyzer_rp2040 README（master・https://github.com/dgatf/logic_analyzer_rp2040#configuration ）Configuration 節: 「GPIO 19 to GND: use stage-based triggers（PulseView triggers are interpreted as level triggers）」「GPIO 18 to GND: enable debug mode. Debug output is available on GPIO 16 at 115200 bps」「If neither GPIO is grounded … Trigger edge override: enabled ／ Debug mode: disabled」。`src/common.h`: `GPIO_DEBUG_ENABLE = 18` / `GPIO_TRIGGER_STAGES = 19`。`src/main.c`: 両ピンに `gpio_pull_up()` を掛けてから `gpio_get()` し、Low のときだけ有効 | **指摘のとおり SPEC の表が逆だった。修正した**（GP18 = GND でデバッグ有効／GP19 = GND でレベルトリガ）。あわせて、ソースが内蔵プルアップを使うことから **未接続 = 既定動作（デバッグ無効・エッジトリガ）** が確定し、旧 §7 注意 2 の「内蔵プルダウンで GND と誤認される可能性・未確認」を解消した。テストパッドの配線は変更なし（TP3 = GP18・TP4 = GP19） | **SPEC §7（表の GP16〜22 行・出典・注意 2）**・§14 #12。KICAD-KIT §7 |

## 「確認できた基本結線」への回答

レビューの基本結線表（16ch 入力・TXU 電源 / OE・RP2040 電源・USB・Flash・発振 / リセット・補助端子）は設計意図と一致しており、異論なし。補足として、sigrok-pico が起動時に GP23 を High に駆動することをソースで確認し、OE = 有効で整合することを SPEC §5.3 に追記した。1.8V 入力を読むときに VREF も 1.8V にする点、EXT / 入力に過電圧保護が無い点は SPEC §6.1 #4〜#6 に使い方として明記した。

## 「再実行した機械検査と限界」への回答

ERC 0 / 期待ネット 88 本一致 / `check_kit5.py` 17 PASS が仕様の正しさの独立証明にならない点は、そのとおり。ファーム出力衝突（#1）と LDO 安定性（#2）は資料照合でしか見つからない種類の問題で、今回の指摘で SPEC に入った。PCB の信号品質・熱・実装方向・製造データの完全性・実機動作は、このレビューでも本回答でも合格判定していない。実機動作は SPEC §11 のチェックリスト（フェーズ 0〜6・今回 #5a を追加）で確定する。

## 変更していないもの

- `hardware/rp2040-logic-analyzer.kicad_sch` / `.kicad_pcb` / `.kicad_pro`・`hardware/out/` の製造データ（Gerber・BOM・CPL・DRC。commit 70e5a8e のまま）・`tools/`・`lib/`
- 発注する BOM（C25 / C26 = C15850・U7 = C6186・SW1 = C393948）

## 付記 — この回答で併せて確定した文書事項

- §10 の汎用 R / C（「汎用」「要選定」だった行）を製造 BOM `bom-jlcpcb.csv` の JLCPCB 品番で確定し、2026-09-20 に JLCPCB 部品 API で区分・在庫・単価を再確認した（100nF C1525／1µF C52923／15pF C1548／10µF C15850／100Ω C25076／5.1kΩ C25905／27Ω **C25100（Extended・0402 の 27Ω に Basic 品が無い）**／1kΩ C11702／10kΩ C25744）。SMT の Extended は 6 種（§9.3 に追記）
- §11 #14 の応答文字列: 配布 `pico_dig26.uf2` は `SRPICO,A001D26,02` を返す（`sr_device.c` の `sprintf` 書式とイメージ内の文字列で確認）。旧記載の `SRPICO,A03D21,00` は 2023 年版 baseline の応答
