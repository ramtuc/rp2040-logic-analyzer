# CPL 回転補正（JLCPCB 列名 Designator / Mid X / Mid Y / Layer / Rotation）

KiCad の位置ファイル（`pos-kicad.csv`・Y 上向き正・mm・原点は KiCad のページ原点＝Gerber と同じ絶対原点）から SMD 実装対象だけを取り、Fabrication Toolkit（bennymeg/Fabrication-Toolkit master `plugins/transformations.csv`・51 行）と同じ規則（フットプリント名の先頭一致）で回転を足した。補正 0 のものは JLCPCB 側の部品向きと一致する保証が無いので、注文画面の 3D プレビューで確認する（KIT §2.3）。

- **Mid Y が負**なのは KiCad の pos 規約（Y 上向き正・基板がページ原点より下にある）。JLCPCB の公式手順（help「How To Export BOM and CPL Files From KiCad 10」2026-09-09 更新）は KiCad の .pos の列名を Designator/Mid X/Mid Y/Rotation/Layer に**改名するだけ**で座標変換を求めておらず、推奨の Fabrication Toolkit も `mid_y = (y − aux_origin.y) × −1`（process.py）で同じ符号を出す。JLCPCB は Gerber と同じ原点で相対位置を見るので負の値のままで受け付ける
- **USB-C J1（`USB_C_Receptacle_HRO_TYPE-C-31-M-12`）は transformations.csv に規則が無い**（USB/Type-C/HRO の行は 0 件）ので補正 0＝KiCad の回転そのまま。位置は KiCad のアンカー（Fabrication Toolkit 既定の「パッド外接矩形の中心」とは 局所 Y で 1.46mm ずれる。THT 固定穴まで含めた矩形なので機械的中心とも一致しない）。**3D プレビューで基板端からの張り出しと向きを目視**

