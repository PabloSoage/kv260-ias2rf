// SPDX-License-Identifier: BSD-2-Clause
// RX Eye-Centering & Link Training FSM (Plain Verilog-2001)
// Supports both Kria UltraScale+ IDELAYE3 (0..511, 2 lanes) and Artix-7 IDELAYE2
// (0..31, 1 lane). Sweeps IDELAY taps while monitoring per-lane descrambled
// /I/ and /A/ framing validity (l*_rx_blk_valid / l*_rx_blk_ok), finds the main
// passing eye window [eye_left .. eye_right], loads its midpoint (left+right)/2,
// and supervises Clause 49 block lock and 2-lane AM deskew.

`timescale 1ns/1ps

module link_rx_train_fsm #(
    parameter [8:0]  DEFAULT_CENTER_TAP = 9'd202,
    parameter [8:0]  MAX_TAP            = 9'd511,
    parameter [8:0]  TAP_STEP           = 9'd8,
    parameter [8:0]  MIN_EYE_STEPS      = 9'd16,
    parameter [8:0]  BAD_TAP            = 9'd78,
    parameter [15:0] WAIT_RESET_CYCLES  = 16'd16,
    parameter [15:0] TAP_SETTLE_CYCLES  = 16'd24,
    parameter [15:0] TAP_DWELL_CYCLES   = 16'd1800,
    parameter [15:0] LOCK_TIMEOUT       = 16'd8192,
    parameter        SINGLE_LANE        = 0,
    parameter        BAD_IDELAY         = 0
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        retrain,

    // Software override / diagnostics
    input  wire        cfg_tap_override,
    input  wire [8:0]  cfg_tap_l0,
    input  wire [8:0]  cfg_tap_l1,

    // Link health & framing validity inputs
    input  wire [7:0]  rx_byte_l0,
    input  wire [7:0]  rx_byte_l1,
    input  wire        l0_block_lock,
    input  wire        l1_block_lock,
    input  wire        deskew_lock,
    input  wire        l0_rx_blk_valid,
    input  wire        l0_rx_blk_ok,
    input  wire        l1_rx_blk_valid,
    input  wire        l1_rx_blk_ok,

    // IDELAY VAR_LOAD controls (per lane)
    output reg         en_vtc,
    output reg         load_l0,
    output reg  [8:0]  cntval_l0,
    output reg         load_l1,
    output reg  [8:0]  cntval_l1,

    // Status & measured eye bounds
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

    localparam [8:0] EYE_HYST = (MIN_EYE_STEPS > 9'd4) ? (MIN_EYE_STEPS >> 2) : 9'd2;

    reg [15:0] timer;
    reg [8:0]  scan_tap;
    reg        scan_sub; // 0 = issue LOAD, 1 = settle + observe clean blocks

    reg [3:0]  consec_ok0, consec_ok1;
    reg        lane0_good, lane1_good;

    reg [8:0]  best_start0, best_end0, best_len0, cur_start0, cur_end0, cur_len0;
    reg [8:0]  best_start1, best_end1, best_len1, cur_start1, cur_end1, cur_len1;
    reg        in_win0, in_win1;

    reg        next_l0_good, next_l1_good;
    reg [8:0]  n_start0, n_len0, n_start1, n_len1;
    reg [9:0]  sum_l0, sum_l1;

    // Suppress unused-input lint warnings on raw bytes kept for compatibility
    wire _unused_rx_bytes = &{1'b0, rx_byte_l0, rx_byte_l1};

    always @* begin
        next_l0_good = lane0_good ||
                       ((timer >= TAP_SETTLE_CYCLES) && l0_rx_blk_valid && l0_rx_blk_ok && (consec_ok0 >= 4'd5));
        if (SINGLE_LANE != 0) begin
            next_l1_good = 1'b1;
        end else begin
            next_l1_good = lane1_good ||
                           ((timer >= TAP_SETTLE_CYCLES) && l1_rx_blk_valid && l1_rx_blk_ok && (consec_ok1 >= 4'd5));
        end
    end

    always @(posedge clk) begin
        if (rst || retrain) begin
            train_state  <= ST_RESET;
            en_vtc       <= 1'b0;
            load_l0      <= 1'b0;
            load_l1      <= 1'b0;
            cntval_l0    <= DEFAULT_CENTER_TAP;
            cntval_l1    <= DEFAULT_CENTER_TAP;
            link_up      <= 1'b0;
            timer        <= 16'd0;
            scan_tap     <= 9'd0;
            scan_sub     <= 1'b0;
            consec_ok0   <= 4'd0;
            consec_ok1   <= 4'd0;
            lane0_good   <= 1'b0;
            lane1_good   <= 1'b0;
            best_start0  <= 9'd0;
            best_end0    <= 9'd0;
            best_len0    <= 9'd0;
            cur_start0   <= 9'd0;
            cur_end0     <= 9'd0;
            cur_len0     <= 9'd0;
            in_win0      <= 1'b0;
            best_start1  <= 9'd0;
            best_end1    <= 9'd0;
            best_len1    <= 9'd0;
            cur_start1   <= 9'd0;
            cur_end1     <= 9'd0;
            cur_len1     <= 9'd0;
            in_win1      <= 1'b0;
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
                            best_start0 <= 9'd0;
                            best_end0   <= 9'd0;
                            cur_len0    <= 9'd0;
                            in_win0     <= 1'b0;
                            best_len1   <= 9'd0;
                            best_start1 <= 9'd0;
                            best_end1   <= 9'd0;
                            cur_len1    <= 9'd0;
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
                        cntval_l0  <= scan_tap;
                        cntval_l1  <= scan_tap;
                        load_l0    <= 1'b1;
                        load_l1    <= 1'b1;
                        timer      <= 16'd0;
                        consec_ok0 <= 4'd0;
                        consec_ok1 <= 4'd0;
                        lane0_good <= 1'b0;
                        lane1_good <= (SINGLE_LANE != 0) ? 1'b1 : 1'b0;
                        scan_sub   <= 1'b1;
                    end else begin
                        if (timer >= TAP_SETTLE_CYCLES) begin
                            if (!lane0_good && l0_rx_blk_valid) begin
                                if (l0_rx_blk_ok) begin
                                    if (consec_ok0 >= 4'd5)
                                        lane0_good <= 1'b1;
                                    else
                                        consec_ok0 <= consec_ok0 + 4'd1;
                                end else begin
                                    consec_ok0 <= 4'd0;
                                end
                            end
                            if ((SINGLE_LANE == 0) && !lane1_good && l1_rx_blk_valid) begin
                                if (l1_rx_blk_ok) begin
                                    if (consec_ok1 >= 4'd5)
                                        lane1_good <= 1'b1;
                                    else
                                        consec_ok1 <= consec_ok1 + 4'd1;
                                end else begin
                                    consec_ok1 <= 4'd0;
                                end
                            end
                        end

                        if ((next_l0_good && next_l1_good) || (timer >= TAP_DWELL_CYCLES)) begin
                            // Lane 0 window update
                            if (next_l0_good) begin
                                n_start0    = in_win0 ? cur_start0 : scan_tap;
                                n_len0      = in_win0 ? (cur_len0 + 9'd1) : 9'd1;
                                in_win0    <= 1'b1;
                                cur_start0 <= n_start0;
                                cur_end0   <= scan_tap;
                                cur_len0   <= n_len0;
                                if (((best_len0 < MIN_EYE_STEPS) && (n_len0 > best_len0)) ||
                                    (n_len0 > (best_len0 + EYE_HYST))) begin
                                    best_len0   <= n_len0;
                                    best_start0 <= n_start0;
                                    best_end0   <= scan_tap;
                                end
                            end else begin
                                in_win0  <= 1'b0;
                                cur_len0 <= 9'd0;
                            end

                            // Lane 1 window update
                            if (SINGLE_LANE == 0) begin
                                if (next_l1_good) begin
                                    n_start1    = in_win1 ? cur_start1 : scan_tap;
                                    n_len1      = in_win1 ? (cur_len1 + 9'd1) : 9'd1;
                                    in_win1    <= 1'b1;
                                    cur_start1 <= n_start1;
                                    cur_end1   <= scan_tap;
                                    cur_len1   <= n_len1;
                                    if (((best_len1 < MIN_EYE_STEPS) && (n_len1 > best_len1)) ||
                                        (n_len1 > (best_len1 + EYE_HYST))) begin
                                        best_len1   <= n_len1;
                                        best_start1 <= n_start1;
                                        best_end1   <= scan_tap;
                                    end
                                end else begin
                                    in_win1  <= 1'b0;
                                    cur_len1 <= 9'd0;
                                end
                            end

                            if (({1'b0, scan_tap} + {1'b0, TAP_STEP}) > {1'b0, MAX_TAP}) begin
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
                        // Mutation mode: pin Lane 0 directly onto the sampling transition edge
                        cntval_l0 <= BAD_TAP;
                        cntval_l1 <= DEFAULT_CENTER_TAP;
                    end else if (cfg_tap_override) begin
                        cntval_l0 <= cfg_tap_l0;
                        cntval_l1 <= cfg_tap_l1;
                    end else begin
                        if (best_len0 >= 9'd2) begin
                            eye_left_l0  <= best_start0;
                            eye_right_l0 <= best_end0;
                            sum_l0 = {1'b0, best_start0} + {1'b0, best_end0};
                            cntval_l0    <= sum_l0[9:1];
                        end else begin
                            cntval_l0 <= DEFAULT_CENTER_TAP;
                        end

                        if (SINGLE_LANE == 0) begin
                            if (best_len1 >= 9'd2) begin
                                eye_left_l1  <= best_start1;
                                eye_right_l1 <= best_end1;
                                sum_l1 = {1'b0, best_start1} + {1'b0, best_end1};
                                cntval_l1    <= sum_l1[9:1];
                            end else begin
                                cntval_l1 <= DEFAULT_CENTER_TAP;
                            end
                        end else begin
                            eye_left_l1  <= 9'd0;
                            eye_right_l1 <= 9'd0;
                            cntval_l1    <= 9'd0;
                        end
                    end
                    load_l0     <= 1'b1;
                    load_l1     <= (SINGLE_LANE == 0) ? 1'b1 : 1'b0;
                    timer       <= 16'd0;
                    train_state <= ST_BLOCK_LOCK;
                end

                ST_BLOCK_LOCK: begin
                    en_vtc <= 1'b0;
                    // Wait >=720 cycles (87 blocks > 64-block Clause 49 window + 16 bad syncs)
                    // after LOAD so stale block_lock from scan_tap=MAX_TAP drops cleanly.
                    if ((timer >= 16'd720) && l0_block_lock && ((SINGLE_LANE != 0) || l1_block_lock)) begin
                        timer       <= 16'd0;
                        if (SINGLE_LANE != 0) begin
                            link_up     <= 1'b1;
                            train_state <= ST_LINK_UP;
                        end else begin
                            train_state <= ST_DESKEW;
                        end
                    end else if (timer >= LOCK_TIMEOUT) begin
                        timer <= 16'd0;
                        if ((BAD_IDELAY == 0) && !cfg_tap_override) begin
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

                ST_DESKEW: begin
                    if (!l0_block_lock || !l1_block_lock) begin
                        timer       <= 16'd0;
                        train_state <= ST_BLOCK_LOCK;
                    end else if (deskew_lock) begin
                        link_up     <= 1'b1;
                        train_state <= ST_LINK_UP;
                    end else if (timer >= LOCK_TIMEOUT) begin
                        timer       <= 16'd0;
                        train_state <= ST_BLOCK_LOCK;
                    end else begin
                        timer <= timer + 16'd1;
                    end
                end

                ST_LINK_UP: begin
                    link_up <= 1'b1;
                    if (!l0_block_lock || ((SINGLE_LANE == 0) && !l1_block_lock)) begin
                        link_up     <= 1'b0;
                        timer       <= 16'd0;
                        train_state <= ST_BLOCK_LOCK;
                    end else if ((SINGLE_LANE == 0) && !deskew_lock) begin
                        link_up     <= 1'b0;
                        timer       <= 16'd0;
                        train_state <= ST_DESKEW;
                    end
                end

                default: train_state <= ST_RESET;
            endcase
        end
    end
endmodule
