# Rev06 Gateware Implementation: Dual-Path 1000BASE-X SGMII + IAS1 (`ENABLE_ETH=1`)

Implementation and verification record for the **Rev06 Dual-Path Ethernet + IAS1** Artix-7 (`XC7A50T-2FTG256I`) gateware (`fpga/artix/top.v`, `ENABLE_ETH=1`).

---

## 1. Architecture Summary

Rev06 adds dedicated `RTL8211FSI-CG` (`U1201`) → `HR911130C` (`J1201`) `1000BASE-T` SGMII Ethernet on its own outer-ring Artix-7 pins while preserving the **complete `2`-lane `IAS1` uplink (`LINK_RX_D0` `L4/M4`, `LINK_RX_D1` `M2/M1`, `LINK_RX_CLK` `N3/N2`) and `1`-lane downlink (`LINK_TX_D0` `M16/N16`, `LINK_TX_CLK` `N13/P13`)**.

| Block | Module (`fpga/artix/`) | Clock Domain(s) | Key Function |
|---|---|---|---|
| **SGMII PCS / SERDES PHY** | `eth_sgmii_phy.v` + `eth_8b10b.v` | `625 MHz` DDR (`ISERDES/OSERDES`), `312.5 MHz` (`10b`), `125 MHz` (`GMII`) | `4`-phase `ISERDESE2` oversampling with `IDELAYE2` (`312.5 MHz` 40-bit sliding window, comma align & dynamic `I/Q` phase selection), `OSERDESE2` `10:1` DDR (`5:1` @ `625 MHz`), `8b/10b` encode/decode (`eth_8b10b_enc`/`dec`), IEEE 802.3 Clause 37 SGMII Auto-Negotiation (`I1`/`I2`/`C1`/`C2`, `lp_adv_ability`) |
| **PHY Management** | `eth_mdio.v` | `125 MHz` → `1.95 MHz` MDC | Clause 22 MDIO master with open-drain `IOBUF` (`.I(1'b0)`, `.T(~(mdio_oe & ~mdio_out))` for `3.3 V` Bank 14 `M15` pulled up to `2.5 V` `DVDDRG` via `R1213`), `10 ms` reset pulse, and BMSR polling |
| **UDP/IPv4 + MAC Engine** | `eth_mac_udp.v` | `125 MHz` | Full GMII/SGMII MAC (`Preamble/SFD`, `CRC-32/FCS` check & append), ARP responder, ICMP echo responder, bidirectional UDP/IPv4 RX (`0xC0DE` control writes mapped to `ctrl_wr_*` registers & `0xE0` dual-path control) and TX streaming (`ip_hdr_csum` 4-stage pipeline during `TX_PREAM` `tx_hdr_idx == 0..3`; `tx_bytes_rem > 16'd2` word-pop guard) |
| **SDR Stream Source** | `eth_sdr_pkt_gen.v` | `125 MHz` | Generates `stream_id=1` SDR UDP packets (`64`-bit header/payload words, `seq_num`) |
| **Dual-Path Store-and-Forward Mux** | `dual_path_mux.v` | `125 MHz` | Dual BRAM store-and-forward FIFOs (`dual_path_sf_fifo`, `512 × 64`-bit, `255` pkt descriptors) supporting 4 runtime policies: `0` Stream Split, `1` `1+1` Mirror Duplication, `2` IAS-Only, `3` ETH-Only |

### Pin Mapping (`fpga/artix/xc7a50t.xdc`)

- **SGMII TX (`ETH_SGTX_PHY`):** `R2` / `R1` (`LVDS_25`, Bank 34 `VCCO = 2.5 V`, `OBUFDS`)
- **SGMII RX (`ETH_SGRX_PHY`):** `R3` / `T2` (`LVDS_25`, `DIFF_TERM = TRUE`, Bank 34 `VCCO = 2.5 V`, `IBUFDS_DIFF_OUT`)
- **MDIO Clock (`ETH_MDC`):** `P1` (`LVCMOS25`, Bank 34)
- **MDIO Data (`ETH_MDIO`):** `M15` (`LVCMOS33`, Bank 14, **open-drain only** via `IOBUF .I(1'b0)`; `BITSTREAM.CONFIG.EXTMASTERCCLK_EN DISABLE` so `EMCCLK` is never active)
- **PHY Reset (`ETH_RST_N`):** `K13` (`LVCMOS33`, Bank 14)
- **Intact `IAS1` Trunk:** `LINK_RX_D0` (`L4/M4`), `LINK_RX_D1` (`M2/M1`), `LINK_RX_CLK` (`N3/N2`), `LINK_TX_D0` (`M16/N16`), `LINK_TX_CLK` (`N13/P13`)

---

## 2. XSim Verification (`fpga/sim/`)

