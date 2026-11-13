# Non-project Vivado build script for Kria K26 (xck26-sfvc784-2LV-c)
set script_dir [file dirname [file normalize [info script]]]
set repo_root  [file normalize [file join $script_dir .. ..]]
set rpt_dir    [file join $script_dir reports]
file mkdir $rpt_dir

read_verilog [list \
    [file join $repo_root fpga/link/link_crc32.v] \
    [file join $repo_root fpga/link/link_scrambler.v] \
    [file join $repo_root fpga/link/link_gearbox.v] \
    [file join $repo_root fpga/link/link_framer.v] \
    [file join $repo_root fpga/link/link_lanes.v] \
    [file join $repo_root fpga/link/link_rx_train_fsm.v] \
    [file join $repo_root fpga/link/link_top.v] \
    [file join $repo_root fpga/kria/link_axis.v] \
    [file join $repo_root fpga/kria/top.v] \
]
read_xdc [file join $script_dir xck26.xdc]

synth_design -top kria_top -part xck26-sfvc784-2LV-c
opt_design
place_design
phys_opt_design
route_design

report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -max_paths 10 -file [file join $rpt_dir timing_summary.rpt]
report_utilization -file [file join $rpt_dir utilization.rpt]
report_drc -file [file join $rpt_dir drc.rpt]

set wns [get_property SLACK [get_timing_paths -max_paths 1 -setup]]
set whs [get_property SLACK [get_timing_paths -max_paths 1 -hold]]
puts "BUILD_SUMMARY: WNS=$wns WHS=$whs"
if {$wns < 0.0 || $whs < 0.0} {
    error "Timing failed: WNS=$wns WHS=$whs"
}
