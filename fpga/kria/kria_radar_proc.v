// SPDX-License-Identifier: Apache-2.0
// Kria PL Streaming Radar 2D Range-Doppler FFT + CA-CFAR Processor
//
// Placed in Kria PL (XCK26) behind IAS1 STREAM_ID 8'h01 (AD9484 + AERIS u_ddc stops at DDC).
// Processes CPIs of M_DOPPLER=16 chirps x N_RANGE=64 fast-time complex baseband samples:
//   1. 64-pt Hann window + Radix-2 DIT Range FFT (6 stages, 192 butterflies/chirp)
//   2. 64 x 16 CPI Corner-Turn BRAM
//   3. 16-pt Hann window + Radix-2 DIT Doppler FFT (4 stages, 32 butterflies/range-bin)
//   4. Power |Z|^2 + 1D/Range Cell-Averaging CFAR detector (guard=1, train=4 each side)
//      streaming the full 64x16 Range-Doppler matrix + detection flags.

`timescale 1ns/1ps

module kria_radar_proc #(
    parameter integer RANGE_N   = 64,
    parameter integer DOPPLER_M = 16
) (
    input  wire               clk,
    input  wire               rst,

    // Complex Baseband Input Stream (packed as contiguous RANGE_N * DOPPLER_M samples per CPI)
    input  wire               in_valid,
    output wire               in_ready,
    input  wire signed [15:0] in_i,
    input  wire signed [15:0] in_q,
    input  wire               cpi_sync_start, // Frame sync: this sample is chirp 0, sample 0
    input  wire               cfg_sync_en,    // 1 = capture only from a sync sample (the Artix CPI mark, G-8)

    // CA-CFAR & Window Configuration
    input  wire               cfg_win_en,       // 1 = enable Hann window on Range & Doppler
    input  wire [15:0]        cfg_cfar_alpha_q8,// CFAR threshold factor Q8 (e.g. 16'd1536 = 6.0x)
    input  wire [31:0]        cfg_cfar_min_pwr, // Minimum absolute noise floor threshold

    // Streaming Range-Doppler Map + CA-CFAR Detection Outputs (1024 cells per CPI)
    output reg                rd_out_valid,
    output reg  [5:0]         rd_out_rbin,
    output reg  [3:0]         rd_out_dbin,
    output reg  [31:0]        rd_out_pwr,
    output reg                rd_out_det,
    output reg                cpi_done_pulse,
    output reg  [15:0]        cpi_det_cnt,
    output reg  [5:0]         peak_rbin,
    output reg  [3:0]         peak_dbin,
    output reg  [31:0]        peak_pwr
);
    // 6-bit bit-reversal for 64-pt DIT FFT, 4-bit for 16-pt DIT FFT
    function automatic [5:0] bitrev6;
        input [5:0] x;
        begin
            bitrev6 = {x[0], x[1], x[2], x[3], x[4], x[5]};
        end
    endfunction

    function automatic [3:0] bitrev4;
        input [3:0] x;
        begin
            bitrev4 = {x[0], x[1], x[2], x[3]};
        end
    endfunction

    // 64-pt Hann window Q15 (0..63), plus 16-pt Hann window (index * 4)
    function automatic signed [15:0] hann64;
        input [5:0] n;
        begin
            case (n)
                6'd0,  6'd63: hann64 = 16'sd0;
                6'd1,  6'd62: hann64 = 16'sd81;
                6'd2,  6'd61: hann64 = 16'sd324;
                6'd3,  6'd60: hann64 = 16'sd727;
                6'd4,  6'd59: hann64 = 16'sd1287;
                6'd5,  6'd58: hann64 = 16'sd1998;
                6'd6,  6'd57: hann64 = 16'sd2853;
                6'd7,  6'd56: hann64 = 16'sd3843;
                6'd8,  6'd55: hann64 = 16'sd4959;
                6'd9,  6'd54: hann64 = 16'sd6190;
                6'd10, 6'd53: hann64 = 16'sd7524;
                6'd11, 6'd52: hann64 = 16'sd8947;
                6'd12, 6'd51: hann64 = 16'sd10446;
                6'd13, 6'd50: hann64 = 16'sd12006;
                6'd14, 6'd49: hann64 = 16'sd13611;
                6'd15, 6'd48: hann64 = 16'sd15246;
                6'd16, 6'd47: hann64 = 16'sd16895;
                6'd17, 6'd46: hann64 = 16'sd18542;
                6'd18, 6'd45: hann64 = 16'sd20170;
                6'd19, 6'd44: hann64 = 16'sd21763;
                6'd20, 6'd43: hann64 = 16'sd23306;
                6'd21, 6'd42: hann64 = 16'sd24782;
                6'd22, 6'd41: hann64 = 16'sd26177;
                6'd23, 6'd40: hann64 = 16'sd27477;
                6'd24, 6'd39: hann64 = 16'sd28670;
                6'd25, 6'd38: hann64 = 16'sd29743;
                6'd26, 6'd37: hann64 = 16'sd30685;
                6'd27, 6'd36: hann64 = 16'sd31487;
                6'd28, 6'd35: hann64 = 16'sd32142;
                6'd29, 6'd34: hann64 = 16'sd32642;
                6'd30, 6'd33: hann64 = 16'sd32767;
                default:      hann64 = 16'sd32767;
            endcase
        end
    endfunction

    // 64-pt Twiddle W_64^k = cos(2*pi*k/64) - j*sin(2*pi*k/64) in Q14 (16384 = 1.0)
    // k = 0..31 suffices for all stages of Radix-2 64-pt DIT FFT
    function automatic signed [15:0] tw64_cos;
        input [4:0] k;
        begin
            case (k)
                5'd0:  tw64_cos =  16'sd16384; 5'd1:  tw64_cos =  16'sd16305;
                5'd2:  tw64_cos =  16'sd16069; 5'd3:  tw64_cos =  16'sd15679;
                5'd4:  tw64_cos =  16'sd15137; 5'd5:  tw64_cos =  16'sd14449;
                5'd6:  tw64_cos =  16'sd13623; 5'd7:  tw64_cos =  16'sd12665;
                5'd8:  tw64_cos =  16'sd11585; 5'd9:  tw64_cos =  16'sd10394;
                5'd10: tw64_cos =  16'sd9102;  5'd11: tw64_cos =  16'sd7723;
                5'd12: tw64_cos =  16'sd6270;  5'd13: tw64_cos =  16'sd4756;
                5'd14: tw64_cos =  16'sd3196;  5'd15: tw64_cos =  16'sd1606;
                5'd16: tw64_cos =  16'sd0;     5'd17: tw64_cos = -16'sd1606;
                5'd18: tw64_cos = -16'sd3196;  5'd19: tw64_cos = -16'sd4756;
                5'd20: tw64_cos = -16'sd6270;  5'd21: tw64_cos = -16'sd7723;
                5'd22: tw64_cos = -16'sd9102;  5'd23: tw64_cos = -16'sd10394;
                5'd24: tw64_cos = -16'sd11585; 5'd25: tw64_cos = -16'sd12665;
                5'd26: tw64_cos = -16'sd13623; 5'd27: tw64_cos = -16'sd14449;
                5'd28: tw64_cos = -16'sd15137; 5'd29: tw64_cos = -16'sd15679;
                5'd30: tw64_cos = -16'sd16069; 5'd31: tw64_cos = -16'sd16305;
            endcase
        end
    endfunction

    function automatic signed [15:0] tw64_sin_neg; // -sin(2*pi*k/64) Q14
        input [4:0] k;
        reg signed [15:0] s_pos;
        begin
            case (k)
                5'd0:  s_pos = 16'sd0;     5'd1:  s_pos = 16'sd1606;
                5'd2:  s_pos = 16'sd3196;  5'd3:  s_pos = 16'sd4756;
                5'd4:  s_pos = 16'sd6270;  5'd5:  s_pos = 16'sd7723;
                5'd6:  s_pos = 16'sd9102;  5'd7:  s_pos = 16'sd10394;
                5'd8:  s_pos = 16'sd11585; 5'd9:  s_pos = 16'sd12665;
                5'd10: s_pos = 16'sd13623; 5'd11: s_pos = 16'sd14449;
                5'd12: s_pos = 16'sd15137; 5'd13: s_pos = 16'sd15679;
                5'd14: s_pos = 16'sd16069; 5'd15: s_pos = 16'sd16305;
                5'd16: s_pos = 16'sd16384; 5'd17: s_pos = 16'sd16305;
                5'd18: s_pos = 16'sd16069; 5'd19: s_pos = 16'sd15679;
                5'd20: s_pos = 16'sd15137; 5'd21: s_pos = 16'sd14449;
                5'd22: s_pos = 16'sd13623; 5'd23: s_pos = 16'sd12665;
                5'd24: s_pos = 16'sd11585; 5'd25: s_pos = 16'sd10394;
                5'd26: s_pos = 16'sd9102;  5'd27: s_pos = 16'sd7723;
                5'd28: s_pos = 16'sd6270;  5'd29: s_pos = 16'sd4756;
                5'd30: s_pos = 16'sd3196;  5'd31: s_pos = 16'sd1606;
            endcase
`ifdef MUTATE_WRONG_TWIDDLE_SIGN
            tw64_sin_neg = s_pos;  // MUTATION: +sin instead of -sin destroys FFT focusing
