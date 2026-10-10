# uno-r4-clock — ロジアナのサンプリング上限テスト用の信号源（Arduino UNO R4）

Arduino **UNO R4 WiFi** の **GPT（General PWM Timer）** で矩形波を **D6** から出し続けるスケッチです。自作ロジアナ（RP2040・最大 120MS/s）に 12〜24MHz を入れて、レートを下げたときに周期・デューティがどう崩れ、どこでエイリアスになるかを見るために使います。

- 対象は **UNO R4 WiFi**（`arduino:renesas_uno:unor4wifi`）。Arduino UNO R4 Boards 1.5.2・arduino-cli 1.5.1 で**コンパイル確認済み**（Minima でも通る）。実機での波形は未確認
- 周波数: **24／16／12／1MHz**（既定 **12MHz**）。スケッチ冒頭の `#define FREQ_MHZ` で切り替え
- 出力: **D6**（5V ロジック）

## 周波数の作り方と制約

GPT のカウントクロックは **PCLKD = 48MHz**（core の `bsp_clock_cfg.h`: クロック源 HOCO 48MHz・PCLKD 分周 /1）。鋸波 PWM で「周期 N カウント・High M カウント」を **生のカウント値**で設定します（`PwmOut::begin(period, pulse, raw = true, TIMER_SOURCE_DIV_1)`）。周波数を float で渡す `begin(freq, duty)` は `1/freq × 48e6` を整数に切り捨てるので、周期 2〜4 カウントのような値では使っていません。

Arduino core が使う FSP 4.0.0 の `r_gpt.c` は `GTPR = 周期 − 1`、`GTCCR = High − 1` を書き込み、出力は「周期の終わりで High・コンペアマッチで Low」です。

| `FREQ_MHZ` | 周期（カウント） | High（カウント） | GTPR | GTCCR | デューティ | マニュアルの範囲 |
|--:|--:|--:|--:|--:|--:|:---|
| **12** | 4 | 2 | 3 | 1 | **50%** | 範囲内 |
| 16 | 3 | 2 | 2 | 1 | **67%**（50% は作れない） | 範囲内 |
| 24 | 2 | 1 | 1 | 0 | 50%（のはず） | **範囲外**（下記） |
| 1 | 48 | 24 | 47 | 23 | 50% | 範囲内 |

RA4M1 グループ ユーザーズマニュアル ハードウェア編（R01UH0887EJ0110 Rev.1.10）より:

- **22.9.2 (5) In saw-wave PWM mode**（p.512）: 「The GTCCRA register must be set with the range of **0 < GTCCRA < GTPR**. If GTCCRA = 0 or GTCCRA = GTPR is set, a compare match occurs within the cycle only when GTCCRA = 0 or GTCCRA = GTPR is satisfied.」→ **24MHz（GTPR = 1・GTCCR = 0）はこの範囲を満たさない。** 周期 2 カウントでは 0 と 1 の間に整数が無いため、どう設定しても範囲内にならない
- **Table 22.5 Note 2**（p.423）: 周期の終わりとコンペアマッチが同じタイミングになった場合、鋸波 PWM モードでは周期の終わり側の設定が優先される

**24MHz を使うときは、先にオシロで Freq＝24MHz・+Duty＝50% 付近になっていることを確かめてから**ロジアナにつないでください（High に張り付く・デューティが崩れる可能性がある）。記事の主役は範囲内で 50% が作れる **12MHz** です。

## 周波数の精度

UNO R4 のシステムクロックは水晶ではなく **内蔵 HOCO** です。マニュアル **Table 48.22 Clock timing**（p.1341）の fHOCO48 は **47.52〜48.48MHz（Ta = −20〜85°C・±1%）**。出力周波数も同じ割合でずれます（12MHz なら最大 ±120kHz）。ロジアナ（RP2040・水晶）との差がそのまま「うなり」の周波数として見えるので、オシロの Freq で実際の値を必ず記録してください。

## 出力の立ち上がり時間（目安）

マニュアルに汎用 I/O ポートの出力立ち上がり時間の規定は見当たりませんでした。近い参考値として、**CLKOUT 端子（クロック出力機能）の出力立ち上がり／立ち下がり時間は最大 12ns**（VCC = 2.7V 以上・**Table 48.39 CLKOUT timing**・p.1367）。24MHz の High 幅は 20.8ns なので、12ns 級のエッジだと台形に近くなります。**実際の立ち上がりはオシロで実測**してください。エッジが鈍いときは `USE_MIDDLE_DRIVE 1`（ポートの駆動能力を「中」にする）を試せます。

## 書き込み（人間）

Arduino IDE 2.x:

1. `uno-r4-clock.ino` を開く（フォルダ名とファイル名が同じなのでそのまま開ける）
2. ボード「Arduino UNO R4 WiFi」・ポートを選ぶ
3. 冒頭の `#define FREQ_MHZ` を選んで「書き込み」
4. シリアルモニタ（115200）に次のように出れば設定どおり（UNO R4 WiFi の `Serial` は RA4M1 の UART1（P109/P110）→ 基板上の ESP32-S3 が USB に橋渡しするので、ボーレートはスケッチと同じ 115200 に合わせる）:

```text
running: PCLKD 48000000 Hz / period 4 counts / high 2 counts -> 12.000 MHz on D6
```

`begin FAILED` が出たら D6 のタイマ設定に失敗しています。

arduino-cli なら:

```bash
arduino-cli compile --upload -p COMx --fqbn arduino:renesas_uno:unor4wifi uno-r4-clock
```

## 配線

| UNO R4 | ロジアナ | 備考 |
|:---|:---|:---|
| **D6** | **CH0（J2 の D2）** | ジャンパはなるべく短く |
| **GND** | **J2 外側列の GND** | GND を先につなぐ |

- **SW1 = 5V**（UNO R4 は 5V ロジック）。**J3 を外してから SW1 を動かす**（チェックリストの安全の約束 1）
- オシロは CH1（×10）を D6 に当て、GND は UNO R4 の GND から
- UNO R4 と PC は USB でつないだまま（給電とシリアル確認）

## D6 の根拠

`D6` が MCU のどのピン・どの GPT 出力になるかは core の variant 定義で決まり、**UNO R4 WiFi と Minima で違います**（スケッチは `PwmOut` が variant の表から自動で選ぶので、どちらでも同じ `D6` でよい）。

| ボード | D6 のポート | GPT 出力 | 出典 |
|:---|:---|:---|:---|
| **UNO R4 WiFi（使う方）** | **P111** | **GTIOC3A（GPT163・16bit）** | `variants/UNOWIFIR4/variant.cpp` の `g_pin_cfg`（`(6) D6~` = `BSP_IO_PORT_01_PIN_11`）・`pinmux.inc` の `P111`（`PIN_PWM`・`CHANNEL_3`・`PWM_CHANNEL_A`） |
| UNO R4 Minima（参考） | P106 | GTIOC0B（GPT320・32bit） | `variants/MINIMA/variant.cpp`・`pinmux.inc` の `P106` |

周期は最大 48 カウントなので、16bit の GPT163 で足ります。D6 はチェックリストの SPI（D10・D11・D13）・UART（D1）・サーボ（D9）と重ならないピンとして選んでいます。WiFi の LED マトリクス（P003 など）とも重なりません。
