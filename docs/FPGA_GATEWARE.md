# FPGA Gateware Architecture — Artix-7 Front-End & Kria KV260 Zynq UltraScale+ PL

Complete RTL, post-route Vivado 2026.1 implementation, and full-system XSim co-simulation documentation for the dual-FPGA **KV260-IAS2RF** platform (licensed under **Apache License 2.0**, with `fpga/third_party/aeris/` retained under MIT from `AERIS-10 / PLFM_RADAR`).

---

## 1. Dual-FPGA Hardware/Gateware Partition

```
+---------------------------------------------------+     IAS1 (J101 -> J8, 5 LVDS pairs + 4 SE 1.8V)     +----------------------------------------------------+
|     ADAPTER FRONT-END FPGA (U1101)                | ===================================================> |        AMD KRIA KV260 SOM (XCK26-SFVC784-2LV-c)    |
|     Xilinx Artix-7 XC7A50T-FTG256-2               |  2x 1.0 Gb/s 64b/66b Uplink  (LINK_RX_D0/D1 + CLK)   |                                                    |
|                                                   | <=================================================== |  PL (ia2rf_k26_bd):                                |
|  · AD9484 400 MSPS Radar ADC + AERIS-10 DDC (79DSP)|  1x 1.0 Gb/s 64b/66b Downlink (LINK_TX_D0 + CLK)    |   · kria_pl_link_0 (5x/4x ISERDESE3+IDELAYE3+PCS)  |
|  · AD9253 2x125 MSPS SDR ADC + Dual DDC (30 DSP)  |  + HK I2C (1.8V), FPGA_PROG_B, FPGA_IRQ              |   · axi_dma_0 (64-bit MM2S/S2MM -> HP0_FPD)        |
|  · AD9708 LFM Chirp TX + AD9767 Dual 14b SDR TX   |                                                      |   · axi_smc_hp0 + axi_smc_ctrl + EMIO SPI/I2C      |
|  · 8x ADAR1000 Beamformer + 4x M3SWA2-34DR+ SW    |     Dedicated 1000BASE-T Ethernet (U1201 -> J1201)   |                                                    |
|  · Dual-Path Mux (IAS1 + SGMII 1.25G Soft PHY)    | ---------------------------------------------------> |  PS8 (Quad Cortex-A53 @ 1.33 GHz + 4 GB DDR4):     |
|                                                   |  192.168.10.2 UDP Port 0x4952 -> KV260 J10 (GEM3)    |   · Pulse compression, Doppler FFT, CFAR, Tracking |
| Post-Route: 15,681 LUT (48.1%), 110 DSP, WNS +0.111ns|                                                      |   · SDR FM/AM/SSB/PMR demodulation & Linux host IO |
+---------------------------------------------------+     Failsafe Pmod J1102 <-> Carrier J2 (EMIO SPI0)   +----------------------------------------------------+
```

High-resolution vector schematics & silicon die renders (`SVG` / `PDF` / `4K PNG`) live in [`img/highres/fpga/`](img/highres/fpga/).

---

## 2. Artix-7 XC7A50T-FTG256-2 (`artix_top`)

Top-level file: [`fpga/artix/top.v`](../fpga/artix/top.v), constrained by [`fpga/artix/xc7a50t.xdc`](../fpga/artix/xc7a50t.xdc) and built with [`fpga/artix/build_rev06.tcl`](../fpga/artix/build_rev06.tcl) (`ENABLE_ETH = 1'b1`).

### 2.1 Vivado Post-Route Silicon Die Floorplan

The post-route floorplan below is plotted directly from Vivado 2026.1 placed leaf cells across Clock Regions `X0Y0`..`X1Y2` (`_work/fpga_views/artix7_die_data.json`):

![Artix-7 XC7A50T-FTG256-2 Silicon Die Floorplan](img/fpga/artix7_silicon_floorplan.png)

- **Vector / 4K Downloads:** [4K PNG](img/highres/fpga/artix7_silicon_floorplan_4k.png) · [Vector SVG](img/highres/fpga/artix7_silicon_floorplan.svg) · [Vector PDF](img/highres/fpga/artix7_silicon_floorplan.pdf)

### 2.2 Hierarchical Circuit Schematic

![Artix-7 XC7A50T-FTG256-2 Vivado Hierarchical Circuit Schematic](img/fpga/artix7_vivado_schematic.png)

- **Vector / 4K Downloads:** [4K PNG](img/highres/fpga/artix7_vivado_schematic_4k.png) · [Vector SVG](img/highres/fpga/artix7_vivado_schematic.svg) · [Vector PDF](img/highres/fpga/artix7_vivado_schematic.pdf)

### 2.3 Complete Module Inventory (`fpga/artix/` & `fpga/link/`)

