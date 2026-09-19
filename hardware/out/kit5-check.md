| # | 項目 | 判定 | 根拠（ネットリスト） |
|--:|:---|:---|:---|
| 1 | RP2040 の 100nF が 10 個（IOVDD×6・USB_VDD・ADC_AVDD → +3V3、DVDD×2） | **PASS** | +3V3–GND: ['C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C9', 'C10']（8） / DVDD–GND: ['C7', 'C8']（2）。C11 = U2 用、C12 = 予備（+3V3） |
| 2 | VREG_VIN / VREG_VOUT に 1µF 各 1・VREG_VOUT→DVDD(23,50)・DVDD は +3V3 と別ネット | **PASS** | C21→+3V3 / C22→/DVDD / DVDD ノード: [('C22', '1'), ('C7', '1'), ('C8', '1'), ('U1', '23'), ('U1', '45'), ('U1', '50')] |
| 3 | 15pF ×2（XIN 側・XOUT 側） | **PASS** | C23: /XIN / C24: /XTAL_DRV（水晶側 = XTAL_DRV） |
| 4 | 1kΩ は XOUT と水晶の間・XIN は直結 | **PASS** | R21: /XOUT↔/XTAL_DRV / XIN ネット: ['C23', 'U1', 'X1'] |
| 5 | R23 10kΩ は DNP・LCSC 空・QSPI_SS_N↔+3V3 にフットプリントだけ置く | **PASS** | dnp=True LCSC='' +3V3↔/QSPI_SS_N |
| 6 | SW2 → R22(1kΩ) → QSPI_SS_N | **PASS** | USB_BOOT: ['R22', 'SW2'] / SW2 pin3→GND |
| 7 | USB_DP/DM に 27Ω 各 1・プルアップ/ダウン無し | **PASS** | USB_DP: ['J1', 'R19', 'U8'] → R19 → USB_DP_MCU: ['R19', 'U1'] |
| 8 | CC1 / CC2 に 5.1kΩ 各 1・独立に GND | **PASS** | CC1: ['J1', 'R17'] / CC2: ['J1', 'R18'] |
| 9 | USBLC6 はコネクタ側ネット（27Ω の外側）・VBUS/GND 接続 | **PASS** | U8 pins: 1→/USB_DP 6→/USB_DP 3→/USB_DM 4→/USB_DM 5→+5V |
| 10 | TXU_OE = GP23 ＋ 10kΩ プルアップは +3V3（VREF ではない） | **PASS** | R24: +3V3↔/TXU_OE / TXU_OE: ['R24', 'U1', 'U3', 'U4', 'U5', 'U6'] |
| 11 | VCCA/VCCB に 100nF 各 1 ×4（C13–C20）・A 入力に外付け無し・NC(6,9) 未接続 | **PASS** | U3: VCCA←C13(VREF) VCCB←C14(+3V3) NC6/9 未接続 / U4: VCCA←C15(VREF) VCCB←C16(+3V3) NC6/9 未接続 / U5: VCCA←C17(VREF) VCCB←C18(+3V3) NC6/9 未接続 / U6: VCCA←C19(VREF) VCCB←C20(+3V3) NC6/9 未接続 |
| 12 | SW1: ピン1 = VREF(コモン)・2 = +3V3・3 = EXT・4 = +5V（+3V3 と +5V が隣接しない） | **PASS** | SW1 {1: 'VREF', 2: '+3V3', 3: '/VREF_EXT', 4: '+5V', 5: 'unconnected-(SW1-MNT-Pad5)', 6: 'unconnected-(SW1-MNT-Pad6)'}（5/6 = 固定ラグ・未接続） |
| 13 | R1–R16 = 100Ω、J2 と TXU0104 A ピンの間（1kΩ ではない） | **PASS** | R1–R16 すべて 100Ω・CHn_IN(J2 奇数ピン)↔CHn_A |
| 14 | D1 = +3V3、D2 = VREF、D3 = LED_STATUS(GP25)、各 1kΩ | **PASS** | D1←+3V3 / D2←VREF / D3←/LED_STATUS |
| 15 | SWD を出すか決める（SPEC §6 に無い） | **要決定** | SWCLK→unconnected-(U1-SWCLK-Pad24) / SWDIO→unconnected-(U1-SWDIO-Pad25)。未決のため no_connect で明示。テストパッド 2 点の追加は handoff で提案 |
| 補 | RUN(26) に外付け部品なし（SW3 で GND に落とすだけ） | **PASS** | RUN: ['SW3', 'U1'] |

PASS 15 / FAIL 0 / 要決定 1
