# Artix-7 Constraints for U1101 (XC7A50T-FTG256-2) on CSI2-KRIA-KV260_Rev01
# Sources: fpga/link/PINMAP.md, docs/CONTROL_SPEC.md, _work/sheets/control_spec.py

set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]

# ------------------------------------------------------------------------------
# Bank 14 (VCCO = 3.3 V): Clocks, AD9484 ADC, IAS1 Downlink RX
#   Note: LVDS_25 inputs are legal in a 3.3 V bank only with DIFF_TERM = FALSE
#         and external 100 ohm termination (R105, R106, R1101..R1110).
# ------------------------------------------------------------------------------
set_property PACKAGE_PIN N11 [get_ports fpga_clk_p]
set_property PACKAGE_PIN N12 [get_ports fpga_clk_n]
set_property IOSTANDARD  LVDS_25 [get_ports {fpga_clk_p fpga_clk_n}]
set_property DIFF_TERM   FALSE   [get_ports {fpga_clk_p fpga_clk_n}]

# AD9484 LVDS Data (D[7:0]), OR, and Inverted DCO (N14=DCO_N, P14=DCO_P)
set_property PACKAGE_PIN P15 [get_ports {adcr_d_p[0]}]
set_property PACKAGE_PIN P16 [get_ports {adcr_d_n[0]}]
set_property PACKAGE_PIN R15 [get_ports {adcr_d_p[1]}]
set_property PACKAGE_PIN R16 [get_ports {adcr_d_n[1]}]
set_property PACKAGE_PIN T14 [get_ports {adcr_d_p[2]}]
set_property PACKAGE_PIN T15 [get_ports {adcr_d_n[2]}]
set_property PACKAGE_PIN R13 [get_ports {adcr_d_p[3]}]
set_property PACKAGE_PIN T13 [get_ports {adcr_d_n[3]}]
set_property PACKAGE_PIN R10 [get_ports {adcr_d_p[4]}]
set_property PACKAGE_PIN R11 [get_ports {adcr_d_n[4]}]
set_property PACKAGE_PIN T9  [get_ports {adcr_d_p[5]}]
set_property PACKAGE_PIN T10 [get_ports {adcr_d_n[5]}]
set_property PACKAGE_PIN T7  [get_ports {adcr_d_p[6]}]
set_property PACKAGE_PIN T8  [get_ports {adcr_d_n[6]}]
set_property PACKAGE_PIN R6  [get_ports {adcr_d_p[7]}]
set_property PACKAGE_PIN R7  [get_ports {adcr_d_n[7]}]
set_property PACKAGE_PIN M6  [get_ports adcr_or_p]
set_property PACKAGE_PIN N6  [get_ports adcr_or_n]
set_property PACKAGE_PIN N14 [get_ports adcr_dco_n]
set_property PACKAGE_PIN P14 [get_ports adcr_dco_p]

set_property IOSTANDARD LVDS_25 [get_ports {adcr_d_p[*] adcr_d_n[*] adcr_or_p adcr_or_n adcr_dco_n adcr_dco_p}]
set_property DIFF_TERM  FALSE   [get_ports {adcr_d_p[*] adcr_d_n[*] adcr_or_p adcr_or_n adcr_dco_n adcr_dco_p}]

# AD9253 14-bit SDR ADC LVDS Inputs (Bank 14, VCCO = 3.3 V, ext 100 ohm -> DIFF_TERM = FALSE)
set_property PACKAGE_PIN P10 [get_ports adcs_dco_p]
set_property PACKAGE_PIN P11 [get_ports adcs_dco_n]
set_property PACKAGE_PIN N9  [get_ports adcs_fco_p]
set_property PACKAGE_PIN P9  [get_ports adcs_fco_n]
set_property PACKAGE_PIN P8  [get_ports adcs_d0_p]
set_property PACKAGE_PIN R8  [get_ports adcs_d0_n]
set_property PACKAGE_PIN R5  [get_ports adcs_d1_p]
set_property PACKAGE_PIN T5  [get_ports adcs_d1_n]
set_property IOSTANDARD  LVDS_25 [get_ports {adcs_dco_p adcs_dco_n adcs_fco_p adcs_fco_n adcs_d0_p adcs_d0_n adcs_d1_p adcs_d1_n}]
set_property DIFF_TERM   FALSE   [get_ports {adcs_dco_p adcs_dco_n adcs_fco_p adcs_fco_n adcs_d0_p adcs_d0_n adcs_d1_p adcs_d1_n}]

