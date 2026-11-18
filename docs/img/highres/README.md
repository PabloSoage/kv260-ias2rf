# High-Resolution (4K) & Vector Assets Gallery

This directory provides **4K raster renders (`3840 × 2160` PNG)** and **lossless vector drawings (SVG / PDF)** for detailed inspection of the final **8-layer (`JLC08161H-2116C`) KV260-IAS2RF** hardware, thermal/heatsink mechanical integration, Vivado 2026.1 FPGA silicon floorplans & gateware schematics, Enclosure v2 CAD/CFD/FEA, and 8-layer signal/power integrity simulations.

---

## 1. Schematics (`sch/`)

- Combined single-page full wired circuit (all 11 sheets stitched onto one vector canvas):
  - [`FULL_CIRCUIT.pdf`](sch/FULL_CIRCUIT.pdf) · [`FULL_CIRCUIT.svg`](sch/FULL_CIRCUIT.svg) · [`FULL_CIRCUIT_4k.png`](sch/FULL_CIRCUIT_4k.png)
- Root hierarchy sheet:
  - [`CSI2-KRIA-KV260_Rev01.svg`](sch/CSI2-KRIA-KV260_Rev01.svg) · [`ROOT_4k.png`](sch/ROOT_4k.png)
- Individual schematic sheets (SVG + 4K PNG):
  - `ADC_RADAR`: [`CSI2-KRIA-KV260_Rev01-ADC_RADAR.svg`](sch/CSI2-KRIA-KV260_Rev01-ADC_RADAR.svg) · [`ADC_RADAR_4k.png`](sch/ADC_RADAR_4k.png)
  - `ADC_SDR`: [`CSI2-KRIA-KV260_Rev01-ADC_SDR.svg`](sch/CSI2-KRIA-KV260_Rev01-ADC_SDR.svg) · [`ADC_SDR_4k.png`](sch/ADC_SDR_4k.png)
  - `CLOCK`: [`CSI2-KRIA-KV260_Rev01-CLOCK.svg`](sch/CSI2-KRIA-KV260_Rev01-CLOCK.svg) · [`CLOCK_4k.png`](sch/CLOCK_4k.png)
  - `CONTROL`: [`CSI2-KRIA-KV260_Rev01-CONTROL.svg`](sch/CSI2-KRIA-KV260_Rev01-CONTROL.svg) · [`CONTROL_4k.png`](sch/CONTROL_4k.png)
  - `DAC_RADAR`: [`CSI2-KRIA-KV260_Rev01-DAC_RADAR.svg`](sch/CSI2-KRIA-KV260_Rev01-DAC_RADAR.svg) · [`DAC_RADAR_4k.png`](sch/DAC_RADAR_4k.png)
  - `DAC_SDR`: [`CSI2-KRIA-KV260_Rev01-DAC_SDR.svg`](sch/CSI2-KRIA-KV260_Rev01-DAC_SDR.svg) · [`DAC_SDR_4k.png`](sch/DAC_SDR_4k.png)
  - `IAS_LINK`: [`CSI2-KRIA-KV260_Rev01-IAS_LINK.svg`](sch/CSI2-KRIA-KV260_Rev01-IAS_LINK.svg) · [`IAS_LINK_4k.png`](sch/IAS_LINK_4k.png)
  - `POWER`: [`CSI2-KRIA-KV260_Rev01-POWER.svg`](sch/CSI2-KRIA-KV260_Rev01-POWER.svg) · [`POWER_4k.png`](sch/POWER_4k.png)
  - `ROUTING`: [`CSI2-KRIA-KV260_Rev01-ROUTING.svg`](sch/CSI2-KRIA-KV260_Rev01-ROUTING.svg) · [`ROUTING_4k.png`](sch/ROUTING_4k.png)
  - `RX_VU`: [`CSI2-KRIA-KV260_Rev01-RX_VU.svg`](sch/CSI2-KRIA-KV260_Rev01-RX_VU.svg) · [`RX_VU_4k.png`](sch/RX_VU_4k.png)
  - `STATUS`: [`CSI2-KRIA-KV260_Rev01-STATUS.svg`](sch/CSI2-KRIA-KV260_Rev01-STATUS.svg) · [`STATUS_4k.png`](sch/STATUS_4k.png)

