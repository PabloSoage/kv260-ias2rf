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

    localparam [2:0] ST_LOAD_CHIRP  = 3'd0,
                     ST_RFFT_BFLY   = 3'd1,
                     ST_RFFT_STORE  = 3'd2,
                     ST_DFFT_LOAD   = 3'd3,
                     ST_DFFT_BFLY   = 3'd4,
                     ST_DFFT_POWER  = 3'd5,
                     ST_CFAR_SCAN   = 3'd6,
                     ST_RFFT_LOAD   = 3'd7;

    reg [2:0] state;
    reg       synced;
    assign in_ready = (state == ST_LOAD_CHIRP);

    // Scratchpads for 64-pt Range FFT & 16-pt Doppler FFT
    reg signed [23:0] fft_re [0:RANGE_N-1];
    reg signed [23:0] fft_im [0:RANGE_N-1];

    // CPI Corner-Turn Complex Memory (64 x 16 = 1024 entries)
    (* ram_style = "block" *) reg signed [23:0] cpi_re [0:(RANGE_N*DOPPLER_M)-1];
    (* ram_style = "block" *) reg signed [23:0] cpi_im [0:(RANGE_N*DOPPLER_M)-1];
    // Range-Doppler Power Map (64 x 16 = 1024 x 32-bit unsigned)
    (* ram_style = "block" *) reg [31:0] rd_pwr [0:(RANGE_N*DOPPLER_M)-1];

    reg [5:0]  samp_idx;
    reg [3:0]  chirp_idx;
    reg [2:0]  bfly_stage;
    reg [4:0]  bfly_idx;
    reg [5:0]  scan_r;
    reg [3:0]  scan_d;

    integer ii;

    always @(posedge clk) begin
        if (rst) begin
            state          <= ST_LOAD_CHIRP;
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
        end else begin
            rd_out_valid   <= 1'b0;
            cpi_done_pulse <= 1'b0;

            case (state)
                ST_LOAD_CHIRP: begin
                    // Capture full 1024-sample CPI continuously into cpi_re/im without dropping beats
                    if (in_valid && cpi_sync_start) begin
                        // the marked sample is chirp 0, sample 0
                        cpi_re[{4'd0, 6'd0}] <= {{8{in_i[15]}}, in_i};
                        cpi_im[{4'd0, 6'd0}] <= {{8{in_q[15]}}, in_q};
                        chirp_idx <= 4'd0;
                        samp_idx  <= 6'd1;
                        synced    <= 1'b1;
                    end else if (in_valid && (synced || !cfg_sync_en)) begin
                        cpi_re[{chirp_idx, samp_idx}] <= {{8{in_i[15]}}, in_i};
                        cpi_im[{chirp_idx, samp_idx}] <= {{8{in_q[15]}}, in_q};
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

                ST_RFFT_LOAD: begin : blk_rld
                    reg signed [23:0] raw_r, raw_i;
                    reg signed [31:0] wi, wq;
                    reg [5:0] dst;
                    dst   = bitrev6(samp_idx);
                    raw_r = cpi_re[{chirp_idx, samp_idx}];
                    raw_i = cpi_im[{chirp_idx, samp_idx}];
                    if (cfg_win_en) begin
                        wi = ($signed(raw_r[15:0]) * $signed(hann64(samp_idx))) >>> 15;
                        wq = ($signed(raw_i[15:0]) * $signed(hann64(samp_idx))) >>> 15;
                    end else begin
                        wi = {{16{raw_r[15]}}, raw_r[15:0]};
                        wq = {{16{raw_i[15]}}, raw_i[15:0]};
                    end
                    fft_re[dst] <= wi[23:0];
                    fft_im[dst] <= wq[23:0];
                    if (samp_idx == 6'd63) begin
                        samp_idx   <= 6'd0;
                        bfly_stage <= 3'd0;
                        bfly_idx   <= 5'd0;
                        state      <= ST_RFFT_BFLY;
                    end else begin
                        samp_idx <= samp_idx + 6'd1;
                    end
                end

                ST_RFFT_BFLY: begin : blk_rfft
                    // 6 stages (0..5), 32 butterflies per stage -> 1 butterfly/clk
                    integer half, group, pos, idx_a, idx_b;
                    reg [4:0] tw_k;
                    reg signed [23:0] a_r, a_i, b_r, b_i;
                    reg signed [15:0] wr, wi;
                    reg signed [41:0] t_r, t_i;
                    reg signed [23:0] bw_r, bw_i;

                    half  = 1 << bfly_stage;
                    group = bfly_idx >> bfly_stage;
                    pos   = bfly_idx & (half - 1);
                    idx_a = (group << (bfly_stage + 1)) + pos;
                    idx_b = idx_a + half;
                    tw_k  = (pos << (5 - bfly_stage));

                    wr = tw64_cos(tw_k);
                    wi = tw64_sin_neg(tw_k);
                    a_r = fft_re[idx_a]; a_i = fft_im[idx_a];
                    b_r = fft_re[idx_b]; b_i = fft_im[idx_b];

                    t_r  = ($signed(b_r) * $signed(wr) - $signed(b_i) * $signed(wi)) >>> 14;
                    t_i  = ($signed(b_r) * $signed(wi) + $signed(b_i) * $signed(wr)) >>> 14;
                    bw_r = t_r[23:0];
                    bw_i = t_i[23:0];

                    // Divide by 2 each stage prevents growth over 6 stages
                    fft_re[idx_a] <= (a_r + bw_r) >>> 1;
                    fft_im[idx_a] <= (a_i + bw_i) >>> 1;
                    fft_re[idx_b] <= (a_r - bw_r) >>> 1;
                    fft_im[idx_b] <= (a_i - bw_i) >>> 1;

                    if (bfly_idx == 5'd31) begin
                        bfly_idx <= 5'd0;
                        if (bfly_stage == 3'd5) begin
                            samp_idx <= 6'd0;
                            state    <= ST_RFFT_STORE;
                        end else begin
                            bfly_stage <= bfly_stage + 3'd1;
                        end
                    end else begin
                        bfly_idx <= bfly_idx + 5'd1;
                    end
                end

                ST_RFFT_STORE: begin
                    // Write chirp m's 64 range bins into CPI corner-turn BRAM
                    cpi_re[{chirp_idx, samp_idx}] <= fft_re[samp_idx];
                    cpi_im[{chirp_idx, samp_idx}] <= fft_im[samp_idx];
                    if (samp_idx == 6'd63) begin
                        samp_idx <= 6'd0;
                        if (chirp_idx == 4'd15) begin
                            chirp_idx   <= 4'd0;
                            scan_r      <= 6'd0;
                            scan_d      <= 4'd0;
                            state       <= ST_DFFT_LOAD;
                        end else begin
                            chirp_idx <= chirp_idx + 4'd1;
                            state     <= ST_RFFT_LOAD;
                        end
                    end else begin
                        samp_idx <= samp_idx + 6'd1;
                    end
                end

                ST_DFFT_LOAD: begin : blk_dld
                    // Read 16 slow-time chirps for range bin scan_r into fft_re/im[0..15] bit-reversed
                    reg [3:0] dst4;
                    reg signed [23:0] raw_r, raw_i;
                    reg signed [41:0] w_r, w_i;
                    dst4  = bitrev4(scan_d);
                    raw_r = cpi_re[{scan_d, scan_r}];
                    raw_i = cpi_im[{scan_d, scan_r}];
                    if (cfg_win_en) begin
                        w_r = ($signed(raw_r) * $signed(hann64({scan_d, 2'b10}))) >>> 15;
                        w_i = ($signed(raw_i) * $signed(hann64({scan_d, 2'b10}))) >>> 15;
                    end else begin
                        w_r = {{18{raw_r[23]}}, raw_r};
                        w_i = {{18{raw_i[23]}}, raw_i};
                    end
                    // Scale up by 8 before 4-stage (/16) Doppler FFT to keep faint targets crisp
                    fft_re[dst4] <= w_r[20:0] <<< 3;
                    fft_im[dst4] <= w_i[20:0] <<< 3;

                    if (scan_d == 4'd15) begin
                        scan_d     <= 4'd0;
                        bfly_stage <= 3'd0;
                        bfly_idx   <= 5'd0;
                        state      <= ST_DFFT_BFLY;
                    end else begin
                        scan_d <= scan_d + 4'd1;
                    end
                end

                ST_DFFT_BFLY: begin : blk_dfft
                    // 4 stages (0..3), 8 butterflies per stage (16-pt FFT)
                    integer half, group, pos, idx_a, idx_b;
                    reg [4:0] tw_k;
                    reg signed [23:0] a_r, a_i, b_r, b_i;
                    reg signed [15:0] wr, wi;
                    reg signed [41:0] t_r, t_i;
                    reg signed [23:0] bw_r, bw_i;

                    half  = 1 << bfly_stage;
                    group = bfly_idx[2:0] >> bfly_stage;
                    pos   = bfly_idx[2:0] & (half - 1);
                    idx_a = (group << (bfly_stage + 1)) + pos;
                    idx_b = idx_a + half;
                    tw_k  = (pos << (5 - bfly_stage)); // scale 16-pt twiddle idx onto 64-pt table (pos * 4 >> stage)

                    wr = tw64_cos(tw_k);
                    wi = tw64_sin_neg(tw_k);
                    a_r = fft_re[idx_a]; a_i = fft_im[idx_a];
                    b_r = fft_re[idx_b]; b_i = fft_im[idx_b];

                    t_r  = ($signed(b_r) * $signed(wr) - $signed(b_i) * $signed(wi)) >>> 14;
                    t_i  = ($signed(b_r) * $signed(wi) + $signed(b_i) * $signed(wr)) >>> 14;
                    bw_r = t_r[23:0];
                    bw_i = t_i[23:0];

                    fft_re[idx_a] <= (a_r + bw_r) >>> 1;
                    fft_im[idx_a] <= (a_i + bw_i) >>> 1;
                    fft_re[idx_b] <= (a_r - bw_r) >>> 1;
                    fft_im[idx_b] <= (a_i - bw_i) >>> 1;

                    if (bfly_idx[2:0] == 3'd7) begin
                        bfly_idx <= 5'd0;
                        if (bfly_stage == 3'd3) begin
                            scan_d <= 4'd0;
                            state  <= ST_DFFT_POWER;
                        end else begin
                            bfly_stage <= bfly_stage + 3'd1;
                        end
                    end else begin
                        bfly_idx <= bfly_idx + 5'd1;
                    end
                end

                ST_DFFT_POWER: begin : blk_pwr
                    reg signed [23:0] zr, zi;
                    reg [47:0] psum;
                    zr = fft_re[scan_d];
                    zi = fft_im[scan_d];
                    psum = ($signed(zr) * $signed(zr)) + ($signed(zi) * $signed(zi));
                    rd_pwr[{scan_r, scan_d}] <= psum[31:0];

                    if (scan_d == 4'd15) begin
                        scan_d <= 4'd0;
                        if (scan_r == 6'd63) begin
                            scan_r      <= 6'd0;
                            scan_d      <= 4'd0;
                            cpi_det_cnt <= 16'd0;
                            peak_pwr    <= 32'd0;
                            peak_rbin   <= 6'd0;
                            peak_dbin   <= 4'd0;
                            state       <= ST_CFAR_SCAN;
                        end else begin
                            scan_r <= scan_r + 6'd1;
                            state  <= ST_DFFT_LOAD;
                        end
                    end else begin
                        scan_d <= scan_d + 4'd1;
                    end
                end

                ST_CFAR_SCAN: begin : blk_cfar
                    // Range CA-CFAR: guard = 1 each side, train = 4 each side (8 cells mod 64)
                    reg [31:0] cut_p;
                    reg [35:0] train_sum, mean_p, thr_p;
                    reg        is_det;
                    cut_p = rd_pwr[{scan_r, scan_d}];
                    train_sum = {4'b0, rd_pwr[{(scan_r - 6'd5), scan_d}]}
                              + {4'b0, rd_pwr[{(scan_r - 6'd4), scan_d}]}
                              + {4'b0, rd_pwr[{(scan_r - 6'd3), scan_d}]}
                              + {4'b0, rd_pwr[{(scan_r - 6'd2), scan_d}]}
                              + {4'b0, rd_pwr[{(scan_r + 6'd2), scan_d}]}
                              + {4'b0, rd_pwr[{(scan_r + 6'd3), scan_d}]}
                              + {4'b0, rd_pwr[{(scan_r + 6'd4), scan_d}]}
                              + {4'b0, rd_pwr[{(scan_r + 6'd5), scan_d}]};
                    mean_p = train_sum >> 3;
                    thr_p  = (mean_p * {20'b0, cfg_cfar_alpha_q8}) >> 8;
                    is_det = ({4'b0, cut_p} > thr_p) && (cut_p >= cfg_cfar_min_pwr);

                    rd_out_valid <= 1'b1;
                    rd_out_rbin  <= scan_r;
                    rd_out_dbin  <= scan_d;
                    rd_out_pwr   <= cut_p;
                    rd_out_det   <= is_det;
                    if (is_det)
                        cpi_det_cnt <= cpi_det_cnt + 16'd1;
                    if (cut_p > peak_pwr) begin
                        peak_pwr  <= cut_p;
                        peak_rbin <= scan_r;
                        peak_dbin <= scan_d;
                    end

                    if (scan_d == 4'd15) begin
                        scan_d <= 4'd0;
                        if (scan_r == 6'd63) begin
                            scan_r         <= 6'd0;
                            cpi_done_pulse <= 1'b1;
                            state          <= ST_LOAD_CHIRP;
                        end else begin
                            scan_r <= scan_r + 6'd1;
                        end
                    end else begin
                        scan_d <= scan_d + 4'd1;
                    end
                end

                default: state <= ST_LOAD_CHIRP;
            endcase
        end
    end
endmodule
