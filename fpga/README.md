# KV260-IAS2RF Gateware (`fpga/`)

Verilog-2001 gateware, Vivado build scripts, timing/utilization reports, and XSim verification benches for the bidirectional AC-coupled LVDS IAS1-to-RF bridge connecting the front-end Artix-7 (`XC7A50T-FTG256-2`) and the KV260 Kria K26 Zynq UltraScale+ SOM (`XCK26-SFVC784-2LV-c`).

## Architecture & Directory Layout

- [`artix/`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/artix) — Front-end Artix-7 (`U1101`, `XC7A50T-FTG256-2`) RTL, XDC ([`xc7a50t.xdc`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/artix/xc7a50t.xdc)), and build scripts:
  - [`top.v`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/artix/top.v) (`artix_top`): AD9484 400 MSPS radar ADC capture (`adc_capture.v`) -> AERIS 400->100 MSPS DDC + post-decimation (`ddc_wrapper.v`), AD9253 dual 14-bit SDR ADC capture (`adcs_capture.v`) + SDR DDC (`sdr_ddc.v`), AD9708 LFM radar DAC (`dac_radar.v`), AD9767 dual 14-bit SDR DAC (`dac_sdr.v`), 8x ADAR1000 SPI beamformer (`adar_ctrl.v`) + RF switches (`rf_switch.v`), shared converter SPI (`conv_spi.v`), housekeeping I2C/Si549 XO/XADC/PPS (`hk_i2c_master.v`, `hk_xo_ctrl.v`, `hk_xadc_pps.v`), Pmod J1102 SPI fallback (`pmod_spi.v`), 2-lane 64b/66b TX / 1-lane RX PCS, and Rev06 SGMII Ethernet + dual-path mux (`ENABLE_ETH`, default `1`).
  - [`build.tcl`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/artix/build.tcl) -> routed reports in [`artix/reports/`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/artix/reports).
  - [`build_rev06.tcl`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/artix/build_rev06.tcl) -> Rev06 Ethernet build reports in `artix/reports_rev06/`.
- [`link/`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/link) — Shared 64b/66b PCS, Clause 49 scrambler (`link_scrambler.v`), 66:8/8:66 gearboxes (`link_gearbox.v`), IEEE CRC-32 (`link_crc32.v`), packet framer/deframer (`link_framer.v`), 7-series/UltraScale+ SERDES wrappers (`link_lanes.v`), eye/bitslip/deskew training FSM (`link_rx_train_fsm.v`), top wrappers (`link_top.v`), [`LINK_PROTOCOL.md`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/link/LINK_PROTOCOL.md), and [`PINMAP.md`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/link/PINMAP.md).
- [`kria/`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/kria) — Kria K26 (`XCK26-SFVC784-2LV-c`) PL design and Vivado IPI Block Design:
  - [`kria_pl_link.v`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/kria/kria_pl_link.v) + [`link_axis.v`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/kria/link_axis.v): AXI4-Lite CSRs (`0x00..0x34`), 64-bit AXI4-Stream RX/TX DMA interfaces, MMCM (`300 MHz` `IDELAYCTRL` refclk + `500 MHz` / `125 MHz` downlink TX clocks from `ps8/pl_clk0`), and 2-lane uplink RX SERDES/PCS.
  - [`bd.tcl`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/kria/bd.tcl) + [`xck26_bd.xdc`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/kria/xck26_bd.xdc): Full Zynq UltraScale+ PS (`ps8`, `IOPLL` `pl_clk0 = 100 MHz`) + `axi_dma_0` (S2MM + MM2S, 64-bit) + `kria_pl_link_0` + `axi_smc_ctrl` + `axi_smc_hp0` + EMIO I2C0/SPI0/GPIO, generating `ias2rf_k26.bit` and `ias2rf_k26.xsa` in `fpga/kria/out/` and reports in [`kria/reports/`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/kria/reports).
  - [`top.v`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/kria/top.v) + [`build.tcl`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/kria/build.tcl) + [`xck26.xdc`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/kria/xck26.xdc): Standalone PL-only wrapper build (`kria_top`).
