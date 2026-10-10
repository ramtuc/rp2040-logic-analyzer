// 自作ロジアナ #3 のサーボ PWM 測定用スケッチ（UNO R4 WiFi ＋ SG90）
// D9 から Servo ライブラリの PWM を出し、0° → 90° → 180° を 2 秒ごとに繰り返す。
// 配線: D9 → ロジアナ CH0(D2)・SW1 = 5V（J3 を外してから）。サーボの電源は外部 5V・GND だけ共通。
#include <Servo.h>

Servo sg90;
const int SERVO_PIN = 9;
const int ANGLES[] = {0, 90, 180};

void setup() {
  sg90.attach(SERVO_PIN, 500, 2400);  // SG90: 0° = 500µs・180° = 2400µs
  Serial.begin(115200);
}

void loop() {
  for (int i = 0; i < 3; i++) {
    sg90.write(ANGLES[i]);
    Serial.print("angle ");
    Serial.print(ANGLES[i]);
    Serial.print(" -> ");
    Serial.print(sg90.readMicroseconds());
    Serial.println(" us");
    delay(2000);
  }
}
