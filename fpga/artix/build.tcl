# Non-project Vivado build script for Artix-7 XC7A50T-FTG256-2 (U1101)
# Usage: vivado -mode batch -source fpga/artix/build.tcl -nojournal -nolog

set script_dir [file dirname [file normalize [info script]]]
set fpga_dir   [file dirname $script_dir]
set rpt_dir    [file join $script_dir "reports"]
file mkdir $rpt_dir

set_part xc7a50t-ftg256-2

# Read RTL (AERIS DDC + link PCS + Artix integration)
read_verilog [glob [file join $fpga_dir "third_party" "aeris" "*.v"]]
read_verilog [glob [file join $fpga_dir "link" "*.v"]]
read_verilog [glob [file join $script_dir "*.v"]]
read_xdc     [file join $script_dir "xc7a50t.xdc"]

synth_design -top artix_top -part xc7a50t-ftg256-2 -flatten_hierarchy rebuilt
opt_design
place_design
phys_opt_design
route_design

report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -max_paths 10 -file [file join $rpt_dir "timing_summary.rpt"]
report_utilization    -hierarchical -file [file join $rpt_dir "utilization.rpt"]
report_drc            -file [file join $rpt_dir "drc.rpt"]

set wns [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]]
puts [format "ARTIX_BUILD_DONE WNS=%s ns" $wns]
