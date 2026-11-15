# Export real Vivado post-route silicon die geometry, placed cells, clock regions,
# DSP/BRAM/PS/IO columns, and module utilization for Artix-7 and Kria K26.
# Usage: vivado -mode batch -nojournal -nolog -source fpga/export_vivado_views.tcl

set script_dir [file dirname [file normalize [info script]]]
set repo_root  [file dirname $script_dir]
set out_dir    [file join $repo_root "_work" "fpga_views"]
file mkdir $out_dir
set run_mode   [expr {$argc > 0 ? [lindex $argv 0] : "all"}]

proc json_esc {s} {
    return [string map [list "\\" "\\\\" "\"" "\\\"" "\n" "\\n" "\r" "" "\t" "\\t"] $s]
}

proc export_die_json {json_path top_name part_name} {
    set fp [open $json_path "w"]
    fconfigure $fp -encoding utf-8

    set wns [get_property -quiet SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]]
    set whs [get_property -quiet SLACK [get_timing_paths -max_paths 1 -nworst 1 -hold]]
    if {$wns eq ""} { set wns 0.0 }
    if {$whs eq ""} { set whs 0.0 }

    puts $fp "{"
    puts $fp "  \"top\": \"[json_esc $top_name]\","
    puts $fp "  \"part\": \"[json_esc $part_name]\","
    puts $fp "  \"wns_ns\": $wns,"
    puts $fp "  \"whs_ns\": $whs,"

    # 1. Die tile extents
    set all_tiles [get_tiles]
    set all_x [lsort -integer [get_property GRID_POINT_X $all_tiles]]
    set all_y [lsort -integer [get_property GRID_POINT_Y $all_tiles]]
    puts $fp "  \"die_bounds\": {\"min_x\": [lindex $all_x 0], \"max_x\": [lindex $all_x end], \"min_y\": [lindex $all_y 0], \"max_y\": [lindex $all_y end]},"

    # 2. Clock regions
    puts $fp "  \"clock_regions\": \["
    set crs [get_clock_regions]
    set n_cr [llength $crs]
    set idx 0
    foreach cr $crs {
        incr idx
        set cr_name [get_property NAME $cr]
        set row_i   [get_property ROW_INDEX $cr]
        set col_i   [get_property COLUMN_INDEX $cr]
        set ctiles  [get_tiles -quiet -of_objects $cr]
        set cxs     [lsort -integer [get_property GRID_POINT_X $ctiles]]
        set cys     [lsort -integer [get_property GRID_POINT_Y $ctiles]]
        set comma [expr {$idx < $n_cr ? "," : ""}]
        puts $fp "    {\"name\": \"$cr_name\", \"row\": $row_i, \"col\": $col_i, \"x0\": [lindex $cxs 0], \"x1\": [lindex $cxs end], \"y0\": [lindex $cys 0], \"y1\": [lindex $cys end]}$comma"
    }
    puts $fp "  \],"

    # 3. Architectural columns (DSP, BRAM36, MMCM/PLL, PS8, IO) across entire die
    puts $fp "  \"arch_sites\": \["
    set bg_sites [get_sites -quiet -filter {SITE_TYPE =~ DSP48* || SITE_TYPE =~ RAMB36* || SITE_TYPE =~ MMCME* || SITE_TYPE =~ PLLE* || SITE_TYPE =~ PSS* || SITE_TYPE =~ PS8* || SITE_TYPE =~ XADC* || SITE_TYPE =~ SYSMON* || SITE_TYPE =~ IOB33* || SITE_TYPE =~ HPIO* || SITE_TYPE =~ HDIO*}]
    set bg_rows [list]
    foreach s $bg_sites {
        set t [get_tiles -quiet -of_objects $s]
        if {$t eq ""} { continue }
        set sname [get_property NAME $s]
        set stype [get_property SITE_TYPE $s]
        set gx [get_property GRID_POINT_X $t]
        set gy [get_property GRID_POINT_Y $t]
        set is_used [get_property IS_USED $s]
        lappend bg_rows "    {\"s\": \"[json_esc $sname]\", \"t\": \"[json_esc $stype]\", \"x\": $gx, \"y\": $gy, \"u\": $is_used}"
    }
    puts $fp [join $bg_rows ",\n"]
    puts $fp "  \],"

    # 4. Cache tile (x,y) per unique placed site & dump placed leaf primitives
    set cells [get_cells -hierarchical -filter {IS_PRIMITIVE && LOC != ""}]
    set c_names [get_property NAME $cells]
    set c_refs  [get_property REF_NAME $cells]
    set c_locs  [get_property LOC $cells]

    array set site_gx {}
    array set site_gy {}
    set uniq_locs [lsort -unique $c_locs]
    foreach loc $uniq_locs {
        set s [get_sites -quiet $loc]
        if {$s ne ""} {
            set t [get_tiles -quiet -of_objects $s]
            if {$t ne ""} {
                set site_gx($loc) [get_property GRID_POINT_X $t]
                set site_gy($loc) [get_property GRID_POINT_Y $t]
            }
        }
    }

    puts $fp "  \"placed_cells\": \["
    set first_cell 1
    array set mod_stats {}
    foreach nm $c_names rf $c_refs lc $c_locs {
        if {![info exists site_gx($lc)]} { continue }
        # Top-level hierarchy bucket (2 segments when useful, else 1)
        set parts [split $nm "/"]
        set h0 [lindex $parts 0]
        if {[llength $parts] > 2 && ($h0 eq "g_eth" || $h0 eq "u_adc" || $h0 eq "u_adcs")} {
            set grp "$h0/[lindex $parts 1]"
        } elseif {[llength $parts] > 1} {
            set grp $h0
        } else {
            set grp "_top_io"
        }

        # Categorize primitive kind
        set kind "OTHER"
        if {[string match "LUT*" $rf]} {
            set kind "LUT"
        } elseif {[string match "FD*" $rf] || [string match "LD*" $rf]} {
            set kind "FF"
        } elseif {[string match "RAMB*" $rf] || [string match "FIFO*" $rf]} {
            set kind "BRAM"
        } elseif {[string match "DSP*" $rf]} {
            set kind "DSP"
        } elseif {[string match "MMCM*" $rf] || [string match "PLL*" $rf]} {
            set kind "CLK"
        } elseif {[string match "ISERDES*" $rf] || [string match "OSERDES*" $rf] || [string match "IDELAY*" $rf] || [string match "ODDR*" $rf] || [string match "IDDR*" $rf]} {
            set kind "SERDES"
        } elseif {[string match "*BUF*" $rf] || [string match "IBUF*" $rf] || [string match "OBUF*" $rf]} {
            set kind "IO"
        } elseif {[string match "CARRY*" $rf] || [string match "MUX*" $rf] || [string match "SRL*" $rf]} {
            set kind "LOGIC"
        } elseif {[string match "XADC*" $rf] || [string match "SYSMON*" $rf]} {
            set kind "SYS"
        }

        set skey "${grp}|${kind}"
        if {[info exists mod_stats($skey)]} {
            incr mod_stats($skey)
        } else {
            set mod_stats($skey) 1
        }

        set prefix [expr {$first_cell ? "    " : ",\n    "}]
        set first_cell 0
        puts -nonewline $fp "${prefix}\[\"[json_esc $grp]\",\"[json_esc $kind]\",\"[json_esc $rf]\",\"[json_esc $lc]\",$site_gx($lc),$site_gy($lc)\]"
    }
    puts $fp "\n  \],"

    # 5. Summary counts by module & kind
    puts $fp "  \"module_counts\": {"
    set mkeys [lsort [array names mod_stats]]
    set mlen [llength $mkeys]
    set midx 0
    foreach mk $mkeys {
        incr midx
        set comma [expr {$midx < $mlen ? "," : ""}]
        puts $fp "    \"[json_esc $mk]\": $mod_stats($mk)$comma"
    }
    puts $fp "  },"

    # 6. Placed top-level ports
    puts $fp "  \"ports\": \["
    set prows [list]
    foreach p [get_ports] {
        set pn [get_property NAME $p]
        set ppin [get_property -quiet PACKAGE_PIN $p]
        if {$ppin eq ""} { continue }
        set dir [get_property DIRECTION $p]
        set iostd [get_property -quiet IOSTANDARD $p]
        set psite [get_sites -quiet -of_objects [get_package_pins -quiet $ppin]]
        if {$psite eq ""} {
            set psite [get_sites -quiet -of_objects $p]
        }
        set gx -1
        set gy -1
        if {$psite ne ""} {
            set pt [get_tiles -quiet -of_objects $psite]
            if {$pt ne ""} {
                set gx [get_property GRID_POINT_X $pt]
                set gy [get_property GRID_POINT_Y $pt]
            }
        }
        lappend prows "    {\"name\": \"[json_esc $pn]\", \"pin\": \"$ppin\", \"dir\": \"$dir\", \"iostd\": \"$iostd\", \"x\": $gx, \"y\": $gy}"
    }
    puts $fp [join $prows ",\n"]
    puts $fp "  \]"

    puts $fp "}"
    close $fp
    puts "EXPORTED_JSON: $json_path"
}