# IAS1 Downlink RX (Kria -> Artix): LINK_TX_CLK (SRCC) & LINK_TX_D0
set_property PACKAGE_PIN N13 [get_ports link_tx_clk_p]
set_property PACKAGE_PIN P13 [get_ports link_tx_clk_n]
set_property PACKAGE_PIN M16 [get_ports link_tx_d0_p]
set_property PACKAGE_PIN N16 [get_ports link_tx_d0_n]
set_property IOSTANDARD  LVDS_25 [get_ports {link_tx_clk_p link_tx_clk_n link_tx_d0_p link_tx_d0_n}]
set_property DIFF_TERM   FALSE   [get_ports {link_tx_clk_p link_tx_clk_n link_tx_d0_p link_tx_d0_n}]

# ------------------------------------------------------------------------------
# Bank 34 (VCCO = 2.5 V): IAS1 Uplink TX (Artix -> Kria)
# ------------------------------------------------------------------------------
set_property PACKAGE_PIN N3  [get_ports link_rx_clk_p]
set_property PACKAGE_PIN N2  [get_ports link_rx_clk_n]
set_property PACKAGE_PIN L4  [get_ports link_rx_d0_p]
set_property PACKAGE_PIN M4  [get_ports link_rx_d0_n]
set_property PACKAGE_PIN M2  [get_ports link_rx_d1_p]
set_property PACKAGE_PIN M1  [get_ports link_rx_d1_n]
set_property IOSTANDARD  LVDS_25 [get_ports {link_rx_clk_p link_rx_clk_n link_rx_d0_p link_rx_d0_n link_rx_d1_p link_rx_d1_n}]

# Rev06 Dedicated Ethernet SGMII PHY (Final Routed Pins)
#   Bank 34 (VCCO = 2.5 V, CFG_LDO=01 -> DVDDRG = 2.5 V)
set_property PACKAGE_PIN R2  [get_ports eth_sgtx_p]
set_property PACKAGE_PIN R1  [get_ports eth_sgtx_n]
set_property IOSTANDARD  LVDS_25 [get_ports {eth_sgtx_p eth_sgtx_n}]

set_property PACKAGE_PIN R3  [get_ports eth_sgrx_p]
set_property PACKAGE_PIN T2  [get_ports eth_sgrx_n]
set_property IOSTANDARD  LVDS_25 [get_ports {eth_sgrx_p eth_sgrx_n}]
set_property DIFF_TERM   TRUE    [get_ports {eth_sgrx_p eth_sgrx_n}]

set_property PACKAGE_PIN P1  [get_ports eth_mdc]
set_property IOSTANDARD  LVCMOS25 [get_ports eth_mdc]
set_property SLEW        SLOW     [get_ports eth_mdc]
set_property DRIVE       4        [get_ports eth_mdc]

#   Bank 14 (VCCO = 3.3 V): MDIO open-drain (R1213 1.5k -> 2.5V DVDDRG, do not use EMCCLK), RST_N pulled up via R1214
set_property PACKAGE_PIN M15 [get_ports eth_mdio]
set_property PACKAGE_PIN K13 [get_ports eth_rst_n]
set_property IOSTANDARD  LVCMOS33 [get_ports {eth_mdio eth_rst_n}]
set_property SLEW        SLOW     [get_ports eth_mdio]
set_property DRIVE       4        [get_ports eth_mdio]
set_property BITSTREAM.CONFIG.EXTMASTERCCLK_EN DISABLE [current_design]