*(Full 13-page multi-sheet vector PDF: the root, the composite and the 11 sheets: [`docs/KV260-IAS2RF_schematic.pdf`](../../KV260-IAS2RF_schematic.pdf).)*

---

## 2. 8-Layer PCB Layout (`layout/`)

Every copper layer of the **JLC08161H-2116C** 8-layer stackup, plus composite views matching the 10-page vector layout PDF ([`docs/KV260-IAS2RF_layout.pdf`](../../KV260-IAS2RF_layout.pdf)):

- **L1 (`F.Cu`):** [`layer_01_L1_F_Cu.svg`](layout/layer_01_L1_F_Cu.svg) · [`layer_01_L1_F_Cu_4k.png`](layout/layer_01_L1_F_Cu_4k.png)
- **L2 (`In1.Cu` GND):** [`layer_02_L2_In1_GND.svg`](layout/layer_02_L2_In1_GND.svg) · [`layer_02_L2_In1_GND_4k.png`](layout/layer_02_L2_In1_GND_4k.png)
- **L3 (`In2.Cu` SIG):** [`layer_03_L3_In2_SIG.svg`](layout/layer_03_L3_In2_SIG.svg) · [`layer_03_L3_In2_SIG_4k.png`](layout/layer_03_L3_In2_SIG_4k.png)
- **L4 (`In3.Cu` PWR):** [`layer_04_L4_In3_PWR.svg`](layout/layer_04_L4_In3_PWR.svg) · [`layer_04_L4_In3_PWR_4k.png`](layout/layer_04_L4_In3_PWR_4k.png)
- **L5 (`In4.Cu` GND):** [`layer_05_L5_In4_GND.svg`](layout/layer_05_L5_In4_GND.svg) · [`layer_05_L5_In4_GND_4k.png`](layout/layer_05_L5_In4_GND_4k.png)
- **L6 (`In5.Cu` SIG):** [`layer_06_L6_In5_SIG.svg`](layout/layer_06_L6_In5_SIG.svg) · [`layer_06_L6_In5_SIG_4k.png`](layout/layer_06_L6_In5_SIG_4k.png)
- **L7 (`In6.Cu` GND):** [`layer_07_L7_In6_GND.svg`](layout/layer_07_L7_In6_GND.svg) · [`layer_07_L7_In6_GND_4k.png`](layout/layer_07_L7_In6_GND_4k.png)
- **L8 (`B.Cu`):** [`layer_08_L8_B_Cu.svg`](layout/layer_08_L8_B_Cu.svg) · [`layer_08_L8_B_Cu_4k.png`](layout/layer_08_L8_B_Cu_4k.png)
- **Combined 8 layers:** [`layer_09_all_8_layers.svg`](layout/layer_09_all_8_layers.svg) · [`layer_09_all_8_layers_4k.png`](layout/layer_09_all_8_layers_4k.png)
- **Transparent tracks (GND & PWR copper pours removed):** [`layer_10_tracks_transparent.svg`](layout/layer_10_tracks_transparent.svg) · [`layer_10_tracks_transparent_4k.png`](layout/layer_10_tracks_transparent_4k.png)

---

## 3. Vivado 2026.1 FPGA Silicon Floorplans & Schematics (`fpga/`)

Generated directly from post-route Vivado 2026.1 checkpoints ([`docs/FPGA_GATEWARE.md`](../../FPGA_GATEWARE.md)):

- **Artix-7 `XC7A50T-FTG256-2` Silicon Die Floorplan (`25,068` Slice LUTs, `28,881` FFs, `119` DSP48E1, `18` BRAM36 eq.):**
  - [`artix7_silicon_floorplan.pdf`](fpga/artix7_silicon_floorplan.pdf) · [`artix7_silicon_floorplan.svg`](fpga/artix7_silicon_floorplan.svg) · [`artix7_silicon_floorplan_4k.png`](fpga/artix7_silicon_floorplan_4k.png)
- **Artix-7 `artix_top` Post-Route Circuit Schematic:**
  - [`artix7_vivado_schematic.pdf`](fpga/artix7_vivado_schematic.pdf) · [`artix7_vivado_schematic.svg`](fpga/artix7_vivado_schematic.svg) · [`artix7_vivado_schematic_4k.png`](fpga/artix7_vivado_schematic_4k.png)
