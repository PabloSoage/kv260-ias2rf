# Hardware, RF, Signal Integrity & Physical Design Review — CSI2-KRIA-KV260_Rev01

**Reviewer:** Gemini (Gateware & Hardware Verification Audit)  
**Target:** `CSI2-KRIA-KV260_Rev01.kicad_pcb`, `CSI2-KRIA-KV260_Rev01.kicad_sch`, `rev03/*.kicad_sch`, `CSI2-KRIA-KV260_Rev01.kicad_dru`, `CSI2-KRIA-KV260_Rev01-erc.rpt`, and `docs/*.md`  
**Verification Scripts:**
- [`fpga/review/parse_pcb_rf_audit.py`](../fpga/review/parse_pcb_rf_audit.py) — deterministic S-expression extraction of stackup, zone boundaries, via fences, exposed-pad thermal vias, SMA launch order, differential pair lengths/skews/split-plane crossings, and schematic netlists across all 9 sheets.
- [`fpga/review/calc_rf_si_margins.py`](../fpga/review/calc_rf_si_margins.py) — closed-form analytical EM (Hammerstad-Jensen microstrip, Wadell CBCPW, Cohn/Wheeler conformal asymmetric stripline), 2-port ABCD ladder filter analysis, Friis/IIP3 RF cascades, aperture-jitter SNR, automotive ISO pulse withstand, and thermal junction estimates.

---

## Executive Summary & Methodology

**Overall Assessment:** **NO-GO for Rev01 fabrication / field deployment without targeted fixes.**  
While the 8-layer `JLC08161H-2116C` stackup (`140.0 x 132.0 x 1.5416 mm`), SMA launch keepouts (`In1.Cu..In5.Cu` cleared above `In6.Cu` `L7` GND), and high-pin-count ADC thermal pads (`U501` = 18 vias, `U601` = 19 vias) demonstrate solid RF intent, quantitative inspection uncovered **2 BLOCKER** defects (one guarantees semiconductor failure on external `10 MHz` ref mode; the other destroys the reverse-polarity FET under inductive automotive/UAV transients), **7 HIGH** defects (notably uncoupled / cross-layer routing of `1 Gbps` LVDS `LINK_RX_D0/D1` and `1.25 Gbps` SGMII `ETH_SGRX_PHY` with `9.369 mm` skew, violated Artix-7 power sequencing, buck-fed gain/clock rails without LDO isolation, `1`-via thermal pad on `U1201`, and `POFV`/stackup contradictions against fabrication docs), and **4 MEDIUM** issues.

No `.kicad_pcb` or `.kicad_sch` files were modified during this review. All PCB and schematic metrics below come directly from parsing the Rev01 design files and vendor datasheets. Every calculation can be reproduced offline via:

```bash
python fpga/review/parse_pcb_rf_audit.py
python fpga/review/calc_rf_si_margins.py
```

---

## Master Findings Summary Table

