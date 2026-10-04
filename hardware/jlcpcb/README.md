# JLCPCB 正規製造データ

このフォルダには、**JLCPCB の注文ページからダウンロードした BOM / CPL / Gerber をそのまま置きます。** ファイル名は配布のままで、変更しません。**実装の正（正規データ）はこのフォルダのファイル**です。

- `../out/` にある BOM・CPL・Gerber は KiCad（kicad-cli）の出力で、JLCPCB にアップロードする前の設計側のデータです
- A0 の注文では、USB-C（J1）を部品が入手できなかったため実装から外しています。このフォルダのデータは、その状態の注文のものです
- A0 の PCB は SW1 のコモンの配線が誤っています（コモンはピン 2）。改修方法はリポジトリ直下の README の「既知の問題」を参照してください

---

# JLCPCB manufacturing data (authoritative)

This folder holds the BOM / CPL / Gerber files downloaded from the JLCPCB order page, stored as-is with their original file names. These files are the authoritative assembly data. The files in `../out/` are the KiCad outputs before upload. In the A0 order, the USB-C connector (J1) was excluded from assembly because the part was unavailable.
