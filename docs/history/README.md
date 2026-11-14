# Design History & Revision Archive

This directory preserves the chronological engineering history, intermediate design audits, and stackup comparison studies that led to the production **KV260-IAS2RF** (8-layer simultaneous IAS1 + SGMII) hardware and gateware release on `main`.

## Chronological Evolution

| Revision | Milestone | Key Changes & Archived Records |
|---|---|---|
| **Rev01** | Initial Altium-imported MIPI draft | Superseded dual-IAS0/IAS1 direct-converter concept with unverified pin mappings and linear LDO dissipation issues. See [`AUDIT_Rev01.md`](AUDIT_Rev01.md) and [`HISTORY_Rev01.md`](HISTORY_Rev01.md). |
| **Rev02** | Blocker discovery & physical audit | Verified KV260 carrier schematic (`XTP682`), revealing `IAS0` terminates on the `AP1302` ISP, `IAS1` exposes 5 direct PL LVDS pairs, `M3SWA2-34DR+` requires bipolar `±3.3 V` supplies, and `AD9253` 1-lane caps at `62.5 MSPS`. Prompted the Artix-7 front-end FPGA architecture. |
| **Rev03** | Hierarchical 9-sheet schematic rebuild | Re-drew the complete system from datasheets across 9 hierarchical sheets (`IAS_LINK`, `CLOCK`, `ADC_RADAR`, `ADC_SDR`, `DAC_RADAR`, `DAC_SDR`, `ROUTING`, `CONTROL`, `POWER`) using `XC7A50T-FTG256`. |
| **Rev04** | 6-layer PCB & initial SI/PI extraction | First fully routed 6-layer board (`JLC06161H-2116A`) and openEMS/telegrapher SI/PDN extraction. |
| **Rev05** | 8-layer stackup upgrade & RF hardening | Upgraded to the **8-layer `JLC08161H-2116C`** stackup (`L2/L5/L7` solid ground planes), added stitched RF ground fences, automotive 12 V input protection (`LM74502-Q1` + back-to-back N-FETs + `SMCJ33CA`), ESD arrays (`PESD5V0F1BL` on SMAs, `TPD4E05U06` on Pmod/JTAG), and re-tuned 7th-order DAC reconstruction filters. See [`EIGHT_LAYERS.md`](EIGHT_LAYERS.md) and [`RF_REVIEW_EXTERNAL.md`](RF_REVIEW_EXTERNAL.md). |
| **Rev06 (Final on `main`)** | Simultaneous Dual-Link + Full Gateware + Enclosure v2 | Dedicated Bank 34/14 pins for `U1201` (`RTL8211FSI-CG`) `1.25 Gb/s` SGMII Gigabit Ethernet alongside the full 5-pair IAS1 LVDS link (`3 Gb/s` aggregate, `551` fitted parts, `0` DNP); low-DCR `FB401` clock bead; complete Artix-7 & Kria K26 Verilog gateware with physics-aware Vivado XSim E2E co-simulation; and CNC/3D-printed Enclosure v2 with decoupled heatsinks and 47 mm open-spoke intake. See [`REV06_REVIEW.md`](REV06_REVIEW.md). |

## Archived Documents & Plots

- [`AUDIT_Rev01.md`](AUDIT_Rev01.md) — Forensic audit of the original Rev01 schematics, BOM, and PCB.
- [`HISTORY_Rev01.md`](HISTORY_Rev01.md) — Record of the earliest design iterations prior to the Rev03 clean rebuild.
- [`EIGHT_LAYERS.md`](EIGHT_LAYERS.md) — Side-by-side comparison of the superseded 6-layer board against the 8-layer stackup (`sim/rev04_*.png`).
- [`RF_REVIEW_EXTERNAL.md`](RF_REVIEW_EXTERNAL.md) — Independent RF, signal integrity, PDN, and physical layout review that drove the filter re-tuning, ESD/TVS hardening, and dedicated Ethernet pinout.
- [`REV06_REVIEW.md`](REV06_REVIEW.md) — Final pre-tapeout hardware, thermal, mechanical FEA, and co-simulation signoff matrix comparing the final design against Rev05.
- [`sim/`](sim/) — Archived 6-layer vs 8-layer comparison figures (`rev04_eyes.png`, `rev04_eye_open.png`, `rev04_eye_penalty.png`, `rev04_skew.png`, `rev04_pdn.png`, `rev04_sma.png`), shared-pair Ethernet stub study (`eth_branches.png`), and before/after DAC filter comparison (`rev05_filters.png`).