# ------------------------------------------------------------------------------
# Bank 15 (VCCO = 3.3 V): Adapter Pmod J1102
# ------------------------------------------------------------------------------
set_property PACKAGE_PIN H16 [get_ports pmod_cs_n]
set_property PACKAGE_PIN G16 [get_ports pmod_mosi]
set_property PACKAGE_PIN J15 [get_ports pmod_miso]
set_property PACKAGE_PIN D13 [get_ports pmod_sclk]
set_property PACKAGE_PIN J16 [get_ports beam_strobe]
set_property PACKAGE_PIN H14 [get_ports pps_sync]
set_property PACKAGE_PIN G15 [get_ports pmod_spare1]
set_property PACKAGE_PIN G11 [get_ports pmod_spare2]
set_property IOSTANDARD  LVCMOS33 [get_ports {pmod_cs_n pmod_mosi pmod_miso pmod_sclk beam_strobe pps_sync pmod_spare1 pmod_spare2}]

# AD9708 8-bit Radar DAC (Bank 15, VCCO = 3.3 V)
set_property PACKAGE_PIN C13 [get_ports dacr_clk]
set_property PACKAGE_PIN A14 [get_ports {dacr_d[0]}]
set_property PACKAGE_PIN A13 [get_ports {dacr_d[1]}]
set_property PACKAGE_PIN A12 [get_ports {dacr_d[2]}]
set_property PACKAGE_PIN B11 [get_ports {dacr_d[3]}]
set_property PACKAGE_PIN B10 [get_ports {dacr_d[4]}]
set_property PACKAGE_PIN A10 [get_ports {dacr_d[5]}]
set_property PACKAGE_PIN A9  [get_ports {dacr_d[6]}]
set_property PACKAGE_PIN A8  [get_ports {dacr_d[7]}]
set_property IOSTANDARD  LVCMOS33 [get_ports {dacr_clk dacr_d[*]}]

# AD9767 Dual 14-bit Interleaved SDR DAC (Bank 15, VCCO = 3.3 V)
set_property PACKAGE_PIN D11 [get_ports {dacs_d[0]}]
set_property PACKAGE_PIN E12 [get_ports {dacs_d[1]}]
set_property PACKAGE_PIN F13 [get_ports {dacs_d[2]}]
set_property PACKAGE_PIN C11 [get_ports {dacs_d[3]}]
set_property PACKAGE_PIN E13 [get_ports {dacs_d[4]}]
set_property PACKAGE_PIN C12 [get_ports {dacs_d[5]}]
set_property PACKAGE_PIN D14 [get_ports {dacs_d[6]}]
set_property PACKAGE_PIN D15 [get_ports {dacs_d[7]}]
set_property PACKAGE_PIN B14 [get_ports {dacs_d[8]}]
set_property PACKAGE_PIN D16 [get_ports {dacs_d[9]}]
set_property PACKAGE_PIN B15 [get_ports {dacs_d[10]}]
set_property PACKAGE_PIN C16 [get_ports {dacs_d[11]}]
set_property PACKAGE_PIN A15 [get_ports {dacs_d[12]}]
set_property PACKAGE_PIN B16 [get_ports {dacs_d[13]}]
set_property PACKAGE_PIN E11 [get_ports dacs_iqclk]
set_property PACKAGE_PIN D10 [get_ports dacs_iqreset]
set_property PACKAGE_PIN G12 [get_ports dacs_iqsel]
set_property PACKAGE_PIN F12 [get_ports dacs_iqwrt]
set_property IOSTANDARD  LVCMOS33 [get_ports {dacs_d[*] dacs_iqclk dacs_iqreset dacs_iqsel dacs_iqwrt}]