| Module | File(s) | Clock Domain(s) | Function & Key Implementation Details |
| :--- | :--- | :--- | :--- |
| **Top, Clocks & Mode Ctrl** | [`fpga/artix/top.v`](../fpga/artix/top.v) + [`clk_mode_ctrl.v`](../fpga/artix/clk_mode_ctrl.v) | `cfgmclk`, `fpga_clk` (`500M`/`400M`), `dac_clk` (`125M`/`100M`), `link_clk` (`125M`) | `STARTUPE2` `CFGMCLK` safe-boot sequencer, `MMCME2_ADV` DRP (`DIVCLK_DIVIDE` `5<->4` for `500<->400 MHz`), non-MMCM 2-bit Johnson `÷4` `dac_clk`, Ethernet `MMCME2_ADV`, `0x00..0xE0` CSR regfile, 3-way uplink arbiter |
| **Radar ADC Capture** | [`fpga/artix/adc_capture.v`](../fpga/artix/adc_capture.v) | `adcr_dco` (`200M`) -> `clk_400m` (`400M`) / `clk_100m` (`100M`) | Private `MMCME2_ADV` (`1000 MHz` VCO), `DCO_INVERT=1` (`N14=DCO_N, P14=DCO_P`), `IBUFDS_DIFF_OUT` + `IDELAYE2` + `ISERDESE2` 8-bit DDR capture (`400 MSPS`) + 32-tap automated eye scanner |
| **AERIS-10 Radar DDC** | [`fpga/artix/ddc_wrapper.v`](../fpga/artix/ddc_wrapper.v) + [`fpga/third_party/aeris/`](../fpga/third_party/aeris/) | `clk_400m` (`400M`), `clk_100m` (`100M`), `link_clk` (`125M`) | Verbatim `PLFM_RADAR` (`62d4c55`, MIT) 400 MSPS -> 100 MSPS I/Q DDC (`nco_400m_enhanced`, `cic_decimator_4x_enhanced`, `fir_lowpass_parallel`, `ddc_input_interface`), optional `POST_DECIM`, async BRAM FIFO, packetizer (`stream_id = 8'h01`) |
| **SDR Dual ADC Capture** | [`fpga/artix/adcs_capture.v`](../fpga/artix/adcs_capture.v) | `adcs_dco` (`437.5 MHz` DDR) -> `adcs_clk_div` (`125 MHz`) | AD9253 2-wire 14-bit DDR capture (`ISERDESE2` 7:1 + `IDELAYE2` + bitslip FSM locked to `FCO`), crosses via 16-entry Gray FIFO to `BUFG` `adcs_ddc_clk` |
| **Dual-Ch SDR DDC** | [`fpga/artix/sdr_ddc.v`](../fpga/artix/sdr_ddc.v) | `adcs_ddc_clk` (`125M`), `link_clk` (`125M`) | Two independent 125 MSPS channels (`8'h04` Ch A, `8'h05` Ch B on `IF_RX_C J951` enabled at reset for switch-free HF), each with 32-bit NCO + 3-stage CIC3 + 15-tap symmetric halfband FIR + programmable decimation `2..65535` + Gray async BRAM FIFO |
| **Radar Chirp DAC TX** | [`fpga/artix/dac_radar.v`](../fpga/artix/dac_radar.v) | `dac_clk` (`125M`/`100M`), `link_clk` (`125M`) | 32-bit LFM up/down chirp DDS (`FTW(n) = f0 + n*df`) + programmable `pulse_len` & `pri_len` + `ODDR` clock forward from non-MMCM `÷4` `dac_clk` (`D1=0, D2=1` center-aligned) to `AD9708` (`U701`) |
| **SDR Interleaved DAC TX** | [`fpga/artix/dac_sdr.v`](../fpga/artix/dac_sdr.v) | `dac_clk` (`125M`/`100M`), `link_clk` (`125M`) | Unpacks 64-bit downlink `8'h12` (or long `8'h10`) IQ frames across async FIFO -> 14-bit `IQWRT`/`IQSEL`/`IQCLK` interleaved bus on non-MMCM `dac_clk` to `AD9767` (`U801`); `hf_dac2_mode=1` default routes primary `I` to `DAC2 / IF_TX_C J952` (`dac1_mute` clamps `DAC1`) |
| **8x ADAR1000 Beamformer** | [`fpga/artix/adar_ctrl.v`](../fpga/artix/adar_ctrl.v) | `link_clk` (`125M`) -> `15.625 MHz` SPI | `32 beams x 8 chips x 24 bytes` BRAM table, broadcast/per-chip Mode-0 4-wire SPI (`J1103`), hardware `beam_strobe` loader, programmable `guard_pre` / `guard_post` T/R switching deadtime |
| **RF Switch Matrix** | [`fpga/artix/rf_switch.v`](../fpga/artix/rf_switch.v) | `link_clk` (`125M`) | Glitch-free control of the four `M3SWA2-34DR+` SPDT switches (`U901..U904`) with programmable `1 us` (`125 cyc`) settle lockout |
| **1000BASE-T SGMII PHY** | [`fpga/artix/eth_sgmii_phy.v`](../fpga/artix/eth_sgmii_phy.v) + [`fpga/artix/eth_8b10b.v`](../fpga/artix/eth_8b10b.v) | `625M` (`0°/90°`), `312.5M` (`0°/45°`), `125M` | XAPP523-style 4x `ISERDESE2` oversampling RX (`IDELAYE2` + `K28.5` barrel shifter), `10:1` `OSERDESE2` TX, IEEE 802.3 Clause 37 SGMII AN, `eth_mdio.v` Clause 22 open-drain management to `RTL8211FSI` (`U1201`) |
| **UDP/IPv4 MAC + Dual-Mux** | [`fpga/artix/eth_mac_udp.v`](../fpga/artix/eth_mac_udp.v) + [`fpga/artix/dual_path_mux.v`](../fpga/artix/dual_path_mux.v) + [`fpga/artix/eth_sdr_pkt_gen.v`](../fpga/artix/eth_sdr_pkt_gen.v) | `link_clk` (`125M`) | Full GMII MAC with HW ARP & ICMP echo responders, Jumbo UDP frames (`192.168.10.2:0x4952`), zero-loss packet-atomic `dual_path_mux` (`SPLIT`, `MIRROR_1P1`, `IAS_ONLY`, `ETH_ONLY`) |
| **IAS1 64b/66b PCS** | [`fpga/link/`](../fpga/link/) (`link_*.v`) | `link_clk` (`125M`), `tx_clk_ddr` (`500M`), `dl_rx_clk` (`125M`) | 2-lane `2.0 Gb/s` uplink TX (`OSERDESE2` 8:1 DDR + `16:66` scrambler + `CRC-32`) and 1-lane `1.0 Gb/s` downlink RX (`IDELAYE2` 32-tap eye trainer + `64b/66b` descrambler + deframer) |
| **Housekeeping & XADC/PPS** | [`fpga/artix/conv_spi.v`](../fpga/artix/conv_spi.v), [`hk_i2c_master.v`](../fpga/artix/hk_i2c_master.v), [`hk_xo_ctrl.v`](../fpga/artix/hk_xo_ctrl.v), [`hk_xadc_pps.v`](../fpga/artix/hk_xadc_pps.v), [`pmod_spi.v`](../fpga/artix/pmod_spi.v) | `cfgmclk`, `link_clk` (`125M`) | Auto-init 3-wire SPI for `AD9484`/`AD9253`, open-drain `TMP1075`/`M24C02` I2C polling, `Si549` fractional N-delta I2C (`±50 ppm` `ENABLE_ETH` clamp) + `CLK_SEL`, 12-bit XADC temp/voltage monitor, 1-PPS period/ppm frequency counter & 64-bit ns timestamping, failsafe Pmod SPI slave |

