// 自作ロジアナ #3 の SPI／UART 測定用スケッチ（UNO R4 WiFi ＋ 74HC595 LED 基板）
// - 100ms ごとに 74HC595 へ 1 バイト（0x0F）を送る（shiftOut またはハードウェア SPI 1MHz）
// - 同時に D1(TX) の Serial1 から固定文字列を 115200bps で出す（UART の測定用）
// 配線: SER = D11（COPI）／SRCLK = D13（SCK）／RCLK = D10（ラッチ・CS に見立てる）
//       ロジアナ: SRCLK → CH0(D2)・SER → CH1(D3)・RCLK → CH2(D4)・D1(TX) → CH3(D5)・SW1 = 5V

#include <SPI.h>

#define USE_HW_SPI 0        // 0 = shiftOut、1 = ハードウェア SPI（1MHz・MODE0・MSBFIRST）
#define UART_BAUD 115200    // B-5 で 9600 に変えて書き込み直す

const int SER   = 11;  // データ（COPI）
const int SRCLK = 13;  // クロック（SCK）
const int RCLK  = 10;  // ラッチ（CS に見立てる）
const uint8_t VALUE = 0x0F;  // MSB/LSB の違いが見える値

void setup() {
  pinMode(RCLK, OUTPUT);
  digitalWrite(RCLK, HIGH);
#if USE_HW_SPI
  SPI.begin();
#else
  pinMode(SER, OUTPUT);
  pinMode(SRCLK, OUTPUT);
#endif
  Serial1.begin(UART_BAUD);  // D1(TX)/D0(RX) = RA4M1 の SCI2（WiFi でも Minima でも D1）
}

void loop() {
  digitalWrite(RCLK, LOW);
#if USE_HW_SPI
  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
  SPI.transfer(VALUE);
  SPI.endTransaction();
#else
  shiftOut(SER, SRCLK, MSBFIRST, VALUE);
#endif
  digitalWrite(RCLK, HIGH);

  Serial1.print("electwork 74HC595 0x0F\r\n");
  delay(100);
}