# RF Switches & Si549 Clock Mux/I2C (Bank 15, VCCO = 3.3 V)
set_property PACKAGE_PIN C8  [get_ports {sw_ctrl[0]}]
set_property PACKAGE_PIN C9  [get_ports {sw_ctrl[1]}]
set_property PACKAGE_PIN B9  [get_ports {sw_ctrl[2]}]
set_property PACKAGE_PIN B12 [get_ports {sw_ctrl[3]}]
set_property PACKAGE_PIN D9  [get_ports xo_scl]
set_property PACKAGE_PIN C14 [get_ports xo_sda]
set_property PACKAGE_PIN D8  [get_ports clk_sel]
set_property IOSTANDARD  LVCMOS33 [get_ports {sw_ctrl[*] xo_scl xo_sda clk_sel}]

# ------------------------------------------------------------------------------
# Bank 35 (VCCO = 1.8 V): Housekeeping I2C, Alert, Carrier IRQ, Conv SPI, 8x ADAR1000
# ------------------------------------------------------------------------------
set_property PACKAGE_PIN K5  [get_ports hk_scl]
set_property PACKAGE_PIN J5  [get_ports hk_sda]
set_property PACKAGE_PIN K2  [get_ports hk_alert_n]
set_property PACKAGE_PIN H5  [get_ports fpga_irq]
set_property IOSTANDARD  LVCMOS18 [get_ports {hk_scl hk_sda hk_alert_n fpga_irq}]

# Shared Converter 3-wire SPI (AD9484 CSB_R, AD9253 CSB_S)
set_property PACKAGE_PIN J4  [get_ports conv_spi_csb_r]
set_property PACKAGE_PIN L2  [get_ports conv_spi_csb_s]
set_property PACKAGE_PIN K3  [get_ports conv_spi_sclk]
set_property PACKAGE_PIN L3  [get_ports conv_spi_sdio]
set_property IOSTANDARD  LVCMOS18 [get_ports {conv_spi_csb_r conv_spi_csb_s conv_spi_sclk conv_spi_sdio}]

# 8x ADAR1000 Beamformer Ribbon J1103 (Bank 35 LVCMOS18, SLEW SLOW + DRIVE 4 for ribbon SI)
set_property PACKAGE_PIN J1  [get_ports adar_sclk]
set_property PACKAGE_PIN J3  [get_ports adar_sdio]
set_property PACKAGE_PIN K1  [get_ports adar_sdo]
set_property PACKAGE_PIN A5  [get_ports {adar_csb[0]}]
set_property PACKAGE_PIN C6  [get_ports {adar_csb[1]}]
set_property PACKAGE_PIN C4  [get_ports {adar_csb[2]}]
set_property PACKAGE_PIN B1  [get_ports {adar_csb[3]}]
set_property PACKAGE_PIN D3  [get_ports {adar_csb[4]}]
set_property PACKAGE_PIN E1  [get_ports {adar_csb[5]}]
set_property PACKAGE_PIN G4  [get_ports {adar_csb[6]}]
set_property PACKAGE_PIN H1  [get_ports {adar_csb[7]}]
set_property PACKAGE_PIN A4  [get_ports {adar_rx_load[0]}]
set_property PACKAGE_PIN B4  [get_ports {adar_rx_load[1]}]
set_property PACKAGE_PIN B2  [get_ports {adar_rx_load[2]}]
set_property PACKAGE_PIN C2  [get_ports {adar_rx_load[3]}]
set_property PACKAGE_PIN E3  [get_ports {adar_rx_load[4]}]
set_property PACKAGE_PIN F3  [get_ports {adar_rx_load[5]}]
set_property PACKAGE_PIN G1  [get_ports {adar_rx_load[6]}]
set_property PACKAGE_PIN H3  [get_ports {adar_rx_load[7]}]
set_property PACKAGE_PIN A7  [get_ports {adar_tx_load[0]}]
set_property PACKAGE_PIN B5  [get_ports {adar_tx_load[1]}]
set_property PACKAGE_PIN A2  [get_ports {adar_tx_load[2]}]
set_property PACKAGE_PIN C3  [get_ports {adar_tx_load[3]}]
set_property PACKAGE_PIN C1  [get_ports {adar_tx_load[4]}]
set_property PACKAGE_PIN E2  [get_ports {adar_tx_load[5]}]
set_property PACKAGE_PIN F2  [get_ports {adar_tx_load[6]}]
set_property PACKAGE_PIN H2  [get_ports {adar_tx_load[7]}]
set_property PACKAGE_PIN B6  [get_ports {adar_tr[0]}]
set_property PACKAGE_PIN A3  [get_ports {adar_tr[1]}]
set_property PACKAGE_PIN D5  [get_ports {adar_tr[2]}]
set_property PACKAGE_PIN D4  [get_ports {adar_tr[3]}]
set_property PACKAGE_PIN D1  [get_ports {adar_tr[4]}]
set_property PACKAGE_PIN F4  [get_ports {adar_tr[5]}]
set_property PACKAGE_PIN G2  [get_ports {adar_tr[6]}]
set_property PACKAGE_PIN H4  [get_ports {adar_tr[7]}]
set_property IOSTANDARD  LVCMOS18 [get_ports {adar_sclk adar_sdio adar_sdo adar_csb[*] adar_rx_load[*] adar_tx_load[*] adar_tr[*]}]
set_property SLEW        SLOW     [get_ports {adar_sclk adar_sdio adar_csb[*] adar_rx_load[*] adar_tx_load[*] adar_tr[*]}]
set_property DRIVE       4        [get_ports {adar_sclk adar_sdio adar_csb[*] adar_rx_load[*] adar_tx_load[*] adar_tr[*]}]

