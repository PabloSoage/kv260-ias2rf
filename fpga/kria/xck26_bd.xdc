# Kria K26 SOM (XCK26-SFVC784-2LV-C) Block-Design Constraints for KV260 IAS1 Link
# Matches fpga/kria/xck26.xdc pinout and IO standards for the Block Design wrapper.

# ------------------------------------------------------------------------------
# 1. Clocks & CDC Boundaries
# ------------------------------------------------------------------------------
# Zynq UltraScale+ PS pl_clk0 (100 MHz) is auto-constrained by the PS IP as clk_pl_0.
create_clock -period 2.000 -name link_rx_clk [get_ports link_rx_clk_p]

set_clock_groups -asynchronous \
    -group [get_clocks -include_generated_clocks clk_pl_0] \
    -group [get_clocks -include_generated_clocks link_rx_clk]

# LINK_RX_CLK lands on C1/B1 (QBC pin in Bank 66 HP, HPIOB_M_I -> BUFGCE/BUFGCE_DIV)
set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets -hier -filter {NAME =~ */rx_clk_ibuf}]
set_property CLOCK_DELAY_GROUP rx_clk_grp [get_nets -hier -filter {NAME =~ */rx_clk_hs || NAME =~ */rx_clkdiv}]
set_property CLOCK_DELAY_GROUP tx_clk_grp [get_nets -hier -filter {NAME =~ */tx_clk_hs || NAME =~ */tx_clk_div}]

# ------------------------------------------------------------------------------
# 2. Differential Link Pairs -- Bank 66 HP (VCCO = PL_1V2 = 1.2 V, DIFF_SSTL12)
# ------------------------------------------------------------------------------
# Artix -> Kria Uplink (AC-coupled 100 nF on adapter, split RTT_48 termination + 0.6 V bias on die)
set_property PACKAGE_PIN C1 [get_ports link_rx_clk_p]
set_property PACKAGE_PIN B1 [get_ports link_rx_clk_n]
set_property PACKAGE_PIN A2 [get_ports link_rx_d0_p]
set_property PACKAGE_PIN A1 [get_ports link_rx_d0_n]
set_property PACKAGE_PIN B3 [get_ports link_rx_d1_p]
set_property PACKAGE_PIN A3 [get_ports link_rx_d1_n]

# Kria -> Artix Downlink (AC-coupled 100 nF on adapter, RDRV_60_60 -> ~0.55 V across 100 ohm @ Artix)
set_property PACKAGE_PIN D4 [get_ports link_tx_clk_p]
set_property PACKAGE_PIN C4 [get_ports link_tx_clk_n]
set_property PACKAGE_PIN B4 [get_ports link_tx_d0_p]
set_property PACKAGE_PIN A4 [get_ports link_tx_d0_n]

set_property IOSTANDARD DIFF_SSTL12 [get_ports {link_rx_clk_p link_rx_clk_n link_rx_d0_p link_rx_d0_n link_rx_d1_p link_rx_d1_n link_tx_clk_p link_tx_clk_n link_tx_d0_p link_tx_d0_n}]
set_property ODT RTT_48 [get_ports {link_rx_clk_p link_rx_d0_p link_rx_d1_p}]
set_property OUTPUT_IMPEDANCE RDRV_60_60 [get_ports {link_tx_clk_p link_tx_d0_p}]

# ------------------------------------------------------------------------------
# 3. Single-Ended IAS1 Signals & Carrier Pmod J2
# ------------------------------------------------------------------------------
# Bank 66 HP (1.2 V side of carrier SN74AVC4T245 translator U72)
set_property PACKAGE_PIN G8 [get_ports fpga_irq]
set_property IOSTANDARD LVCMOS12 [get_ports fpga_irq]

# Bank 45 HD (3.3 V)
set_property PACKAGE_PIN G11 [get_ports hk_scl]
set_property PACKAGE_PIN F10 [get_ports hk_sda]
set_property PACKAGE_PIN K13 [get_ports fpga_prog_b]
set_property IOSTANDARD LVCMOS33 [get_ports {hk_scl hk_sda fpga_prog_b}]
set_property PULLUP TRUE [get_ports {hk_scl hk_sda}]
set_property DRIVE 8 [get_ports fpga_prog_b]
set_property SLEW SLOW [get_ports fpga_prog_b]

# KV260 Pmod J2 (pins 1..8 = HDA11..18)
set_property PACKAGE_PIN H12 [get_ports pmod_cs_n]
set_property PACKAGE_PIN E10 [get_ports pmod_mosi]
set_property PACKAGE_PIN D10 [get_ports pmod_miso]
set_property PACKAGE_PIN C11 [get_ports pmod_sclk]
set_property PACKAGE_PIN B10 [get_ports pmod_beam_strobe]
set_property PACKAGE_PIN E12 [get_ports pmod_pps_sync]
set_property PACKAGE_PIN D11 [get_ports pmod_spare1]
set_property PACKAGE_PIN B11 [get_ports pmod_spare2]
set_property IOSTANDARD LVCMOS33 [get_ports {pmod_cs_n pmod_mosi pmod_miso pmod_sclk pmod_beam_strobe pmod_pps_sync pmod_spare1 pmod_spare2}]
set_property DRIVE 8 [get_ports {pmod_cs_n pmod_mosi pmod_sclk pmod_beam_strobe pmod_pps_sync pmod_spare1}]
set_property SLEW SLOW [get_ports {pmod_cs_n pmod_mosi pmod_sclk pmod_beam_strobe pmod_pps_sync pmod_spare1}]

# Async / low-rate control I/Os
set_false_path -from [get_ports {fpga_irq hk_scl hk_sda pmod_miso pmod_spare2}]
set_false_path -to   [get_ports {fpga_prog_b hk_scl hk_sda pmod_cs_n pmod_mosi pmod_sclk pmod_beam_strobe pmod_pps_sync pmod_spare1}]
