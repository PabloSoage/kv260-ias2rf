# Vivado non-project build script for 1.25 Gb/s SGMII-over-LVDS proof on xc7a50t-ftg256-2
# Usage: vivado -mode batch -source fpga/eth/test/build.tcl -nojournal -nolog

set script_dir [file dirname [file normalize [info script]]]
set rpt_dir    [file join $script_dir "reports"]
file mkdir $rpt_dir

set_part xc7a50t-ftg256-2

read_verilog [file join $script_dir "sgmii_lvds_test.v"]
read_xdc     [file join $script_dir "sgmii_lvds_test.xdc"]

synth_design -top sgmii_lvds_test -part xc7a50t-ftg256-2 -flatten_hierarchy rebuilt
opt_design
place_design
phys_opt_design
route_design

report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -max_paths 10 -file [file join $rpt_dir "timing_summary.rpt"]
report_pulse_width    -significant_digits 3 -file [file join $rpt_dir "pulse_width.rpt"]
report_utilization    -hierarchical -file [file join $rpt_dir "utilization.rpt"]
report_drc            -file [file join $rpt_dir "drc.rpt"]
report_methodology    -file [file join $rpt_dir "methodology.rpt"]

set wns [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]]
set whs [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -hold]]
puts [format "SGMII_LVDS_BUILD_DONE WNS=%s ns WHS=%s ns" $wns $whs]
