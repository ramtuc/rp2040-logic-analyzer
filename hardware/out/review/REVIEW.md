# 回路図レビュー（2026-09-20）

## 結論

16ch・GP0〜15・TXU0104×4・USB接続という主構成は仕様に沿っています。ただし、発注・通電前に解決したい事項が2件あります。標準 `pico_baseline` の使用は出力衝突を起こすため不可、U7の出力コンデンサは安定性の根拠が不足しています。ERC合格だけで動作保証とは判断できません。

今回の作業はレビューのみです。回路図・PCB・プロジェクト設定・仕様書は変更していません。

## 1. 優先度高：標準 pico_baseline と CH0 が出力衝突する

対象：U1 pin2（GP0）、U3 pin13（B1Y）、R24、SPEC.md 80行・608行付近。

現行ネットリストでは `/D0` に U1 pin2 と U3 pin13 が直結されています。TXU0104のOEはR24でプルアップされ、通常有効です。一方、sigrok-picoのbaseline設定は `UART_EN=1` で、起動時にGP0をUART TX出力に設定します。TXU出力とMCU出力が異なる値を出すと電流が衝突します。単に「CH0が使えず14chになる」という問題ではありません。[モード定義](https://github.com/pico-coder/sigrok-pico/blob/main/pico_sdk_sigrok/sr_device.h)、[UART初期化](https://github.com/pico-coder/sigrok-pico/blob/main/pico_sdk_sigrok/pico_sdk_sigrok.c)

入力側のR1=100ΩはJ2とTXUのA入力の間であり、この出力同士の経路には入っていません。TXU入力には内蔵プルダウンがあるため、VREF給電・OE有効なら、プローブを外した状態でもTXU側LOWとUARTのアイドルHIGHが衝突し得ます。破損する電流量までは未測定ですが、避けるべき接続です。[TIデータシート §7.3.1.1・§7.3.3](https://www.ti.com/lit/ds/symlink/txu0104.pdf)

推奨対応：

- 16chデジタル用途の初回書き込み手順を `pico_dig26.uf2` に統一する。dig26はUART無効でGP0〜15が入力対象です。
- アナログ3chも必要なら、UARTを無効にしてGP0を出力にしないbaseline派生ファームを用意するか、回路側でCH0を切り離せる構成にする。標準baselineをそのまま書かない。
- 共通OEを下げるだけでは全16chが切れるため、14ch＋ADCの互換性対策にはなりません。

上流mainのソースを2026-09-20に確認した結果です。実際に採用するUF2の版・ビルド設定は固定して再確認してください。PIN_TEST_MODE等、測定ピンを出力にするテストビルドも不可です。

## 2. 優先度中：AMS1117＋10µFセラミックの安定性が未確認

対象：U7=AMS1117-3.3（C6186）、C26=10µF、SPEC.md §4.4・BOM。

`tools/make_outputs.py` はC25/C26をC15850（10µF X5Rセラミック）に割り当てます。採用品に紐づくAMSの資料は出力コンデンサを周波数補償の一部とし、全動作条件での安定性を示す例は22µF固体タンタルです。小容量でも使える条件の記述はありますが、今回の10µF低ESRセラミック＋分散パスコンの構成について安定性を裏付ける条件は確認できませんでした。[AMS1117資料 p.4 Stability](https://datasheet.lcsc.com/datasheet/pdf/e6935943fc6b1bbf350a1a0f3e90dc4a.pdf?productCode=C6186)

これは「必ず発振する」という断定ではなく、設計保証が不足しているという指摘です。NCP1117の参考回路とピン互換であることだけでは、出力コンデンサ条件まで同じとは言えません。

推奨対応：セラミック安定性を明示したLDOへ変更するか、実際に採用するAMS1117についてメーカー条件に合う容量・種類・ESRを確定する。変更時はピン配置・フットプリント・発熱・起動条件も確認し、実機では起動波形と負荷変動時の3.3Vをオシロで測定する。

## 3. 使用条件：外部VREFをつないだままSW1を切り替えない

KICAD-KIT.md §1.2.3で既に認識されている制約です。同資料が記録するshorting型という条件では、3.3V―EXT―5Vの配置は内蔵3.3Vと5Vの直接短絡を避けますが、EXT接続中は切替途中で外部電源と内蔵電源が一時的に直結し得ます。EXTを中央に置くだけで、外部電源への逆流まで防げるわけではありません。

外部VREF線は切替時に外し、適切な電圧を選択してから接続する運用が必要です。通電切替を許容したいなら、non-shorting型や逆流防止を含めた回路変更が必要です。今回はスイッチの原図を新たに取得できておらず、shorting特性の根拠はリポジトリ内の記録です。

## 4. 軽微：dgatfの設定ピン説明が逆

SPEC.md 329〜330行の説明は、確認した上流READMEと逆です。上流ではGP18をGNDにするとデバッグ有効、GP19をGNDにするとレベルトリガ動作です。どちらも接地しなければデバッグ無効・エッジ動作と説明されています。これは文書の修正事項で、現行テストパッド配線そのものの誤りではありません。[dgatf Configuration](https://github.com/dgatf/logic_analyzer_rp2040#configuration)

## 確認できた基本結線

| ブロック | 結果 |
| --- | --- |
| 16ch入力 | J2奇数ピン→100Ω→TXU A入力→B出力→GP0〜15。CH順序一致 |
| TXU電源・OE | VCCA=VREF、VCCB=3.3V、各100nF、NC6/9未接続。OEはGP23＋3.3Vへの10kΩ。OEを3.3V基準とすることはTIのVCC(MIN)制御と整合 |
| RP2040電源 | IOVDD/USB/ADC=3.3V、内蔵VREG出力→DVDD。コアを3.3Vへ誤接続していない。100nF×10、VREG入出力1µF |
| USB | CC1/CC2独立5.1kΩ、DP/DM各27Ω、USBLC6は抵抗のコネクタ側。U8のDP1/6・DM3/4・VBUS5・GND2が一致 |
| Flash | W25Q128JVの電源・CS・CLK・IO0〜3のピン対応一致。BOOTSELは1kΩ経由CS→GND。R23はDNP |
| 発振・リセット | 12MHz、15pF×2、XOUT側1kΩ。RUNスイッチ→GND。負荷容量の最終適否は寄生容量・実装にも依存 |
| 補助端子 | SWDはTP8/TP9、ADCはGP26〜28。J4はDNPで保護なしの0〜3.3V専用 |

基本部品の照合資料：[RP2040公式設計ガイド](https://datasheets.raspberrypi.com/rp2040/hardware-design-with-rp2040.pdf)、[Winbond W25Q128JV](https://www.winbond.com/resource-files/w25q128jv%20revf%2003272018%20plus.pdf)、[ST USBLC6-2](https://www.st.com/resource/en/datasheet/usblc6-2.pdf)。

1.8V入力を読むにはVREFも対象に適した値に設定する必要があります。外部VREFはTXUのA側電源およびD2の電源でもあり、単なる高インピーダンス検出端子ではありません。デジタル入力も過電圧・負電圧・商用電源向けの保護入力ではありません。

## 再実行した機械検査と限界

- KiCad 10.0.3で現行回路図からネットリストを再出力。82部品。
- ERC：エラー0・警告0・個別除外0。既存設定で4種のチェック（単独グローバルラベル・4分岐接続・SPICEモデル・フットプリントフィルタ）は無効のまま。
- `verify_netlist.expected()` の期待88ネットと完全一致。
- 既存 `check_kit5.py` の17項目を、今回出力したネットリストで再実行：17 PASS / 0 FAIL。
- これら期待表も同じ仕様から作られているため、仕様そのものの正しさの独立証明にはなりません。上記のファーム出力衝突・LDO安定性は別途資料照合して見つけた事項です。
- PCBの信号品質、配線長、リターン経路、パスコン距離、熱、全フットプリント寸法、実装方向、製造データの完全性、実機動作は今回の回路図レビューで合格判定していません。前回のDRC合格とも別の検証です。

証拠ファイル：[ERC](erc.json)、[ネットリスト](current.net)、[部品・接続・SHA256](audit.json)、[17項目結果](kit5-check.md)。再実行スクリプト：[review_schematic.py](../review_schematic.py)。