| ID | Severity | Section | Target / Refdes | Finding Summary | Required Action |
|---|---|---|---|---|---|
| **B1** | **BLOCKER** | §6 | `Q1001` (`DMP3013SFV`), `D1001` (`SMBJ15CA`) | Reverse-polarity PFET `Q1001` (`V_DSS = -30 V` max) sits **upstream** of TVS `D1001`. An `ISO 7637-2 Pulse 1` (`-100 V` to `-150 V`) applies `|V_DS| = 112–162 V` across `Q1001` before `D1001` clamps; `SMBJ15CA` also absorbs `12.9–152.7 J` under Load Dump vs `~1.5 J` 100 ms capability. | Place automotive bi-directional/uni-directional TVS (`SMCJ18A`/`SM8S18A` or eFuse `LM74800` + TVS) **upstream** of `Q1001`, or replace `Q1001` with `>= 60–100 V` PFET + series ideal-diode controller protected at input. |
| **B2** | **BLOCKER** | §3 | `C414..C421` (`100 pF`), `U401` (`ADCLK948`) | Series `100 pF` AC-coupling caps on all four `U401` LVPECL outputs into `50 ohm` per-leg load create an **`f_c(-3 dB) = 31.83 MHz`** HPF corner. Passing an external `10 MHz` ref suffers **`-10.47 dB` attenuation**, collapsing receiver swing below reliable triggering. | Replace `C414..C421` with `10 nF–100 nF` C0G/X7R (`0402`, `f_c <= 318 kHz`, `< 0.005 dB` loss at `10 MHz`). Keep `U401 CLK0` pins 2–4 tied to `C413` (`100 nF`) as already wired (confirmed internal `50 ohm` termination active). |
| **H1** | **HIGH** | §4 | `LINK_RX_D0/D1`, `LINK_TX_CLK/D0`, `ETH_SGRX_PHY` | High-speed pairs are largely **uncoupled**: `LINK_RX_D0` (`0.0/121.8 mm` coupled, `84.2 mm` on `F.Cu` @ `0.183 mm`, `2.5–13.2 mm` gap), `LINK_RX_D1` (`0.0/95.8 mm` on `F.Cu`), `LINK_TX_CLK` (`0.0/72.1 mm`, P/N split `In2/In5`), `LINK_TX_D0` (`4.8/69.1 mm`, `4.148 mm` end-to-end skew), `ETH_SGRX_PHY` (`0.8/55.9 mm`, `P` `B.Cu` vs `N` `In5/In2`, **`9.369 mm` = `63.8 ps` / `8.0%` UI skew**, `6.39 mm` return via gap). | Route all `LVDS100` (`500 MHz` DDR / `1 Gbps`) and `SGMII` (`1.25 Gbps`) pairs strictly edge-coupled on inner stripline (`In2.Cu` or `In5.Cu`, `w=0.10 mm`, `s=0.15 mm`, `Z_diff = 107.9 ohm`) with length matching `<= 0.5 mm` and return vias `< 1.0 mm` at every layer transition. |
| **H2** | **HIGH** | §5 | `U1002`, `U1003`, `U1004`, `U1101` (`XC7A50T`) | All three buck `EN` pins (`+3V3_D`, `+2V5`, `+1V0`) pull directly to `+5V0` via `10k`, causing simultaneous unconstrained power-up and violating Xilinx `DS181` Artix-7 monotonic sequence (`VCCINT -> VCCBRAM -> VCCAUX -> VCCO`). | RC-delay or PGOOD-daisy-chain buck `EN` pins (`U1004 +1V0` PG -> `U1006 +1V8_D` -> `U1003 +2V5` / `U1002 +3V3_D`). |
| **H3** | **HIGH** | §2, §3, §5 | `U502/U503`, `U602/U603`, `U401`, `Y401` | Analog IF gain chain (`+5V_IFR`, `+5V_IFS` driving `AD8352` stages up to `25 dB` gain) and clock distribution (`+3V3_CLK` driving `Si549` + `ADCLK948`) connect directly to switching bucks (`+5V0` `400 kHz`, `+3V3_D` `580 kHz`) through `600R@100MHz` ferrites only (`<10 ohm` at switching fundamental) without LDOs. | Feed `+3V3_CLK` from clean `+3V3_A` (or dedicated low-noise LDO) and filter/post-regulate `+5V_IFR/+5V_IFS` from a higher intermediate rail or dedicated LC pi filter (`>= 40 dB` @ `400 kHz`). |
| **H4** | **HIGH** | §3, §4 | `U401-CLK0`, `U401-Q3`, `Y401`, `CLK_ADCS`, `CLK_FPGA` | `U401-CLK0` (`74.48 mm`) and `U401-Q3` (`79.79 mm`) route single-ended on `In2.Cu` directly across digital `+3V3_D` and `In3.Cu` splits (`+3V3_D/+5V_IFR/+3V3_CLK`). `Y401` clock vias sit `3.04/4.01 mm` from nearest GND via; `CLK_ADCS` has `4.660 mm` (`31.7 ps`) skew; `CLK_FPGA` (`3.578 mm` skew) crosses `+3V3_CLK` split on `In3.Cu`. | Move `CLK0`/`Q3` away from `+3V3_D` onto microstrip/CPWG over solid `L2` GND (`In1.Cu`), place adjacent GND vias `< 1 mm` from `Y401` transition vias, and deskew `CLK_ADCS`/`CLK_FPGA` to `< 0.5 mm`. |
| **H5** | **HIGH** | §4, §8 | `ADCS_*`, `ADCR_D0/D5/OR`, `J1103` (`2x20`) | `ADCS_D0/D1/DCO/FCO` are `0–4%` coupled across mixed `F.Cu`/`B.Cu`/`In5.Cu` (`2.749 mm` `FCO` skew); `ADCR_D0/D5/OR` and `ADCS_D0/DCO` cross `In3.Cu` power-plane splits. `J1103` carries **`35` single-ended `1.8 V` signals with only `5` GND pins** (all clustered on pins 34/36/38/39/40; **zero GND in pins 1–33**) and zero series damping. | Re-route `ADCS_*` identically to `ADCR_*` (`w=0.10/s=0.15 mm` coupled), avoid `In3.Cu` splits or ensure tight return vias to `In1`/`In4` GND; add interleaved GND pins on `J1103` (at least `1:2` GND:signal) + `22–33 ohm` series resistors. |
| **H6** | **HIGH** | §7 | `U1201` (`RTL8211FSI-CG`), `U603`, `U602` | `U1201` (`4.4 x 4.4 mm` EP, `~450 mW`) has only **1 thermal via** (`r4=3`), raising effective `theta_JA` to `~65 C/W` (`T_j ~ 99 C` at `70 C` ambient). `U603` (`AD8352`) has `2` EP vias (`r4=5`); `U602` has `3` EP vias. | Populate `3x3` (`9+`) filled/capped thermal vias (`0.2–0.3 mm`) inside `U1201` EP and `4–5` vias in `U602/U603` EPs. |
| **H7** | **HIGH** | §9, §10 | PCB Mechanics, `FABRICATION.md`, `JLCPCB_QUOTE.md` | `J101/J102` sit **`26.65 mm` cantilevered south** of `H1/H2` (`y = 85.60` vs `112.25 mm`); `97.5 mm` `Y`-span bare FR4 `f0 ~ 258 Hz` drops steeply under KV260 mass. Docs/CAD conflict: `FABRICATION.md` (`3313` `0.100 mm`, `0.25/0.50 mm` vias) vs PCB (`2116` `0.1194/0.1300 mm`, `0.20/0.45 mm` vias); `.kicad_pcb` has `capping=no, filling=no` despite `POFV` quote; **8 BOM stockouts**. | Add two `M2.5/M3` mounting standoffs flanking `J101/J102`; enable IPC-4761 VII (`capping=yes, filling=yes`) in KiCad setup; synchronize `FABRICATION.md` to `JLC08161H-2116C`; qualify alternates for 8 out-of-stock parts. |
| **M1** | **MEDIUM** | §2 | `T701/T801/T802` (`ADT2-1T+`), DAC LPF (`107.3 nH`/`106 pF`) | `ADT2-1T+` lower `-3 dB` edge is `0.4 MHz` typ (`~4x` above `0.1 MHz` SDR lower target); exact ABCD LPF model (`44p / 214.6n / 106p / 214.6n / 33p`) gives **`f_c(-3 dB) = 69.7 MHz`** with **`2.04 dB` passband ripple (`S11 = -4.27 dB` @ `30 MHz`)** and `-34.3 dB` at `120 MHz`. `T801` secondary legs differ by `9.75 mm` (`2.68 deg` @ `120 MHz`). | Swap baluns to wideband TC2-1T+/ADT1-1WT (`0.05–400 MHz`) if `< 400 kHz` TX/RX is required; re-synthesize DAC filter for `100 ohm` differential image impedance (E24/E12 parts); match `T801` secondary leg lengths within `< 1 mm`. |
| **M2** | **MEDIUM** | §1, §2 | `IF_RX_A/B/C`, `IF_TX_A/B`, `R501/601/621` | `L1` GND pour ends at `y = 199.60 mm` (`54.82 -> 50.29 ohm` step, `RL = -27.3 dB`), leaving `IF_TX_B` (`111.65 mm`, `0.50 dB` loss @ `250 MHz`) as bare microstrip; `IF_RX_B` dips onto `In2.Cu` (`6.94 mm`) over `In3.Cu` (`+5V_IFR`/`+3V3_D` split). `64.9R || 3k = 63.53 ohm` gives `RL = -18.48 dB` (`VSWR = 1.27`). | Extend fenced CPWG (`g = 0.25–0.30 mm` for `52–53 ohm`) along RF channels, keep `IF_RX_B` off `In2.Cu` over split planes, and verify whether `64.9 ohm` shunt matches intended input VSWR. |
| **M3** | **MEDIUM** | §8, §9 | `J1001` (`PJ-102AH`), `J1102/1103`, `U1201`/`Y1201`, SMAs | Barrel jack `PJ-102AH` and unlatched headers (`J1102/1103`) lack vibration locking for UAV flight; `Y1201` (`25 MHz` XTAL) sits `11.14 mm` from `U401` (`15.77 mm` from `Y401`). `8.50 mm` SMA pitch leaves `0.50 mm` radial clearance for `8.0 mm` hex torque wrenches. | Use locking power/shrouded headers (`XT30`/`Molex Nano-Fit`, keyed box header with ejectors); increase SMA pitch to `>= 9.5–10.0 mm` or stagger wrenches; shield/relocate `Y1201` further from `Y401/U401`. |
| **M4** | **MEDIUM** | §4 | `IAS_LINK` (`R105/106`, `R101..104`) | Schematic text/doc refers to `2x49.9 ohm` split termination, whereas PCB/BOM populates single `R105/R106 = 100 ohm` across the pair with `10k` (`R101..104`) pull-bias to `+1V2`. (`100 ohm` differential is valid; weak VCM bias.) | Align schematic note/spec with `100 ohm` diff + `10k` bias (or populate `2x49.9 ohm` center-tapped if tight AC common-mode rejection is desired). |
| **L1** | **LOW** | §10 | `DAC_*`, `.kicad_pcb` vias, ERC | Non-E-series values (`107.3 nH`, `106 pF`) complicate procurement; `777` of `2177` `0.45/0.20 mm` vias lack tenting flags (`1400` tented); ERC retains `7` benign pin-type warnings (`CFGBVS_0`, unused XADC). | Round DAC LPF values to standard E24 values (`100 nH`/`110 nH`, `100 pF`/`33 pF`/`22 pF`) after ABCD re-optimization; apply uniform tenting/POFV rules; attach explicit no-connect/`PWR_FLAG` to silence ERC warnings. |

