# KV260 (xck26-sfvc784-2LV-c) Block Design + Bitstream + XSA Build Script
# Run headless from repo root:
#   vivado -mode batch -nojournal -nolog -source fpga/kria/bd.tcl

set script_dir [file dirname [file normalize [info script]]]
set fpga_dir   [file dirname $script_dir]
set proj_dir   [file join $script_dir ".bd_proj"]
set rpt_dir    [file join $script_dir "reports"]
set out_dir    [file join $script_dir "out"]
file mkdir $rpt_dir
file mkdir $out_dir

create_project -force kria_bd $proj_dir -part xck26-sfvc784-2LV-c

# Import plain-Verilog link modules + Kria BD-compatible wrapper
add_files -norecurse [glob [file join $fpga_dir "link" "*.v"]]
add_files -norecurse [file join $script_dir "link_axis.v"]
add_files -norecurse [file join $script_dir "kria_cordic.v"]
add_files -norecurse [file join $script_dir "kria_channel_rx.v"]
add_files -norecurse [file join $script_dir "kria_adsb_rx.v"]
add_files -norecurse [file join $script_dir "kria_tx_mod.v"]
add_files -norecurse [file join $script_dir "kria_radar_proc.v"]
add_files -norecurse [file join $script_dir "kria_dsp_suite.v"]
add_files -norecurse [file join $script_dir "kria_pl_link.v"]
add_files -norecurse [file join $script_dir "kria_pps.v"]
add_files -norecurse [file join $script_dir "integrations" "kria_bev_grid.v"]
add_files -norecurse [file join $script_dir "kria_bev_axi.v"]
add_files -norecurse [file join $script_dir "integrations" "kria_doa.v"]
add_files -norecurse [file join $script_dir "integrations" "kria_sweep.v"]
update_compile_order -fileset sources_1

# ------------------------------------------------------------------------------
# Create Block Design: ias2rf_k26_bd
# ------------------------------------------------------------------------------
create_bd_design "ias2rf_k26_bd"

set ps8 [create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e ps8]
set_property -dict [list \
    CONFIG.PSU__FPGA_PL0_ENABLE {1} \
    CONFIG.PSU__CRL_APB__PL0_REF_CTRL__SRCSEL {IOPLL} \
    CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {100} \
    CONFIG.PSU__USE__M_AXI_GP0 {0} \
    CONFIG.PSU__USE__M_AXI_GP1 {0} \
    CONFIG.PSU__USE__M_AXI_GP2 {1} \
    CONFIG.PSU__MAXIGP2__DATA_WIDTH {32} \
    CONFIG.PSU__USE__S_AXI_GP2 {1} \
    CONFIG.PSU__SAXIGP2__DATA_WIDTH {64} \
    CONFIG.PSU__USE__IRQ0 {1} \
    CONFIG.PSU__I2C0__PERIPHERAL__ENABLE {1} \
    CONFIG.PSU__I2C0__PERIPHERAL__IO {EMIO} \
    CONFIG.PSU__SPI0__PERIPHERAL__ENABLE {1} \
    CONFIG.PSU__SPI0__PERIPHERAL__IO {EMIO} \
    CONFIG.PSU__UART1__PERIPHERAL__ENABLE {1} \
    CONFIG.PSU__UART1__PERIPHERAL__IO {EMIO} \
    CONFIG.PSU__GPIO_EMIO__PERIPHERAL__ENABLE {1} \
    CONFIG.PSU__GPIO_EMIO__PERIPHERAL__IO {8} \
    CONFIG.PSU__DDRC__ENABLE {1} \
    CONFIG.PSU__DDRC__COMPONENTS {Components} \
    CONFIG.PSU__DDRC__DEVICE_CAPACITY {4096 MBits} \
    CONFIG.PSU__DDRC__ROW_ADDR_COUNT {15} \
    CONFIG.PSU__DDRC__BUS_WIDTH {64 Bit} \
    CONFIG.PSU__DDRC__SPEED_BIN {DDR4_2400P} \
] $ps8

set rst_sys [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset rst_ps8_100M]
set link_pl [create_bd_cell -type module -reference kria_pl_link kria_pl_link_0]
# GPS PPS capture and disciplined PPS generator (fpga/kria/kria_pps.v)
set pps_blk [create_bd_cell -type module -reference kria_pps kria_pps_0]
# EMIO GPIO[2], the software PPS, into kria_pps (mode 0 keeps the old behaviour)
set gpio2 [create_bd_cell -type ip -vlnv xilinx.com:ip:xlslice xlslice_gpio2]
set_property -dict [list CONFIG.DIN_WIDTH {8} CONFIG.DIN_FROM {2} CONFIG.DIN_TO {2}] $gpio2