- [`third_party/aeris/`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/third_party/aeris) — MIT-licensed AERIS-10 DDC (`ddc_400m.v`, `cic_decimator_4x_enhanced.v`, `fir_lowpass.v`) adapted for Vivado 7-series timing closure at 400 MHz.
- [`sim/`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/sim) — Vivado XSim batch runner ([`run.ps1`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/sim/run.ps1)) and unit/system/mutation testbenches.
- [`../sw/`](file:///D:/Repos/kv260-ias2rf-gemini/sw) — KV260 Linux device-tree overlay ([`ias2rf_pl.dtsi`](file:///D:/Repos/kv260-ias2rf-gemini/sw/ias2rf_pl.dtsi)) and userspace CSR/DMA smoke test ([`ias2rf_dma_test.c`](file:///D:/Repos/kv260-ias2rf-gemini/sw/ias2rf_dma_test.c)).

---

## Resource Utilization (Both FPGAs)

All primitive counts below are taken directly from routed Vivado 2026.1 hierarchical utilization reports:
- Artix-7: [`fpga/artix/reports/utilization.rpt`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/artix/reports/utilization.rpt) (`artix_top` on `xc7a50tftg256-2`, `ENABLE_ETH=1`)
- Kria K26: [`fpga/kria/reports/utilization.rpt`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/kria/reports/utilization.rpt) (`ias2rf_k26_bd_wrapper` on `xck26-sfvc784-2LV-c`)

### Side-by-Side Total Utilization

| Device & Design | Total LUTs | Logic LUTs | LUTRAMs | SRLs | FFs | RAMB36 | RAMB18 | URAM | DSP Blocks |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **Artix-7 `XC7A50T-FTG256-2`** (`artix_top`, routed) | **15,576** | 15,410 | 166 | 0 | **17,449** | **13** | **6** | — | **110** |
| **Kria K26 `XCK26-SFVC784-2LV-c`** (`ias2rf_k26_bd_wrapper`, routed) | **8,533** | 7,606 | 790 | 137 | **12,327** | **2** | **2** | **0** | **0** |

### Artix-7 Hierarchical Breakdown (`artix_top`)

| Subsystem (`artix_top` instance) | Total LUTs | Logic LUTs | LUTRAMs | FFs | RAMB36 | RAMB18 | DSP Blocks |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `u_sdr_ddc` (AD9253 dual SDR DDC) | 5,672 | 5,672 | 0 | 3,754 | 2 | 4 | 30 |
| `u_ddc` (AERIS 400->100 MSPS radar DDC) | 1,827 | 1,827 | 0 | 4,602 | 0 | 0 | 79 |
| `u_ul_pcs_tx` (2-lane 64b/66b TX PCS + framer) | 1,232 | 1,232 | 0 | 958 | 0 | 0 | 0 |
| `u_xadc_pps` (XADC + 64-bit PPS timestamp) | 949 | 949 | 0 | 1,015 | 0 | 0 | 0 |
| `gen_rev06_eth.u_eth_mac` (UDP/IPv4/ARP MAC) | 870 | 870 | 0 | 888 | 0 | 0 | 0 |
| `u_dl_pcs_rx` (1-lane 64b/66b RX PCS + deframer) | 721 | 721 | 0 | 621 | 0 | 0 | 0 |
| `gen_rev06_eth.u_eth_phy` (SGMII 8b/10b PHY + AN) | 551 | 551 | 0 | 349 | 0 | 1 | 0 |
| `gen_rev06_eth.u_dual_mux` (IAS1/ETH dual-path mux) | 518 | 518 | 0 | 326 | 8 | 0 | 0 |
| `u_adc_cap` (AD9484 400 MSPS LVDS capture) | 482 | 482 | 0 | 622 | 0 | 0 | 0 |
| `u_dac_radar` (AD9708 LFM chirp generator) | 466 | 466 | 0 | 238 | 0 | 1 | 1 |
| `u_adar_ctrl` (8x ADAR1000 SPI + beam BRAM) | 310 | 310 | 0 | 197 | 2 | 0 | 0 |
| `u_dac_sdr` (AD9767 dual 14-bit SDR DAC) | 172 | 172 | 0 | 146 | 1 | 0 | 0 |
| `u_adcs_cap` (AD9253 serial LVDS capture) | 110 | 110 | 0 | 151 | 0 | 0 | 0 |
| *(Remaining glue: regfile, SPI/I2C, train, SERDES, async FIFOs)* | 1,696 | 1,530 | 166 | 3,582 | 0 | 0 | 0 |

### Kria K26 BD Hierarchical Breakdown (`ias2rf_k26_bd_wrapper`)

| Subsystem (`ias2rf_k26_bd_i` instance) | Total LUTs | Logic LUTs | LUTRAMs | SRLs | FFs | RAMB36 | RAMB18 | DSP Blocks |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `kria_pl_link_0` (`u_pcs_rx`, `u_pcs_dl_tx`, `u_link_axis`, `u_train_fsm`, `u_fifo_rx2pl`, CSRs) | 4,426 | 4,018 | 408 | 0 | 6,555 | 0 | 0 | 0 |
| `axi_dma_0` (AXI DMA 64-bit S2MM + MM2S) | 1,935 | 1,800 | 8 | 127 | 2,539 | 2 | 2 | 0 |
| `axi_smc_hp0` (HP0 SmartConnect 64-bit memory path) | 1,669 | 1,286 | 374 | 9 | 2,709 | 0 | 0 | 0 |
| `axi_smc_ctrl` (HPM0_LPD SmartConnect AXI-Lite control) | 489 | 489 | 0 | 0 | 491 | 0 | 0 | 0 |
| *(BD glue: `rst_ps8_100M`, etc.)* | 14 | 13 | 0 | 1 | 33 | 0 | 0 | 0 |

---

## Timing & Signoff Summary

### Artix-7 (`artix_top`, Routed)
Source: [`fpga/artix/reports/timing_summary.rpt`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/artix/reports/timing_summary.rpt), [`drc.rpt`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/artix/reports/drc.rpt), [`methodology.rpt`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/artix/reports/methodology.rpt), [`cdc.rpt`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/artix/reports/cdc.rpt).
- **Overall:** `WNS = 0.019 ns`, `TNS = 0.000 ns` (`0 / 56,401` endpoints), `WHS = 0.036 ns`, `THS = 0.000 ns` (`0 / 56,163` endpoints), `WPWS = 0.008 ns`, `TPWS = 0.000 ns` (`0 / 17,977` endpoints). **All constraints met.**
- **Key Intra-Clock Slacks (WNS / WHS in ns):**
  - `clk_400m_unbuf` (400 MHz AD9484 DDC): `0.019 / 0.053`
  - `clk_200m_unbuf` (200 MHz): `0.281 / 0.121`
  - `clk_100m_unbuf` (100 MHz DDC / SPI): `1.823 / 0.036`
  - `link_clk_unbuf` (125 MHz link TX CLKDIV): `0.279 / 0.058`
  - `dl_rx_clk` (125 MHz downlink BUFR): `1.104 / 0.118`
  - `adcs_ddc_clk_unbuf` (64 MHz AD9253 DDC): `0.831 / 0.061`
  - `gen_rev06_eth.clk_312p5_u` (312.5 MHz SGMII): `0.179 / 0.120`
  - `clk_adcr_dco` (400 MHz DDR DCO): `0.371 / 0.082`
- **DRC:** `0` Errors (`113` Warnings/Advisory: DSP pipeline/output advisories `DPIP-1`/`DPOP-1`/`DPOP-2`/`AVAL-4`/`AVAL-5`, BRAM reset advisories `REQP-1839`/`REQP-1840`, `BUFC-1`, `CHECK-3`, `RTSTAT-10`).

### Kria K26 BD (`ias2rf_k26_bd_wrapper`, Routed)
Source: [`fpga/kria/reports/timing_summary.rpt`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/kria/reports/timing_summary.rpt), [`drc.rpt`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/kria/reports/drc.rpt), [`methodology.rpt`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/kria/reports/methodology.rpt), [`cdc.rpt`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/kria/reports/cdc.rpt).
- **Overall:** `WNS = 0.975 ns`, `TNS = 0.000 ns` (`0 / 42,544` endpoints), `WHS = 0.010 ns`, `THS = 0.000 ns` (`0 / 42,544` endpoints), `WPWS = 0.000 ns`, `TPWS = 0.000 ns` (`0 / 13,773` endpoints). **All constraints met.**
- **Clock Summary & Intra-Clock Slacks (WNS / WHS in ns):**
  - `clk_pl_0` (`ps8/pl_clk0`, `IOPLL`, `100.000 MHz`): `5.704 / 0.010`
  - `clk_300_u` (MMCM `IDELAYCTRL` refclk, `300.000 MHz`): `2.853 / 0.144`
  - `clk_500_u` (MMCM downlink HS TX, `500.000 MHz`): `WPWS = 0.147`
  - `tx_clk_div` (MMCM downlink CLKDIV, `125.000 MHz`): `4.804 / 0.050`
  - `link_rx_clk` (uplink RX HS, `500.000 MHz`): `WPWS = 0.280`
  - `rx_clkdiv` (uplink RX CLKDIV, `125.000 MHz`): `2.880 / 0.022`
- **DRC:** `0` Errors (`5` Warnings: `PLCK-58` x1 from `LINK_RX_CLK` on QBC pin `C1/B1` with `CLOCK_DEDICATED_ROUTE = FALSE`, `REQP-1934` x2, `REQP-1935` x2 on Xilinx `axi_dma_0` SDP FIFOs).
- **Generated Artifacts:** `fpga/kria/out/ias2rf_k26.bit` (7,797,912 B) and `fpga/kria/out/ias2rf_k26.xsa` (1,059,656 B), ignored from git via [`fpga/.gitignore`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/.gitignore).

---

## Building & Running Simulations

### Vivado Batch Builds
Always run outside simulation sessions (and remove `fpga/kria/.bd_proj/` before running [`run.ps1`](file:///D:/Repos/kv260-ias2rf-gemini/fpga/sim/run.ps1), since `run.ps1` globs `*.v` recursively under `fpga/kria/`):
```powershell
# Artix-7 full build -> fpga/artix/reports/
& "D:\AMDDesignTools\2026.1\Vivado\bin\vivado.bat" -mode batch -nojournal -nolog -source fpga\artix\build.tcl

# Kria K26 full PS+PL Block Design + .bit + .xsa -> fpga/kria/out/ & fpga/kria/reports/
& "D:\AMDDesignTools\2026.1\Vivado\bin\vivado.bat" -mode batch -nojournal -nolog -source fpga\kria\bd.tcl
```

### XSim Testbenches (`fpga/sim/run.ps1`)
Run individual benches from the repository root (`D:\Repos\kv260-ias2rf-gemini`):
```powershell
.\fpga\sim\run.ps1 tb_artix_top
.\fpga\sim\run.ps1 tb_adc_ddc
.\fpga\sim\run.ps1 tb_e2e
.\fpga\sim\run.ps1 tb_rev06
.\fpga\sim\run.ps1 tb_adcs_capture
.\fpga\sim\run.ps1 tb_dac_tx
.\fpga\sim\run.ps1 tb_adar_ctrl
.\fpga\sim\run.ps1 tb_hk
.\fpga\sim\run.ps1 tb_link_axis
.\fpga\sim\run.ps1 tb_link_k2a
.\fpga\sim\run.ps1 tb_link_a2k
.\fpga\sim\run.ps1 tb_pcs_loop
.\fpga\sim\run.ps1 tb_pcs_unit
.\fpga\sim\run.ps1 tb_pmod_spi
.\fpga\sim\run.ps1 tb_serdes7
.\fpga\sim\run.ps1 tb_serdes_us
```
Each testbench supports `-Mutate <name>` negative checks (e.g., `tb_artix_top -Mutate no_reg_resp` and `tb_artix_top -Mutate missing_ack`).

---

## KV260 Linux Bring-Up (`sw/`)

See [`sw/README.md`](file:///D:/Repos/kv260-ias2rf-gemini/sw/README.md) for devicetree overlay (`ias2rf_pl.dtsi`) and userspace CSR/DMA smoke test (`ias2rf_dma_test.c`) usage:
- `0x80000000`: `kria_pl_link` AXI4-Lite CSRs (`0x00..0x34`), interrupts GIC `89` (`irq_fpga`), `90` (`irq_link_up`).
- `0x80010000`: `axi_dma_0` 64-bit S2MM + MM2S DMA (`HP0`, `dma-coherent`), interrupts GIC `91` (`s2mm_introut`), `92` (`mm2s_introut`).
- PS EMIO `i2c0` (`100 kHz` to `HK_SCL`/`HK_SDA`) and `spi0` (`Pmod J2`).

## Known issue (14 Nov 2026): Kria uplink eye training

A whole-system simulation (`tb_system`, real Artix top + real Kria PL link joined by board-channel models;
Gemini task 22, in progress) found that `link_rx_train_fsm` on the Kria side does not train the uplink:

- with the board's realistic channels (1.17-1.36 ns delay, 14-77 ps jitter) the eye scan finds a ~16-tap window
  on lane 1 only, at a different place on each retry, and nothing on lane 0, so the link never comes up;
- with ideal 100 ps channels it reaches LINK_UP, but still sees only 16 taps on lane 1 and none on lane 0;
- the bench's TAP_DWELL_CYCLES=160 speed-up made it worse (block lock needs longer per tap).

The good-tap criterion or the per-lane eye bookkeeping is wrong: most of the 1 ns UI should read as good, per
lane, and a channel delay longer than one UI must not matter. The per-block benches (`tb_link_a2k`, `tb_e2e`)
pass because they use fixed taps. **To fix before the boards are ordered.**