---

## Detailed Engineering Audit (Sections 1–10)

### 1. Stackup, CPWG, Asymmetric Stripline & Via Transitions
* **Stackup (`JLC08161H-2116C`) [PASS / WARN]:** `140.0 x 132.0 x 1.5416 mm` 8-layer buildup: `F.Cu` (`0.035 mm`) — `d1 = 0.1194 mm` (`Er = 4.29`) — `In1.Cu GND` (`0.0152 mm`) — `d2 = 0.1300 mm` (`Er = 4.17`) — `In2.Cu Sig` — `d3 = 0.3658 mm` (`Er = 4.29`) — `In3.Cu PWR` — `d4 = 0.1300 mm` (`Er = 4.17`) — `In4.Cu GND` — `d5 = 0.3658 mm` (`Er = 4.29`) — `In5.Cu Sig` — `d6 = 0.1300 mm` (`Er = 4.17`) — `In6.Cu GND` — `d7 = 0.1194 mm` (`Er = 4.29`) — `B.Cu` (`0.035 mm`), `tan_d = 0.02`. Symmetry and adjacent GND planes for `L1`, `L3`, `L6`, `L8` are fundamentally sound, **except** `L3` (`In2.Cu`) and `L6` (`In5.Cu`) also couple vertically (`h2 = 0.3658 mm`) to the **split power plane `In3.Cu` (`L4`)** (`In5.Cu` sees solid `In4.Cu` GND instead of splits on its thick side).
* **L1 / L8 `RF50` (`0.183 mm`) CPWG & Microstrip [PASS / WARN]:**
  * Bare solder-masked microstrip (`w = 0.183 mm`, `h = 0.1194 mm`, `t = 0.035 mm`, `Er = 4.29`): **`Z0 = 50.29 ohm`** (`51.29 ohm` unmasked) — tightly centered on `50 ohm`!
  * Inside `L1 RF band GND` (`x = 95.50..200.50, y = 199.60..214.45 mm`), zone `connect_pads` sets **`clearance = 0.50 mm`**, giving **`Z0 = 54.82 ohm`** (`L8` `clearance = 0.30 mm` gives **`53.23 ohm`**; `.kicad_dru` `RF50` `0.20 mm` clearance would give `51.66 ohm`).
  * At `y = 199.60 mm`, `L1/L8` GND pours end abruptly; long RF runs (`IF_TX_B = 111.65 mm`, `IF_RX_B = 76.27 mm`, `IF_RX_C = 61.68 mm`, `IF_RX_A = 59.53 mm`) transition to `50.29 ohm` microstrip (`RL = -27.3 dB`). Calculated conductor+dielectric loss at `120 / 250 / 500 MHz` is `0.0290 / 0.0448 / 0.0693 dB/cm` (`0.32 / 0.50 / 0.77 dB` total over `IF_TX_B`).
  * **[WARN]** `IF_RX_B` dips onto `In2.Cu` for `6.94 mm` directly over `In3.Cu` (`+5V_IFR` / `+3V3_D` plane boundary). Continuous `0.183 mm` asymmetric stripline gives `Z0 = 48.65 ohm` (`RL = -37.3 dB`), but crossing the `In3.Cu` split perturbs return current and injects buck switching noise into the `25 dB`-gain radar receiver!