### 2.4 Artix-7 Post-Route Resource & Timing Closure (`reports_rev06/` & `reports/`)

| Hierarchy / Metric | Total LUTs | FFs | RAMB36 | RAMB18 | DSP48E1 | Role |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **`artix_top` (Total, `XC7A50T-FTG256-2`)** | **`15,681` (`48.1%`)** | **`18,084` (`27.7%`)** | **`13`** | **`6`** (`21.3%` BRAM) | **`110` (`91.7%`)** | Full integrated RF/Radar/SDR + Ethernet + IAS1 design |
| `u_sdr_ddc` | `5,564` | `3,754` | `2` | `4` | `30` | Dual-channel wideband HF/VHF/UHF SDR DDC |
| `u_ddc` (`ddc_wrapper` + `PLFM_RADAR`) | `1,913` | `4,591` | `0` | `0` | `79` | 400 -> 100 MSPS AERIS-10 radar DDC |
| `u_ul_pcs_tx` | `1,218` | `958` | `0` | `0` | `0` | 2-lane `64b/66b` IAS1 uplink PCS |
| `gen_rev06_eth.*` (`mux`, `mac`, `phy`, `mdio`, `gen`) | `2,089` | `1,867` | `8` | `1` | `0` | `1000BASE-T` SGMII + UDP MAC + Dual-Path Failover |
| `u_dl_pcs_rx` + `u_dl_train_fsm` | `876` | `725` | `0` | `0` | `0` | 1-lane `1.0 Gb/s` IAS1 downlink + eye trainer |
| `u_xadc_pps` + `u_hk_i2c` + `u_clk_mode_ctrl` (`u_hk_xo`) + `u_pmod_spi` | `2,025` | `1,856` | `0` | `0` | `0` | Safe-boot MMCM DRP/Si549, XADC, 1-PPS, I2C, Pmod SPI |
| `u_adc_cap` + `u_adcs_cap` + `u_conv_spi` | `760` | `888` | `0` | `0` | `0` | High-speed LVDS ADC capture & 3-wire init |
| `u_dac_radar` + `u_dac_sdr` + `u_adar_ctrl` + `u_rf_switch` | `916` | `619` | `3` | `1` | `1` | Non-MMCM DACs, `8x ADAR1000` beamformer, switches |