All benches run with Xilinx `xsim` (`Vivado v2026.1`):

| Testbench / Mutation | Command | Result | Observed Output Summary |
|---|---|---|---|
| `tb_sgmii_lvds` | `.\fpga\sim\run.ps1 tb_sgmii_lvds` | **PASS** | `PASS: tb_sgmii_lvds (+100/-100 ppm 60,000 bits, 0 errors)` |
| `tb_rev06` (baseline) | `.\fpga\sim\run.ps1 tb_rev06` | **PASS** | `PASS: tb_rev06 ias_s1=79 eth_s1=11 ias_s2=51 eth_s2=61 max_s1=78 max_s2=100 phase_sw=145 lost=0` |
| `tb_rev06` (`no_phase_select`) | `.\fpga\sim\run.ps1 tb_rev06 -Mutate no_phase_select` | **FAIL (expected)** | Fails SGMII comma lock / auto-negotiation with dynamic phase selection disabled |
| `tb_rev06` (`eth_skip_fcs`) | `.\fpga\sim\run.ps1 tb_rev06 -Mutate eth_skip_fcs` | **FAIL (expected)** | Accepts corrupted-FCS UDP control frame instead of dropping it |
| `tb_e2e` regression | `.\fpga\sim\run.ps1 tb_e2e` | **PASS** | `PASS: tb_e2e peak_k=60 img_rej_db=61.03 pkts=32 crc_err=0 seq_err=0 proto_err=0 ts=0001000000004528` |

---

## 3. Vivado Place & Route (`XC7A50T-FTG256-2`, `build_rev06.tcl`)

Synthesized, placed, physically optimized, and routed with `-generic ENABLE_ETH=1'b1` (`fpga/artix/reports_rev06/`):

### Timing Summary (`reports_rev06/timing_summary.rpt`, `pulse_width.rpt`)

| Metric | Result | Failing Endpoints | Total Endpoints |
|---|---|---|---|
| **WNS / TNS (Setup)** | **`+0.039 ns`** / `0.000 ns` | `0` | `28,902` |
| **WHS / THS (Hold)** | **`+0.036 ns`** / `0.000 ns` | `0` | `28,836` |
| **WPWS / TPWS (Pulse Width)** | **`+0.008 ns`** / `0.000 ns` | `0` | `8,515` |
| **DRC (`reports_rev06/drc.rpt`)** | **`0` Errors** (`50` Warnings/Advisories) | — | — |

Key clock domains closed: `clk_adcr_dco` (`200 MHz`, `WNS=0.076 ns`), `clk_100m_unbuf` (`100 MHz`, `WNS=1.964 ns`), `clk_200m_unbuf` (`200 MHz`, `WNS=0.282 ns`), `clk_400m_unbuf` (`400 MHz`, `WNS=0.210 ns`), `link_clk_unbuf` (`125 MHz`, `WNS=0.444 ns`), `gen_rev06_eth.clk_312p5_u` (`312.5 MHz`, `WNS=0.219 ns`), `gen_rev06_eth.clk_625_0_u` / `clk_625_90_u` (`625 MHz` DDR, `WPWS=0.008 ns`), and `dl_rx_clk` (`125 MHz`, `WNS=2.021 ns`).

### Hierarchical Utilization (`reports_rev06/utilization.rpt`)

| Hierarchy | Module | LUTs (Logic / LUTRAM) | FFs | RAMB36 | RAMB18 | DSP48E1 |
|---|---|---|---|---|---|---|
| **`artix_top` (Total)** | — | **`6,369`** (`6,223` / `146`) | **`8,088`** | **`8`** | **`1`** | **`87`** |
| `gen_rev06_eth.u_dual_mux` | `dual_path_mux` | `473` (`473` / `0`) | `299` | `8` | `0` | `0` |
| `gen_rev06_eth.u_eth_mac` | `eth_mac_udp` | `798` (`798` / `0`) | `868` | `0` | `0` | `0` |
| `gen_rev06_eth.u_eth_mdio` | `eth_mdio` | `131` (`131` / `0`) | `99` | `0` | `0` | `0` |
| `gen_rev06_eth.u_eth_phy` | `eth_sgmii_phy` | `561` (`515` / `46`) | `349` | `0` | `1` | `0` |
| `gen_rev06_eth.u_sdr_gen` | `eth_sdr_pkt_gen` | `20` (`20` / `0`) | `132` | `0` | `0` | `0` |
| **Rev06 Ethernet Subtotal** | — | **`1,983`** (`1,937` / `46`) | **`1,747`** | **`8`** | **`1`** | **`0`** |
| `u_adc_cap` + `u_ddc` + `u_ul_pcs_tx` + `u_dl_*` + `u_pmod_spi` | Core + `IAS1` | `4,386` | `6,341` | `0` | `0` | `87` |