# ==============================================================================
# 1. Artix-7 XC7A50T-FTG256-2 (artix_top, ENABLE_ETH=1)
# ==============================================================================
if {$run_mode eq "all" || $run_mode eq "artix"} {
    set artix_dir [file join $script_dir "artix"]
    set_part xc7a50t-ftg256-2
    read_verilog [glob [file join $script_dir "third_party" "aeris" "*.v"]]
    read_verilog [glob [file join $script_dir "link" "*.v"]]
    read_verilog [glob [file join $artix_dir "*.v"]]
    read_xdc     [file join $artix_dir "xc7a50t.xdc"]

    synth_design -top artix_top -part xc7a50t-ftg256-2 -flatten_hierarchy rebuilt -generic ENABLE_ETH=1'b1
    opt_design
    place_design
    phys_opt_design
    route_design
    phys_opt_design                                ;# as build_rev06.tcl: the same netlist and WNS as the reports

    export_die_json [file join $out_dir "artix7_die_data.json"] "artix_top" "xc7a50t-ftg256-2"
    close_design
}

# ==============================================================================
# 2. Kria K26 XCK26-SFVC784-2LV-c (kria_top)
# ==============================================================================
if {$run_mode eq "all" || $run_mode eq "kria"} {
    set kria_dir [file join $script_dir "kria"]
    read_verilog [list \
        [file join $script_dir "link" "link_crc32.v"] \
        [file join $script_dir "link" "link_scrambler.v"] \
        [file join $script_dir "link" "link_gearbox.v"] \
        [file join $script_dir "link" "link_framer.v"] \
        [file join $script_dir "link" "link_lanes.v"] \
        [file join $script_dir "link" "link_rx_train_fsm.v"] \
        [file join $script_dir "link" "link_top.v"] \
        [file join $kria_dir "link_axis.v"] \
        [file join $kria_dir "top.v"] \
    ]
    read_xdc [file join $kria_dir "xck26.xdc"]

    synth_design -top kria_top -part xck26-sfvc784-2LV-c -flatten_hierarchy rebuilt
    opt_design
    place_design
    phys_opt_design
    route_design

    export_die_json [file join $out_dir "kria_k26_die_data.json"] "kria_top" "xck26-sfvc784-2LV-c"
    close_design
}
puts "VIVADO_VIEWS_EXPORT_COMPLETE"