# ------------------------------------------------------------------------------
# Timing Constraints
# ------------------------------------------------------------------------------
# Primary RF/FPGA clock (400 MHz radar OR 500 MHz SDR, mutually exclusive)
create_clock -period 2.000 -name clk_fpga_500 [get_ports fpga_clk_p]
create_clock -period 2.500 -name clk_fpga_400 -add [get_ports fpga_clk_p]

# Non-MMCM DAC clock (CLK_FPGA / 4 = 125 MHz @ 500M SDR, 100 MHz @ 400M Radar)
create_generated_clock -name clk_dac_500 -divide_by 4 -add -source [get_pins u_clk_mode_ctrl/dac_div_q_reg[1]/C] -master_clock clk_fpga_500 [get_pins u_clk_mode_ctrl/dac_div_q_reg[1]/Q]
create_generated_clock -name clk_dac_400 -divide_by 4 -add -source [get_pins u_clk_mode_ctrl/dac_div_q_reg[1]/C] -master_clock clk_fpga_400 [get_pins u_clk_mode_ctrl/dac_div_q_reg[1]/Q]

# Hardware DRP reconfigures MMCM DIVCLK_DIVIDE (5->4) in 400 MHz mode so VCO/MMCM outputs remain identical
# to 500 MHz mode (200 MHz IDELAYCTRL REFCLK, 125 MHz link_clk, 625/312.5 MHz ETH). Prevent static 4/5 scaling
# through fixed-DIVCLK_DIVIDE=5 RTL MMCM parameters while keeping clk_fpga_400 & clk_dac_400 active at 400/100 MHz.
set_clock_sense -stop_propagation -clocks [get_clocks clk_fpga_400] [get_pins -quiet {u_mmcm_sys/CLKIN1 gen_rev06_eth.u_mmcm_eth/CLKIN1}]

# Always-on STARTUPE2 CFGMCLK (~65 MHz +/-50% -> worst-case 97.5 MHz -> 10 ns)
create_clock -period 10.000 -name clk_cfgmclk [get_pins u_clk_mode_ctrl/u_startupe2/CFGMCLK]

