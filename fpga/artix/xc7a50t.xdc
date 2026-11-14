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

#   Bank 14 (VCCO = 3.3 V): MDIO open-drain (R1213 1.5k -> 2.5V DVDDRG, do not use EMCCLK), RST_N pulled up via R1214
set_property PACKAGE_PIN M15 [get_ports eth_mdio]
set_property PACKAGE_PIN K13 [get_ports eth_rst_n]
set_property IOSTANDARD  LVCMOS33 [get_ports {eth_mdio eth_rst_n}]
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
create_clock -period 10.000 -name clk_fpga     [get_ports fpga_clk_p]
create_clock -period 5.000  -name clk_adcr_dco [get_ports adcr_dco_n]
create_clock -period 4.000  -name clk_adcs_dco [get_ports adcs_dco_p]
create_clock -period 2.000  -name clk_link_tx  [get_ports link_tx_clk_p]

set_clock_groups -asynchronous \
    -group [get_clocks -include_generated_clocks clk_fpga] \
    -group [get_clocks -include_generated_clocks clk_adcr_dco] \
    -group [get_clocks -include_generated_clocks clk_adcs_dco] \
    -group [get_clocks -include_generated_clocks clk_link_tx]

# Asynchronous / dynamically eye-trained board I/Os
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
set_max_delay -datapath_only 3.500 -from [get_clocks clk_adcr_dco] -to [get_clocks clk_200m_unbuf]
set_max_delay -datapath_only 2.400 -from [get_clocks clk_100m_unbuf] -to [get_clocks clk_400m_unbuf]
set_max_delay -datapath_only 2.400 -from [get_clocks clk_400m_unbuf] -to [get_clocks clk_100m_unbuf]
set_max_delay -datapath_only 2.400 -from [get_clocks link_clk_unbuf] -to [get_cells -quiet -hier -filter {NAME =~ *tr_start_sync_reg[0]* || NAME =~ *tr_pat_sync_reg[0]*}]
set_max_delay -datapath_only 3.500 -from [get_clocks clk_200m_unbuf] -to [get_pins -quiet adc_tr_100_sync_reg[0]/D]
set_max_delay -quiet -datapath_only 3.000 -from [get_clocks -quiet -of_objects [get_pins -quiet gen_rev06_eth.u_mmcm_eth/CLKOUT2]] -to [get_clocks -of_objects [get_pins u_mmcm_sys/CLKOUT0]]
set_max_delay -quiet -datapath_only 3.000 -from [get_clocks -of_objects [get_pins u_mmcm_sys/CLKOUT0]] -to [get_clocks -quiet -of_objects [get_pins -quiet gen_rev06_eth.u_mmcm_eth/CLKOUT2]]
set_max_delay -quiet -datapath_only 6.000 -from [get_clocks -of_objects [get_pins u_mmcm_sys/CLKOUT0]] -to [get_clocks -of_objects [get_pins u_mmcm_sys/CLKOUT3]]
set_max_delay -quiet -datapath_only 6.000 -from [get_clocks -of_objects [get_pins u_mmcm_sys/CLKOUT3]] -to [get_clocks -of_objects [get_pins u_mmcm_sys/CLKOUT0]]
set_max_delay -quiet -datapath_only 3.000 -from [get_clocks link_clk_unbuf] -to [get_clocks -quiet -of_objects [get_pins -quiet gen_rev06_eth.u_mmcm_eth/CLKOUT2]]