- **Kria K26 `XCK26-SFVC784-2LV-c` Silicon Die Floorplan (full `ias2rf_k26_bd` block design: `51,870` Slice LUTs, `44,547` FFs, `229` DSP48E2, `40` BRAM36 eq.):**
  - [`kria_k26_silicon_floorplan.pdf`](fpga/kria_k26_silicon_floorplan.pdf) · [`kria_k26_silicon_floorplan.svg`](fpga/kria_k26_silicon_floorplan.svg) · [`kria_k26_silicon_floorplan_4k.png`](fpga/kria_k26_silicon_floorplan_4k.png)
- **Kria K26 PS + PL `ias2rf_k26_bd` Block Design & PL Circuit Schematic:**
  - [`kria_k26_vivado_bd_schematic.pdf`](fpga/kria_k26_vivado_bd_schematic.pdf) · [`kria_k26_vivado_bd_schematic.svg`](fpga/kria_k26_vivado_bd_schematic.svg) · [`kria_k26_vivado_bd_schematic_4k.png`](fpga/kria_k26_vivado_bd_schematic_4k.png)
- **Dual-FPGA AERIS-10 Radar + Wideband SDR Signal-Chain Architecture:**
  - [`dsp_radar_sdr_pipeline_schematic.pdf`](fpga/dsp_radar_sdr_pipeline_schematic.pdf) · [`dsp_radar_sdr_pipeline_schematic.svg`](fpga/dsp_radar_sdr_pipeline_schematic.svg) · [`dsp_radar_sdr_pipeline_schematic_4k.png`](fpga/dsp_radar_sdr_pipeline_schematic_4k.png)

---

## 4. Hardware, Heatsink & Enclosure 4K Renders (`renders/`)

- **Bare Adapter PCB (`3840 × 2160` KiCad raytrace):**
  - [`board_iso_4k.png`](renders/board_iso_4k.png) · [`board_top_4k.png`](renders/board_top_4k.png) · [`board_bottom_4k.png`](renders/board_bottom_4k.png)
- **Heatsink Placement, Envelope & Sizing (`3840 × 2160` Cycles + Vector Map):**
  - [`board_heatsinks_4k.jpg`](renders/board_heatsinks_4k.jpg) (annotated 4K overview with ghosted `50 × 50 × 15 mm` overhead fan)
  - [`board_heatsinks_clean_4k.jpg`](renders/board_heatsinks_clean_4k.jpg) (clean 4K render without overlays)
  - [`board_heatsinks_closeup_4k.jpg`](renders/board_heatsinks_closeup_4k.jpg) (4K macro on `HS1`–`HS4` showing `4.0 mm` air gap between `HS2` `U401` and `HS3` `Y401`)
  - [`heatsink_mechanical_map.svg`](renders/heatsink_mechanical_map.svg) (vector CAD keep-out, height budget, and sizing table)
- **Enclosure v2 & KV260 Assembly (`3840 × 2160` Cycles OPTIX + Reference Views):**
  - [`case_v2_closed_4k.jpg`](renders/case_v2_closed_4k.jpg) · [`case_v2_open_4k.jpg`](renders/case_v2_open_4k.jpg) · [`case_v2_section_4k.jpg`](renders/case_v2_section_4k.jpg)
  - The 1600-px Enclosure v1/v2, FEA and mount views (`case_*.jpg`, `case3d_*.jpg`, `mount_*.jpg`) are in [`docs/img/`](..).
  - The Blender 4K views are published as JPEG (q90); their PNG masters stay out of the repository (`_work/mech/publish_4k.py`).

---

## 5. Signal & Power Integrity Vector Plots (`sim/`)

- [`eyes_1g.svg`](sim/eyes_1g.svg) · [`eye_openings.svg`](sim/eye_openings.svg) · [`lvds_skew.svg`](sim/lvds_skew.svg) · [`pdn_impedance.svg`](sim/pdn_impedance.svg) · [`sma_launch.svg`](sim/sma_launch.svg) · [`dac_filters.svg`](sim/dac_filters.svg)