* **SMA Edge-Launch & ESD Compensation (`PESD5V0F1BL`) [PASS]:**
  * Under all 12 edge-mount SMAs (`J911..J952`, `J401..J402`), keepout zones clear `In1.Cu..In5.Cu` down to `In6.Cu` (`L7` GND, `h ~ 1.37 mm`) to strip launch pad capacitance.
  * The `2.16 mm` (`0.76 + 1.40 mm`) `w = 0.10 mm` neckdown at `PESD5V0F1BL` (`C_d = 0.40 pF` typ / `0.55 pF` max) sees `Z_trace = 148.8 ohm` over `L7`, creating `L ~ 1.95 nH`. Effective lumped synthetic impedance **`sqrt(L / 0.40 pF) = 69.8 ohm`** (vs `50 ohm`, compensating capacitive notch above `1 GHz`; clean at `<= 500 MHz`).
* **Asymmetric Stripline `LVDS100` (`In2.Cu` / `In5.Cu`) [PASS]:**
  * Continuous Cohn conformal model on `h1 = 0.130 mm (Er = 4.17)`, `h2 = 0.3658 mm (Er = 4.29)`, `t = 0.0152 mm`:
    * `LVDS100` nominal (`w = 0.10 mm, s = 0.15 mm`): **`Z0 = 63.53 ohm`, `Z_odd = 53.93 ohm`, `Z_diff = 107.86 ohm`** (`+7.9%`).
    * BGA neckdown (`w = 0.09 mm, s = 0.12 mm`): **`Z0 = 66.11 ohm`, `Z_odd = 53.18 ohm`, `Z_diff = 106.37 ohm`** (within `1.5 ohm` across BGA breakout!).

---

### 2. RF Signal Chain & Converter Analog Front-End
* **SPDT RF Routing Matrix (`U901..U904`, `M3SWA2-34DR+`) [PASS]:** Verified `DC–30 GHz`, `~1.0–1.1 dB` typ insertion loss `< 1 GHz`, `~61 dB` typ isolation, `+48..+52 dBm` IIP3. Control divider/clamp (`+3V3_D -> R9x1(11.5R) -> D9x1(5.6V)//C9x1(100n)//C9x2(100p)`, `-3V3 -> R9x2(11.5R) -> D9x2(5.6V)//C9x3(100p)//C9x4(100n)`) matches `M3SWA2` datasheet Figure 2 (confirming `C912/913` and `D911/912` are **bias-network parts, not RF-path faults**), with `100 nF` DC blocks (`f_c = 31.8 kHz`) at every SMA.
* **RX Gain, NF & IIP3 Cascades [WARN]:**
  * **AFE Input Match (`R501/R601/R621 = 64.9 ohm || AD8352 ~ 3 kohm`):** `Z_in = 63.53 ohm`, `VSWR = 1.27`, **`RL = -18.48 dB`** (intentionally replicates AERIS-10 single-ended-to-differential network).
  * **Radar RX (`U902 -> U502 [15 dB, R504=68R] -> U503 [10 dB, R508=115R] -> AD9484`):** Net **`G = +23.70 dB`, `NF = 15.01 dB`, `IIP3 = +16.88 dBm`**, giving `-76.0 dBm` thermal+NF noise floor integrated over `200 MHz` Nyquist (`400 MSPS`).
  * **SDR RX (`U901 -> U602 [12 dB, R604=120R] -> AD9253`):** Net **`G = +10.70 dB`, `NF = 15.80 dB`, `IIP3 = +30.27 dBm`**.
  * **[HIGH]** Both `AD8352` pairs draw `+5V_IFR`/`+5V_IFS` directly from the `400 kHz` buck `+5V0` (`LMR33630`) through `FB501`/`FB601` alone (no LDO!).
* **TX Baluns (`ADT2-1T+`), Reconstruction LPF & Secondary Skew [WARN]:**
  * **[MEDIUM]** `ADT2-1T+` lower `-3 dB` edge is **`0.4 MHz` typ** — `4x` higher than the `0.1 MHz` lower SDR target (`3 dB` datasheet rolloff near band edges).
  * **[MEDIUM]** Exact 2-port ABCD simulation of the 5th-order differential ladder (`44 pF -> 214.6 nH -> 106 pF -> 214.6 nH -> 33 pF`, doubly terminated `99.8 ohm <-> 100 ohm` via `R702/R703 = 49.9R` and `2:1` balun) shows **`f_c(-3 dB) = 69.7 MHz`** (`-34.27 dB` at `120 MHz`, strictly 1st-Nyquist baseband TX only) with **`-2.04 dB` passband dip (`|S11| = -4.27 dB`) at `30 MHz`** due to `sqrt(L/C)` mismatch to `100 ohm`.
  * **[MEDIUM]** On `DAC_SDR`, `T801` secondary traces are mismatched: `SEC = 3.97 mm` (`0` vias) vs `SEC_DOT = 13.72 mm` (`2` vias, `dL = 9.75 mm`), introducing **`2.68 deg` phase imbalance at `120 MHz`** (degrading balun even-order HD2 suppression).

