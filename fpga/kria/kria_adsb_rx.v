// SPDX-License-Identifier: Apache-2.0
// 1090 MHz Mode-S Extended Squitter (ADS-B) PPM Preamble Detector & CRC-24 Decoder
//
// Placed in Kria PL (0 DSP48E2) behind IAS1. Processes the complex I/Q stream: envelope (alpha-max plus
// beta-min), averaged over cfg_chip_osr samples per 0.5 us chip, the 8 us four-pulse preamble
// [1,0,1,0,0,0,0,1,0,1,0,0,0,0,0,0], 112 PPM data bits (0.5 us chips, 1 bit/us), and the ICAO Annex 10 24-bit
// CRC, G(x) = 0x1FFF409.
//
// Rev08 G-8: the chip grid is free-running against the received frame, so a grid half a chip off averages every
// chip with its neighbour and the PPM decisions fail. Four decoders run on grids a quarter chip apart
// (kria_adsb_phase); one of them is always within an eighth of a chip of the frame. The first CRC-good frame is
// reported; the other phases' copies of the same frame (finishing within 2 us of it) are dropped. A frame no
// phase decodes is reported once, with msg_crc_ok low, when that window closes.
//   cfg_chip_osr[6:0] samples per chip; [7] adds one sample on every other chip (8'h8C = 12.5 samples at
//   25 MSPS, the Artix stream). preamble_cnt, crc_ok_cnt and crc_err_cnt count frames, not phases.
// Mutation (run.ps1 -Mutate): bad_crc_poly (wrong generator), one_phase (only the first grid).

`timescale 1ns/1ps

module kria_adsb_phase #(
    parameter integer PHASE = 0              // grid offset in quarter chips
) (
    input  wire               clk,
    input  wire               rst,
    input  wire               in_valid,
    input  wire [16:0]        env_inst,
    input  wire [7:0]         cfg_chip_osr,
    input  wire [15:0]        cfg_min_hi_sum,
    output reg                pre_hit_o,
    output reg                done,
    output reg                crc_ok,
    output reg  [111:0]       data,
    output reg  [15:0]        snr_est
);
`ifdef MUTATE_BAD_CRC_POLY
    localparam [23:0] MODE_S_CRC_POLY = 24'hAFE409; // MUTATION: wrong ICAO CRC-24 generator
