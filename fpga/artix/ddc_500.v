// SPDX-License-Identifier: Apache-2.0
// Rev08 G-7: D2, the 500 MSPS DDC for the AD9484 (master clock at 500 MHz).
//
// adc_capture hands over four samples per link_clk cycle (125 MHz = 500 MSPS / 4, frequency-locked to the
// AD9484's clock), so the whole path runs on link_clk with four lanes and no DSP48 (the Artix has 9 free):
//   NCO     32-bit phase, lane i at acc + i * FTW, acc += 4 * FTW; 12-bit phase into a quarter-wave table of
//           1024 x 12 bits (one dual-port RAMB18 per lane: the sine's and the cosine's index); worst phase
//           truncation spur -72 dBc
//   mixer   the code as an odd 9-bit number (2 * (code - 128) + 1, so mid-scale has no DC) times e^-j(theta),
//           rounded to 16 bits; CONJ flips the spectrum (the AERIS DDC's output is the conjugate)
//   CIC     5 stages, decimation 5, 500 -> 100 MSPS, 28-bit integrators in four-lane prefix form (one adder in
//           each accumulator loop); what folds onto +/-10 MHz (100 MHz multiples +/- 10 MHz) at least 94 dB
//           down, onto +/-12.5 MHz 83 dB; droop 0.69 dB at 10 MHz; gain 3125 / 4096
//   ddc_hb4 the radar DDC's two half-bands, 100 -> 25 MSPS (flat to 0.07 dB up to 10 MHz, -49.6 dB from 15 to
//           25 MHz); its input is valid 4 cycles in 5
//   packets 512-byte packets of 25 MSPS {Q, I} pairs, as ddc_wrapper's, on stream 0x01, so the Kria sees the
//           same stream in both clock modes (no CPI mark: the X-band front end is off at 500 MHz); when en
//           falls, a packet under way is finished first (pkt_busy), so the uplink arbiter never waits on it
// A real tone of amplitude A codes at FTW + d gives |bb| = 97.63 * A * CIC droop(d) (A = 127.5: -8.4 dBFS).
// The lanes' largest-magnitude code per word goes to fe_agc's band peak (adc_peak) in place of the 400 MSPS one.
// Mutations (run.ps1 -Mutate): d2_nco_lane0 (every lane on the word's phase), d2_lane_swap (lanes 1 and 2
// swapped), both checked by tb_ddc_500.

`timescale 1ns/1ps
`default_nettype none

(* use_dsp = "no" *)
module ddc_500 #(
    parameter integer PKT_WORDS = 64,         // 64-bit words per packet (2 I/Q samples each)
    parameter integer FIFO_AW   = 7,          // log2 of the packet FIFO depth in 64-bit words (> PKT_WORDS)
    parameter [7:0]   STREAM_ID = 8'h01
) (
    input  wire               clk,            // link_clk
    input  wire               rst,
    input  wire               en,
    input  wire [31:0]        ftw,            // f_NCO = FTW * 500 MHz / 2^32 (quasi-static)
    input  wire               conj,
    input  wire [35:0]        word,           // 4 x {or, code[7:0]} (offset binary), [8:0] the earliest
    input  wire               word_valid,

    output reg  [7:0]         pk_code = 8'd0, // largest-magnitude code of the word
    output reg                pk_or   = 1'b0,
    output reg                pk_valid = 1'b0,

    output wire               bb_valid,
    output wire signed [15:0] bb_i,
    output wire signed [15:0] bb_q,

    input  wire [63:0]        timestamp_cnt,
    output wire               pkt_valid,
    input  wire               pkt_ready,
    output wire               pkt_sop,
    output wire               pkt_eop,
    output wire [7:0]         pkt_stream_id,
    output wire [15:0]        pkt_len,
    output reg  [31:0]        pkt_seq,
    output reg  [63:0]        pkt_timestamp,
    output wire [63:0]        pkt_data,
    output reg  [23:0]        dropped_cnt,
    output wire               pkt_busy        // a packet is under way (it is finished even after en falls)
);
    localparam integer W = 28;                // CIC register width: 16 + 5 * log2(5) rounded up
    integer i, s;
    wire run = en && !rst;

    // ---------------------------------------------------------------------------------------------------------
    // Lanes in
    // ---------------------------------------------------------------------------------------------------------
    wire [8:0] lane_in [0:3];
