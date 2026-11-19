# Non-project Vivado build script for Rev06 Artix-7 XC7A50T-FTG256-2 (IAS1 + SGMII ETH)
# Usage: vivado -mode batch -source fpga/artix/build_rev06.tcl -nojournal -nolog

set script_dir [file dirname [file normalize [info script]]]
set fpga_dir   [file dirname $script_dir]
set rpt_dir    [file join $script_dir "reports_rev06"]
file mkdir $rpt_dir

set_part xc7a50t-ftg256-2

read_verilog [glob [file join $fpga_dir "third_party" "aeris" "*.v"]]
read_verilog [glob [file join $fpga_dir "link" "*.v"]]
read_verilog [glob [file join $script_dir "*.v"]]
read_xdc     [file join $script_dir "xc7a50t.xdc"]

set now_sec    [clock seconds]
set build_date [clock format $now_sec -format "%Y%m%d"]
set build_time [clock format $now_sec -format "00%H%M%S"]
set git_hash   "DEADC0DE"
catch { set git_hash [string toupper [string trim [exec git -C [file dirname $fpga_dir] rev-parse --short=8 HEAD]]] }
if {![regexp {^[0-9A-F]{8}$} $git_hash]} { set git_hash "DEADC0DE" }

synth_design -top artix_top -part xc7a50t-ftg256-2 -flatten_hierarchy rebuilt \
    -generic ENABLE_ETH=1'b1 \
    -generic BUILD_DATE=32'h$build_date \
    -generic BUILD_TIME=32'h$build_time \
    -generic GIT_HASH=32'h$git_hash
opt_design
place_design -directive AltSpreadLogic_high
# Post-place physical optimisation without -dsp_register_opt: that pass pulled the AERIS mixer's AREG out of the
# DSP48 into a slice, which left a fabric -> DSP multiplier path short of the 2.5 ns cycle (WNS -0.146 ns).
phys_opt_design -fanout_opt -placement_opt -rewire -critical_cell_opt -critical_pin_opt -retime \
    -shift_register_opt -bram_register_opt -hold_fix
route_design
# post-route: the 400 MHz AERIS CIC comb sits within +/-0.05 ns of the cycle and moves with placement
phys_opt_design -directive AggressiveExplore
# 17 Nov: with the beam scan mode in adar_ctrl the placement left the SGMII PHY's 312.5 MHz transmit path at
# -0.021 ns after this pass, and a later build closed at exactly 0.000 ns. While setup slack is below a 50 ps
# margin, more post-route passes with other directives (each keeps what it gains; none runs on a design that
# already has that margin).
foreach dir {AlternateFlowWithRetiming AggressiveFanoutOpt Explore} {
    if {[get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]] >= 0.050} { break }
    puts "post-route phys_opt_design -directive $dir"
    phys_opt_design -directive $dir
}

report_timing_summary    -delay_type min_max -report_unconstrained -check_timing_verbose -max_paths 10 -file [file join $rpt_dir "timing_summary.rpt"]
report_pulse_width       -all_violators -file [file join $rpt_dir "pulse_width.rpt"]
report_utilization       -hierarchical -file [file join $rpt_dir "utilization.rpt"]
report_clock_utilization -file [file join $rpt_dir "clock_utilization.rpt"]
report_drc               -file [file join $rpt_dir "drc.rpt"]
report_methodology       -file [file join $rpt_dir "methodology.rpt"]
report_cdc               -details -file [file join $rpt_dir "cdc.rpt"]

set_operating_conditions -grade industrial -process typical -ambient_temp 25.0 -board_layers 8to11 -airflow 0
report_power -file [file join $rpt_dir "power_25c_typ.rpt"]
set_operating_conditions -grade industrial -process maximum -ambient_temp 70.0 -board_layers 8to11 -airflow 0
report_power -file [file join $rpt_dir "power_70c_max.rpt"]

set wns [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]]
set whs [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -hold]]
# the routed design, for export_vivado_views.tcl (floorplan figures); git-ignored
file mkdir [file join $fpga_dir "artix" ".build_rev06"]
write_checkpoint -force [file join $fpga_dir "artix" ".build_rev06" "artix_top_routed.dcp"]
puts [format "ARTIX_REV06_BUILD_DONE WNS=%s ns WHS=%s ns" $wns $whs]