# Bird's-eye-view fusion grid (fpga/kria/kria_bev_axi.v around integrations/kria_bev_grid.v) and an
# S2MM-only DMA that writes its 64 KiB dumps to DDR
set bev [create_bd_cell -type module -reference kria_bev_axi kria_bev_0]
set dma1 [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma axi_dma_1]
set_property -dict [list \
    CONFIG.c_include_sg {0} \
    CONFIG.c_sg_include_stscntrl_strm {0} \
    CONFIG.c_include_mm2s {0} \
    CONFIG.c_sg_length_width {17} \
    CONFIG.c_m_axi_s2mm_data_width {64} \
    CONFIG.c_s_axis_s2mm_tdata_width {64} \
    CONFIG.c_s2mm_burst_size {64} \
] $dma1

set dma0 [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma axi_dma_0]
set_property -dict [list \
    CONFIG.c_include_sg {0} \
    CONFIG.c_sg_include_stscntrl_strm {0} \
    CONFIG.c_sg_length_width {23} \
    CONFIG.c_m_axi_mm2s_data_width {64} \
    CONFIG.c_m_axi_s2mm_data_width {64} \
    CONFIG.c_m_axis_mm2s_tdata_width {64} \
    CONFIG.c_s_axis_s2mm_tdata_width {64} \
    CONFIG.c_include_mm2s_dre {1} \
    CONFIG.c_include_s2mm_dre {1} \
    CONFIG.c_m_axi_mm2s_max_burst_len {64} \
    CONFIG.c_m_axi_s2mm_max_burst_len {64} \
] $dma0

# KrakenSDR direction finding (integrations/kria_doa.v): the A53s' aligned snapshots in through an MM2S-only DMA;
# R and the Bartlett spectrum are read back over AXI-Lite
set doa [create_bd_cell -type module -reference kria_doa_axi kria_doa_0]
set dma2 [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma axi_dma_2]
set_property -dict [list \
    CONFIG.c_include_sg {0} \
    CONFIG.c_sg_include_stscntrl_strm {0} \
    CONFIG.c_include_s2mm {0} \
    CONFIG.c_sg_length_width {23} \
    CONFIG.c_m_axi_mm2s_data_width {64} \
    CONFIG.c_m_axis_mm2s_tdata_width {64} \
    CONFIG.c_mm2s_burst_size {64} \
] $dma2

# HackRF Pro sweep (integrations/kria_sweep.v): USB blocks in, 128 power bins per block out, one DMA each way
set swp [create_bd_cell -type module -reference kria_sweep_axi kria_sweep_0]
set dma3 [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma axi_dma_3]
set_property -dict [list \
    CONFIG.c_include_sg {0} \
    CONFIG.c_sg_include_stscntrl_strm {0} \
    CONFIG.c_sg_length_width {23} \
    CONFIG.c_m_axi_mm2s_data_width {64} \
    CONFIG.c_m_axis_mm2s_tdata_width {64} \
    CONFIG.c_m_axi_s2mm_data_width {64} \
    CONFIG.c_s_axis_s2mm_tdata_width {64} \
    CONFIG.c_mm2s_burst_size {64} \
    CONFIG.c_s2mm_burst_size {64} \
] $dma3

set smc_ctrl [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect axi_smc_ctrl]
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {9}] $smc_ctrl

set smc_hp0 [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect axi_smc_hp0]
set_property -dict [list CONFIG.NUM_SI {6} CONFIG.NUM_MI {1}] $smc_hp0

set irqc [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconcat xlconcat_0]
set_property -dict [list CONFIG.NUM_PORTS {8}] $irqc

