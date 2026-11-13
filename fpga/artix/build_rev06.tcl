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

synth_design -top artix_top -part xc7a50t-ftg256-2 -flatten_hierarchy rebuilt -generic ENABLE_ETH=1'b1
opt_design
place_design
phys_opt_design
route_design

report_timing_summary    -delay_type min_max -report_unconstrained -check_timing_verbose -max_paths 10 -file [file join $rpt_dir "timing_summary.rpt"]
report_pulse_width       -all_violators -file [file join $rpt_dir "pulse_width.rpt"]
report_utilization       -hierarchical -file [file join $rpt_dir "utilization.rpt"]
report_clock_utilization -file [file join $rpt_dir "clock_utilization.rpt"]
report_drc               -file [file join $rpt_dir "drc.rpt"]
report_methodology       -file [file join $rpt_dir "methodology.rpt"]

set wns [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]]
set whs [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -hold]]
puts [format "ARTIX_REV06_BUILD_DONE WNS=%s ns WHS=%s ns" $wns $whs]
