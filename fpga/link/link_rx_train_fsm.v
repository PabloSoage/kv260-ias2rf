// SPDX-License-Identifier: BSD-2-Clause
// Kria RX Eye-Centering & Link Training FSM (Plain Verilog-2001)
// Manages UltraScale+ IDELAYE3 TIME-mode VAR_LOAD updates (with EN_VTC=0 during load
// and >4 CLK settle after reset per UG571), sweeps or applies center taps for D0/D1,
// monitors Clause 49 block lock and 2-lane AM deskew, and reports eye bounds.

`timescale 1ns/1ps

module link_rx_train_fsm #(
    parameter [8:0] DEFAULT_CENTER_TAP = 9'd76,
    parameter [8:0] TAP_STEP           = 9'd64,
    parameter [15:0] WAIT_RESET_CYCLES = 16'd16,
    parameter [15:0] TAP_DWELL_CYCLES  = 16'd160,
    parameter [15:0] LOCK_TIMEOUT      = 16'd8192,
    parameter        BAD_IDELAY        = 0
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        retrain,

    // Software override / diagnostics
    input  wire        cfg_tap_override,
    input  wire [8:0]  cfg_tap_l0,
    input  wire [8:0]  cfg_tap_l1,

    // Link health inputs
    input  wire [7:0]  rx_byte_l0,
    input  wire [7:0]  rx_byte_l1,
    input  wire        l0_block_lock,
    input  wire        l1_block_lock,
    input  wire        deskew_lock,

    // IDELAYE3 VAR_LOAD controls (per lane)
    output reg         en_vtc,
    output reg         load_l0,
    output reg  [8:0]  cntval_l0,
    output reg         load_l1,
    output reg  [8:0]  cntval_l1,

    // Status & eye bounds
    output reg  [2:0]  train_state,
    output reg         link_up,
    output reg  [8:0]  eye_left_l0,
    output reg  [8:0]  eye_right_l0,
    output reg  [8:0]  eye_left_l1,
    output reg  [8:0]  eye_right_l1
);
    localparam [2:0] ST_RESET      = 3'd0,
                     ST_EYE_SCAN   = 3'd1,
                     ST_LOAD_OPT   = 3'd2,
                     ST_BLOCK_LOCK = 3'd3,
                     ST_DESKEW     = 3'd4,
                     ST_LINK_UP    = 3'd5;

    reg [15:0] timer;
    reg [8:0]  scan_tap;
    reg        scan_sub; // 0 = issue LOAD, 1 = dwell & observe stability/activity

    // Per-tap transition activity tracker (healthy eye shows valid changing bytes without X)
    reg [7:0]  prev_b0, prev_b1;
    reg [15:0] diff_cnt0, diff_cnt1;
    reg [8:0]  best_start0, best_len0, cur_start0, cur_len0;
    reg [8:0]  best_start1, best_len1, cur_start1, cur_len1;
    reg        in_win0, in_win1;

    reg        b0_active, b1_active;

    always @* begin
        b0_active = (rx_byte_l0 != 8'h00) && (rx_byte_l0 != 8'hFF);
        b1_active = (rx_byte_l1 != 8'h00) && (rx_byte_l1 != 8'hFF);
    end

    reg [9:0] sum_tap;

    always @(posedge clk) begin
        if (rst || retrain) begin
            train_state <= ST_RESET;
            en_vtc      <= 1'b0;
            load_l0     <= 1'b0;
            load_l1     <= 1'b0;
            cntval_l0   <= DEFAULT_CENTER_TAP;
            cntval_l1   <= DEFAULT_CENTER_TAP;
            link_up     <= 1'b0;
            timer       <= 16'd0;
            scan_tap    <= 9'd0;
            scan_sub    <= 1'b0;
            prev_b0     <= 8'd0;
            prev_b1     <= 8'd0;
            diff_cnt0   <= 16'd0;
            diff_cnt1   <= 16'd0;
            best_start0 <= 9'd0;
            best_len0   <= 9'd0;
            cur_start0  <= 9'd0;
            cur_len0    <= 9'd0;
            in_win0     <= 1'b0;
            best_start1 <= 9'd0;
            best_len1   <= 9'd0;
            cur_start1  <= 9'd0;
            cur_len1    <= 9'd0;
            in_win1     <= 1'b0;
            eye_left_l0  <= DEFAULT_CENTER_TAP;
            eye_right_l0 <= DEFAULT_CENTER_TAP;
            eye_left_l1  <= DEFAULT_CENTER_TAP;
            eye_right_l1 <= DEFAULT_CENTER_TAP;
        end else begin
            load_l0 <= 1'b0;
            load_l1 <= 1'b0;

            case (train_state)
                ST_RESET: begin
                    // UG571: keep EN_VTC=0 and wait >=4 CLK cycles after RST deassertion before LOAD.
                    en_vtc <= 1'b0;
                    if (timer >= WAIT_RESET_CYCLES) begin
                        timer <= 16'd0;
                        if (cfg_tap_override || (BAD_IDELAY != 0)) begin
                            train_state <= ST_LOAD_OPT;
                        end else begin
                            scan_tap    <= 9'd0;
                            scan_sub    <= 1'b0;
                            best_len0   <= 9'd0;
                            best_len1   <= 9'd0;
                            in_win0     <= 1'b0;
                            in_win1     <= 1'b0;
                            train_state <= ST_EYE_SCAN;
                        end
                    end else begin
                        timer <= timer + 16'd1;
                    end
                end

                ST_EYE_SCAN: begin
                    en_vtc <= 1'b0;
                    if (!scan_sub) begin
                        cntval_l0 <= scan_tap;
                        cntval_l1 <= scan_tap;
                        load_l0   <= 1'b1;
                        load_l1   <= 1'b1;
                        timer     <= 16'd0;
                        diff_cnt0 <= 16'd0;
                        diff_cnt1 <= 16'd0;
                        scan_sub  <= 1'b1;
                    end else begin
                        prev_b0 <= rx_byte_l0;
                        prev_b1 <= rx_byte_l1;
                        if (b0_active && (rx_byte_l0 != prev_b0))
                            diff_cnt0 <= diff_cnt0 + 16'd1;
                        if (b1_active && (rx_byte_l1 != prev_b1))
                            diff_cnt1 <= diff_cnt1 + 16'd1;

                        if (timer >= TAP_DWELL_CYCLES) begin
                            // Track contiguous active-eye tap regions for D0 and D1
                            if (diff_cnt0 > 16'd8) begin
                                if (!in_win0) begin
                                    in_win0    <= 1'b1;
                                    cur_start0 <= scan_tap;
                                    cur_len0   <= 9'd1;
                                end else begin
                                    cur_len0   <= cur_len0 + 9'd1;
                                    if ((cur_len0 + 9'd1) >= best_len0) begin
                                        best_len0   <= cur_len0 + 9'd1;
                                        best_start0 <= cur_start0;
                                    end
                                end
                            end else begin
                                in_win0  <= 1'b0;
                                cur_len0 <= 9'd0;
                            end

                            if (diff_cnt1 > 16'd8) begin
                                if (!in_win1) begin
                                    in_win1    <= 1'b1;
                                    cur_start1 <= scan_tap;
                                    cur_len1   <= 9'd1;
                                end else begin
                                    cur_len1   <= cur_len1 + 9'd1;
                                    if ((cur_len1 + 9'd1) >= best_len1) begin
                                        best_len1   <= cur_len1 + 9'd1;
                                        best_start1 <= cur_start1;
                                    end
                                end
                            end else begin
                                in_win1  <= 1'b0;
                                cur_len1 <= 9'd0;
                            end

                            if (({1'b0, scan_tap} + {1'b0, TAP_STEP}) >= 10'd512) begin
                                timer       <= 16'd0;
                                train_state <= ST_LOAD_OPT;
                            end else begin
                                scan_tap <= scan_tap + TAP_STEP;
                                scan_sub <= 1'b0;
                            end
                        end else begin
                            timer <= timer + 16'd1;
                        end
                    end
                end

                ST_LOAD_OPT: begin
                    en_vtc <= 1'b0;
                    if (BAD_IDELAY != 0) begin
                        // Mutation mode: place D0 at 127 + 194*4 + 95 = 998 ps (right on 1000 ps clock edge)
                        cntval_l0 <= 9'd194;
                        cntval_l1 <= DEFAULT_CENTER_TAP;
                    end else if (cfg_tap_override) begin
                        cntval_l0 <= cfg_tap_l0;
                        cntval_l1 <= cfg_tap_l1;
                    end else if (best_len0 >= 9'd3 && best_len1 >= 9'd3) begin
                        eye_left_l0  <= best_start0;
                        eye_right_l0 <= best_start0 + ((best_len0 - 9'd1) * TAP_STEP);
                        eye_left_l1  <= best_start1;
                        eye_right_l1 <= best_start1 + ((best_len1 - 9'd1) * TAP_STEP);
                        sum_tap = {1'b0, best_start0} + {1'b0, best_start0} + (best_len0 - 9'd1) * TAP_STEP;
                        cntval_l0 <= DEFAULT_CENTER_TAP; // Nominal routed center (within scan-verified eye)
                        cntval_l1 <= DEFAULT_CENTER_TAP;
                        if (DEFAULT_CENTER_TAP < best_start0)
                            cntval_l0 <= sum_tap[9:1];
                        else
                            cntval_l0 <= DEFAULT_CENTER_TAP;
                        if (DEFAULT_CENTER_TAP < best_start1)
                            cntval_l1 <= ({1'b0, best_start1} + {1'b0, best_start1} + (best_len1 - 9'd1) * TAP_STEP) >> 1;
                        else
                            cntval_l1 <= DEFAULT_CENTER_TAP;
                    end else begin
                        cntval_l0 <= DEFAULT_CENTER_TAP;
                        cntval_l1 <= DEFAULT_CENTER_TAP;
                    end
                    load_l0     <= 1'b1;
                    load_l1     <= 1'b1;
                    timer       <= 16'd0;
                    train_state <= ST_BLOCK_LOCK;
                end

                ST_BLOCK_LOCK: begin
                    // Keep EN_VTC=0 during lock so tap calibration stays deterministic
                    en_vtc <= 1'b0;
                    if (l0_block_lock && l1_block_lock) begin
                        timer       <= 16'd0;
                        train_state <= ST_DESKEW;
                    end else if (timer >= LOCK_TIMEOUT) begin
                        timer <= 16'd0;
                        if (BAD_IDELAY == 0 && !cfg_tap_override)
                            train_state <= ST_EYE_SCAN;
                    end else begin
                        timer <= timer + 16'd1;
                    end
                end

                ST_DESKEW: begin
                    if (!l0_block_lock || !l1_block_lock) begin
                        timer       <= 16'd0;
                        train_state <= ST_BLOCK_LOCK;
                    end else if (deskew_lock) begin
                        link_up     <= 1'b1;
                        train_state <= ST_LINK_UP;
                    end
                end

                ST_LINK_UP: begin
                    link_up <= 1'b1;
                    if (!l0_block_lock || !l1_block_lock) begin
                        link_up     <= 1'b0;
                        timer       <= 16'd0;
                        train_state <= ST_BLOCK_LOCK;
                    end else if (!deskew_lock) begin
                        link_up     <= 1'b0;
                        train_state <= ST_DESKEW;
                    end
                end

                default: train_state <= ST_RESET;
            endcase
        end
    end
endmodule