# A-1 & G-7 (docs/REV08_PLAN.md): u_adc_cap's DCO MMCM and u_ddc are held in reset whenever the master clock
# is 500 MHz, so clk_adcr_dco (5.000 ns: 400 MSPS -> 200 MHz DDR DCO) is the only DCO clock through the MMCM.
create_clock -period 5.000  -name clk_adcr_dco     [get_ports adcr_dco_n]
# G-7: with D2 running (500 MSPS) the DCO is 250 MHz (4.000 ns) and clocks only the IDDRs, the BUFR capture
# registers and D2's packer; it is stopped at the DCO MMCM, which stays in reset in that mode.
create_clock -period 4.000  -name clk_adcr_dco_500 -add [get_ports adcr_dco_n]
set_clock_sense -stop_propagation -clocks [get_clocks clk_adcr_dco_500] [get_pins u_adc_cap/u_mmcm_adc/CLKIN1]
# G-7: the AD9484 trainer's clock is a BUFGCTRL of clk_200m (400 MSPS) and refclk_200m (500 MSPS); the select changes
# only with the capture in reset, so the two are separate, exclusive clocks at its output
create_generated_clock -name clk_trn_400 -divide_by 1 -add -source [get_pins u_adc_cap/u_bufg_200m/I0] -master_clock [get_clocks clk_200m_unbuf] [get_pins u_adc_cap/u_bufg_200m/O]
create_generated_clock -name clk_trn_500 -divide_by 1 -add -source [get_pins u_adc_cap/u_bufg_200m/I1] -master_clock [get_clocks refclk_200m_unbuf] [get_pins u_adc_cap/u_bufg_200m/O]
set_clock_groups -physically_exclusive -group [get_clocks clk_trn_400] -group [get_clocks clk_trn_500]

# A-2 (docs/REV08_PLAN.md): AD9253 runs 1-lane 16-bit DDR (DCO = 8 * f_S):
#   - 500 MHz master (f_S = 62.5 MSPS) -> 500 MHz DCO (2.000 ns), BUFR(DIV4) clk_div = 125 MHz (8.000 ns)
#   - 400 MHz master (f_S = 50.0 MSPS) -> 400 MHz DCO (2.500 ns), BUFR(DIV4) clk_div = 100 MHz (10.000 ns)
create_clock -period 2.000  -name clk_adcs_dco_500 [get_ports adcs_dco_p]
create_clock -period 2.500  -name clk_adcs_dco_400 -add [get_ports adcs_dco_p]

create_clock -period 2.000  -name clk_link_tx      [get_ports link_tx_clk_p]

set_clock_groups -physically_exclusive \
    -group [get_clocks -include_generated_clocks clk_fpga_500] \
    -group [get_clocks -include_generated_clocks clk_fpga_400]

set_clock_groups -physically_exclusive \
    -group [get_clocks -include_generated_clocks clk_adcs_dco_500] \
    -group [get_clocks -include_generated_clocks clk_adcs_dco_400]

# G-7: the 250 MHz DCO exists only at 500 MHz, with the DCO MMCM in reset
set_clock_groups -physically_exclusive \
    -group [get_clocks clk_adcr_dco_500] \
    -group [get_clocks -include_generated_clocks {clk_adcr_dco clk_fpga_400}]

set_clock_groups -asynchronous \
    -group [get_clocks -include_generated_clocks {clk_fpga_500 clk_fpga_400}] \
    -group [get_clocks clk_cfgmclk] \
    -group [get_clocks -include_generated_clocks clk_adcr_dco] \
    -group [get_clocks -include_generated_clocks {clk_adcs_dco_500 clk_adcs_dco_400}] \
    -group [get_clocks -include_generated_clocks clk_link_tx]