- **Timing (`timing_summary.rpt` & `pulse_width.rpt`, with post-route `phys_opt_design`):** `WNS = +0.111 ns` (`0 / 58,037` failing setup endpoints), `WHS = +0.016 ns` (`0 / 57,590` failing hold endpoints), `WPWS = +0.008 ns` (`0 / 18,616` failing pulse-width endpoints across `625 MHz` SGMII, `500 MHz` IAS1 DDR, `400 MHz` radar ADC, and `437.5 MHz` SDR ADC clocks).
- **Non-MMCM `÷4` DAC Clock Jitter Reduction:** Driving `dac_clk` (`125 MHz @ 500M` / `100 MHz @ 400M`) from a glitch-free 2-bit Johnson divider on `fpga_clk_bufg -> BUFG` instead of an MMCM `CLKOUT` cuts Vivado `Clock Uncertainty` from `0.165 ns` down to **`0.035 ns`** (`4.7x` improvement) and eliminates MMCM `Discrete Jitter` (`0.124 ns -> 0.000 ns`) and `Phase Error` (`0.099 ns -> 0.000 ns`).
- **Safe-Boot & Live `400 <-> 500 MHz` Mode Switch (`clk_mode_ctrl`):** On POR, `STARTUPE2 CFGMCLK` holds `mmcm_rst = 1` while `Y401` (`Si549`) programs and settles (`>= 30.7 ms` FCAL wait), configures both MMCMs via DRP (`DIVCLK_DIVIDE = 5` for `500 MHz`, `4` for `400 MHz`), and releases `mmcm_rst` (`XO_CTRL[14] xo_boot_done`, `[12] xo_boot_err`). Writing `XO_CTRL[2] prog_start` switches live between `500 MHz` and `400 MHz`; during the switch, `mmcm_rst` drops `link_clk`, so IAS1 link training and SGMII MAC/PHY reset and retrain cleanly, and `dac_rst` applies a glitchless reset to `dac_radar`/`dac_sdr`. `ADPLL_DELTA_M` writes to `XO_DELTA_M` are clamped to `±50.0 ppm` (`±429553`, latched in `XO_CTRL[13] xo_delta_clamped`) when `ENABLE_ETH=1`.
- **DRC (`drc.rpt`):** `0` errors. *(Top-level slice counts in `utilization.rpt` reflect Vivado cross-hierarchy LUT combining and `phys_opt_design` post-route optimization in `build.tcl` and `build_rev06.tcl`.)*

---

## 3. Kria KV260 Zynq UltraScale+ PL & Block Design (`XCK26-SFVC784-2LV-c`)

Sources: [`fpga/kria/top.v`](../fpga/kria/top.v), [`fpga/kria/kria_pl_link.v`](../fpga/kria/kria_pl_link.v), [`fpga/kria/link_axis.v`](../fpga/kria/link_axis.v), [`fpga/kria/bd.tcl`](../fpga/kria/bd.tcl), [`fpga/kria/xck26.xdc`](../fpga/kria/xck26.xdc).

### 3.1 Kria K26 Silicon Die Floorplan & Occupancy

![Kria K26 XCK26-SFVC784-2LV-c Silicon Die Floorplan](img/fpga/kria_k26_silicon_floorplan.png)

- **Vector / 4K Downloads:** [4K PNG](img/highres/fpga/kria_k26_silicon_floorplan_4k.png) · [Vector SVG](img/highres/fpga/kria_k26_silicon_floorplan.svg) · [Vector PDF](img/highres/fpga/kria_k26_silicon_floorplan.pdf)

### 3.2 Vivado IPI Block Design (`ias2rf_k26_bd`) & PL Link Circuit

![Kria K26 Vivado IPI Block Design Circuit Schematic](img/fpga/kria_k26_vivado_bd_schematic.png)

