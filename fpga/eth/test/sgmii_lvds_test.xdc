# Constraints for SGMII 1.25 Gb/s Over LVDS Feasibility Proof (XC7A50T-FTG256-2)
# Pins match PINMAP.md ETH assembly option + unused Bank 14 balls from control_spec.py.

set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]

# Primary 100 MHz clock (Bank 14 MRCC, external matched attenuator)
set_property PACKAGE_PIN N11     [get_ports fpga_clk_p]
set_property PACKAGE_PIN N12     [get_ports fpga_clk_n]
set_property IOSTANDARD  LVDS_25 [get_ports {fpga_clk_p fpga_clk_n}]
set_property DIFF_TERM   FALSE   [get_ports {fpga_clk_p fpga_clk_n}]

# ETH SGMII RX (Bank 14 VCCO = 3.3V, external 100 ohm termination R105/R1209)
set_property PACKAGE_PIN M16     [get_ports sgmii_rx_p]
set_property PACKAGE_PIN N16     [get_ports sgmii_rx_n]
set_property IOSTANDARD  LVDS_25 [get_ports {sgmii_rx_p sgmii_rx_n}]
set_property DIFF_TERM   FALSE   [get_ports {sgmii_rx_p sgmii_rx_n}]

# ETH SGMII TX (Bank 34 VCCO = 2.5V, native LVDS_25 output)
set_property PACKAGE_PIN L4      [get_ports sgmii_tx_p]
set_property PACKAGE_PIN M4      [get_ports sgmii_tx_n]
set_property IOSTANDARD  LVDS_25 [get_ports {sgmii_tx_p sgmii_tx_n}]

# Unused Bank 14 balls for reset and status observation (keeps logic live)
set_property PACKAGE_PIN K13      [get_ports rst_n]
set_property PACKAGE_PIN K12      [get_ports status_locked]
set_property PACKAGE_PIN L13      [get_ports status_aligned]
set_property PACKAGE_PIN M15      [get_ports status_err]
set_property IOSTANDARD  LVCMOS33 [get_ports {rst_n status_locked status_aligned status_err}]

# Primary 100 MHz clock definition -> MMCM derives 200 / 625(0/90) / 312.5(0/45) / 125 MHz
create_clock -period 10.000 -name sys_clk_100m [get_ports fpga_clk_p]

# Asynchronous I/O and reset paths
set_false_path -from [get_ports {rst_n sgmii_rx_p sgmii_rx_n}]
set_false_path -to   [get_ports {sgmii_tx_p sgmii_tx_n status_locked status_aligned status_err}]
set_false_path -to   [get_pins -quiet -hier -filter {NAME =~ *rst*sync*/PRE || NAME =~ *rst*sync*/CLR}]

# Gray-code & toggle CDC paths between 312.5 MHz and 125 MHz
set_max_delay -datapath_only 3.000 \
    -from [get_clocks -of_objects [get_pins u_mmcm_sgmii/CLKOUT3]] \
    -to   [get_clocks -of_objects [get_pins u_mmcm_sgmii/CLKOUT5]]
set_max_delay -datapath_only 3.000 \
    -from [get_clocks -of_objects [get_pins u_mmcm_sgmii/CLKOUT5]] \
    -to   [get_clocks -of_objects [get_pins u_mmcm_sgmii/CLKOUT3]]