`else
            tw64_sin_neg = -s_pos;
`endif
        end
    endfunction

    // G-8 timing closure: every phase of the CPI is a pipeline. The state machine issues one operation per clock
    // (a load, a butterfly, a store, a power, a CFAR cell) exactly as before; each runs through its own pipeline
    // registers and writes where the former single-clock code wrote. Between phases that read what the previous
    // one wrote (and between FFT stages) the machine waits in ST_WAIT until the pipelines are empty, so every
    // operation sees the operands it saw before. The map, the detections and the CPI statistics are the former
    // ones; a CPI takes about 1,500 clocks (15 us) more. The corner-turn memory has a single write and a single
    // synchronous read port outside the reset branch, so it maps to block RAM; the power map is nine block-RAM copies.
    localparam [3:0] ST_LOAD_CHIRP  = 4'd0,
                     ST_RFFT_BFLY   = 4'd1,
                     ST_RFFT_STORE  = 4'd2,
                     ST_DFFT_LOAD   = 4'd3,
                     ST_DFFT_BFLY   = 4'd4,
                     ST_DFFT_POWER  = 4'd5,
                     ST_CFAR_SCAN   = 4'd6,
                     ST_RFFT_LOAD   = 4'd7,
                     ST_WAIT        = 4'd8;

    reg [3:0] state, next_state;
    reg [2:0] wait_cnt;
    reg       synced;
    assign in_ready = (state == ST_LOAD_CHIRP);

    // Scratchpads for 64-pt Range FFT & 16-pt Doppler FFT
    reg signed [23:0] fft_re [0:RANGE_N-1];
    reg signed [23:0] fft_im [0:RANGE_N-1];

    // CPI Corner-Turn Complex Memory (64 x 16 = 1024 entries)
    (* ram_style = "block" *) reg signed [23:0] cpi_re [0:(RANGE_N*DOPPLER_M)-1];
    (* ram_style = "block" *) reg signed [23:0] cpi_im [0:(RANGE_N*DOPPLER_M)-1];
    // Range-Doppler Power Map (64 x 16 = 1024 x 32-bit unsigned). CFAR reads nine cells per clock, so the map is
    // kept as nine block-RAM copies with one write port and one synchronous read port each; rd_pwr is copy 8 (the
    // cell under test) and the name the equivalence benches look at.
    reg [31:0] pwr_wd;
    reg [9:0]  pwr_wa;
    reg        pwr_we;
    (* ram_style = "block" *) reg [31:0] rd_pwr  [0:(RANGE_N*DOPPLER_M)-1];
    (* ram_style = "block" *) reg [31:0] pwr_m0 [0:(RANGE_N*DOPPLER_M)-1];
    (* ram_style = "block" *) reg [31:0] pwr_m1 [0:(RANGE_N*DOPPLER_M)-1];
    (* ram_style = "block" *) reg [31:0] pwr_m2 [0:(RANGE_N*DOPPLER_M)-1];
    (* ram_style = "block" *) reg [31:0] pwr_m3 [0:(RANGE_N*DOPPLER_M)-1];
    (* ram_style = "block" *) reg [31:0] pwr_m4 [0:(RANGE_N*DOPPLER_M)-1];
    (* ram_style = "block" *) reg [31:0] pwr_m5 [0:(RANGE_N*DOPPLER_M)-1];
    (* ram_style = "block" *) reg [31:0] pwr_m6 [0:(RANGE_N*DOPPLER_M)-1];
    (* ram_style = "block" *) reg [31:0] pwr_m7 [0:(RANGE_N*DOPPLER_M)-1];

    reg [5:0]  samp_idx;
    reg [3:0]  chirp_idx;
    reg [2:0]  bfly_stage;
    reg [4:0]  bfly_idx;
    reg [5:0]  scan_r;
    reg [3:0]  scan_d;

    integer ii;

    // ---- pipeline registers
    // range / Doppler load: l1 block-RAM data, l2 window and write
    reg               l1_v, l1_dop;
    reg [5:0]         l1_n;          // range: sample index; Doppler: {2'b0, chirp}
    reg signed [23:0] l1_r, l1_i;
    // butterflies: b1 indices and twiddle, b2 operands, b3 products, write
    reg               b1_v, b2_v, b3_v;
    reg [5:0]         b1_a, b1_b, b2_a, b2_b, b3_a, b3_b;
    reg signed [15:0] b1_wr, b1_wi, b2_wr, b2_wi;
    reg signed [23:0] b2_ar, b2_ai, b2_br, b2_bi, b3_ar, b3_ai;
    reg signed [41:0] b3_p1, b3_p2, b3_p3, b3_p4;
    // store: s1 the bin read from the scratchpad
    reg               s1_v;
    reg [9:0]         s1_addr;
    reg signed [23:0] s1_r, s1_i;
    // power: q1 operands, q2 squares, write
    reg               q1_v, q2_v;
    reg [9:0]         q1_addr, q2_addr;
    reg signed [23:0] q1_r, q1_i;
    reg signed [47:0] q2_rr, q2_ii;
    // CFAR: c1 addresses, c2 the nine reads, c3 partial sums, c4 mean, c5 threshold, outputs
    reg               c1_v, c2_v, c3_v, c4_v, c5_v;
    reg               c1_last, c2_last, c3_last, c4_last, c5_last;
    reg [5:0]         c1_r, c2_r, c3_r, c4_r, c5_r;
    reg [3:0]         c1_d, c2_d, c3_d, c4_d, c5_d;
    reg [9:0]         c1_ad [0:8];
    reg [31:0]        c2_p [0:8];   // written by the power-map RAM block
    reg [31:0]        c3_cut, c4_cut, c5_cut;
    reg [35:0]        c3_s0, c3_s1, c4_mean, c5_thr;

    // butterfly addressing for the issue at bfly_stage / bfly_idx (range: 64 points, Doppler: 16)
    reg [5:0] bi_a, bi_b;
    reg [4:0] bi_k;
    always @(*) begin : blk_bidx
        integer half, group, pos, idx_a;
        half  = 1 << bfly_stage;
        if (state == ST_DFFT_BFLY) begin
            group = bfly_idx[2:0] >> bfly_stage;
            pos   = bfly_idx[2:0] & (half - 1);
        end else begin
            group = bfly_idx >> bfly_stage;
            pos   = bfly_idx & (half - 1);
        end
        idx_a = (group << (bfly_stage + 1)) + pos;
        bi_a  = idx_a;
        bi_b  = idx_a + half;
        bi_k  = (pos << (5 - bfly_stage));
    end

    // corner-turn memory: one write port (the capture in ST_LOAD_CHIRP, else the range-FFT store) and one
    // synchronous read port (l1_r/l1_i for the range and Doppler loads), outside the reset block so that each
    // half maps to block RAM
    reg        cm_we;
    reg [9:0]  cm_wa, cm_ra;
    reg signed [23:0] cm_wr, cm_wi;
    always @(*) begin
        cm_we = 1'b0; cm_wa = s1_addr; cm_wr = s1_r; cm_wi = s1_i;
        if (rst) begin
            cm_we = 1'b0;
        end else if (state == ST_LOAD_CHIRP && in_valid && (cpi_sync_start || synced || !cfg_sync_en)) begin
            cm_we = 1'b1;
            cm_wa = cpi_sync_start ? 10'd0 : {chirp_idx, samp_idx};
            cm_wr = {{8{in_i[15]}}, in_i};
            cm_wi = {{8{in_q[15]}}, in_q};
        end else if (s1_v) begin
            cm_we = 1'b1;
        end
        cm_ra = (state == ST_DFFT_LOAD) ? {scan_d, scan_r} : {chirp_idx, samp_idx};
    end
    always @(posedge clk) begin
        if (cm_we) begin
            cpi_re[cm_wa] <= cm_wr;
            cpi_im[cm_wa] <= cm_wi;
        end
        if (state == ST_RFFT_LOAD || state == ST_DFFT_LOAD) begin
            l1_r <= cpi_re[cm_ra];
            l1_i <= cpi_im[cm_ra];
        end
    end

    // power map: the write from power step 3 and the nine CFAR reads (c2), outside the reset block so that each
    // copy maps to one RAMB36
    always @(*) begin : blk_pwr
        reg [47:0] psum;
        psum   = q2_rr + q2_ii;
        pwr_we = q2_v;
        pwr_wa = q2_addr;
        pwr_wd = psum[31:0];
    end
    always @(posedge clk) begin
        if (pwr_we) begin
            pwr_m0[pwr_wa] <= pwr_wd; pwr_m1[pwr_wa] <= pwr_wd; pwr_m2[pwr_wa] <= pwr_wd;
            pwr_m3[pwr_wa] <= pwr_wd; pwr_m4[pwr_wa] <= pwr_wd; pwr_m5[pwr_wa] <= pwr_wd;
            pwr_m6[pwr_wa] <= pwr_wd; pwr_m7[pwr_wa] <= pwr_wd; rd_pwr[pwr_wa] <= pwr_wd;
        end
        if (c1_v) begin
            c2_p[0] <= pwr_m0[c1_ad[0]]; c2_p[1] <= pwr_m1[c1_ad[1]]; c2_p[2] <= pwr_m2[c1_ad[2]];
            c2_p[3] <= pwr_m3[c1_ad[3]]; c2_p[4] <= pwr_m4[c1_ad[4]]; c2_p[5] <= pwr_m5[c1_ad[5]];
            c2_p[6] <= pwr_m6[c1_ad[6]]; c2_p[7] <= pwr_m7[c1_ad[7]]; c2_p[8] <= rd_pwr[c1_ad[8]];
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            state          <= ST_LOAD_CHIRP;
            next_state     <= ST_LOAD_CHIRP;
            wait_cnt       <= 3'd0;
            synced         <= 1'b0;
            samp_idx       <= 6'd0;
            chirp_idx      <= 4'd0;
            bfly_stage     <= 3'd0;
            bfly_idx       <= 5'd0;
            scan_r         <= 6'd0;
            scan_d         <= 4'd0;
            rd_out_valid   <= 1'b0;
            rd_out_rbin    <= 6'd0;
            rd_out_dbin    <= 4'd0;
            rd_out_pwr     <= 32'd0;
            rd_out_det     <= 1'b0;
            cpi_done_pulse <= 1'b0;
            cpi_det_cnt    <= 16'd0;
            peak_rbin      <= 6'd0;
            peak_dbin      <= 4'd0;
            peak_pwr       <= 32'd0;
            l1_v <= 1'b0; b1_v <= 1'b0; b2_v <= 1'b0; b3_v <= 1'b0; s1_v <= 1'b0; q1_v <= 1'b0; q2_v <= 1'b0;
            c1_v <= 1'b0; c2_v <= 1'b0; c3_v <= 1'b0; c4_v <= 1'b0; c5_v <= 1'b0;
        end else begin
            rd_out_valid   <= 1'b0;
            cpi_done_pulse <= 1'b0;
            l1_v <= 1'b0; b1_v <= 1'b0; s1_v <= 1'b0; q1_v <= 1'b0; c1_v <= 1'b0;

            // ================= pipelines =================
            // load, step 2: window and write to the scratchpad (bit-reversed)
            if (l1_v) begin
                if (!l1_dop) begin : blk_rld
                    reg signed [31:0] wi, wq;
                    if (cfg_win_en) begin
                        wi = ($signed(l1_r[15:0]) * $signed(hann64(l1_n))) >>> 15;
                        wq = ($signed(l1_i[15:0]) * $signed(hann64(l1_n))) >>> 15;
                    end else begin
                        wi = {{16{l1_r[15]}}, l1_r[15:0]};
                        wq = {{16{l1_i[15]}}, l1_i[15:0]};
                    end
                    fft_re[bitrev6(l1_n)] <= wi[23:0];
                    fft_im[bitrev6(l1_n)] <= wq[23:0];
                end else begin : blk_dld
                    reg signed [41:0] w_r, w_i;
                    if (cfg_win_en) begin
                        w_r = ($signed(l1_r) * $signed(hann64({l1_n[3:0], 2'b10}))) >>> 15;
                        w_i = ($signed(l1_i) * $signed(hann64({l1_n[3:0], 2'b10}))) >>> 15;
                    end else begin
                        w_r = {{18{l1_r[23]}}, l1_r};
                        w_i = {{18{l1_i[23]}}, l1_i};
                    end
                    // Scale up by 8 before 4-stage (/16) Doppler FFT to keep faint targets crisp
                    fft_re[bitrev4(l1_n[3:0])] <= w_r[20:0] <<< 3;
                    fft_im[bitrev4(l1_n[3:0])] <= w_i[20:0] <<< 3;
                end
            end

            // butterfly, step 2: operands
            b2_v <= b1_v;
            if (b1_v) begin
                b2_a <= b1_a; b2_b <= b1_b; b2_wr <= b1_wr; b2_wi <= b1_wi;
                b2_ar <= fft_re[b1_a]; b2_ai <= fft_im[b1_a];
                b2_br <= fft_re[b1_b]; b2_bi <= fft_im[b1_b];
            end
            // step 3: products
            b3_v <= b2_v;
            if (b2_v) begin
                b3_a <= b2_a; b3_b <= b2_b; b3_ar <= b2_ar; b3_ai <= b2_ai;
                b3_p1 <= $signed(b2_br) * $signed(b2_wr);
                b3_p2 <= $signed(b2_bi) * $signed(b2_wi);
                b3_p3 <= $signed(b2_br) * $signed(b2_wi);
                b3_p4 <= $signed(b2_bi) * $signed(b2_wr);
            end
            // step 4: sums, scaling, write back (divide by 2 each stage prevents growth)
            if (b3_v) begin : blk_bw
                reg signed [41:0] t_r, t_i;
                reg signed [23:0] bw_r, bw_i;
                t_r  = (b3_p1 - b3_p2) >>> 14;
                t_i  = (b3_p3 + b3_p4) >>> 14;
                bw_r = t_r[23:0];
                bw_i = t_i[23:0];
                fft_re[b3_a] <= (b3_ar + bw_r) >>> 1;
                fft_im[b3_a] <= (b3_ai + bw_i) >>> 1;
                fft_re[b3_b] <= (b3_ar - bw_r) >>> 1;
                fft_im[b3_b] <= (b3_ai - bw_i) >>> 1;
            end

            // store, step 2: write the range bin to the corner-turn memory
            // (the write itself is in the corner-turn memory block above)

            // power, step 2: squares; step 3: write
            q2_v <= q1_v;
            if (q1_v) begin
                q2_addr <= q1_addr;
                q2_rr   <= $signed(q1_r) * $signed(q1_r);
                q2_ii   <= $signed(q1_i) * $signed(q1_i);
            end

            // CFAR: c2 reads, c3 partial sums, c4 mean, c5 threshold, then the decision and the outputs
            c2_v <= c1_v;
            if (c1_v) begin
                c2_r <= c1_r; c2_d <= c1_d; c2_last <= c1_last;
            end
            c3_v <= c2_v;
            if (c2_v) begin
                c3_cut <= c2_p[8];
                c3_s0  <= {4'b0, c2_p[0]} + {4'b0, c2_p[1]} + {4'b0, c2_p[2]} + {4'b0, c2_p[3]};
                c3_s1  <= {4'b0, c2_p[4]} + {4'b0, c2_p[5]} + {4'b0, c2_p[6]} + {4'b0, c2_p[7]};
                c3_r <= c2_r; c3_d <= c2_d; c3_last <= c2_last;
            end
            c4_v <= c3_v;
            if (c3_v) begin : blk_mean
                reg [35:0] train_sum;
                train_sum = c3_s0 + c3_s1;
                c4_mean <= train_sum >> 3;
                c4_cut  <= c3_cut;
                c4_r <= c3_r; c4_d <= c3_d; c4_last <= c3_last;
            end
            c5_v <= c4_v;
            if (c4_v) begin
                c5_thr <= (c4_mean * {20'b0, cfg_cfar_alpha_q8}) >> 8;
                c5_cut <= c4_cut;
                c5_r <= c4_r; c5_d <= c4_d; c5_last <= c4_last;
            end
            if (c5_v) begin : blk_cfar
                reg is_det;
                is_det = ({4'b0, c5_cut} > c5_thr) && (c5_cut >= cfg_cfar_min_pwr);
                rd_out_valid <= 1'b1;
                rd_out_rbin  <= c5_r;
                rd_out_dbin  <= c5_d;
                rd_out_pwr   <= c5_cut;
                rd_out_det   <= is_det;
                if (is_det)
                    cpi_det_cnt <= cpi_det_cnt + 16'd1;
                if (c5_cut > peak_pwr) begin
                    peak_pwr  <= c5_cut;
                    peak_rbin <= c5_r;
                    peak_dbin <= c5_d;
                end
                if (c5_last)
                    cpi_done_pulse <= 1'b1;
            end

            // ================= issue =================
            case (state)
                ST_LOAD_CHIRP: begin
                    // Capture full 1024-sample CPI continuously into cpi_re/im without dropping beats
                    if (in_valid && cpi_sync_start) begin
                        // the marked sample is chirp 0, sample 0
                        chirp_idx <= 4'd0;
                        samp_idx  <= 6'd1;
                        synced    <= 1'b1;
                    end else if (in_valid && (synced || !cfg_sync_en)) begin
                        if (samp_idx == 6'd63) begin
                            samp_idx <= 6'd0;
                            if (chirp_idx == 4'd15) begin
                                chirp_idx <= 4'd0;
                                synced    <= 1'b0;      // the next CPI starts at the next mark
                                state     <= ST_RFFT_LOAD;
                            end else begin
                                chirp_idx <= chirp_idx + 4'd1;
                            end
                        end else begin
                            samp_idx <= samp_idx + 6'd1;
                        end
                    end
                end

                ST_RFFT_LOAD: begin
                    l1_v   <= 1'b1;
                    l1_dop <= 1'b0;
                    l1_n   <= samp_idx;
                    if (samp_idx == 6'd63) begin
                        samp_idx   <= 6'd0;
                        bfly_stage <= 3'd0;
                        bfly_idx   <= 5'd0;
                        wait_cnt   <= 3'd1;
                        next_state <= ST_RFFT_BFLY;
                        state      <= ST_WAIT;
                    end else begin
                        samp_idx <= samp_idx + 6'd1;
                    end
                end

                ST_RFFT_BFLY, ST_DFFT_BFLY: begin
                    // range: 6 stages (0..5), 32 butterflies per stage; Doppler: 4 stages, 8 per stage
                    b1_v  <= 1'b1;
                    b1_a  <= bi_a;
                    b1_b  <= bi_b;
                    b1_wr <= tw64_cos(bi_k);
                    b1_wi <= tw64_sin_neg(bi_k);
                    if ((state == ST_RFFT_BFLY) ? (bfly_idx == 5'd31) : (bfly_idx[2:0] == 3'd7)) begin
                        bfly_idx <= 5'd0;
                        wait_cnt <= 3'd3;                   // the stage's last write lands 3 clocks later
                        state    <= ST_WAIT;
                        if (bfly_stage == ((state == ST_RFFT_BFLY) ? 3'd5 : 3'd3)) begin
                            samp_idx   <= 6'd0;
                            scan_d     <= 4'd0;
                            next_state <= (state == ST_RFFT_BFLY) ? ST_RFFT_STORE : ST_DFFT_POWER;
                        end else begin
                            bfly_stage <= bfly_stage + 3'd1;
                            next_state <= state;
                        end
                    end else begin
                        bfly_idx <= bfly_idx + 5'd1;
                    end
                end

                ST_RFFT_STORE: begin
                    // Write chirp m's 64 range bins into CPI corner-turn BRAM
                    s1_v    <= 1'b1;
                    s1_addr <= {chirp_idx, samp_idx};
                    s1_r    <= fft_re[samp_idx];
                    s1_i    <= fft_im[samp_idx];
                    if (samp_idx == 6'd63) begin
                        samp_idx <= 6'd0;
                        wait_cnt <= 3'd1;
                        state    <= ST_WAIT;
                        if (chirp_idx == 4'd15) begin
                            chirp_idx  <= 4'd0;
                            scan_r     <= 6'd0;
                            scan_d     <= 4'd0;
                            next_state <= ST_DFFT_LOAD;
                        end else begin
                            chirp_idx  <= chirp_idx + 4'd1;
                            next_state <= ST_RFFT_LOAD;
                        end
                    end else begin
                        samp_idx <= samp_idx + 6'd1;
                    end
                end

                ST_DFFT_LOAD: begin
                    // Read 16 slow-time chirps for range bin scan_r into fft_re/im[0..15] bit-reversed
                    l1_v   <= 1'b1;
                    l1_dop <= 1'b1;
                    l1_n   <= {2'b00, scan_d};
                    if (scan_d == 4'd15) begin
                        scan_d     <= 4'd0;
                        bfly_stage <= 3'd0;
                        bfly_idx   <= 5'd0;
                        wait_cnt   <= 3'd1;
                        next_state <= ST_DFFT_BFLY;
                        state      <= ST_WAIT;
                    end else begin
                        scan_d <= scan_d + 4'd1;
                    end
                end

                ST_DFFT_POWER: begin
                    q1_v    <= 1'b1;
                    q1_addr <= {scan_r, scan_d};
                    q1_r    <= fft_re[scan_d];
                    q1_i    <= fft_im[scan_d];
                    if (scan_d == 4'd15) begin
                        scan_d <= 4'd0;
                        if (scan_r == 6'd63) begin
                            scan_r      <= 6'd0;
                            scan_d      <= 4'd0;
                            cpi_det_cnt <= 16'd0;
                            peak_pwr    <= 32'd0;
                            peak_rbin   <= 6'd0;
                            peak_dbin   <= 4'd0;
                            wait_cnt    <= 3'd2;            // the last power lands 2 clocks later
                            next_state  <= ST_CFAR_SCAN;
                            state       <= ST_WAIT;
                        end else begin
                            scan_r <= scan_r + 6'd1;
                            state  <= ST_DFFT_LOAD;         // its first write is 2 clocks away: after these reads
                        end
                    end else begin
                        scan_d <= scan_d + 4'd1;
                    end
                end

                ST_CFAR_SCAN: begin
                    // Range CA-CFAR: guard = 1 each side, train = 4 each side (8 cells mod 64)
                    c1_v     <= 1'b1;
                    c1_r     <= scan_r;
                    c1_d     <= scan_d;
                    c1_last  <= (scan_d == 4'd15) && (scan_r == 6'd63);
                    c1_ad[0] <= {(scan_r - 6'd5), scan_d};
                    c1_ad[1] <= {(scan_r - 6'd4), scan_d};
                    c1_ad[2] <= {(scan_r - 6'd3), scan_d};
                    c1_ad[3] <= {(scan_r - 6'd2), scan_d};
                    c1_ad[4] <= {(scan_r + 6'd2), scan_d};
                    c1_ad[5] <= {(scan_r + 6'd3), scan_d};
                    c1_ad[6] <= {(scan_r + 6'd4), scan_d};
                    c1_ad[7] <= {(scan_r + 6'd5), scan_d};
                    c1_ad[8] <= {scan_r, scan_d};
                    if (scan_d == 4'd15) begin
                        scan_d <= 4'd0;
                        if (scan_r == 6'd63) begin
                            scan_r     <= 6'd0;
                            wait_cnt   <= 3'd5;             // back in ST_LOAD_CHIRP with cpi_done_pulse
                            next_state <= ST_LOAD_CHIRP;
                            state      <= ST_WAIT;
                        end else begin
                            scan_r <= scan_r + 6'd1;
                        end
                    end else begin
                        scan_d <= scan_d + 4'd1;
                    end
                end

                ST_WAIT: begin
                    if (wait_cnt <= 3'd1)
                        state <= next_state;
                    wait_cnt <= wait_cnt - 3'd1;
                end

                default: state <= ST_LOAD_CHIRP;
            endcase
        end
    end
endmodule
