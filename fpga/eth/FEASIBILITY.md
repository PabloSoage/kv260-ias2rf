# Artix-7 SGMII-over-LVDS Feasibility Study (`XC7A50T-2FTG256I`)

**Target:** `XC7A50T-2FTG256I` (`-2` industrial speed grade, Bank 14 `VCCO = 3.3 V` RX / Bank 34 `VCCO = 2.5 V` TX) wired to the Rev04/Rev05 Ethernet BOM option (`U1201 RTL8211FSI-CG` via `C1218–C1221`, sharing `LINK_RX_D0` on `L4/M4` and `LINK_TX_D0` on `M16/N16`).

## 1. Executive Verdict

| Speed Grade | 1.25 Gb/s SGMII over SelectIO LVDS | Evidence | Fallback |
|---|---|---|---|
| **`-2` (`XC7A50T-2FTG256I`, board part)** | **FEASIBLE (Proven in Vivado 2026.1 + XSim)** | `DS181 Table 15` rates DDR LVDS TX/RX at **1250 Mb/s** on `-2`; Vivado `gig_ethernet_pcs_pma:17.0` accepts `Physical_Interface=LVDS` on `-2`; routed PoC closes timing (`WNS = +0.137 ns`, `WHS = +0.082 ns`, `WPWS = +0.008 ns`, `0` DRC errors); XSim passes `±100 ppm` PRBS-7 (`0` bit errors over `60,000` bits) | `100 Mb/s` SGMII (`10×` symbol repetition fallback) |
| **`-1` (downgraded silicon)** | **NOT FEASIBLE at 1.25 Gb/s** | `DS181 Table 15` caps `-1` DDR LVDS TX/RX at **950 Mb/s**; `-1` `BUFG` max is `464 MHz` (`Table 32`); `-1` `BUFIO`/`IDELAY` max is `600 MHz` (`Table 33`/`25`); Vivado `gig_ethernet_pcs_pma:17.0` rejects `LVDS` on `-1` (`IP_Flow 19-3461`) | **`100 Mb/s` SGMII mandatory** |

Previous assumptions treated 1.25 Gb/s SGMII-over-LVDS on `-2` Artix-7 as unviable without GTP transceivers. On `-2`, both Xilinx/AMD characterization (`DS181`), Vivado IP customization (`gig_ethernet_pcs_pma:17.0`), routed static timing (`fpga/eth/test/reports/`), and asynchronous cycle-level simulation (`tb_sgmii_lvds`) confirm that **1.25 Gb/s SGMII over SelectIO LVDS works on `XC7A50T-2FTG256I`**.

---

## 2. Primary-Source Characterization (`DS181`, `XAPP523`, `PG047`)

### 2.1 Verbatim Citations from `DS181` (v1.27, Feb 10, 2022)

Extracted directly from `_work/datasheets/DS181.pdf`:

- **Table 15: Networking Applications Interface Performances** (p. 15):
  > `SDR LVDS transmitter (using OSERDES; DATA_WIDTH = 4 to 8)`: `-3` = `680`, `-2/-2LE` = `680`, `-1` = `600`, `-1LI` = `600`, `-2LE (0.9V)` = `600 Mb/s`  
  > `DDR LVDS transmitter (using OSERDES; DATA_WIDTH = 4 to 14)`: `-3` = `1250`, `-2/-2LE` = `1250`, `-1` = `950`, `-1LI` = `950`, `-2LE (0.9V)` = `950 Mb/s`  
  > `SDR LVDS receiver (SFI-4.1)(1)`: `-3` = `680`, `-2/-2LE` = `680`, `-1` = `600`, `-1LI` = `600`, `-2LE (0.9V)` = `600 Mb/s`  
  > `DDR LVDS receiver (SPI-4.2)(1)`: `-3` = `1250`, `-2/-2LE` = `1250`, `-1` = `950`, `-1LI` = `950`, `-2LE (0.9V)` = `950 Mb/s`  
  > `Notes: 1. LVDS receivers are typically bounded with certain applications where specific dynamic phase-alignment (DPA) algorithms dominate deterministic performance.`