# Clocks & Reset
connect_bd_net [get_bd_pins ps8/pl_clk0] \
    [get_bd_pins ps8/maxihpm0_lpd_aclk] \
    [get_bd_pins ps8/saxihp0_fpd_aclk] \
    [get_bd_pins rst_ps8_100M/slowest_sync_clk] \
    [get_bd_pins kria_pl_link_0/pl_clk_100m]     [get_bd_pins kria_pps_0/clk] \
    [get_bd_pins axi_dma_0/s_axi_lite_aclk] \
    [get_bd_pins axi_dma_0/m_axi_mm2s_aclk] \
    [get_bd_pins axi_dma_0/m_axi_s2mm_aclk] \
    [get_bd_pins kria_bev_0/clk] \
    [get_bd_pins axi_dma_1/s_axi_lite_aclk] \
    [get_bd_pins axi_dma_1/m_axi_s2mm_aclk] \
    [get_bd_pins kria_doa_0/clk] [get_bd_pins axi_dma_2/s_axi_lite_aclk] [get_bd_pins axi_dma_2/m_axi_mm2s_aclk] \
    [get_bd_pins kria_sweep_0/clk] [get_bd_pins axi_dma_3/s_axi_lite_aclk] \
    [get_bd_pins axi_dma_3/m_axi_mm2s_aclk] [get_bd_pins axi_dma_3/m_axi_s2mm_aclk] \
    [get_bd_pins axi_smc_ctrl/aclk] \
    [get_bd_pins axi_smc_hp0/aclk]

connect_bd_net [get_bd_pins ps8/pl_resetn0] [get_bd_pins rst_ps8_100M/ext_reset_in]
connect_bd_net [get_bd_pins rst_ps8_100M/peripheral_aresetn] \
    [get_bd_pins kria_pl_link_0/pl_resetn]     [get_bd_pins kria_pps_0/resetn] \
    [get_bd_pins axi_dma_0/axi_resetn] \
    [get_bd_pins kria_bev_0/resetn] [get_bd_pins axi_dma_1/axi_resetn] \
    [get_bd_pins kria_doa_0/resetn] [get_bd_pins axi_dma_2/axi_resetn] \
    [get_bd_pins kria_sweep_0/resetn] [get_bd_pins axi_dma_3/axi_resetn] \
    [get_bd_pins axi_smc_ctrl/aresetn] \
    [get_bd_pins axi_smc_hp0/aresetn]

# AXI4-Lite Control Plane (PS HPM0_LPD -> kria_pl_link CSRs & axi_dma CSRs)
connect_bd_intf_net [get_bd_intf_pins ps8/M_AXI_HPM0_LPD] [get_bd_intf_pins axi_smc_ctrl/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_smc_ctrl/M00_AXI] [get_bd_intf_pins kria_pl_link_0/s_axi]
connect_bd_intf_net [get_bd_intf_pins axi_smc_ctrl/M01_AXI] [get_bd_intf_pins axi_dma_0/S_AXI_LITE]
connect_bd_intf_net [get_bd_intf_pins axi_smc_ctrl/M02_AXI] [get_bd_intf_pins kria_pps_0/s_axi]
connect_bd_intf_net [get_bd_intf_pins axi_smc_ctrl/M03_AXI] [get_bd_intf_pins kria_bev_0/s_axi]
connect_bd_intf_net [get_bd_intf_pins axi_smc_ctrl/M04_AXI] [get_bd_intf_pins axi_dma_1/S_AXI_LITE]
connect_bd_intf_net [get_bd_intf_pins axi_smc_ctrl/M05_AXI] [get_bd_intf_pins kria_doa_0/s_axi]
connect_bd_intf_net [get_bd_intf_pins axi_smc_ctrl/M06_AXI] [get_bd_intf_pins axi_dma_2/S_AXI_LITE]
connect_bd_intf_net [get_bd_intf_pins axi_smc_ctrl/M07_AXI] [get_bd_intf_pins kria_sweep_0/s_axi]
connect_bd_intf_net [get_bd_intf_pins axi_smc_ctrl/M08_AXI] [get_bd_intf_pins axi_dma_3/S_AXI_LITE]

# AXI4 High-Performance Data Plane (axi_dma S2MM/MM2S <-> PS S_AXI_HP0_FPD)
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXI_MM2S] [get_bd_intf_pins axi_smc_hp0/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXI_S2MM] [get_bd_intf_pins axi_smc_hp0/S01_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_dma_1/M_AXI_S2MM] [get_bd_intf_pins axi_smc_hp0/S02_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_dma_2/M_AXI_MM2S] [get_bd_intf_pins axi_smc_hp0/S03_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_dma_3/M_AXI_MM2S] [get_bd_intf_pins axi_smc_hp0/S04_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_dma_3/M_AXI_S2MM] [get_bd_intf_pins axi_smc_hp0/S05_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_smc_hp0/M00_AXI]  [get_bd_intf_pins ps8/S_AXI_HP0_FPD]