---

### 3. Clock Distribution, Phase Noise & External Reference Path
* **Internal Oscillator (`Si549` + `ADCLK948`) Jitter Margin [PASS]:**
  * Root-sum-square additive RMS jitter (`95 fs` `Si549` + `75 fs` `ADCLK948`) = **`121.0 fs` typ**.
  * Theoretical aperture-jitter SNR ceilings: **`80.79 dB` at `120 MHz`** and **`74.42 dB` at `250 MHz`** (exceeds `AD9484` `47 dBFS` across the board; meets `AD9253` `74 dBFS` up to `~250 MHz`, dropping to `69.31 dB` at `450 MHz` — tight for undersampling near `450 MHz` unless external low-noise source is injected via `J401`).
* **`U401` (`ADCLK948`) Input Termination Verified [PASS]:** Direct schematic/pad verification confirmed pins 2, 3, and 4 (`~CLK0`, `VREF0`, `VT0`) are tied together to `C413` (`100 nF`) to GND, which properly engages **`ADCLK948` internal `50 ohm` single-ended AC-coupled termination** on `CLK0`. *(Previous concern regarding missing termination on `J401/CLK0` was falsified by schematic verification.)*
* **Series `100 pF` Coupling Caps (`C414..C421`) Break `10 MHz` Ref Pass-Through [FAIL — BLOCKER B2]:**
  * All four differential outputs (`Q0..Q3`) pass through **`100 pF` (`C414..C421`)** into `50 ohm` per-leg load (`100 ohm` diff or `R412 = 49.9R` on `~Q3`): `f_c(-3 dB) = 1 / (2 * pi * 50 * 100 pF) = 31.83 MHz`.
  * At `400 MHz` (`-0.0274 dB`), this is lossless. At **`10 MHz` external reference pass-through**, attenuation is **`-10.47 dB`** (`0.30 V` peak-to-peak out of `1.0 V` nominal), violating receiver threshold / causing massive duty-cycle distortion and false triggering.
* **Clock Plane Noise, Crossings & Skew [FAIL — HIGH H3, H4]:**
  * `+3V3_CLK` (`U401` + `Y401`) comes from **digital buck `+3V3_D` (`580 kHz`) via `FB401`** — no LDO!
  * `U401-CLK0` (`74.48 mm`, `66.10 mm` on `In2.Cu` @ `0.183 mm`, `Z0 = 48.6 ohm`) and `U401-Q3` (`79.79 mm`, `71.34 mm` on `In2.Cu`) cross **`In3.Cu` power-plane splits (`+3V3_D` / `+5V_IFR` / `+3V3_CLK`)** over noisy digital copper.
  * `Y401` (`Si549`) `CLK+/CLK-` vias sit **`3.04 mm` and `4.01 mm`** from the nearest GND return via.
  * `CLK_ADCS` has **`4.660 mm` intra-pair skew (`31.7 ps` = `1.59%` of 500 MHz clock)**; `CLK_FPGA` has **`3.578 mm` skew (`24.4 ps`)** and crosses the `+3V3_CLK` split on `In3.Cu`.

---

### 4. High-Speed Digital, LVDS & SGMII (`IAS_LINK`, `ADCR`, `ADCS`, `ETH`)
* **Pair-by-Pair Geometric Coupling & Skew Audit (`v_p ~ 146.8 mm/ns`) [FAIL — HIGH H1, H5]:**