# Debug UART (PMOD_SPARE1 RX / PMOD_SPARE2 TX) + asynchronous board I/Os
set_property PULLUP TRUE [get_ports pmod_spare1]
set_false_path -from [get_ports {pmod_* beam_strobe pps_sync hk_alert_n}]
set_false_path -to   [get_ports {pmod_miso pmod_spare2 fpga_irq}]

# Trained source-synchronous IDDR / ISERDESE2 inputs (centered via IDELAYE2)
set_false_path -from [get_ports {adcr_d_p[*] adcr_or_p}]
set_false_path -from [get_ports {adcs_fco_p adcs_fco_n adcs_d0_p adcs_d0_n adcs_d1_p adcs_d1_n}]
set_false_path -from [get_ports link_tx_d0_p]
set_false_path -to   [get_ports {link_rx_clk_p link_rx_d0_p link_rx_d1_p}]

# Peripheral DAC / SPI / ADAR / RF-SW / XO I/Os (forwarded ODDR clocks or slow async busses)
set_false_path -from [get_ports {conv_spi_sdio adar_sdio adar_sdo xo_scl xo_sda}]
set_false_path -to   [get_ports {dacr_clk dacr_d[*] dacs_d[*] dacs_iqclk dacs_iqreset dacs_iqsel dacs_iqwrt conv_spi_* adar_* sw_ctrl[*] xo_scl xo_sda clk_sel}]

# Rev06 Ethernet SGMII / MDIO / PHY pins (asynchronous oversampled RX & slow MDIO)
set_false_path -from [get_ports {eth_sgrx_p eth_sgrx_n eth_mdio}]
set_false_path -to   [get_ports {eth_sgtx_p eth_sgtx_n eth_mdc eth_mdio eth_rst_n}]

