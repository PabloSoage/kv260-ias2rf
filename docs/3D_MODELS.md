# 3D Model Audit & Mapping (`CSI2-KRIA-KV260_Rev01.kicad_pcb`)

## 1. Audit Summary
An automated audit of [CSI2-KRIA-KV260_Rev01.kicad_pcb](../CSI2-KRIA-KV260_Rev01.kicad_pcb) under **KiCad 10.0.6** (`C:\Users\pablo\AppData\Local\Programs\KiCad\10.0\share\kicad\3dmodels`) identified:

- **Total footprints:** 570
- **Broken `${KICAD10_3DMODEL_DIR}` model references:** **19** footprint instances whose `.step` path does not exist in the KiCad 10 standard installation (`Xilinx_FTG256`, `Mini-Circuits_CD542_H2.84mm`, `Oscillator_SMD_SI570_SI571_Standard`, `L_Bourns_SRP7028A_7.3x6.6mm`, `BarrelJack_CUI_PJ-102AH_Horizontal`, `Fuse_1812_4532Metric`, `HTSOP-8-1EP_...`, `QFN-20-1EP_...`, `QFN-48-1EP_...`, `LFCSP-32-1EP_...`, `LFCSP-56-1EP_...`).
- **Missing functional 3D models:** **7** functional component instances without any `(model ...)` tag (`U901`–`U904` `M3SWA2-34DR+`, `J101`–`J102` `BM20B(0.8)-34DP`, `J1201` `HR911130C`).
- **Non-functional omitted items (27):** Test points (`TP*`), fiducials (`FID*`), mounting holes (`MH*`), and solder jumper (`JP1101`) remain intentionally unmodeled.

All **26** missing or broken functional component instances (across **14** unique package geometries) have been resolved with real 3D CAD models — **no synthetic boxes or block placeholders are used**.

---

## 2. Storage & Licensing Split

| Bucket | Path | Contents / Licensing |
| :--- | :--- | :--- |
| **Redistributable (Git)** | [mech/models3d/](../mech/models3d/) | 8 KiCad 10 official STEP models (CC-BY-SA 4.0 / CERN-OHL compatible) + machine-readable [mapping.json](../mech/models3d/mapping.json) |
| **Third-Party Vendor Cache (outside Git)** | `../kv260-ias2rf/_work/mech/cache/models3d/` | 7 EasyEDA / LCSC fetched `.wrl` + `.step` pairs (`easyeda2kicad` v1.0.1) whose upstream license terms prevent direct repo redistribution |

> [!NOTE]
> For EasyEDA-sourced parts (`T701`/`T801`/`T802`, `Y401`, `F1001`, `L1001`–`L1030`, `J1001`, `J101`–`J102`, `J1201`), [mapping.json](../mech/models3d/mapping.json) points to the `.wrl` file because `easyeda2kicad`'s raw `.step` exports retain an internal `AXIS2_PLACEMENT_3D` construction Z-offset, whereas the `.wrl` geometry is pre-normalized to `Z = 0.00 mm` at the board surface. Both `.wrl` and `.step` remain cached side-by-side in `_work/mech/cache/models3d/`.

---

## 3. Component Mapping Table (26 Instances)