- **Table 11: LVDS_25 DC Specifications(1)** (p. 11):
  > `VCCO Supply Voltage`: Min `2.375`, Typ `2.500`, Max `2.625 V`  
  > `VODIFF Differential Output Voltage`: Min `247`, Typ `350`, Max `600 mV` (`RT = 100 Ω`)  
  > `VIDIFF Differential Input Voltage`: Min `100`, Typ `350`, Max `600 mV`; `VICM`: Min `0.300`, Typ `1.200`, Max `1.500 V`  
  > `Notes: 1. Differential inputs for LVDS_25 can be placed in banks with VCCO levels that are different from the required level for outputs. Consult the 7 Series FPGAs SelectIO Resources User Guide (UG471) for more information.`  
  *(Matches our PCB: Bank 34 TX outputs at `VCCO = 2.5 V`, Bank 14 RX inputs at `VCCO = 3.3 V` with `DIFF_TERM = FALSE` and external `100 Ω` + AC coupling `C1218/C1219`.)*

- **Table 23: ISERDES Switching Characteristics** (p. 24):
  > `TISDCK_DDLY_DDR / TISCKD_DDLY_DDR` (DDLY pin setup/hold with respect to CLK at DDR mode using IDELAY, Note 1: `Recorded at 0 tap value`): `-3` = `0.12/0.12 ns`, **`-2/-2LE` = `0.14/0.14 ns`**, `-1` = `0.17/0.17 ns`.  
  > `TISCKO_Q` (CLKDIV to out at Q pin): `-3` = `0.53 ns`, **`-2/-2LE` = `0.54 ns`**, `-1` = `0.66 ns`.

- **Table 24: OSERDES Switching Characteristics** (p. 25):
  > `TOSCKO_OQ` (Clock to out from CLK to OQ): `-3` = `0.40 ns`, **`-2/-2LE` = `0.42 ns`**, `-1` = `0.48 ns`.  
  > `TOSDCK_D / TOSCKD_D` (D input setup/hold with respect to CLKDIV): `-3` = `0.42/0.03 ns`, **`-2/-2LE` = `0.45/0.03 ns`**, `-1` = `0.63/0.03 ns`.

- **Table 25: Input/Output Delay Switching Characteristics** (p. 26):
  > `FIDELAYCTRL_REF` (`Attribute REFCLK frequency = 200.00(1)`): `200.00 MHz`; Note 1: `Average Tap Delay at 200 MHz = 78 ps, at 300 MHz = 52 ps, and at 400 MHz = 39 ps.`  
  > `TDLYCCO_RDY` (Reset to ready for IDELAYCTRL): `3.67 µs`.  
  > `TIDELAYPAT_JIT` (`PRBS 23`, Note 3: `HIGH_PERFORMANCE mode = TRUE`): **`±5 ps per tap`**.  
  > `TIDELAY_CLK_MAX` (Maximum frequency of CLK input to IDELAY): `-3` = `680.00 MHz`, **`-2/-2LE` = `680.00 MHz`**, `-1` = `600.00 MHz`.

- **Table 32 & Table 33: Clock Buffers** (p. 36):
  > `FMAX_BUFG` (Global clock tree): `-3` = `628.00 MHz`, **`-2/-2LE` = `628.00 MHz`**, **`-1` = `464.00 MHz`**.  
  > `FMAX_BUFIO` (I/O clock tree): `-3` = `680.00 MHz`, **`-2/-2LE` = `680.00 MHz`**, **`-1` = `600.00 MHz`**.