`else
    localparam [23:0] MODE_S_CRC_POLY = 24'hFFF409;
`endif

    wire [6:0] osr_base = (cfg_chip_osr[6:0] == 7'd0) ? 7'd1 : cfg_chip_osr[6:0];
    // the grid starts PHASE quarter chips after the first sample
    wire [8:0] start_at = ({2'b00, osr_base} * PHASE) >> 2;
    reg  [8:0] start_cnt;
    reg        started;

    // Integrate/average over the chip (+1 on odd chips when cfg_chip_osr[7] for .5 rates)
    reg [6:0]  osr_cnt;
    reg        osr_odd;
    reg [23:0] chip_acc;
    reg        chip_valid;
    reg [15:0] chip_amp;
    wire [6:0] osr_eff = osr_base + {6'd0, (cfg_chip_osr[7] & osr_odd)};

    always @(posedge clk) begin
        if (rst) begin
            osr_cnt    <= 7'd0;
            osr_odd    <= 1'b0;
            chip_acc   <= 24'd0;
            chip_valid <= 1'b0;
            chip_amp   <= 16'd0;
            start_cnt  <= 9'd0;
            started    <= (PHASE == 0);
        end else begin
            chip_valid <= 1'b0;
            if (in_valid && !started) begin
                start_cnt <= start_cnt + 9'd1;
                if (start_cnt + 9'd1 >= start_at) started <= 1'b1;
            end else if (in_valid) begin
                if (osr_cnt >= (osr_eff - 7'd1)) begin
                    osr_cnt    <= 7'd0;
                    osr_odd    <= ~osr_odd;
                    chip_amp   <= (chip_acc + {{7{1'b0}}, env_inst}) / osr_eff;
                    chip_acc   <= 24'd0;
                    chip_valid <= 1'b1;
                end else begin
                    osr_cnt  <= osr_cnt + 7'd1;
                    chip_acc <= chip_acc + {{7{1'b0}}, env_inst};
                end
            end
        end
    end

    // 16-chip sliding preamble history: p[15] newest; with the current chip as slot 15 the preamble's slots
    // 0..14 are p[1..15]: high at slots 0, 2, 7, 9
    reg [15:0] p [0:15];
    reg        rx_active;
    reg        chip_phase;    // 0 = first half-bit chip, 1 = second half-bit chip
    reg [15:0] first_chip;
    reg [6:0]  bit_idx;
    reg [111:0] msg_shift;
    reg [23:0] crc_reg;
    integer    k;

    wire [17:0] hi4 = {2'b0, p[1]} + {2'b0, p[3]} + {2'b0, p[8]} + {2'b0, p[10]};
    wire [19:0] lo12 = {4'b0, p[2]} + {4'b0, p[4]} + {4'b0, p[5]} + {4'b0, p[6]}
                     + {4'b0, p[7]} + {4'b0, p[9]} + {4'b0, p[11]} + {4'b0, p[12]}
                     + {4'b0, p[13]} + {4'b0, p[14]} + {4'b0, p[15]} + {4'b0, chip_amp};

`ifdef MUTATE_STRICT_PREAMBLE
    // the former high-SNR rules: each pulse twice its neighbouring gaps, every other gap under half the pulses'
    // mean, pulses' mean twice the gaps' mean (90 % decode 6 dB short of a timing-aware decoder)
    wire [15:0] half_hi_mean = hi4[17:3]; // 0.5 * mean(4 preamble pulses)
    wire pre_shape_ok = (p[1]  > {p[2][14:0], 1'b0})  &&
                        (p[3]  > {p[2][14:0], 1'b0})  && (p[3] > {p[4][14:0], 1'b0}) &&
                        (p[8]  > {p[7][14:0], 1'b0})  && (p[8] > {p[9][14:0], 1'b0}) &&
                        (p[10] > {p[9][14:0], 1'b0})  && (p[10] > {p[11][14:0], 1'b0}) &&
                        (p[5]  < half_hi_mean) && (p[6]  < half_hi_mean) && (p[7]  < half_hi_mean) &&
                        (p[12] < half_hi_mean) && (p[13] < half_hi_mean) && (p[14] < half_hi_mean) &&
                        (p[15] < half_hi_mean) && (chip_amp < half_hi_mean);
    wire pre_thr_ok   = (hi4 >= {2'b0, cfg_min_hi_sum}) && (({2'b0, hi4} * 20'd3) > (lo12 * 20'd2));
`else
    // Preamble test for chips averaged over 12.5 samples: the weakest of the four pulses above the strongest of
    // the twelve gaps, the pulses' mean 1.5 times the gaps' mean (2 hi4 > lo12), and the summed pulses above
    // software's floor. A chip average of noise varies little, so this holds down to about -87 dBm at the
    // antenna (90 % of frames), against -82.7 dBm for per-chip ratios of 2; on noise alone it never fired in
    // 20 ms of a numerical model (G-8).
    function automatic [15:0] max2(input [15:0] a, input [15:0] b); max2 = (a > b) ? a : b; endfunction
    function automatic [15:0] min2(input [15:0] a, input [15:0] b); min2 = (a < b) ? a : b; endfunction
    wire [15:0] hi_min = min2(min2(p[1], p[3]), min2(p[8], p[10]));
    wire [15:0] lo_max = max2(max2(max2(max2(p[2], p[4]), max2(p[5], p[6])), max2(max2(p[7], p[9]), max2(p[11], p[12]))),
                              max2(max2(p[13], p[14]), max2(p[15], chip_amp)));
    wire pre_shape_ok = (hi_min > lo_max);
    wire pre_thr_ok   = (hi4 >= {2'b0, cfg_min_hi_sum}) && (({1'b0, hi4, 1'b0}) > {1'b0, lo12});
`endif
    wire pre_hit      = chip_valid && !rx_active && pre_shape_ok && pre_thr_ok;

    function automatic [23:0] crc24_step;
        input [23:0] cur;
        input        bit_in;
        reg          fb;
        begin
            fb = cur[23] ^ bit_in;
            crc24_step = {cur[22:0], 1'b0} ^ (fb ? MODE_S_CRC_POLY : 24'd0);
        end
    endfunction

    always @(posedge clk) begin
        if (rst) begin
            for (k = 0; k < 16; k = k + 1) p[k] <= 16'd0;
            rx_active  <= 1'b0;
            chip_phase <= 1'b0;
            first_chip <= 16'd0;
            bit_idx    <= 7'd0;
            msg_shift  <= 112'd0;
            crc_reg    <= 24'd0;
            pre_hit_o  <= 1'b0;
            done       <= 1'b0;
            crc_ok     <= 1'b0;
            data       <= 112'd0;
            snr_est    <= 16'd0;
        end else begin
            done      <= 1'b0;
            pre_hit_o <= 1'b0;
            if (chip_valid) begin
                for (k = 0; k < 15; k = k + 1)
                    p[k] <= p[k + 1];
                p[15] <= chip_amp;

                if (rx_active) begin
                    if (!chip_phase) begin
                        first_chip <= chip_amp;
                        chip_phase <= 1'b1;
                    end else begin : blk_bit
                        reg        dec_b;
                        reg [23:0] crc_nxt;
                        reg [111:0] msg_nxt;
                        dec_b   = (first_chip >= chip_amp); // PPM: 10 = '1', 01 = '0'
                        msg_nxt = {msg_shift[110:0], dec_b};
                        crc_nxt = crc24_step(crc_reg, dec_b);
                        msg_shift  <= msg_nxt;
                        crc_reg    <= crc_nxt;
                        chip_phase <= 1'b0;
                        if (bit_idx == 7'd111) begin
                            rx_active <= 1'b0;
                            done      <= 1'b1;
                            data      <= msg_nxt;
                            crc_ok    <= (crc_nxt == 24'd0);
                        end else begin
                            bit_idx <= bit_idx + 7'd1;
                        end
                    end
                end else if (pre_hit) begin
                    rx_active  <= 1'b1;
                    chip_phase <= 1'b0;
                    bit_idx    <= 7'd0;
                    crc_reg    <= 24'd0;
                    msg_shift  <= 112'd0;
                    snr_est    <= hi4[17:2];
                    pre_hit_o  <= 1'b1;
                end
            end
        end
    end
endmodule


module kria_adsb_rx (
    input  wire               clk,
    input  wire               rst,
    input  wire               in_valid,
    input  wire signed [15:0] in_i,
    input  wire signed [15:0] in_q,

    // Configuration
    input  wire [7:0]         cfg_chip_osr,   // Input samples per 0.5 us chip ([7]: +1 on odd chips)
    input  wire [15:0]        cfg_min_hi_sum, // Minimum summed 4-pulse preamble amplitude

    // Decoded DF17 / Mode-S message outputs
    output reg                msg_valid,
    output reg                msg_crc_ok,
    output reg  [111:0]       msg_data,
    output reg  [15:0]        msg_snr_est,
    output reg  [31:0]        preamble_cnt,
    output reg  [31:0]        crc_ok_cnt,
    output reg  [31:0]        crc_err_cnt
);
`ifdef MUTATE_ONE_PHASE
    localparam integer NPH = 1;
`else
    localparam integer NPH = 4;
`endif

    // Alpha-max plus beta-min envelope magnitude |I + jQ| (0 DSP48)
    wire [15:0] abs_i = in_i[15] ? (~in_i + 16'd1) : in_i;
    wire [15:0] abs_q = in_q[15] ? (~in_q + 16'd1) : in_q;
    wire [15:0] mag_max = (abs_i >= abs_q) ? abs_i : abs_q;
    wire [15:0] mag_min = (abs_i >= abs_q) ? abs_q : abs_i;
    wire [16:0] env_inst = {1'b0, mag_max} + {2'b0, mag_min[15:1]} - {5'b0, mag_max[15:4]};

    wire [NPH-1:0]   ph_pre, ph_done, ph_ok;
    wire [111:0]     ph_data [0:NPH-1];
    wire [15:0]      ph_snr  [0:NPH-1];

    genvar gi;
    generate
        for (gi = 0; gi < NPH; gi = gi + 1) begin : g_ph
            kria_adsb_phase #(.PHASE(gi)) u_ph (
                .clk(clk), .rst(rst), .in_valid(in_valid), .env_inst(env_inst),
                .cfg_chip_osr(cfg_chip_osr), .cfg_min_hi_sum(cfg_min_hi_sum),
                .pre_hit_o(ph_pre[gi]), .done(ph_done[gi]), .crc_ok(ph_ok[gi]),
                .data(ph_data[gi]), .snr_est(ph_snr[gi]));
        end
    endgenerate

    // Same-frame window: the phases see one frame within a chip of each other; 2 us (four chips) of samples
    wire [6:0]  osr_base = (cfg_chip_osr[6:0] == 7'd0) ? 7'd1 : cfg_chip_osr[6:0];
    wire [9:0]  win_samps = {osr_base, 2'b00} + 10'd4;
    reg  [9:0]  pre_win, done_win;      // samples left in the window after a preamble / a frame end
    reg         got_ok;                 // the frame in the current done window was reported good
    reg         pend_fail;
    reg [111:0] fail_data;
    reg [15:0]  fail_snr;
    integer     j;

    always @(posedge clk) begin
        if (rst) begin
            msg_valid    <= 1'b0;
            msg_crc_ok   <= 1'b0;
            msg_data     <= 112'd0;
            msg_snr_est  <= 16'd0;
            preamble_cnt <= 32'd0;
            crc_ok_cnt   <= 32'd0;
            crc_err_cnt  <= 32'd0;
            pre_win      <= 10'd0;
            done_win     <= 10'd0;
            got_ok       <= 1'b0;
            pend_fail    <= 1'b0;
            fail_data    <= 112'd0;
            fail_snr     <= 16'd0;
        end else begin : blk_arb
            reg         any_ok, any_fail;
            reg [111:0] ok_d, fl_d;
            reg [15:0]  ok_s, fl_s;
            msg_valid <= 1'b0;
            any_ok = 1'b0; any_fail = 1'b0;
            ok_d = 112'd0; fl_d = 112'd0; ok_s = 16'd0; fl_s = 16'd0;
            for (j = NPH - 1; j >= 0; j = j - 1) begin
                if (ph_done[j] && ph_ok[j])  begin any_ok = 1'b1;   ok_d = ph_data[j]; ok_s = ph_snr[j]; end
                if (ph_done[j] && !ph_ok[j]) begin any_fail = 1'b1; fl_d = ph_data[j]; fl_s = ph_snr[j]; end
            end

            // preambles: count one per frame
            if (in_valid && pre_win != 10'd0) pre_win <= pre_win - 10'd1;
            if (|ph_pre) begin
                if (pre_win == 10'd0) preamble_cnt <= preamble_cnt + 32'd1;
                pre_win <= win_samps;
            end

            if (in_valid && done_win != 10'd0) done_win <= done_win - 10'd1;
            if (any_ok && !(done_win != 10'd0 && got_ok)) begin
                // first good copy of this frame
                msg_valid   <= 1'b1;
                msg_crc_ok  <= 1'b1;
                msg_data    <= ok_d;
                msg_snr_est <= ok_s;
                crc_ok_cnt  <= crc_ok_cnt + 32'd1;
                got_ok      <= 1'b1;
                pend_fail   <= 1'b0;
                done_win    <= win_samps;
            end else if (any_fail && done_win == 10'd0) begin
                // a frame starts failing: wait for the other phases before calling it bad
                got_ok    <= 1'b0;
                pend_fail <= 1'b1;
                fail_data <= fl_d;
                fail_snr  <= fl_s;
                done_win  <= win_samps;
            end else if (pend_fail && done_win == 10'd0 && !got_ok) begin
                msg_valid   <= 1'b1;
                msg_crc_ok  <= 1'b0;
                msg_data    <= fail_data;
                msg_snr_est <= fail_snr;
                crc_err_cnt <= crc_err_cnt + 32'd1;
                pend_fail   <= 1'b0;
            end
        end
    end
endmodule
