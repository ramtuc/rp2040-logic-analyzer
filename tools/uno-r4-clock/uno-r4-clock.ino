// UNO R4 WiFi の GPT タイマで矩形波を D6 から出し続ける（Minima でも動く）。
// 自作ロジアナ（RP2040）のサンプリング上限テスト用の信号源。
//
// GPT のカウントクロックは PCLKD = 48MHz（core の bsp_clock_cfg.h: HOCO 48MHz・PCLKD Div /1）。
// 鋸波 PWM で「周期 = PERIOD_COUNTS カウント」「High = PULSE_COUNTS カウント」を生のカウント値で渡す。
// 周波数を float で渡す begin(freq, duty) は 1/freq × 48e6 を切り捨てるので、高い周波数では使わない。

#include "pwm.h"

// ---- 出力周波数を選ぶ: 24 / 16 / 12 / 1（MHz）----
#define FREQ_MHZ 12

// High を「中位の駆動能力」にする（1 = 有効）。エッジが鈍いときに試す
#define USE_MIDDLE_DRIVE 0

#if FREQ_MHZ == 24
// 周期 2 カウント → GTPR = 1・GTCCR = 0。RA4M1 ハードウェアマニュアル 22.9.2(5) の
// 「0 < GTCCRA < GTPR」を満たさない（推奨範囲外）。オシロで 24MHz・50% を確かめてから使う
#define PERIOD_COUNTS 2
#define PULSE_COUNTS  1
#elif FREQ_MHZ == 16
// 周期 3 カウント → 50% は作れない。High 2 / Low 1 = デューティ 67%（GTPR = 2・GTCCR = 1）
#define PERIOD_COUNTS 3
#define PULSE_COUNTS  2
#elif FREQ_MHZ == 12
// 周期 4 カウント → High 2 / Low 2 = 50%（GTPR = 3・GTCCR = 1）
#define PERIOD_COUNTS 4
#define PULSE_COUNTS  2
#elif FREQ_MHZ == 1
#define PERIOD_COUNTS 48
#define PULSE_COUNTS  24
#else
#error "FREQ_MHZ は 24 / 16 / 12 / 1 のどれか"
#endif

const int CLOCK_PIN = D6;  // WiFi: P111 = GTIOC3A ／ Minima: P106 = GTIOC0B（core の variant.cpp・pinmux.inc）
PwmOut clk(CLOCK_PIN);
bool ok = false;

void setup() {
  Serial.begin(115200);
  ok = clk.begin(PERIOD_COUNTS, PULSE_COUNTS, true, TIMER_SOURCE_DIV_1);
#if USE_MIDDLE_DRIVE
  R_IOPORT_PinCfg(&g_ioport_ctrl, g_pin_cfg[CLOCK_PIN].pin,
                  (uint32_t)(IOPORT_CFG_PERIPHERAL_PIN | IOPORT_PERIPHERAL_GPT1 | IOPORT_CFG_DRIVE_MID));
#endif
}

void loop() {
  // 出力はタイマが出し続ける。設定値の確認だけ 2 秒ごとに USB シリアルへ
  uint32_t pclkd = R_FSP_SystemClockHzGet(FSP_PRIV_CLOCK_PCLKD);
  uint32_t period = clk.get_timer()->get_period_raw();
  Serial.print(ok ? "running" : "begin FAILED");
  Serial.print(": PCLKD ");
  Serial.print(pclkd);
  Serial.print(" Hz / period ");
  Serial.print(period);
  Serial.print(" counts / high ");
  Serial.print(PULSE_COUNTS);
  Serial.print(" counts -> ");
  Serial.print(period ? (float)pclkd / period / 1e6 : 0.0, 3);
  Serial.println(" MHz on D6");
  delay(2000);
}
