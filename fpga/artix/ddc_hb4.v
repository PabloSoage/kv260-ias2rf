// SPDX-License-Identifier: Apache-2.0
// Rev08 G-8: anti-alias decimation by 4 for the radar DDC's 100 MSPS output (ddc_wrapper POST_DECIM = 4).
//
// The post-decimation used to keep one sample in four with no filter, so everything the AERIS FIR passes
// (about +/-45 MHz) folded into the 25 MSPS stream: the noise density rose 2.5 dB and signals 15 to 40 MHz away
// landed in the channel. Two half-band stages, both multiplierless (constant products in LUTs, no DSP48):
//   A  100 -> 50 MSPS, 11 taps [3 0 -25 0 150 256 150 0 -25 0 3] / 512: -42.5 dB from 40 to 50 MHz
//   B   50 -> 25 MSPS, 27 taps (/2048): -49.6 dB from 15 to 25 MHz
// Passband flat to 0.07 dB up to +/-10 MHz. Latency about 9 output samples (ddc_wrapper's CPI mark delay).
// Mutation (run.ps1 -Mutate): no_aa_filter (the old one-in-four), checked by tb_ddc_hb4.

`timescale 1ns/1ps
`default_nettype none

module ddc_hb4 (
    input  wire               clk,
    input  wire               rst,
    input  wire               in_valid,
    input  wire signed [15:0] in_i,
    input  wire signed [15:0] in_q,
    output reg                out_valid,
    output reg  signed [15:0] out_i,
    output reg  signed [15:0] out_q
);
`ifdef MUTATE_NO_AA_FILTER
    reg [1:0] ph;
    always @(posedge clk) begin
        if (rst) begin ph <= 2'd0; out_valid <= 1'b0; out_i <= 16'sd0; out_q <= 16'sd0; end
        else begin
            out_valid <= 1'b0;
            if (in_valid) begin
                ph <= ph + 2'd1;
                if (ph == 2'd3) begin out_valid <= 1'b1; out_i <= in_i; out_q <= in_q; end
            end
        end
    end
`else
    wire        a_valid;
    wire signed [15:0] a_i, a_q;
    ddc_hb_stage #(.STAGE(0)) u_a (.clk(clk), .rst(rst), .in_valid(in_valid), .in_i(in_i), .in_q(in_q),
        .out_valid(a_valid), .out_i(a_i), .out_q(a_q));
    wire        b_valid;
    wire signed [15:0] b_i, b_q;
    ddc_hb_stage #(.STAGE(1)) u_b (.clk(clk), .rst(rst), .in_valid(a_valid), .in_i(a_i), .in_q(a_q),
        .out_valid(b_valid), .out_i(b_i), .out_q(b_q));
    always @(posedge clk) begin
        out_valid <= b_valid;
        out_i     <= b_i;
        out_q     <= b_q;
    end
`endif
endmodule


// One half-band decimate-by-2 stage. STAGE 0: 11 taps / 512; STAGE 1: 27 taps / 2048. The odd taps are zero
// except the centre, so each output is the centre tap plus (N + 1) / 4 symmetric pairs.
(* use_dsp = "no" *)
module ddc_hb_stage #(
    parameter integer STAGE = 0
) (
    input  wire               clk,
    input  wire               rst,
    input  wire               in_valid,
    input  wire signed [15:0] in_i,
    input  wire signed [15:0] in_q,
    output reg                out_valid,
    output reg  signed [15:0] out_i,
    output reg  signed [15:0] out_q
);
    localparam integer NT    = (STAGE == 0) ? 11 : 27;
    localparam integer NP    = (NT + 1) / 4;          // non-zero symmetric pairs (3 and 7)
    localparam integer SHIFT = (STAGE == 0) ? 9 : 11;

    function automatic signed [15:0] coef(input integer k);   // pair k: taps k*2 and NT-1-k*2
        begin
            if (STAGE == 0)
                case (k) 0: coef = 16'sd3; 1: coef = -16'sd25; default: coef = 16'sd150; endcase
            else
                case (k)
                    0: coef = 16'sd8;   1: coef = -16'sd16; 2: coef = 16'sd32;  3: coef = -16'sd58;
                    4: coef = 16'sd103; 5: coef = -16'sd200; default: coef = 16'sd646;
                endcase
        end
    endfunction
    localparam signed [15:0] CENTRE = (STAGE == 0) ? 16'sd256 : 16'sd1024;

    reg signed [15:0] di [0:NT-1];
    reg signed [15:0] dq [0:NT-1];
    reg               ph;
    // pipeline: pair sums, products, accumulate, round
    reg               v1, v2, v3;
    reg signed [16:0] si [0:NP-1], sq [0:NP-1];
    reg signed [15:0] ci, cq;
    reg signed [33:0] pi [0:NP], pq [0:NP];
    reg signed [37:0] acc_i, acc_q;
    integer k;

    function automatic signed [15:0] sat_round(input signed [37:0] v);
        reg signed [37:0] r;
        begin
            r = (v + (38'sd1 <<< (SHIFT - 1))) >>> SHIFT;
            if (r > 38'sd32767)       sat_round = 16'sd32767;
            else if (r < -38'sd32768) sat_round = -16'sd32768;
            else                      sat_round = r[15:0];
        end
    endfunction

    always @(posedge clk) begin
        if (rst) begin
            for (k = 0; k < NT; k = k + 1) begin di[k] <= 16'sd0; dq[k] <= 16'sd0; end
            ph <= 1'b0; v1 <= 1'b0; v2 <= 1'b0; v3 <= 1'b0; out_valid <= 1'b0;
            out_i <= 16'sd0; out_q <= 16'sd0; acc_i <= 38'sd0; acc_q <= 38'sd0;
        end else begin
            v1 <= 1'b0;
            if (in_valid) begin
                di[0] <= in_i; dq[0] <= in_q;
                for (k = 1; k < NT; k = k + 1) begin di[k] <= di[k - 1]; dq[k] <= dq[k - 1]; end
                ph <= ~ph;
                v1 <= ph;                                   // every other input sample makes an output
            end
            // stage 1: the delay line as it stands after the shift (registered: one valid later)
            for (k = 0; k < NP; k = k + 1) begin
                si[k] <= {di[2 * k][15], di[2 * k]} + {di[NT - 1 - 2 * k][15], di[NT - 1 - 2 * k]};
                sq[k] <= {dq[2 * k][15], dq[2 * k]} + {dq[NT - 1 - 2 * k][15], dq[NT - 1 - 2 * k]};
            end
            ci <= di[(NT - 1) / 2];
            cq <= dq[(NT - 1) / 2];
            v2 <= v1;
            // stage 2: constant products
            for (k = 0; k < NP; k = k + 1) begin
                pi[k] <= si[k] * coef(k);
                pq[k] <= sq[k] * coef(k);
            end
            pi[NP] <= ci * CENTRE;
            pq[NP] <= cq * CENTRE;
            v3 <= v2;
            // stage 3: sum; stage 4: round and saturate
            begin : blk_sum
                reg signed [37:0] ti, tq;
                ti = 38'sd0; tq = 38'sd0;
                for (k = 0; k <= NP; k = k + 1) begin ti = ti + pi[k]; tq = tq + pq[k]; end
                acc_i <= ti; acc_q <= tq;
            end
            out_valid <= v3;
            out_i     <= sat_round(acc_i);
            out_q     <= sat_round(acc_q);
        end
    end
endmodule
`default_nettype wire