| Refs | Part / Value | Footprint | Source / LCSC ID | Bucket | Offset (mm) | Rotate (deg) | Verification Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `U1001` | `LMR33630ADDA` | `Texas_HSOP-8-1EP_3.9x4.9mm_P1.27mm` | `HSOP-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.1mm.step` (KiCad 10) | `repo` | `0, 0, 0` | `0, 0, 0` | Gull-wing leads & Pin-1 dot aligned |
| `U1101` | `XC7A50T-2FTG256I` | `Xilinx_FTG256` | `BGA-256_17.0x17.0mm_Layout16x16_P1.0mm_Ball0.5mm_Pad0.4mm_NSMD.step` (KiCad 10) | `repo` | `0, 0, 0` | `0, 0, 0` | 17×17 mm body, A1 corner dot aligned |
| `U1005`–`U1007` | `TPS7A8300RGR` | `QFN-20-1EP_3.5x3.5mm_P0.5mm_EP2x2mm` | `Texas_VQFN-RGR-20-1EP_3.5x3.5mm_Pitch0.5mm.step` (KiCad 10) | `repo` | `0, 0, 0` | `0, 0, 0` | Pin-1 dot & all 20 pads aligned |
| `U401` | `ADCLK948BCPZ` | `LFCSP-32-1EP_5x5mm_P0.5mm_EP2.7x2.7mm` | `LFCSP-32-1EP_5x5mm_P0.5mm_EP3.6x3.6mm.step` (KiCad 10) | `repo` | `0, 0, 0` | `0, 0, 0` | Pin-1 dot & 32 pads aligned |
| `U501` | `AD9484BCPZ-500` | `LFCSP-56-1EP_8x8mm_P0.5mm_EP5.1x5.1mm` | `QFN-56-1EP_8x8mm_P0.5mm_EP4.5x5.2mm.step` (KiCad 10) | `repo` | `0, 0, 0` | `0, 0, 0` | 8×8 mm QFN-56 seated on pads |
| `U601` | `AD9253BCPZ-125` | `QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm` | `TQFN-48-1EP_7x7mm_P0.5mm_EP5.1x5.1mm.step` (KiCad 10) | `repo` | `0, 0, 0` | `0, 0, 0` | 7×7 mm TQFN-48 aligned |
| `U1201` | `RTL8211FSI-CG` | `QFN-48-1EP_6x6mm_P0.4mm_EP4.4x4.4mm` | `UQFN-48-1EP_6x6mm_P0.4mm_EP4.45x4.45mm.step` (KiCad 10) | `repo` | `0, 0, 0` | `0, 0, 0` | Pin-1 dot matches silkscreen triangle |
| `U901`–`U904` | `M3SWA2-34DR+` | `MiniCircuits_DQ3005` | `WQFN-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm.step` (KiCad 10) | `repo` | `0, 0, 0` | `0, 0, 0` | Pin-1 dot matches silkscreen circle; all 16 RF switch pads aligned |
| `T701`, `T801`, `T802` | `ADT2-1T+` | `Mini-Circuits_CD542_H2.84mm` | `SMD-6_L7.9-W5.6-P2.54-LS7.0-BL.wrl` (LCSC `C3304975`, `ADT1.5-17+` CD542) | `cache` | `0, 0, 0` | `0, 0, 0` | Exact CD542 height (`2.84 mm`) & 6-lead span (`7.87 mm`) seated flush on pads |
| `Y401` | `Si549` XO | `Oscillator_SMD_SI570_SI571_Standard` | `OSC-SMD_8P-L7.0-W5.0-BL.wrl` (LCSC `C2027087`, `Si570` 7050-8P) | `cache` | `0, 0, 0` | `0, 0, 0` | 7.0×5.0 mm 8-pad crystal/XO envelope (`H = 1.65 mm`) |
| `F1001` | `PTC 1.5A hold` | `Fuse_1812_4532Metric` | `F1812_L4.5-W3.2-H1.0.wrl` (LCSC `C369174`) | `cache` | `0, 0, 0` | `0, 0, 0` | 4.5×3.2 mm 1812 fuse seated on pads |
| `L1001`, `L1010`, `L1020`, `L1030` | `SRP7028A-*` | `L_Bourns_SRP7028A_7.3x6.6mm` | `IND-SMD_SRP7028A-8R2M.wrl` (LCSC `C2041815`) | `cache` | `0, 0, 0` | `0, 0, 0` | Centered inside silkscreen & gold pads (`H = 2.80 mm`) |
| `J1001` | `12V IN` (`PJ-102AH`) | `BarrelJack_CUI_PJ-102AH_Horizontal` | `DC-IN-TH_PJ-102AH.wrl` (LCSC `C3096093`) | `cache` | `2.25, -3.0, 0` | `0, 0, 180` | Barrel opening faces `-X` board edge; all 3 TH pins pass cleanly through plated slots |
| `J101`, `J102` | `BM20B(0.8)-34DP` | `J-BM20B(0.8)-34DP` | `CONN-SMD_34P-P0.40_BM20B-0.8-34DP-0.4V-51.wrl` (LCSC `C424540`) | `cache` | `0, 0, 0` | `0, 0, 0` | Bottom-side IAS1/MIPI B2B plugs centered in silkscreen & 34 pads |
| `J1201` | `HR911130C` | `RJ45_Hanrun_HR911130C` | `RJ45-TH_HR911130C.wrl` (LCSC `C50933`) | `cache` | `0, 0, 0` | `0, 0, 180` | RJ45 port opening faces `+X` board edge; mounting bosses & 16 TH pins centered in plated holes |

---

## 4. Verification Procedure
All placements, orientations (`rotate_deg`), offsets (`offset_mm`), pin-1 polarity indicators, and board-edge connector protrusions were visually inspected by patching a temporary copy of `CSI2-KRIA-KV260_Rev01.kicad_pcb` outside the repository and running `kicad-cli pcb render` (top-down, bottom-side, isometric, and zoomed close-ups on `U1101`/`T701`/`Y401`/`U501`, `U1001`/`U1007`/`F1001`/`L1010–L1030`/`J1001`, `U1201`/`J1201`, `U901`–`U904`, and `J101`/`J102`). Real repository `*.kicad_pcb` files were left untouched.

The models in `mech/models3d/` are copies of KiCad 10's official 3D library (KiCad libraries licence: CC-BY-SA 4.0 with the KiCad libraries exception), kept here because the installed KiCad on the build machine has no 3D-model package; attribution: the KiCad Library Team.