# Async-assert reset synchronizers and Gray-code / toggle CDC crossings
set_false_path -to [get_pins -quiet -hier -filter {NAME =~ *rst*sync*/PRE || NAME =~ *rst*sync*/CLR}]
set_max_delay -datapath_only 3.500 -from [get_clocks clk_adcr_dco] -to [get_clocks {clk_200m_unbuf clk_trn_400}]
# G-7: the AERIS CIC's comb stages 1-4 take one sample per 4 clk_400m cycles and load each register 4 cycles
# after the registers it reads (cic_decimator_4x_enhanced.v)
set_multicycle_path -setup 4 -from [get_cells -hier -filter {NAME =~ u_ddc/u_ddc/cic_*_inst/comb_reg* || NAME =~ u_ddc/u_ddc/cic_*_inst/comb_delay_reg*}] -to [get_cells -hier -filter {NAME =~ u_ddc/u_ddc/cic_*_inst/comb_reg* || NAME =~ u_ddc/u_ddc/cic_*_inst/comb_delay_reg* || NAME =~ u_ddc/u_ddc/cic_*_inst/temp_scaled_output_reg*}]
set_multicycle_path -hold 3 -from [get_cells -hier -filter {NAME =~ u_ddc/u_ddc/cic_*_inst/comb_reg* || NAME =~ u_ddc/u_ddc/cic_*_inst/comb_delay_reg*}] -to [get_cells -hier -filter {NAME =~ u_ddc/u_ddc/cic_*_inst/comb_reg* || NAME =~ u_ddc/u_ddc/cic_*_inst/comb_delay_reg* || NAME =~ u_ddc/u_ddc/cic_*_inst/temp_scaled_output_reg*}]
# G-7: D2's Gray FIFO (dco_bufr -> link_clk) and the trainer's two-flop sampler (dco_bufr -> refclk_200m through
# u_adc_cap/u_bufg_200m); the BUFGCTRL's select changes only with the capture in reset; the training status
# into link_clk (D2_STAT, D2's enable)
set_max_delay -datapath_only 4.000 -from [get_clocks clk_adcr_dco_500] -to [get_clocks -of_objects [get_pins {u_mmcm_sys/CLKOUT0 u_mmcm_sys/CLKOUT2}]]
set_max_delay -datapath_only 4.000 -from [get_clocks clk_adcr_dco_500] -to [get_clocks clk_trn_500]
set_false_path -to [get_pins {u_adc_cap/u_bufg_200m/S0 u_adc_cap/u_bufg_200m/S1}]
# the OR pin's IDDR (M6/N6, far from the DCO's BUFR) is not used at 500 MSPS: D2 takes codes 0 and 255 as over-range
set_false_path -from [get_clocks clk_adcr_dco_500] -through [get_pins {u_adc_cap/g_adc_bits[8].u_iddr_d/Q1 u_adc_cap/g_adc_bits[8].u_iddr_d/Q2}]
# the trainer's results (steady after training) run on refclk_200m in 500 MSPS mode: into link_clk (D2_STAT,
# the tap readback, D2's enable) and the D2 run condition into refclk_200m
set_max_delay -datapath_only 8.000 -from [get_cells -quiet {u_adc_cap/adc_trained_reg* u_adc_cap/dco_phase_err_reg* u_adc_cap/eye_width_min_reg* u_adc_cap/tap_val_reg*}] -to [get_clocks -of_objects [get_pins u_mmcm_sys/CLKOUT0]]
set_max_delay -datapath_only 4.000 -from [get_clocks -of_objects [get_pins u_mmcm_sys/CLKOUT0]] -to [get_cells -quiet {d2_run_ref_s_reg[0]}]
set_max_delay -datapath_only 2.400 -from [get_clocks clk_100m_unbuf] -to [get_clocks clk_400m_unbuf]
set_max_delay -datapath_only 2.400 -from [get_clocks clk_400m_unbuf] -to [get_clocks clk_100m_unbuf]
set_max_delay -datapath_only 2.400 -from [get_clocks link_clk_unbuf] -to [get_cells -quiet -hier -filter {NAME =~ *tr_start_sync_reg[0]* || NAME =~ *tr_pat_sync_reg[0]*}]
set_max_delay -datapath_only 3.500 -from [get_clocks {clk_200m_unbuf clk_trn_400}] -to [get_pins -quiet adc_tr_100_sync_reg[0]/D]
set_max_delay -quiet -datapath_only 3.000 -from [get_clocks -quiet -of_objects [get_pins -quiet gen_rev06_eth.u_mmcm_eth/CLKOUT2]] -to [get_clocks -of_objects [get_pins u_mmcm_sys/CLKOUT0]]
set_max_delay -quiet -datapath_only 3.000 -from [get_clocks -of_objects [get_pins u_mmcm_sys/CLKOUT0]] -to [get_clocks -quiet -of_objects [get_pins -quiet gen_rev06_eth.u_mmcm_eth/CLKOUT2]]
set_max_delay -quiet -datapath_only 6.000 -from [get_clocks -of_objects [get_pins u_mmcm_sys/CLKOUT0]] -to [get_clocks -of_objects [get_pins u_mmcm_sys/CLKOUT3]]
set_max_delay -quiet -datapath_only 6.000 -from [get_clocks -of_objects [get_pins u_mmcm_sys/CLKOUT3]] -to [get_clocks -of_objects [get_pins u_mmcm_sys/CLKOUT0]]
set_max_delay -quiet -datapath_only 6.000 -from [get_clocks -of_objects [get_pins u_mmcm_sys/CLKOUT0]] -to [get_clocks {clk_dac_500 clk_dac_400}]
set_max_delay -quiet -datapath_only 6.000 -from [get_clocks {clk_dac_500 clk_dac_400}] -to [get_clocks -of_objects [get_pins u_mmcm_sys/CLKOUT0]]
set_max_delay -quiet -datapath_only 3.000 -from [get_clocks -of_objects [get_pins u_mmcm_sys/CLKOUT0]] -to [get_clocks -quiet -of_objects [get_pins -quiet gen_rev06_eth.u_mmcm_eth/CLKOUT2]]
