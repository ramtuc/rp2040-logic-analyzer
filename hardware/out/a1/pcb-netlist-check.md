# 基板パッド ↔ 回路図ネットリスト 照合

- 基板: `hardware\rp2040-logic-analyzer.kicad_pcb`／ネットリスト: `hardware\out\rp2040-logic-analyzer.net`
- 回路図の名前付きネット: **88**／全ノード一致したネット: **88**／ノード不一致: **0**／基板だけにあるネット付きパッド: **0**

| ネット | 回路図ノード | 基板で一致 | 判定 |
|:--|--:|--:|:--|
| `+3V3` | 35 | 35 | OK |
| `+5V` | 8 | 8 | OK |
| `/CC1` | 2 | 2 | OK |
| `/CC2` | 2 | 2 | OK |
| `/CH0_A` | 2 | 2 | OK |
| `/CH0_IN` | 2 | 2 | OK |
| `/CH10_A` | 2 | 2 | OK |
| `/CH10_IN` | 2 | 2 | OK |
| `/CH11_A` | 2 | 2 | OK |
| `/CH11_IN` | 2 | 2 | OK |
| `/CH12_A` | 2 | 2 | OK |
| `/CH12_IN` | 2 | 2 | OK |
| `/CH13_A` | 2 | 2 | OK |
| `/CH13_IN` | 2 | 2 | OK |
| `/CH14_A` | 2 | 2 | OK |
| `/CH14_IN` | 2 | 2 | OK |
| `/CH15_A` | 2 | 2 | OK |
| `/CH15_IN` | 2 | 2 | OK |
| `/CH1_A` | 2 | 2 | OK |
| `/CH1_IN` | 2 | 2 | OK |
| `/CH2_A` | 2 | 2 | OK |
| `/CH2_IN` | 2 | 2 | OK |
| `/CH3_A` | 2 | 2 | OK |
| `/CH3_IN` | 2 | 2 | OK |
| `/CH4_A` | 2 | 2 | OK |
| `/CH4_IN` | 2 | 2 | OK |
| `/CH5_A` | 2 | 2 | OK |
| `/CH5_IN` | 2 | 2 | OK |
| `/CH6_A` | 2 | 2 | OK |
| `/CH6_IN` | 2 | 2 | OK |
| `/CH7_A` | 2 | 2 | OK |
| `/CH7_IN` | 2 | 2 | OK |
| `/CH8_A` | 2 | 2 | OK |
| `/CH8_IN` | 2 | 2 | OK |
| `/CH9_A` | 2 | 2 | OK |
| `/CH9_IN` | 2 | 2 | OK |
| `/D0` | 2 | 2 | OK |
| `/D1` | 2 | 2 | OK |
| `/D10` | 2 | 2 | OK |
| `/D11` | 2 | 2 | OK |
| `/D12` | 2 | 2 | OK |
| `/D13` | 2 | 2 | OK |
| `/D14` | 2 | 2 | OK |
| `/D15` | 2 | 2 | OK |
| `/D2` | 2 | 2 | OK |
| `/D3` | 2 | 2 | OK |
| `/D4` | 2 | 2 | OK |
| `/D5` | 2 | 2 | OK |
| `/D6` | 2 | 2 | OK |
| `/D7` | 2 | 2 | OK |
| `/D8` | 2 | 2 | OK |
| `/D9` | 2 | 2 | OK |
| `/DVDD` | 6 | 6 | OK |
| `/GP16` | 2 | 2 | OK |
| `/GP17` | 2 | 2 | OK |
| `/GP18` | 2 | 2 | OK |
| `/GP19` | 2 | 2 | OK |
| `/GP20` | 2 | 2 | OK |
| `/GP21` | 2 | 2 | OK |
| `/GP22` | 2 | 2 | OK |
| `/GP26_ADC0` | 2 | 2 | OK |
| `/GP27_ADC1` | 2 | 2 | OK |
| `/GP28_ADC2` | 2 | 2 | OK |
| `/LED_STATUS` | 2 | 2 | OK |
| `/QSPI_SCLK` | 2 | 2 | OK |
| `/QSPI_SD0` | 2 | 2 | OK |
| `/QSPI_SD1` | 2 | 2 | OK |
| `/QSPI_SD2` | 2 | 2 | OK |
| `/QSPI_SD3` | 2 | 2 | OK |
| `/QSPI_SS_N` | 4 | 4 | OK |
| `/RUN` | 3 | 3 | OK |
| `/SWCLK` | 2 | 2 | OK |
| `/SWDIO` | 2 | 2 | OK |
| `/TXU_OE` | 6 | 6 | OK |
| `/USB_BOOT` | 3 | 3 | OK |
| `/USB_DM` | 5 | 5 | OK |
| `/USB_DM_MCU` | 2 | 2 | OK |
| `/USB_DP` | 5 | 5 | OK |
| `/USB_DP_MCU` | 2 | 2 | OK |
| `/VREF_EXT` | 2 | 2 | OK |
| `/XIN` | 3 | 3 | OK |
| `/XOUT` | 2 | 2 | OK |
| `/XTAL_DRV` | 3 | 3 | OK |
| `GND` | 70 | 70 | OK |
| `Net-(D1-A)` | 2 | 2 | OK |
| `Net-(D2-A)` | 2 | 2 | OK |
| `Net-(D3-A)` | 2 | 2 | OK |
| `VREF` | 11 | 11 | OK |

## SW1（SK13D07VG5）のパッド

| pad | 回路図 | 基板 | 役割 |
|:--|:--|:--|:--|
| 1 | `+3V3` | `+3V3` | 接点（スライダ位置 1） |
| 2 | `VREF` | `VREF` | コモン |
| 3 | `/VREF_EXT` | `/VREF_EXT` | 接点（位置 2） |
| 4 | `+5V` | `+5V` | 接点（位置 3） |
| 5 | `unconnected-(SW1-MNT-Pad5)` | `unconnected-(SW1-MNT-Pad5)` | 固定ラグ |
| 6 | `unconnected-(SW1-MNT-Pad6)` | `unconnected-(SW1-MNT-Pad6)` | 固定ラグ |