`ifdef MUTATE_D2_LANE_SWAP
    assign lane_in[0] = word[8:0];   assign lane_in[1] = word[26:18];
    assign lane_in[2] = word[17:9];  assign lane_in[3] = word[35:27];
`else
    assign lane_in[0] = word[8:0];   assign lane_in[1] = word[17:9];
    assign lane_in[2] = word[26:18]; assign lane_in[3] = word[35:27];
`endif

    // band peak: magnitude as adc_peak forms it (offset binary -> MSB flip, one's complement for negatives)
    function automatic [6:0] mag7(input [7:0] code);
        reg [7:0] t;
        begin t = code ^ 8'h80; mag7 = t[7] ? ~t[6:0] : t[6:0]; end
    endfunction
    reg [7:0] pk_a = 8'd0, pk_b = 8'd0;
    reg       pk_ora = 1'b0, pk_v1 = 1'b0;
    always @(posedge clk) begin
        pk_a   <= (mag7(lane_in[0][7:0]) >= mag7(lane_in[1][7:0])) ? lane_in[0][7:0] : lane_in[1][7:0];
        pk_b   <= (mag7(lane_in[2][7:0]) >= mag7(lane_in[3][7:0])) ? lane_in[2][7:0] : lane_in[3][7:0];
        pk_ora <= lane_in[0][8] | lane_in[1][8] | lane_in[2][8] | lane_in[3][8];
        pk_v1  <= word_valid && run;
        pk_code  <= (mag7(pk_a) >= mag7(pk_b)) ? pk_a : pk_b;
        pk_or    <= pk_ora;
        pk_valid <= pk_v1;
    end

    // ---------------------------------------------------------------------------------------------------------
    // P0: samples as odd 9-bit numbers; NCO lane phases
    // ---------------------------------------------------------------------------------------------------------
    reg  [31:0] f2 = 32'd0, f3 = 32'd0, f4 = 32'd0, acc = 32'd0;
    reg  [31:0] th [0:3];
    reg  signed [8:0] x0 [0:3];
    reg         v0 = 1'b0;
    always @(posedge clk) begin
        f2 <= {ftw[30:0], 1'b0};
        f3 <= ftw + {ftw[30:0], 1'b0};
        f4 <= {ftw[29:0], 2'b00};
        v0 <= word_valid && run;
        for (i = 0; i < 4; i = i + 1)
            x0[i] <= {~lane_in[i][7], lane_in[i][6:0], 1'b1};          // 2 * (code - 128) + 1
        if (!run) acc <= 32'd0;
        else if (word_valid) acc <= acc + f4;
`ifdef MUTATE_D2_NCO_LANE0
        th[0] <= acc; th[1] <= acc; th[2] <= acc; th[3] <= acc;