# AXI4-Stream Link <-> AXI DMA
connect_bd_intf_net [get_bd_intf_pins kria_pl_link_0/m_axis_rx] [get_bd_intf_pins axi_dma_0/S_AXIS_S2MM]
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXIS_MM2S]   [get_bd_intf_pins kria_pl_link_0/s_axis_tx]
# Grid dumps -> axi_dma_1. s_axis_det is kept for a LiDAR DMA; until then its tvalid is tied to 0
connect_bd_intf_net [get_bd_intf_pins kria_bev_0/m_axis] [get_bd_intf_pins axi_dma_1/S_AXIS_S2MM]
# KrakenSDR snapshots -> kria_doa; HackRF blocks -> kria_sweep -> its bins back to DDR
connect_bd_intf_net [get_bd_intf_pins axi_dma_2/M_AXIS_MM2S] [get_bd_intf_pins kria_doa_0/s_axis]
connect_bd_intf_net [get_bd_intf_pins axi_dma_3/M_AXIS_MM2S] [get_bd_intf_pins kria_sweep_0/s_axis]
connect_bd_intf_net [get_bd_intf_pins kria_sweep_0/m_axis]   [get_bd_intf_pins axi_dma_3/S_AXIS_S2MM]

# Interrupts -> PS pl_ps_irq0[7:0] (all eight used; a ninth source goes to pl_ps_irq1)
connect_bd_net [get_bd_pins kria_pl_link_0/irq_fpga]    [get_bd_pins xlconcat_0/In0]
connect_bd_net [get_bd_pins kria_pl_link_0/irq_link_up] [get_bd_pins xlconcat_0/In1]
connect_bd_net [get_bd_pins axi_dma_0/s2mm_introut]     [get_bd_pins xlconcat_0/In2]
connect_bd_net [get_bd_pins axi_dma_0/mm2s_introut]     [get_bd_pins xlconcat_0/In3]
connect_bd_net [get_bd_pins kria_pps_0/irq]             [get_bd_pins xlconcat_0/In4]
connect_bd_net [get_bd_pins axi_dma_1/s2mm_introut]     [get_bd_pins xlconcat_0/In5]
connect_bd_net [get_bd_pins axi_dma_2/mm2s_introut]     [get_bd_pins xlconcat_0/In6]
connect_bd_net [get_bd_pins axi_dma_3/s2mm_introut]     [get_bd_pins xlconcat_0/In7]
connect_bd_net [get_bd_pins xlconcat_0/dout]            [get_bd_pins ps8/pl_ps_irq0]

# PS EMIO Sideband -> kria_pl_link_0
connect_bd_net [get_bd_pins ps8/emio_i2c0_scl_i] [get_bd_pins kria_pl_link_0/emio_i2c_scl_i]
connect_bd_net [get_bd_pins ps8/emio_i2c0_scl_o] [get_bd_pins kria_pl_link_0/emio_i2c_scl_o]
connect_bd_net [get_bd_pins ps8/emio_i2c0_scl_t] [get_bd_pins kria_pl_link_0/emio_i2c_scl_t]
connect_bd_net [get_bd_pins ps8/emio_i2c0_sda_i] [get_bd_pins kria_pl_link_0/emio_i2c_sda_i]
connect_bd_net [get_bd_pins ps8/emio_i2c0_sda_o] [get_bd_pins kria_pl_link_0/emio_i2c_sda_o]
connect_bd_net [get_bd_pins ps8/emio_i2c0_sda_t] [get_bd_pins kria_pl_link_0/emio_i2c_sda_t]

connect_bd_net [get_bd_pins ps8/emio_spi0_m_o]    [get_bd_pins kria_pl_link_0/emio_spi_mo]
connect_bd_net [get_bd_pins ps8/emio_spi0_sclk_o] [get_bd_pins kria_pl_link_0/emio_spi_sclk]
connect_bd_net [get_bd_pins ps8/emio_spi0_ss_o_n] [get_bd_pins kria_pl_link_0/emio_spi_ssn]
connect_bd_net [get_bd_pins ps8/emio_spi0_m_i]    [get_bd_pins kria_pl_link_0/emio_spi_mi]