| Pair | Total P / N (mm) | PCB Intra-Skew | UI @ Rate | Skew % UI | Tightly Coupled Same-Layer (`<=0.3 mm`) | Routing Defects |
|---|---:|---:|---:|---:|---:|---|
| `/LINK_RX_CLK` | `88.31 / 89.12` | `0.804 mm` (`5.5 ps`) | `2000 ps` (500 MHz) | `0.3%` | `77.0 / 88.3 mm` (`87%`) | **[PASS]** Clean `In5.Cu` (`0.10/0.15 mm`). |
| `/LINK_RX_D0` | `121.83 / 119.79` | `2.048 mm` (`14.0 ps`) | `1000 ps` (`1 Gbps`) | `1.4%` | **`0.0 / 121.8 mm` (`0%`)** | **[FAIL H1]** `84.2 mm` uncoupled on `F.Cu` @ `0.183 mm` (`2.5–13.2 mm` apart)! |
| `/LINK_RX_D1` | `95.79 / 100.57` | `4.786 mm` (`32.6 ps`) | `1000 ps` (`1 Gbps`) | `3.3%` | **`0.0 / 95.8 mm` (`0%`)** | **[FAIL H1]** Uncoupled on `F.Cu` @ `0.183 mm` (`3.0–6.6 mm` apart) + `B.Cu`. |
| `/LINK_TX_CLK` | `72.06 / 72.49` | `0.432 mm` (`2.9 ps`) | `2000 ps` (250 MHz DDR) | `0.1%` | **`0.0 / 72.1 mm` (`0%`)** | **[FAIL H1]** `N` mostly on `In2.Cu`, `P` split `In2/In5` (`3.2–5.8 mm` apart), `0.151 mm` (`2*Z0 = 106.7 ohm`). |
| `/LINK_TX_D0` | `69.12 / 70.14` | `1.020 mm` (`6.9 ps`) | `2000 ps` (500 Mbps) | `0.3%` | **`4.8 / 69.1 mm` (`7%`)** | **[FAIL H1]** Split `In2/In5` (`5.7–11.5 mm` apart); **combined `J_LINK_TX_D0 + LINK_TX_D0` net skew = `4.148 mm` (`28.3 ps`)**. |
| `/CONTROL/ETH_SGRX_PHY` | `55.88 / 46.51` | **`9.369 mm` (`63.8 ps`)** | `800 ps` (`1.25 Gbps`) | **`8.0%`** | **`0.8 / 55.9 mm` (`1.4%`)** | **[FAIL H1]** `P` on `B.Cu` (`45.9 mm`) vs `N` on `In5/In2` (`3.1–10.4 mm` apart), **max return via gap `6.39 mm`**! |
| `/CONTROL/ETH_SGTX_PHY` | `53.32 / 52.24` | `1.073 mm` (`7.3 ps`) | `800 ps` (`1.25 Gbps`) | `0.9%` | `28.9 / 53.3 mm` (`54%`) | **[WARN]** Coupled segments use `F.Cu` `0.117/0.15 mm` (`Z_diff = 111.0 ohm`), remainder spans `B.Cu`. |
| `/ADCR_D0..D7, DCO, OR` | `26.87..44.12` | `0.042..1.164 mm` | `2000 ps` (500 Mbps) | `<= 0.4%` | e.g. `D0`: `35.6/37.4` (`95%`) | **[WARN H5]** `ADCR_D0, D5, OR` on `In2.Cu` cross `In3.Cu` (`+1V8_ADCR_D`, `+1V0`, `+1V8_ADCR_A`) splits. |
| `/ADCS_D0, D1, DCO, FCO` | `38.05..42.64` | `0.772..2.749 mm` | `2667 / 16000 ps` | `<= 0.5%` | **`0.0–1.7 / ~40 mm` (`0–4%`)** | **[FAIL H5]** Routed uncoupled across `F.Cu/B.Cu/In5.Cu`; `ADCS_D0` & `ADCS_DCO` cross `In3.Cu` splits (`+1V0`, `+1V8_ADCS_A`). |

* **Termination Note Discrepancy [MEDIUM M4]:** `IAS_LINK` documentation cites `2x49.9 ohm` split termination, whereas actual schematic/PCB uses single `R105/R106 = 100 ohm` differential with `10k` (`R101..104`) bias to `+1V2` (works electrically on LVDS receivers with internal common-mode range, but provides weaker common-mode AC sinking than a split termination).

---

### 5. PDN, Switching Noise & Power-On Sequencing
* **Artix-7 (`U1101`, `XC7A50T-2FTG256I`) Power Sequencing [FAIL — HIGH H2]:**
  * Xilinx `DS181` requires monotonic startup **`VCCINT (+1V0)` -> `VCCBRAM (+1V0)` -> `VCCAUX (+1V8_D)` -> `VCCO (+1V8/+2V5/+3V3_D)`** (or documented supported groupings without prolonged reverse bias between `VCCINT`/`VCCAUX`/`VCCO`).
  * **Actual circuit:** Buck regulators `U1002 (+3V3_D)`, `U1003 (+2V5)`, and `U1004 (+1V0)` all have their `EN` pins tied straight to `+5V0` through `10k` pull-ups. All three switchers enable simultaneously when `+5V0` crosses UVLO, leaving sequencing order solely to arbitrary soft-start/load capacitance ratios!
* **Analog vs Buck Isolation [FAIL — HIGH H3]:**
  * Switching frequencies present: `U1008 LM2663 = 150 kHz`, `U1001 LMR33630 = 400 kHz`, `U1002..4 TPS562201 = 580 kHz` (+ harmonics).
  * `TPS7A8300` LDOs (`U1005 +1V8_A`, `U1006 +1V8_D`, `U1007 +3V3_A`) provide `~40 dB` PSRR around `400–500 kHz` — isolating ADCs, DACs, and RF switches.
  * By contrast, **`AD8352` (`+5V_IFR`, `+5V_IFS`)** and **`ADCLK948`/`Si549` (`+3V3_CLK`)** lack LDO regulation completely, sitting behind `600R@100MHz` ferrites whose impedance at `400–580 kHz` is **`< 10 ohm`** (near zero ripple rejection).

---

### 6. Automotive / UAV Input Protection
* **Reverse-Polarity PFET Upstream of TVS [FAIL — BLOCKER B1]:**
  * Verified PCB pad netlist path: `J1001 (+12V jack) -> F1001 (1.5 A PTC) -> Q1001 Drain (DMP3013SFV) -> Q1001 Source (+12V rail) -> D1001 (SMBJ15CA TVS) -> U1001 (LMR33630, 36 V abs max)`. (`D1002 = 15 V` Zener protects `Q1001` Gate-Source.)
  * **`Q1001` (`DMP3013SFV`) absolute maximum `V_DSS` is `-30 V`.** When a negative inductive transient (`ISO 7637-2 Pulse 1`: `V_s = -100 V` to `-150 V`, `R_i = 10 ohm`) hits `J1001` while `+12V` bulk caps (`C1001 = 47 uF`, `C1002 = 10 uF`) hold `+12 V`, `Q1001` tries to block reverse current — placing **`|V_DS| = 112–162 V` (`3.7x–5.4x` above abs max)** directly across `Q1001` because `D1001` is on the *downstream* side of `Q1001`! `Q1001` suffers avalanche failure immediately.
  * Furthermore, `D1001` (`SMBJ15CA`, `600 W` @ 10/1000 us, `V_C ~ 24.4 V`) is vastly undersized for automotive/alternator `ISO 16750-2` Load Dump surges (`U_s = 35 / 65 / 87 V`, `R_i = 2 ohm`, `t_d = 200–400 ms`), which inject **`I_pk = 5.3 / 20.3 / 31.3 A` (`P_pk = 129 / 495 / 764 W` continuous-pulse) and `E = 12.9 / 49.5 / 152.7 J`** into the TVS (`~1.5 J` 100 ms single-pulse limit -> thermal short/explosion unless supply is purely regulated UAV LiPo + suppressed bus).