- **Table 37: MMCM Specification** (p. 38):
  > `MMCM_FVCOMAX`: `-3` = `1600.00 MHz`, **`-2/-2LE` = `1440.00 MHz`**, **`-1` = `1200.00 MHz`**. (`1250 MHz` VCO for `625 MHz` CLKOUT fits `-2` and `-3`, and exceeds `-1`'s `1200 MHz` limit.)  
  > `MMCM_FOUTMAX`: `800.00 MHz` (`-3`, `-2/-2LE`, `-1`).  
  > `MMCM_TSTATPHAOFFSET`: `0.12 ns`.

- **Table 48: Sample Window** (pp. 47–48) & **Table 49: Package Skew** (p. 48):
  > `TSAMP` (MMCM capture): `-3` = `0.59 ns`, **`-2/-2LE` = `0.64 ns`**, `-1` = `0.70 ns`.  
  > `TSAMP_BUFIO` (BUFIO + IDELAY): `-3` = `0.35 ns`, **`-2/-2LE` = `0.40 ns`**, `-1` = `0.46 ns`.  
  > `TPKGSKEW` (`XC7A50T FTG256`): **`98 ps`**.

### 2.2 `XAPP523`, `PG047`, and Vivado `gig_ethernet_pcs_pma:17.0` Verification

- **Document availability note:** The `XAPP523` (*LVDS 4x Asynchronous Oversampling Using 7 Series FPGAs*) and `PG047` (*1G/2.5G Ethernet PCS/PMA or SGMII LogiCORE IP*) PDFs are distributed on AMD's website behind web-gated/JS delivery and are **not stored in `_work/datasheets/`**, so verbatim prose excerpts could not be extracted directly from those PDFs. Web summaries corroborate `XAPP523` 4x asynchronous oversampling (`625 MHz` `CLK`/`CLK90` DDR into `ISERDESE2`) and `PG047` requiring `-2` or faster for Artix-7 SGMII over LVDS.
- **Direct local verification in Vivado `2026.1` (`gig_ethernet_pcs_pma_v17_0`):** Vivado ships the full Series-7 LVDS SGMII templates (`D:\AMDDesignTools\2026.1\Vivado\data\ip\xilinx\gig_ethernet_pcs_pma_v17_0\ttcl\series7_sgmii_lvds\sgmii_phy_iob_k7_v.ttcl`, `sgmii_eye_monitor_k7_v.ttcl`, `gearbox_6b_10b_k7_v.ttcl`, `gearbox_10b_6b_k7_v.ttcl`, `sgmii_comma_alignment_lvds_k7_v.ttcl`). Running `create_ip` + `set_property` in Vivado `2026.1` batch directly proves AMD's IP support matrix:
  - `xc7a50tftg256-2`: `CONFIG.Standard=SGMII`, `CONFIG.Physical_Interface=LVDS` -> **accepted (`rc = 0`)**.
  - `xc7a50tftg256-3`: `CONFIG.Standard=SGMII`, `CONFIG.Physical_Interface=LVDS` -> **accepted (`rc = 0`)**.
  - `xc7a50tftg256-1`: `CONFIG.Standard=SGMII`, `CONFIG.Physical_Interface=LVDS` -> **rejected (`rc = 1`)** with `ERROR: [IP_Flow 19-3461] Value 'LVDS' is out of the range for parameter 'Physical Interface(Physical_Interface)' for IP 'test_sp' . Valid values are - TBI`.

---

## 3. Proof-of-Concept Architecture (`fpga/eth/test/sgmii_lvds_test.v`)

To prove feasibility independently of encrypted AMD IP, a standalone open-source SGMII-over-LVDS SERDES PoC (`sgmii_lvds_test`) targeting the exact Rev04/Rev05 pins (`xc7a50tftg256-2`) was implemented and verified:

```
fpga_clk (100 MHz, N11/N12)
  └─ MMCME2_ADV (FVCO = 1250 MHz)
       ├─ CLKOUT0 = 200.0 MHz  ──> IDELAYCTRL (IODELAY_GROUP="bank14_idelay_grp")
       ├─ CLKOUT1 = 625.0 MHz 0° ─> Master & Shadow ISERDESE2 CLK, OSERDESE2 CLK (BUFG)
       ├─ CLKOUT2 = 625.0 MHz 90°─> Master & Shadow ISERDESE2 CLKB (inverted=0, 90° lag)
       ├─ CLKOUT3 = 312.5 MHz 0° ─> ISERDESE2/OSERDESE2 CLKDIV, DRU + 3/4/5->10 gearbox
       ├─ CLKOUT4 = 312.5 MHz 45°─> Shadow ISERDESE2 CLKDIV + phase-crossing flops
       └─ CLKOUT5 = 125.0 MHz    ─> Dual-clock async FIFO read, 10b K28.5 barrel shifter, PRBS-7

sgmii_rx_p/n (M16/N16, Bank 14, DIFF_TERM=FALSE)
  └─ IBUFDS_DIFF_OUT (O -> Master P, OB -> Shadow N inverted internally)
       ├─ Master IDELAYE2 (tap_m, VAR_LOAD) ─> ISERDESE2 (DDR 4-bit: 0°, 90°, 180°, 270°)
       └─ Shadow IDELAYE2 (tap_s, VAR_LOAD) ─> ISERDESE2 (DDR 4-bit @ clk_312p5_45)

tx_prbs7 (clk_125) ─> 10b->8b gearbox (clk_312p5) ─> OSERDESE2 (8:1 DDR @ 625 MHz) ─> OBUFDS (L4/M4, Bank 34)
```

- **XAPP523 4x Oversampling & Drift Tracking (`sgmii_lvds_rx`):** At `1.25 Gb/s` (`1 UI = 800 ps`), `625 MHz` `0°/90°` samples every `200 ps` (`4×` per bit). The master channel holds a fixed phase (`tap_m`) while the shadow channel sweeps `tap_s` (`0..15`, `~78 ps/tap`) plus the `45°` (`~400 ps`) `CLKDIV` offset, verifies a clean window over a `32`-cycle dwell, hands master ownership (`shadow_is_master`) cleanly between the two `IBUFDS_DIFF_OUT` paths on frequency drift (`±100 ppm`), and outputs `3`, `4`, or `5` recovered bits per `312.5 MHz` cycle into a 10-bit packing gearbox and dual-clock Gray-coded async FIFO into `125 MHz`.
- **Clock-rate separation for `clk_312p5` closure:** All high-fanout 20-bit K28.5 (`10'h17C` / `10'h283`) comma-alignment shifting and PRBS-7 error popcounting run in the `125 MHz` (`8.0 ns`) domain, leaving only the compact 10-bit packer and Gray FIFO write logic at `312.5 MHz` (`3.2 ns`).

---

## 4. Vivado `2026.1` Routed Timing, Utilization, and DRC (`xc7a50tftg256-2`)

Built non-project from `fpga/eth/test/build.tcl` (`synth_design`, `opt_design`, `place_design`, `phys_opt_design`, `route_design`). Reports committed under `fpga/eth/test/reports/` (no `.dcp` checkpoints committed):

| Metric | Result | Target / Limit | Source Report |
|---|---|---|---|
| **Worst Negative Slack (`WNS`)** | **`+0.137 ns`** | `≥ 0.000 ns` | `reports/timing_summary.rpt` (`clk_312p5_u`, 1075 endpoints, `0` failing) |
| **Worst Hold Slack (`WHS`)** | **`+0.082 ns`** | `≥ 0.000 ns` | `reports/timing_summary.rpt` (1042 endpoints, `0` failing) |
| **Worst Pulse Width Slack (`WPWS`)** | **`+0.008 ns`** | `≥ 0.000 ns` | `reports/pulse_width.rpt` (`407` endpoints, `0` failing) |
| **Setup critical path** | `2.547 ns` data (`4` LUTs) | `3.200 ns` period | `u_sgmii_rx/wr_ptr_bin_reg[0]/C` → `fifo_mem_reg_0_31_6_9/RAMA/WE` |
| **Async FIFO read (`clk_312p5_u` → `clk_125_u`)** | **`+1.235 ns`** | `3.000 ns` `-datapath_only` | `reports/timing_summary.rpt` (`RAMD32/CLK` → `fifo_word_q_reg[6]/D`) |
| **125 MHz domain (`clk_125_u`)** | **`+2.765 ns` WNS / `+0.121 ns` WHS** | `8.000 ns` period | `reports/timing_summary.rpt` (`536` endpoints) |
| **Pulse width bottleneck (`625 MHz` BUFG)** | `1.600 ns` vs `1.592 ns` min | `628.00 MHz` max (`DS181 Table 32`) | `u_bufg_625_0/I` & `u_bufg_625_90/I` (`WPWS = 0.008 ns`) |
| **DRC (`report_drc`)** | **`0` violations** | `0` | `reports/drc.rpt` (`Checks found: 0`) |
| **Methodology (`report_methodology`)** | `4` Warnings, `0` Critical | Informational | `reports/methodology.rpt` (`1x LUTAR-1`, `1x TIMING-9`, `2x TIMING-47`) |
| **Logic Utilization** | **`287` LUTs (`279` Logic, `8` LUTRAM), `364` FFs, `0` BRAM, `0` DSP** | `32,600` LUT / `65,200` FF (`0.88%` / `0.56%`) | `reports/utilization.rpt` (`u_sgmii_rx` = `260` LUTs, `271` FFs) |

**Integration note on `625 MHz` BUFG margin (`0.008 ns`):** Routing `625 MHz` over `BUFG` meets `DS181 Table 32` (`FMAX_BUFG = 628.00 MHz`) cleanly in Vivado with `8 ps` pulse-width slack, which is tight across process/placement if clocks cross CMT columns (`MMCME2_ADV_X1Y0` → `IDELAY_X0Y35`). In production top-level integration inside `artix_top`, placing the SGMII MMCM in Bank 14's local CMT (`X0Y0`) and driving the `625 MHz` `CLK`/`CLK90` `ISERDESE2` inputs via **`BUFIO`** (`FMAX_BUFIO = 680.00 MHz`, `DS181 Table 33`) instead of `BUFG` raises pulse-width margin from `8 ps` (`3 MHz`) to `130 ps` (`55 MHz`) and reduces `TSAMP` from `0.64 ns` to `0.40 ns` (`DS181 Table 48`).

---

## 5. Bank 14 `IDELAYCTRL` & `adc_capture` Coexistence

In `fpga/artix/top.v` and `fpga/artix/adc_capture.v`, the AD9484 radar ADC (`adcr_d[7:0]`, `adcr_or`, `adcr_dco`) and the IAS1 downlink pair (`link_tx_d0` on `M16/N16`) share **Bank 14** (`VCCO = 3.3 V`, `DIFF_TERM = FALSE`):

1. **Single `IDELAYCTRL` per bank / group:** `adc_capture.v` already exposes parameter `INST_IDELAYCTRL` (`1` by default, `0` when shared at top) and tags all `IDELAYE2` primitives with `(* IODELAY_GROUP = "bank14_idelay_grp" *)`, driven by `refclk_200m = 200.0 MHz` (`~78 ps/tap`). `sgmii_lvds_rx` uses the exact same `IODELAY_GROUP = "bank14_idelay_grp"` and `REFCLK_FREQUENCY = 200.0`, so **one `IDELAYCTRL` calibrates both the AD9484 `IDELAYE2`s and the SGMII `M16/N16` master/shadow `IDELAYE2`s** (with `IDELAYCTRL` instantiated once at `artix_top` and `INST_IDELAYCTRL = 0` on `u_adc_cap`).
2. **Independence of dynamic `LD`/`CNTVALUEIN` tap updates:** Continuous DRU phase tracking in `sgmii_lvds_rx` asserts `LD` (`tap_ld_m`/`tap_ld_s` clocked by `clk_312p5`) on the `M16/N16` `IDELAYE2` primitives only. `IDELAYCTRL` continuously servo-locks an analog bias reference across the Bank 14 I/O tile from `200 MHz REFCLK` without reading or resetting per-pin `CNTVALUEIN` delay registers, and per `DS181 Table 25`, `312.5 MHz` is well below `TIDELAY_CLK_MAX = 680.00 MHz`. Thus **SGMII shadow-channel sweeping cannot disturb `adc_capture`'s trained AD9484 sample taps**, provided `IDELAYCTRL.RST` is asserted only during chip reset and never toggled at runtime.
3. **MMCM sharing in `artix_top`:** `XC7A50T-FTG256` has **5 MMCMs** (Vivado `get_parts` query): `artix_top` currently uses 2 (`u_mmcm_sys` at `1000 MHz` VCO for `125/500/200 MHz`, and `u_mmcm_adc` in `adc_capture`), leaving **3 MMCMs free**. Notice `1250 MHz / 200 MHz = 6.250` fits on `MMCME2_ADV.CLKOUT0_DIVIDE_F` (`0.125` granularity, as proven in `sgmii_lvds_test.v`), so an Ethernet MMCM (`1250 MHz` VCO) can even supply the shared `200 MHz REFCLK` for Bank 14, or reuse `u_mmcm_sys`'s `200 MHz REFCLK` while running an independent `1250 MHz` VCO MMCM for the `625/312.5/125 MHz` SGMII clocks.

---

## 6. XSim Oversampling Simulation (`tb_sgmii_lvds`)

Verified with `.\fpga\sim\run.ps1 tb_sgmii_lvds` (0 errors required across `±100 ppm` crystal offset, plus mandatory failure under mutation `-Mutate no_phase_select`):

| Test Run | Parameters | Result | Observed Log Output |
|---|---|---|---|
| **Baseline pass** | `ui = 799.920 ps` (`+100 ppm`), `ui = 800.080 ps` (`-100 ppm`), PRBS-7 stream + K28.5 (`10'h17C`) comma preamble | **PASS (exit 0)** | `CASE 1 (ui=799.920 ps): comma=1 prbs_lock=1 words=2976 err=0 switches=7`<br>`CASE 2 (ui=800.080 ps): comma=1 prbs_lock=1 words=2977 err=0 switches=6`<br>`PASS: tb_sgmii_lvds (+100/-100 ppm 60,000 bits, 0 errors)` |
| **Mutation check** (`-Mutate no_phase_select`) | Shadow/master phase handover disabled (`DISABLE_PHASE_TRACK=1`) | **FAIL as required (exit 1)** | `CASE 1 (ui=799.920 ps): comma=1 prbs_lock=0 words=0 err=15222 switches=0`<br>`FAIL: tb_sgmii_lvds case 1 (ui=799.920 ps) err=15222 locked=0 sw=0` |

Note why `switches=7` and `switches=6` appear cleanly without bit loss: over `3,000 × 8 ns = 24 µs` at `±100 ppm` (`±2.4 ns` = `±3.0 UI` drift), the shadow tracker seamlessly transfers sample phase ownership before hitting the edge of the eye window, producing `0` dropped or corrupted 10b symbols across the full `60,000`-bit run. Disabling phase selection immediately loses lock (`15,222` errors).

---

## 7. Retained Fallback: 100 Mb/s SGMII (`10×` Symbol Oversampling)

The `100 Mb/s` SGMII fallback remains valid and trivial to activate if a design ever drops to `-1` silicon or faces severe channel distortion:

- In IEEE/Cisco SGMII 100BASE-TX mode, the `RTL8211FSI` repeats every `1.25 Gb/s` 8b/10b symbol **10 consecutive times** (a `10×` oversampled `125 Mb/s` effective symbol stream, where each SGMII "bit" at `125 Mb/s` is `8 ns` wide on `M16/N16`).
- On the Artix-7, sampling at `500 MHz` DDR (`2 ns` steps) gives `4×` oversampling of the `125 Mb/s` symbol stream (`8 ns` UI), or `625 MHz` gives `5×` oversampling per symbol, eliminating `BUFG`/`MMCM` `625 MHz` frequency pressure (`-1` easily closes timing at `250–312.5 MHz` DDR) while reducing usable Ethernet payload throughput from **`~118 MB/s`** (`1000BASE-T`) to **`~11.8 MB/s`** (`100BASE-TX`).