connect_bd_net [get_bd_pins ps8/emio_gpio_o] [get_bd_pins kria_pl_link_0/emio_gpio_o] [get_bd_pins xlslice_gpio2/Din]
connect_bd_net [get_bd_pins xlslice_gpio2/Dout] [get_bd_pins kria_pps_0/sw_pps]
connect_bd_net [get_bd_pins kria_pps_0/pps_out] [get_bd_pins kria_pl_link_0/pps_ref]
create_bd_port -dir I gps_pps
connect_bd_net [get_bd_ports gps_pps] [get_bd_pins kria_pps_0/gps_pps]
connect_bd_net [get_bd_pins ps8/emio_gpio_t] [get_bd_pins kria_pl_link_0/emio_gpio_t]
connect_bd_net [get_bd_pins ps8/emio_gpio_i] [get_bd_pins kria_pl_link_0/emio_gpio_i]

connect_bd_net [get_bd_pins ps8/emio_uart1_txd] [get_bd_pins kria_pl_link_0/emio_uart1_txd]
connect_bd_net [get_bd_pins ps8/emio_uart1_rxd] [get_bd_pins kria_pl_link_0/emio_uart1_rxd]

# External Board Pins (names match fpga/kria/xck26_bd.xdc)
foreach {dir p} {
    I link_rx_clk_p I link_rx_clk_n I link_rx_d0_p I link_rx_d0_n I link_rx_d1_p I link_rx_d1_n
    O link_tx_clk_p O link_tx_clk_n O link_tx_d0_p O link_tx_d0_n
    I fpga_irq IO hk_scl IO hk_sda O fpga_prog_b
    O pmod_cs_n O pmod_mosi I pmod_miso O pmod_sclk
    O pmod_beam_strobe O pmod_pps_sync O pmod_spare1 I pmod_spare2
} {
    create_bd_port -dir $dir $p
    connect_bd_net [get_bd_ports $p] [get_bd_pins kria_pl_link_0/$p]
}

# Address Map matching sw/ias2rf_pl.dtsi & sw/ias2rf_dma_test.c
# Each slave at a fixed address (a blanket assign_bd_address picks its own order and collides)
foreach {seg off} {
    kria_pl_link_0/s_axi/reg0  0x80000000
    axi_dma_0/S_AXI_LITE/Reg   0x80010000
    kria_pps_0/s_axi/reg0      0x80020000
    kria_bev_0/s_axi/reg0      0x80030000
    axi_dma_1/S_AXI_LITE/Reg   0x80040000
    kria_doa_0/s_axi/reg0      0x80050000
    axi_dma_2/S_AXI_LITE/Reg   0x80060000
    kria_sweep_0/s_axi/reg0    0x80070000
    axi_dma_3/S_AXI_LITE/Reg   0x80080000
} {
    assign_bd_address -target_address_space /ps8/Data -offset $off -range 64K [get_bd_addr_segs $seg]
}
# The DMAs' masters reach DDR
assign_bd_address

validate_bd_design
save_bd_design

# Generate HDL Wrapper + XDC
set bd_file [get_files *ias2rf_k26_bd.bd]
make_wrapper -files $bd_file -top -import
add_files -fileset constrs_1 -norecurse [file join $script_dir "xck26_bd.xdc"]
set_property top ias2rf_k26_bd_wrapper [current_fileset]
update_compile_order -fileset sources_1

# Run Synthesis, Implementation, Bitstream & XSA Export
reset_run synth_1
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1

if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {
    error "KRIA_BD_BUILD_FAILED: impl_1 status=[get_property STATUS [get_runs impl_1]]"
}

open_run impl_1
report_timing_summary    -delay_type min_max -report_unconstrained -check_timing_verbose -max_paths 10 -file [file join $rpt_dir "timing_summary.rpt"]
report_utilization       -hierarchical -file [file join $rpt_dir "utilization.rpt"]
report_drc               -file [file join $rpt_dir "drc.rpt"]
report_methodology       -file [file join $rpt_dir "methodology.rpt"]
report_cdc               -details -file [file join $rpt_dir "cdc.rpt"]

set bit_src [glob -nocomplain [file join $proj_dir "kria_bd.runs" "impl_1" "*.bit"]]
if {[llength $bit_src] > 0} {
    file copy -force [lindex $bit_src 0] [file join $out_dir "ias2rf_k26.bit"]
}
write_hw_platform -fixed -include_bit -force -file [file join $out_dir "ias2rf_k26.xsa"]

set wns [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]]
set whs [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -hold]]
puts [format "KRIA_BD_DONE WNS=%s ns WHS=%s ns" $wns $whs]
close_project