`else
        th[0] <= acc;
        th[1] <= acc + ftw;
        th[2] <= acc + f2;
        th[3] <= acc + f3;
`endif
    end

    // ---------------------------------------------------------------------------------------------------------
    // P1: quarter-wave lookups (the ROM's output register); P2: signed sine and cosine
    // ---------------------------------------------------------------------------------------------------------
    wire [11:0] ta [0:3], tb [0:3];
    reg  [1:0]  q1 [0:3];
    reg  signed [8:0] x1 [0:3], x2 [0:3];
    reg  signed [12:0] lo_c [0:3], lo_s [0:3];
    reg         v1 = 1'b0, v2 = 1'b0;
    genvar gl;
    generate
        for (gl = 0; gl < 4; gl = gl + 1) begin : g_rom
            ddc500_rom u_rom (.clk(clk), .addr_a(th[gl][29:20]), .addr_b(~th[gl][29:20]),
                              .dout_a(ta[gl]), .dout_b(tb[gl]));
        end
    endgenerate
    always @(posedge clk) begin
        v1 <= v0; v2 <= v1;
        for (i = 0; i < 4; i = i + 1) begin
            q1[i] <= th[i][31:30];
            x1[i] <= x0[i]; x2[i] <= x1[i];
            // sin: quadrant 0 T[j], 1 T[~j], 2 -T[j], 3 -T[~j]; cos = sin of the next quadrant
            begin : blk_lo
                reg [11:0] sv, cv;
                sv = q1[i][0] ? tb[i] : ta[i];
                cv = q1[i][0] ? ta[i] : tb[i];
                lo_c[i] <= (q1[i][1] ^ q1[i][0]) ? -$signed({1'b0, cv}) : $signed({1'b0, cv});
                // Q = -x sin (e^-j theta); with CONJ, +x sin
                lo_s[i] <= (q1[i][1] ^ conj) ? $signed({1'b0, sv}) : -$signed({1'b0, sv});
            end
        end
    end

    // ---------------------------------------------------------------------------------------------------------
    // P3: products (LUTs); P4: rounded to 16 bits
    // ---------------------------------------------------------------------------------------------------------
    reg signed [21:0] pi4 [0:3], pq4 [0:3];
    reg signed [15:0] mi [0:3], mq [0:3];
    reg               v3 = 1'b0, v4 = 1'b0;
    always @(posedge clk) begin
        v3 <= v2; v4 <= v3;
        for (i = 0; i < 4; i = i + 1) begin
            pi4[i] <= x2[i] * lo_c[i];
            pq4[i] <= x2[i] * lo_s[i];
            mi[i]  <= (pi4[i] + 22'sd16) >>> 5;                      // |x * lo| <= 255 * 4095: fits after >>> 5
            mq[i]  <= (pq4[i] + 22'sd16) >>> 5;
        end
    end

    // ---------------------------------------------------------------------------------------------------------
    // CIC integrators, four lanes per cycle. Stage s, word w: prefix sums p[k] = a[0] + .. + a[k] (registered),
    // then b[k] = acc + p[k] and acc += p[3]. Two cycles per stage.
    // ---------------------------------------------------------------------------------------------------------
    reg signed [W-1:0] ia [0:5][0:3];     // ia[s]: stage s input lanes (ia[0] = mixer), ia[5]: last output
    reg signed [W-1:0] ip [0:4][0:3];     // prefix sums of stage s
    reg signed [W-1:0] iacc [0:4];
    reg [5:0]          vi_a, vi_p;        // valid of ia[s] (bit s) and ip[s]
    reg signed [W-1:0] qa [0:5][0:3];
    reg signed [W-1:0] qp [0:4][0:3];
    reg signed [W-1:0] qacc [0:4];

    always @(posedge clk) begin
        for (i = 0; i < 4; i = i + 1) begin
            ia[0][i] <= {{(W-16){mi[i][15]}}, mi[i]};
            qa[0][i] <= {{(W-16){mq[i][15]}}, mq[i]};
        end
        if (!run) begin
            vi_a <= 6'd0; vi_p <= 6'd0;
            for (s = 0; s < 5; s = s + 1) begin iacc[s] <= {W{1'b0}}; qacc[s] <= {W{1'b0}}; end
        end else begin
            vi_a[0] <= v4;
            for (s = 0; s < 5; s = s + 1) begin
                vi_p[s] <= vi_a[s];
                ip[s][0] <= ia[s][0];
                ip[s][1] <= ia[s][0] + ia[s][1];
                ip[s][2] <= ia[s][0] + ia[s][1] + ia[s][2];
                ip[s][3] <= (ia[s][0] + ia[s][1]) + (ia[s][2] + ia[s][3]);
                qp[s][0] <= qa[s][0];
                qp[s][1] <= qa[s][0] + qa[s][1];
                qp[s][2] <= qa[s][0] + qa[s][1] + qa[s][2];
                qp[s][3] <= (qa[s][0] + qa[s][1]) + (qa[s][2] + qa[s][3]);
                vi_a[s + 1] <= vi_p[s];
                for (i = 0; i < 4; i = i + 1) begin
                    ia[s + 1][i] <= iacc[s] + ip[s][i];
                    qa[s + 1][i] <= qacc[s] + qp[s][i];
                end
                if (vi_p[s]) begin
                    iacc[s] <= iacc[s] + ip[s][3];
                    qacc[s] <= qacc[s] + qp[s][3];
                end
            end
        end
    end

    // ---------------------------------------------------------------------------------------------------------
    // Decimation by 5: of words 0..4, take lane 0, 1, 2, 3 and none (samples 0, 5, 10, 15 of 20); five combs
    // ---------------------------------------------------------------------------------------------------------
    reg [2:0]          dph;
    reg signed [W-1:0] ci [0:5], cq [0:5], zi [0:4], zq [0:4];
    reg [5:0]          vc;
    always @(posedge clk) begin
        if (!run) begin
            dph <= 3'd0; vc <= 6'd0;
            for (s = 0; s < 5; s = s + 1) begin zi[s] <= {W{1'b0}}; zq[s] <= {W{1'b0}}; end
        end else begin
            vc[0] <= 1'b0;
            if (vi_a[5]) begin
                dph <= (dph == 3'd4) ? 3'd0 : dph + 3'd1;
                if (dph != 3'd4) begin
                    vc[0] <= 1'b1;
                    ci[0] <= ia[5][dph[1:0]];
                    cq[0] <= qa[5][dph[1:0]];
                end
            end
            for (s = 0; s < 5; s = s + 1) begin
                vc[s + 1] <= vc[s];
                if (vc[s]) begin
                    ci[s + 1] <= ci[s] - zi[s]; zi[s] <= ci[s];
                    cq[s + 1] <= cq[s] - zq[s]; zq[s] <= cq[s];
                end
            end
        end
    end

    // gain 3125 / 4096; |comb output| <= 32632 * 3125 < 2^27, so no saturation
    reg signed [15:0] c16_i, c16_q;
    reg               c16_v;
    always @(posedge clk) begin
        c16_v <= run && vc[5];
        c16_i <= (ci[5] + 28'sd2048) >>> 12;
        c16_q <= (cq[5] + 28'sd2048) >>> 12;
    end

    ddc_hb4 u_hb4 (.clk(clk), .rst(!run), .in_valid(c16_v), .in_i(c16_i), .in_q(c16_q),
        .out_valid(bb_valid), .out_i(bb_i), .out_q(bb_q));

    // ---------------------------------------------------------------------------------------------------------
    // Packets: two {Q, I} samples per 64-bit word (the first in [31:0]); synchronous FIFO; store and forward
    // ---------------------------------------------------------------------------------------------------------
    localparam integer DEPTH = (1 << FIFO_AW);
    reg [63:0]        fifo_mem [0:DEPTH-1];
    reg [FIFO_AW:0]   wr_ptr, rd_ptr;
    reg               half_phase;
    reg [31:0]        half_word;
    reg [15:0]        word_idx;
    reg               pkt_active;
    wire [FIFO_AW:0]  fill       = wr_ptr - rd_ptr;
    wire              fifo_full  = (fill == DEPTH);
    wire              fifo_empty = (fill == 0);
    wire              pkt_avail  = (fill >= PKT_WORDS);

    assign pkt_stream_id = STREAM_ID;
    assign pkt_len       = PKT_WORDS * 16'd8;
    assign pkt_valid     = pkt_active ? !fifo_empty : pkt_avail;
    assign pkt_sop       = (word_idx == 16'd0);
    assign pkt_eop       = pkt_valid && (word_idx == PKT_WORDS - 1);
    assign pkt_data      = fifo_mem[rd_ptr[FIFO_AW-1:0]];

    always @(posedge clk) begin
        if (bb_valid && half_phase && !fifo_full && run)
            fifo_mem[wr_ptr[FIFO_AW-1:0]] <= {bb_q, bb_i, half_word};
    end

    assign pkt_busy = pkt_active;
    always @(posedge clk) begin
        if (rst) begin
            pkt_seq <= 32'd0; dropped_cnt <= 24'd0;
        end
        if (rst || (!run && !pkt_active)) begin
            wr_ptr <= 0; rd_ptr <= 0; half_phase <= 1'b0; half_word <= 32'd0;
            word_idx <= 16'd0; pkt_active <= 1'b0; pkt_timestamp <= 64'd0;
        end else begin
            if (bb_valid && run) begin
                half_phase <= ~half_phase;
                if (!half_phase) half_word <= {bb_q, bb_i};
                else if (!fifo_full) wr_ptr <= wr_ptr + 1'b1;
                else if (dropped_cnt != 24'hFFFFFF) dropped_cnt <= dropped_cnt + 24'd1;
            end
            if (!pkt_active && pkt_avail && run) begin
                pkt_timestamp <= timestamp_cnt;
                pkt_active    <= 1'b1;
            end
            if (pkt_valid && pkt_ready) begin
                rd_ptr <= rd_ptr + 1'b1;
                if (word_idx == PKT_WORDS - 1) begin
                    word_idx   <= 16'd0;
                    pkt_active <= 1'b0;
                    pkt_seq    <= pkt_seq + 32'd1;
                end else begin
                    word_idx <= word_idx + 16'd1;
                end
            end
        end
    end
endmodule
`default_nettype wire