| Designator | Footprint | KiCad rot | 補正 | CPL rot | 備考 |
|:--|:--|--:|--:|--:|:--|
| C1 | `C_0402_1005Metric` | 90 | +0 | 90 |  |
| C2 | `C_0402_1005Metric` | 0 | +0 | 0 |  |
| C3 | `C_0402_1005Metric` | 90 | +0 | 90 |  |
| C4 | `C_0402_1005Metric` | 0 | +0 | 0 |  |
| C5 | `C_0402_1005Metric` | 0 | +0 | 0 |  |
| C6 | `C_0402_1005Metric` | 0 | +0 | 0 |  |
| C7 | `C_0402_1005Metric` | 90 | +0 | 90 |  |
| C8 | `C_0402_1005Metric` | 0 | +0 | 0 |  |
| C9 | `C_0402_1005Metric` | 0 | +0 | 0 |  |
| C10 | `C_0402_1005Metric` | 0 | +0 | 0 |  |
| C11 | `C_0402_1005Metric` | 90 | +0 | 90 |  |
| C12 | `C_0402_1005Metric` | 0 | +0 | 0 |  |
| C13 | `C_0402_1005Metric` | 90 | +0 | 90 |  |
| C14 | `C_0402_1005Metric` | 90 | +0 | 90 |  |
| C15 | `C_0402_1005Metric` | 90 | +0 | 90 |  |
| C16 | `C_0402_1005Metric` | 90 | +0 | 90 |  |
| C17 | `C_0402_1005Metric` | 90 | +0 | 90 |  |
| C18 | `C_0402_1005Metric` | 90 | +0 | 90 |  |
| C19 | `C_0402_1005Metric` | 90 | +0 | 90 |  |
| C20 | `C_0402_1005Metric` | 90 | +0 | 90 |  |
| C21 | `C_0402_1005Metric` | 0 | +0 | 0 |  |
| C22 | `C_0402_1005Metric` | 0 | +0 | 0 |  |
| C23 | `C_0402_1005Metric` | 0 | +0 | 0 |  |
| C24 | `C_0402_1005Metric` | 0 | +0 | 0 |  |
| C25 | `C_0805_2012Metric` | 90 | +0 | 90 |  |
| C26 | `C_0805_2012Metric` | 90 | +0 | 90 |  |
| C27 | `C_0402_1005Metric` | 90 | +0 | 90 |  |
| D1 | `LED_0603_1608Metric` | 0 | +0 | 0 | ★極性: 3D プレビューで目視（DB に規則なし） |
| D2 | `LED_0603_1608Metric` | 0 | +0 | 0 | ★極性: 3D プレビューで目視（DB に規則なし） |
| D3 | `LED_0603_1608Metric` | 0 | +0 | 0 | ★極性: 3D プレビューで目視（DB に規則なし） |
| J1 | `USB_C_Receptacle_HRO_TYPE-C-31-M-12` | 90 | +0 | 90 | ★原点/向き: 3D プレビューで目視（DB に規則なし） |
| R1 | `R_0402_1005Metric` | 90 | +0 | 90 |  |
| R2 | `R_0402_1005Metric` | 90 | +0 | 90 |  |
| R3 | `R_0402_1005Metric` | 90 | +0 | 90 |  |
| R4 | `R_0402_1005Metric` | 90 | +0 | 90 |  |
| R5 | `R_0402_1005Metric` | 90 | +0 | 90 |  |
| R6 | `R_0402_1005Metric` | 90 | +0 | 90 |  |
| R7 | `R_0402_1005Metric` | 90 | +0 | 90 |  |
| R8 | `R_0402_1005Metric` | 90 | +0 | 90 |  |
| R9 | `R_0402_1005Metric` | 90 | +0 | 90 |  |
| R10 | `R_0402_1005Metric` | 90 | +0 | 90 |  |
| R11 | `R_0402_1005Metric` | 90 | +0 | 90 |  |
| R12 | `R_0402_1005Metric` | 90 | +0 | 90 |  |
| R13 | `R_0402_1005Metric` | 90 | +0 | 90 |  |
| R14 | `R_0402_1005Metric` | 90 | +0 | 90 |  |
| R15 | `R_0402_1005Metric` | 90 | +0 | 90 |  |
| R16 | `R_0402_1005Metric` | 90 | +0 | 90 |  |
| R17 | `R_0402_1005Metric` | 0 | +0 | 0 |  |
| R18 | `R_0402_1005Metric` | 0 | +0 | 0 |  |
| R19 | `R_0402_1005Metric` | 180 | +0 | 180 |  |
| R20 | `R_0402_1005Metric` | 180 | +0 | 180 |  |
| R21 | `R_0402_1005Metric` | 0 | +0 | 0 |  |
| R22 | `R_0402_1005Metric` | 90 | +0 | 90 |  |
| R24 | `R_0402_1005Metric` | 90 | +0 | 90 |  |
| R25 | `R_0402_1005Metric` | 0 | +0 | 0 |  |
| R26 | `R_0402_1005Metric` | 0 | +0 | 0 |  |
| R27 | `R_0402_1005Metric` | 0 | +0 | 0 |  |
| SW2 | `SW-SMD_4P-L5.1-W5.1-P3.70-LS6.5-TL_H1.5` | 0 | +0 | 0 |  |
| SW3 | `SW-SMD_4P-L5.1-W5.1-P3.70-LS6.5-TL_H1.5` | 0 | +0 | 0 |  |
| U1 | `QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm` | -90 | +90 | 0 | 1 番ピン位置を 3D プレビューで目視（DB 規則 +90） |
| U2 | `SOIC-8_5.3x5.3mm_P1.27mm` | 0 | +270 | 270 |  |
| U3 | `TSSOP-14_4.4x5mm_P0.65mm` | -90 | +270 | 180 |  |
| U4 | `TSSOP-14_4.4x5mm_P0.65mm` | -90 | +270 | 180 |  |
| U5 | `TSSOP-14_4.4x5mm_P0.65mm` | -90 | +270 | 180 |  |
| U6 | `TSSOP-14_4.4x5mm_P0.65mm` | -90 | +270 | 180 |  |
| U7 | `SOT-223-3_TabPin2` | 0 | +180 | 180 | タブの向き: 3D プレビューで目視（DB 規則 +180） |
| U8 | `SOT-23-6` | 0 | +180 | 180 |  |
| X1 | `Crystal_SMD_3225-4Pin_3.2x2.5mm` | 0 | +0 | 0 | DB に規則なし（0） |

## CPL から除外した参照子（位置ファイルにはあるが SMD 実装対象でない・5 件）

- J2: THT（手はんだ）
- J3: THT（手はんだ）
- J4: DNP（未実装）
- R23: DNP（未実装）
- SW1: THT（手はんだ）
- TP1〜TP9: exclude_from_pos_files なので位置ファイル自体に出ない（部品なし）
