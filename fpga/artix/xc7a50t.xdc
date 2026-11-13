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

# ------------------------------------------------------------------------------
# Bank 35 (VCCO = 1.8 V): Housekeeping I2C, Alert, Carrier IRQ
# ------------------------------------------------------------------------------
set_property PACKAGE_PIN K5  [get_ports hk_scl]
set_property PACKAGE_PIN J5  [get_ports hk_sda]
set_property PACKAGE_PIN K2  [get_ports hk_alert_n]
set_property PACKAGE_PIN H5  [get_ports fpga_irq]
set_property IOSTANDARD  LVCMOS18 [get_ports {hk_scl hk_sda hk_alert_n fpga_irq}]

# ------------------------------------------------------------------------------
# Timing Constraints
# ------------------------------------------------------------------------------
create_clock -period 10.000 -name clk_fpga     [get_ports fpga_clk_p]
create_clock -period 5.000  -name clk_adcr_dco [get_ports adcr_dco_n]
create_clock -period 2.000  -name clk_link_tx  [get_ports link_tx_clk_p]

set_clock_groups -asynchronous \
    -group [get_clocks -include_generated_clocks clk_fpga] \
    -group [get_clocks -include_generated_clocks clk_adcr_dco] \
    -group [get_clocks -include_generated_clocks clk_link_tx]

# Asynchronous / dynamically eye-trained board I/Os
set_false_path -from [get_ports {pmod_* beam_strobe pps_sync hk_alert_n}]
set_false_path -to   [get_ports {pmod_miso pmod_spare2 fpga_irq}]

# Trained source-synchronous IDDR / ISERDESE2 inputs (centered via IDELAYE2)
set_false_path -from [get_ports {adcr_d_p[*] adcr_or_p}]
set_false_path -from [get_ports link_tx_d0_p]
set_false_path -to   [get_ports {link_rx_clk_p link_rx_d0_p link_rx_d1_p}]

# Async-assert reset synchronizers and Gray-code / toggle CDC crossings
set_false_path -to [get_pins -quiet -hier -filter {NAME =~ *rst_sync*/PRE || NAME =~ *rst_sync*/CLR || NAME =~ *reset_sync*/CLR}]
set_max_delay -datapath_only 3.500 -from [get_clocks clk_adcr_dco] -to [get_clocks clk_200m_unbuf]
set_max_delay -datapath_only 2.400 -from [get_clocks clk_100m_unbuf] -to [get_clocks clk_400m_unbuf]
set_max_delay -datapath_only 2.400 -from [get_clocks clk_400m_unbuf] -to [get_clocks clk_100m_unbuf]
set_max_delay -datapath_only 2.400 -to [get_cells -quiet -hier -filter {NAME =~ *tr_start_sync_reg[0]* || NAME =~ *tr_pat_sync_reg[0]* || NAME =~ *adc_tr_100_sync_reg[0]*}]