- **Vector / 4K Downloads (combined PS + PL `ias2rf_k26_bd` & `kria_pl_link` schematic):** [4K PNG](img/highres/fpga/kria_k26_vivado_bd_schematic_4k.png) · [Vector SVG](img/highres/fpga/kria_k26_vivado_bd_schematic.svg) · [Vector PDF](img/highres/fpga/kria_k26_vivado_bd_schematic.pdf)

### 3.3 K26 Block Design & Post-Route Resources (`fpga/kria/reports/`)

| Instance / Subsystem | Module | Slice LUTs | FFs | BRAM36 | BRAM18 | DSP48E2 | Purpose |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **`ias2rf_k26_bd_wrapper` (Full BD)** | **`ias2rf_k26_bd`** | **`11,034` (`9.4%`)** | **`18,212` (`7.8%`)** | **`2`** | **`2`** (`3.0 eq, 2.1%`) | **`0` (`0.0%`)** | Full PS8 + DMA + SmartConnect + PL link system |
| `kria_pl_link_0` | `kria_pl_link` | `6,662` | `12,126` | `0` | `0` | `0` | Bank 66 HP SERDES + `512`-tap eye trainer + `64b/66b` PCS + `link_axis` |
| `axi_dma_0` + `axi_smc_*` + `rst` | Xilinx IP | `4,372` | `6,086` | `2` | `2` | `0` | `64`-bit `MM2S`/`S2MM` DMA into `PS8 HP0_FPD` DDR4 |
| **Free K26 PL Silicon** | — | **`106,086` (`90.6%`)** | **`216,028` (`92.2%`)** | **`141` (`97.9%`)** | — | **`1,248` (`100%`)** | Available for on-SOM pulse compression, Doppler FFT & CFAR |

- **Timing (`fpga/kria/reports/timing_summary.rpt` & `kria_top` export):** Full BD `WNS = +1.291 ns` (`0` failing endpoints); standalone `kria_top` PL link `WNS = +1.008 ns`, `WHS = +0.017 ns`.
- **UltraScale+ Bank 66 Training:** Uses component-mode `IDELAYE3` (`VAR_LOAD`, `512` taps @ ~`4 ps`, BISC `EN_VTC` handshaking) + `ISERDESE3` at `125 MHz` `CLKDIV` / `500 MHz` `CLK` (`MMCME4_ADV` from `250 MHz` forwarded `LINK_RX_CLK`) and `ODT = RTT_48` internal `DIFF_SSTL12` termination at `1.2 V`.

---

## 4. Wideband SDR & AERIS-10 10.5 GHz Radar DSP Pipelines

![DSP Wideband SDR & 10.5 GHz Radar Pipelines](img/fpga/dsp_radar_sdr_pipeline_schematic.png)

- **Vector / 4K Downloads:** [4K PNG](img/highres/fpga/dsp_radar_sdr_pipeline_schematic_4k.png) · [Vector SVG](img/highres/fpga/dsp_radar_sdr_pipeline_schematic.svg) · [Vector PDF](img/highres/fpga/dsp_radar_sdr_pipeline_schematic.pdf)

### 4.1 Full-Spectrum SDR Architecture (`AD9253` + `AD9767` + `sdr_ddc.v`)

The adapter supports full receive and transmit SDR operation across HF, VHF, and UHF through the dual-channel `14`-bit `125 MSPS` `AD9253` ADC (`U601`) and dual `14`-bit `125 MSPS` `AD9767` TX DAC (`U801`):

1. **Direct-Sampled HF & Lower VHF (`0.1–62.5 MHz` Nyquist Zone 1, Ch A / `J901`):**
   - Covers **AM broadcast (`0.53–1.7 MHz`), SW/HF amateur bands (`160m`–`10m`), Citizen Band (`27 MHz CB`), and 6m (`50 MHz`)** directly without an external mixer.
   - `sdr_ddc_ch` tunes any carrier via a `32`-bit NCO (`0.0291 Hz` resolution at `125 MHz`) and decimates by `R = 2..65535` through a 3-stage `CIC3` + 15-tap symmetric halfband `FIR` (`80 dB` stopband alias rejection, automatically bypassed for `R < 4` wideband IQ).