---

### 7. Thermal Analysis
* **Steady-State Junction Temperature Estimate (Unventilated Enclosure, Still Air) [FAIL — HIGH H6]:**
  * Using datasheet dissipation & JEDEC `theta_JA` adjusted conservatively for PCB exposed-pad via count:

| Ref | Device | Power (`W`) | EP Size (`mm`) | EP GND Vias (`r4mm`) | JEDEC / Eff `theta_JA` (`C/W`) | `T_j @ 55 C` | `T_j @ 70 C` | `T_j Max` | Status |
|---|---|---:|---|---:|---:|---:|---:|---:|---|
| `U501` | `AD9484BCPZ-500` | `0.670` | `5.1 x 5.1` | `18` (`23`) | `23.7` / `~26.0` | `72.4 C` | `87.4 C` | `125 C` | **[PASS]** |
| `U601` | `AD9253BCPZ-125` | `0.440` | `5.6 x 5.6` | `19` (`19`) | `23.7` / `~26.0` | `66.4 C` | `81.4 C` | `125 C` | **[PASS]** |
| `U401` | `ADCLK948BCPZ` | `0.350` | `2.7 x 2.7` | `6` (`8`) | `49.8` / `~55.0` | `74.2 C` | `89.2 C` | `125 C` | **[PASS]** |
| `U502` | `AD8352ACPZ` | `0.185` | `1.6 x 1.6` | `5` (`11`) | `91.4` / `~95.0` | `72.6 C` | `87.6 C` | `125 C` | **[PASS]** |
| `U503` | `AD8352ACPZ` | `0.185` | `1.6 x 1.6` | `4` (`4`) | `91.4` / `~98.0` | `73.1 C` | `88.1 C` | `125 C` | **[PASS]** |
| `U602` | `AD8352ACPZ` | `0.185` | `1.6 x 1.6` | `3` (`6`) | `91.4` / `~105.0` | `74.4 C` | `89.4 C` | `125 C` | **[WARN]** |
| `U603` | `AD8352ACPZ` | `0.185` | `1.6 x 1.6` | **`2`** (`5`) | `91.4` / `~115.0` | `76.3 C` | `91.3 C` | `125 C` | **[WARN H6]** |
| `U1201` | `RTL8211FSI-CG` | `~0.450` | `4.4 x 4.4` | **`1`** (`3`) | `35.0` / `~65.0` | `84.2 C` | **`99.2 C`** | `125 C` | **[FAIL H6]** |

* **LDO & Oscillator Heat Notes:** `Y401` (`Si549`, `1` EP via), `U1005` (`2.5 -> 1.8V @ ~1 A ~ 0.70 W`), `U1006` (`3.3 -> 1.8V @ ~0.4 A ~ 0.60 W`), and `U1007` (`5.0 -> 3.3V @ ~0.25 A ~ 0.43 W`, each with `4` EP vias in `2.0 x 2.0 mm` pads) cluster in the power corridor `x = 93–117 mm` (`U1001` has `15` EP vias); expect significant local PCB heating around `U1005/U1006` without airflow.

---

### 8. EMI / EMC & Crosstalk
* **`J1103` (`2x20 AERIS ADAR`) Return-Path Starvation [FAIL — HIGH H5]:** Verified footprint pad netlist shows `35` active `1.8 V` digital/SPI/control lines with **only `5` GND pins (`34, 36, 38, 39, 40`) — leaving pins `1..33` with zero GND pins** and zero series termination resistors! Multi-bit ribbon toggles form wide-loop common-mode radiating antennas right beside the `120 MHz` IF chain.
* **Outer-Layer Uncoupled Differential Pairs [FAIL — HIGH H1]:** `LINK_RX_D0` (`84.2 mm` @ `1 Gbps`), `LINK_RX_D1` (`~68 mm` @ `1 Gbps`), and `ETH_SGRX_PHY` (`45.9 mm` `P`-leg only on `B.Cu` @ `1.25 Gbps`) act as poorly balanced single-ended outer microstrips, maximizing near-field crosstalk and radiated harmonics (`500–1250 MHz`).
* **Top-Edge GND Via Fence [PASS]:** `124` GND vias stitch `y >= 209.5 mm` with maximum gap `2.85 mm`, yielding **`lambda/20 = 2.54 GHz`** in FR4 (`> 5x` margin at `500 MHz`; `1017` total GND vias, `381` in RF band `y >= 198 mm`).
* **GbE Crystal Proximity [WARN — MEDIUM M3]:** `Y1201` (`25 MHz` Ethernet crystal at `(200.5, 131.25)`) sits **`11.14 mm`** from `U401` (`(198.2, 142.15)`) and **`15.77 mm`** from `Y401` (`(189.2, 142.25)`); `U1201` sits `16.67 mm` from `U401`. Expect `25 MHz` harmonic spurs around the clock buffer if shielding/guarding is tight.

---