2. **External Mixer / IF Receive for VHF, FM, Walkie-Talkie & UHF (`J902` / Ch B):**
   - External RF front-end down-converters covering **Airband AM (`118–137 MHz`), FM Broadcast (`88–108 MHz`), 2m Amateur (`144 MHz`), Walkie-Talkie / PMR446 (`446 MHz`), and 70 cm UHF (`433 MHz`)** inject an IF into the `50`-Ohm `J902`/`J906` SMAs (or Nyquist zone 2/3 undersampling up to `AD9253`'s `650 MHz` analog bandwidth).
   - Independent `NCO_B` (`0x48`) tunes Ch B simultaneously with Ch A, emitting dual coherent 64-bit I/Q packet streams (`8'h04` Ch A, `8'h05` Ch B) over `IAS1` / `1000BASE-T` to K26 `ps8` for FM/AM/SSB/NFM demodulation and spectrum waterfalling.
3. **Interleaved Dual-Channel SDR TX (`AD9767` via `J903` / `DAC2 IF_TX_C J952`):**
   - Downlink packets (`8'h12` or long `8'h10`) carry complex baseband IQ samples from K26 DDR4 to `dac_sdr.v`, driving `dacs_d[13:0]` interleaved (`IQWRT`/`IQSEL`) on the non-MMCM `÷4` `dac_clk` (`125 MSPS` at `500 MHz` mode, `100 MSPS` at `400 MHz` mode) into `ADT2-1T+` transformers (`T801`/`T802`) and low-pass filters.
   - **Switch-free HF defaults:** On power-on reset, `ADCS_CTRL` initializes to `0x0000_0009` (`Ch B / IF_RX_C J951` enabled) and `DACS_CTRL[1] = 0` enables `hf_dac2_mode = 1` so primary `I` routes directly to `DAC2 / IF_TX_C J952` (with optional `DACS_CTRL[2]` `dac1_mute` clamping `DAC1` to midscale `14'h2000`). Clear `DACS_CTRL[1]`=`1` (`hf_dac2_mode = 0`) for standard `DAC1/DAC2` quadrature `I/Q` TX.

### 4.2 `AERIS-10` 10.5 GHz / 20 km Phased-Array Radar Chain

All X-band front-end modules are sized and pin-mapped to drive the external `AERIS-10` antenna array (`8x ADAR1000` = `32` T/R elements for `20 km` instrumented range in `Extended` configuration):

- **TX Pulse Synthesis (`dac_radar.v`):** Generates 32-bit Linear Frequency Modulated (LFM) up/down chirps centered in the `120 MHz` IF window via `AD9708` (`J904` -> external `AERIS-10` upconverter & `10.5 GHz` PA). When `ADAR_CTRL[12]` (`auto_tr_chirp`) is set, `adar_ctrl.v` sequences `guard_pre` deadtime -> T/R switch `TX` -> chirp transmission -> `guard_post` ring-down -> `RX` echo window.
- **Beamforming Control (`adar_ctrl.v` & `rf_switch.v`):** Stores `32` beam tables × `8` chips × `24` bytes in Artix BRAM (`0x88`) and blasts phase/gain weights over `15.625 MHz` 4-wire SPI across `J1103` (`1.8 V` IDC ribbon) with synchronous `LOAD` and hardware `beam_strobe` pulses while guarding the four `M3SWA2-34DR+` SPDT switches.
- **RX 400 MSPS Capture & DDC (`adc_capture.v` + `ddc_wrapper.v`):** Captures `8`-bit `400 MSPS` LVDS samples from `AD9484` (`J905`), digitally down-converts the `120 MHz` IF to `100 MSPS` complex I/Q using `PLFM_RADAR` (`62d4c55`, MIT) DSP48E1 slices (`79` DSPs), applies optional post-decimation (`0.80 Gb/s` sustained over 1 or 2 `IAS1` lanes / UDP), and streams stamped `8'h01` packets to K26 `HP0` DDR4 for matched-filter pulse compression, Range-Doppler FFT, CFAR detection, and target tracking on the Quad Cortex-A53 + K26 PL.

---

## 5. Complete Control, Stream & Register Map

### 5.1 Packet Stream IDs (64-bit Header Format in [`fpga/link/LINK_PROTOCOL.md`](../fpga/link/LINK_PROTOCOL.md))

| `stream_id` | Direction | Generator / Consumer | Payload Content |
| :---: | :---: | :--- | :--- |
| **`8'h01`** | Artix -> Kria | `ddc_wrapper` (`u_ddc`) | AERIS-10 400->100 MSPS Radar DDC Complex `I/Q` `{Q1, I1, Q0, I0}` + 64-bit PPS timestamp |
| **`8'h02`** | Artix -> Kria/ETH | `eth_sdr_pkt_gen` (`u_sdr_gen`) | Diagnostic / telemetry packet generator on SGMII UDP path |
| **`8'h04`** | Artix -> Kria | `sdr_ddc` Ch A (`u_ch_a`) | AD9253 Ch A (HF / CB direct) decimated `16`-bit `I/Q` stream |
| **`8'h05`** | Artix -> Kria | `sdr_ddc` Ch B (`u_ch_b`) | AD9253 Ch B (VHF / FM / Walkie / UHF IF) decimated `16`-bit `I/Q` stream |
| **`8'h10`** | Kria -> Artix | `kria_pl_link` -> `artix_top` | Short CMD packet (`len = 8B`, `{opcode[63:56], flags, addr[47:32], wdata[31:0]}`) or legacy IQ TX (`len >= 24B`) |
| **`8'h11`** | Artix -> Kria | `artix_top` Readback Engine | Register read response `{16'h0002, addr[47:32], rdata[31:0]}` |
| **`8'h12`** | Kria -> Artix | `kria_pl_link` -> `dac_sdr` | AD9767 dual `14`-bit `I/Q` TX sample stream |

### 5.2 Artix-7 Full CSR Space (`0x00..0xE0` via IAS1 CMD `8'h10`, UDP Port `0x4952`, or Pmod SPI)

| Offset | Register | Access | Fields & Function |
| :---: | :--- | :---: | :--- |
| `0x00`–`0x30` | IAS1 Link Control & Telemetry | R/W | Link reset, PRBS-7 TX/RX test, manual `IDELAY` tap control, block/deskew lock, SH/CRC/PRBS error counters, eye window edges ([`LINK_PROTOCOL.md`](../fpga/link/LINK_PROTOCOL.md) §7.1) |
| `0x34` | `ADCS_CTRL` | R/W | `[0]` AD9253 capture enable, `[1]` `start_init` (W1P), `[3:2]` SDR DDC Ch A/B enable (`0x0000_0009` reset: `Ch B / IF_RX_C J951` enabled for switch-free HF) |
| `0x38` | `ADCS_STAT` | R | `[31:24]` AD9253 Chip ID, `[17:16]` conv SPI init `err/done`, `[11:0]` `aligned`, `idelay_done/err`, `bitslip_err`, `best_tap` |
| `0x3C`–`0x40` | `CONV_SPI_CMD` / `STAT` | R/W | Raw 3-wire SPI access to `AD9484` & `AD9253` (`[22]` target, `[21]` rw, `[20:8]` addr, `[7:0]` wdata) |
| `0x44`–`0x50` | `SDR_DDC_NCO_A/B`, `DECIM`, `STAT` | R/W | Independent 32-bit NCO FTWs for Ch A (`0x44`) & Ch B (`0x48`), `[15:0]` CIC3 decim ratio & `[25:16]` words/pkt (`0x4C`), dropped sample counter (`0x50`) |
| `0x54`–`0x6C` | `DACR_*` (Radar LFM Chirp TX) | R/W | Enable/trigger & `amp_scale` (`0x54`), start FTW `f0` (`0x58`), chirp slope `df` (`0x5C`), `pulse_len` (`0x60`), `pri_len` (`0x64`), `chirp_active` (`0x68`), `pulse_cnt` (`0x6C`) |
| `0x70`–`0x78` | `DACS_*` (SDR IQ DAC TX) | R/W | `tx_enable` (`[0]`), `~hf_dac2_mode` (`[1]`, default `0` = primary `I` on `DAC2 / IF_TX_C J952`), `dac1_mute` (`[2]`) (`0x70`); underflow counter (`0x74`); async TX FIFO level (`0x78`) |
| `0x7C`–`0x90` | `ADAR_*` & RF Switches | R/W | `active_beam_id[4:0]`, soft T/R, `sw_req[11:8]`, `auto_tr_chirp[12]`, `soft_load` (`0x7C`); `guard_pre/post` (`0x80`); `sw_settle` (`0x84`); 32-beam RAM write (`0x88`); raw ADAR SPI (`0x8C`); status (`0x90`) |
| `0x94`–`0xA4` | `HK_I2C_*` & `HK_TEMP_ERR` | R/W | Open-drain I2C controller for `TMP1075` (`0x48`) & `CAT24C02` (`0x50`) temperature & EEPROM polling |
| `0xA8`–`0xB4` | `XO_CTRL`, `XO_DELTA_M`, `XO_RAW` | R/W | `Si549` fractional N-delta (`±50 ppm` `ENABLE_ETH` clamp, `0xAC`), raw I2C (`0xB0`/`0xB4`), `CLK_SEL` + safe-boot/`400<->500 MHz` DRP switch (`xo_boot_err[12]`, `xo_delta_clamped[13]`, `xo_boot_done[14]`) |
| `0xB8`–`0xBC` | `XADC_TEMP_VCCINT` / `VCCAUX` | R | On-die Artix-7 XADC 12-bit temperature, `VCCINT`, `VCCAUX`, and overtemp flag |
| `0xC0`–`0xE0` | `PPS_*` & `TS_SYS` / `PPS_LATCH` | R/W | 1-PPS loop gain/nom period/ppm frequency error & locked `64`-bit nanosecond wall-clock timestamp registers |
| UDP `0x0000` / `0x0004` | `ETH_MUX_CTRL` / `ETH_MDIO` | R/W | Dual-path policy (`[1:0]`), SDR UDP gen enable (`[2]`), fault injection (`[4:3]`), AN restart (`[5]`), Clause 22 MDIO access to `RTL8211FSI` |

### 5.3 Kria `kria_pl_link` AXI4-Lite Slave (`s_axi` at `0x8000_0000`)

| Offset | Register | Function |
| :---: | :--- | :--- |
| `0x00` | `CTRL` | Soft reset, loopback enable, retrain trigger, manual IDELAY override, PRBS-7 TX/RX check |
| `0x04` | `STATUS` | `l0_lock`, `l1_lock`, `deskew_lock`, `link_up`, `idelayctrl_rdy`, `train_state`, `st_remote_status` |
| `0x08` / `0x0C` | `TAP_L0` / `TAP_L1` | Active & manual `512`-tap `IDELAYE3` tap values (`~4 ps/tap`) for `LINK_RX_D0/D1` |
| `0x10`–`0x28` | Error & Packet Telemetry | `sh_err_l0`, `sh_err_l1`, `crc_err_cnt`, `pkt_rx_cnt`, `{rx_drop, tx_drop}`, `{am_seq, skew_blocks}`, `prbs_err_cnt` |
| `0x2C` / `0x30` | `EYE_L0` / `EYE_L1` | Measured opening left/right tap boundaries from `link_rx_train_fsm` eye scan |

---

## 6. XSim & Full-System Verification Suite (`fpga/sim/`)

Every module and top-level integration is verified in AMD/Xilinx `xsim` (`Vivado 2026.1`) with unified primitive models (`unisims_ver`, `secureip`, `glbl`) and behavioral hardware board/IC models (`fpga/sim/models/`):

```powershell
# Run full dual-FPGA + PCB board + analog converter co-simulation (500 MHz & 400 MHz):
.\fpga\sim\run.ps1 tb_system
.\fpga\sim\run.ps1 tb_system -Define FPGA_CLK_400M

# Run SGMII, Clock Mode Switch, & Mutation Benches:
.\fpga\sim\run.ps1 tb_clk_mode_switch
.\fpga\sim\run.ps1 tb_clk_mode_switch -Mutate no_delta_clamp
.\fpga\sim\run.ps1 tb_rev06
.\fpga\sim\run.ps1 tb_rev06 -Mutate no_phase_select
.\fpga\sim\run.ps1 tb_e2e
```

| Bench | Scope Verified |
| :--- | :--- |
| `tb_system.v` | Full end-to-end co-simulation at both `500 MHz` (`946.6 s`) and `400 MHz` (`943.57 s`): `artix_top` + `kria_top` + `board_lvds_channel` + `ad9484_radar_model` + `ad9253_sdr_model` + `adar1000_array_model` + `dac_monitor_models` + `hk_i2c_periph_models` + `sgmii_phy_kria_peer` |
| `tb_clk_mode_switch.v` | Safe-boot Si549 `500 MHz` init, live `500 <-> 400 MHz` MMCM DRP + Si549 switching, and `±50 ppm` `ADPLL_DELTA_M` Ethernet clamp (`+` `-Mutate no_delta_clamp`) |
| `tb_rev06.v`, `tb_sgmii_lvds.v` | `1.25 Gb/s` SGMII `XAPP523` oversampler across `+100/-100 ppm` crystal drift (`0` bit errors in `60,000` bits), UDP CSR write, ARP/ICMP, failover `SPLIT`/`MIRROR`/`IAS_ONLY`/`ETH_ONLY` with `0` lost packets (`+` negative mutation checks) |
| `tb_e2e.v`, `tb_artix_top.v` | End-to-end AD9484 400 MSPS -> AERIS DDC -> `64b/66b` IAS1 -> `kria_pl_link` (`0` CRC/seq/proto errors; verified at both `500 MHz` and `400 MHz`) |
| `tb_adcs_capture.v`, `tb_adc_ddc.v` | AD9253 2-wire DDR FCO bitslip alignment + Dual-Ch SDR DDC & AD9484 IDELAY auto-training (both `500 MHz` and `400 MHz`) |
| `tb_dac_tx.v`, `tb_adar_ctrl.v`, `tb_hk.v`, `tb_pmod_spi.v`, `tb_link_*` | Non-MMCM `÷4` `dac_clk` LFM chirp & `hf_dac2_mode` TX, 8-chip ADAR1000 SPI & guard bands, TMP1075/Si549 I2C, XADC/PPS, 2-lane PCS deskew & `IDELAYE3` eye centering (all 18 benches pass at `500 MHz` & `400 MHz`) |

*(See [`SYSTEM_SIM.md`](../fpga/SYSTEM_SIM.md) for the complete recorded output logs of every testbench.)*