### 9. Mechanical & Connectors
* **South SOM Cantilever & Modal Stiffness [FAIL — HIGH H7]:**
  * Five M3 mounting holes sit at `H1=(94.0, 112.25)`, `H2=(203.0, 112.25)`, `H3=(93.0, 209.75)`, `H4=(148.5, 192.5)`, `H5=(204.0, 209.75)`.
  * KV260 Samtec high-density mating connectors `J101=(186.02, 85.60)` and `J102=(135.98, 85.60)` hang **`26.65 mm` south** of `H1/H2` with zero board-edge support beneath the SOM's heavy heatsink mass!
  * Main `H1–H3` `Y`-span is **`97.50 mm`**. Even an unloaded `1.54 mm` FR4 plate across a `97.5 mm` span has a fundamental bending mode around **`~258 Hz`**, which plunges well into typical multicopter rotor/propeller vibration harmonics (`~80–160 Hz`) once carrying the cantilevered KV260 SOM (`>= 220 g`), risking intermittent BGA/Samtec fretting.
* **Unlatched Flight Connectors & Tight SMA Pitch [WARN — MEDIUM M3]:**
  * `J1001` (`PJ-102AH` barrel jack) and `J1102`/`J1103` lack positive mechanical latches.
  * `12` edge SMAs are pitched on **`8.50 mm` centers** (`x = 101.0..194.5 mm`, closest M3 hole `8.51 mm` at `J931`), leaving `0.50 mm` total clearance between `8.0 mm` SMA hex nuts (impossible with thick torque-wrench sockets without sequential outer-to-inner assembly or flexible tools).

---

### 10. DFM / DFA & Documentation Consistency
* **Fabrication Spec vs CAD Mismatches [FAIL — HIGH H7]:**
  * `docs/FABRICATION.md` specifies `JLC08161F-3313` (`0.100 mm` outer prepreg, `0.25 / 0.50 mm` vias), whereas `CSI2-KRIA-KV260_Rev01.kicad_pcb` uses `JLC08161H-2116C` (`0.1194 / 0.1300 mm` dielectrics) and `0.20 / 0.45 mm` (`2177` total) vias.
  * `docs/JLCPCB_QUOTE.md` selects **POFV (Via-in-Pad Plated Over Filled)** for BGA/QFN thermal pads, yet `.kicad_pcb` `setup` flags explicitly declare **`capping = no`, `filling = no`, `covering = no`**, and split vias across **`1400` tented vs `777` untented (`None`)**. If ordered as-exported without overriding FAB notes cleanly, solder wicking under `U1101`/`U1201` will cause assembly defects.
  * `JLCPCB_QUOTE.md` flags **`8` component stockouts** blocking turnkey SMT (`M3SWA2-34DR+`, `AD9253BCPZ-125`, `AD9484BCPZ-500`, `AD9708AR`, `AD8352ACPZ`, `ADCLK948BCPZ`, `ADT2-1T+`, `TMP1075DR`).
* **Non-Standard BOM Values & ERC [WARN — LOW L1]:** `DAC_RADAR`/`DAC_SDR` LPF uses custom/non-E-series values (`107.3 nH`, `106 pF`). `CSI2-KRIA-KV260_Rev01-erc.rpt` reports `0` Errors and `7` benign Warnings (bidirectional vs power-flag warnings on `U1101 CFGBVS_0` and unused XADC pins `VP/VN/VREFP/VREFN/DXP/DXN`).

---

## 11. What I Could Not Check and Why

1. **Full-Wave 3D EM Extraction (S-Parameters, Via Stubs & Plane Cavity Coupling):** Closed-form conformal formulas (`microstrip_z0`, `cpwg_z0`, `asym_stripline_z0`, `abcd_dac_lpf_eval`) cannot resolve 3D via barrel inductances, antipad discontinuities across split `In3.Cu` zones, or exact mode-conversion (`S_dc21`) across the uncoupled `F.Cu`/`B.Cu` `LINK_RX_*` / `ETH_SGRX_PHY` segments. A full 3D EM / 2.5D hybrid solver (HFSS, SIwave, or OpenEMS) is required before sign-off.
2. **IBIS / IBIS-AMI Time-Domain Eye Margins (`1 Gbps` `IAS_LINK`, `1.25 Gbps` `ETH_SG*`):** Without Artix-7, RTL8211FSI, and KV260 SOM internal package flight-time models + IBIS-AMI transmitter/receiver equalization models, static PCB length skew alone cannot certify closed vs open eye height/width across PVT corners. *(Gateware dynamic IDELAYE3 training recovers static skew cleanly, provided channel jitter and ISI remain within the ~2 ns / 1 ns UI eye.)*
3. **PDN Target Impedance `Z(f)` & Measured Transient Load Step:** Verified rail topology, buck switching frequencies, and bypass capacitance counts from schematics, but did not simulate frequency-domain PDN impedance poles/anti-resonances with vendor MLCC ESL/ESR DC-bias derating models (`0402/0603/1210`).
4. **3D Structural Modal / Shock-Response FEA & Thermal CFD:** The bare FR4 fundamental plate frequency (`~258 Hz`) highlights mechanical risk, but exact resonant shift under the bolted Kria KV260 SOM + heatsink (center-of-mass eccentricity, standoffs, connector stiffness) and forced convection / solar enclosure temperatures require SolidWorks/ANSYS FEA + CFD.
5. **Internal KV260 SOM Carrier Stackup & Connector Routing:** Evaluated carrier pins (`J101/J102`) strictly against [`fpga/kria/xck26.xdc`](../fpga/kria/xck26.xdc) and [`docs/PINMAP.md`](PINMAP.md) without Xilinx internal K26 SOM KiCad/Allegro CAD sources.
