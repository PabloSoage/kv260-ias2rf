// SPDX-License-Identifier: Apache-2.0
// Kria PL Programmable Sub-DDC Channelizer & Multi-Mode Demodulator
//
// Placed in Kria PL (XCK26) to leave Artix-7 free DSP48E1 budget untouched (only 10/120 free).
// Accepts 16-bit complex I/Q stream (from u_ddc 8'h01 or u_sdr_ddc 8'h05 via IAS1) and implements:
//   1. Sub-DDC Complex NCO + 4-DSP Mixer -> Decimating 3-Stage CIC (N=3, R=1..2048)
//   2. 31-tap Symmetric Decimating Channel Selectivity FIR (adjacent-channel suppression)
//   3. Multi-Mode Demodulator (cfg_mode[2:0]):
//        0 = AM Envelope (kria_cordic magnitude + DC block + audio LPF)
//        1 = USB (31-tap antisymmetric Hilbert phasing: I_dly - H{Q})
//        2 = LSB (31-tap antisymmetric Hilbert phasing: I_dly + H{Q})
//        3 = NBFM (kria_cordic phase diff + de-emphasis + CTCSS Goertzel tone detector)
//        4 = WBFM Stereo + 19 kHz Pilot Type-II PLL + 38 kHz L-R + 57 kHz RDS BPSK demod

`timescale 1ns/1ps

module kria_channel_rx (
    input  wire               clk,
    input  wire               rst,

    // Complex I/Q Input Stream (from m_axis_rx demux)
    input  wire               in_valid,
    input  wire signed [15:0] in_i,
    input  wire signed [15:0] in_q,

    // Configuration (pl_clk_100m domain)
    input  wire [2:0]         cfg_mode,          // 0=AM, 1=USB, 2=LSB, 3=NBFM, 4=WBFM
    input  wire [31:0]        cfg_nco_ftw,       // Sub-DDC NCO FTW wrt input sample rate (0 = bypass mixer)
    input  wire [15:0]        cfg_cic_decim,     // CIC decimation R >= 1 (1 = bypass CIC)
    input  wire [5:0]         cfg_cic_shift,     // Right-shift for the CIC's gain normalization (R^N)
    input  wire               cfg_cic_n5,        // 1 = five CIC stages (deeper alias rejection), 0 = three
    input  wire [7:0]         cfg_fir_decim,     // Post-CIC FIR decimation >= 1 (1 = decimate by 1, e.g. 2 or 4)
    input  wire [15:0]        cfg_deemph_alpha,  // Q15 IIR LPF alpha: y = y + alpha*(x - y)
    input  wire [31:0]        cfg_pilot_ftw,     // 19 kHz nominal FTW at post-FIR Fs_ch (2^32 * 19e3 / Fs_ch)
    input  wire signed [15:0] cfg_ctcss_coeff,   // Goertzel Q14 2*cos(2*pi*f_tone/Fs_ch)
    input  wire [15:0]        cfg_ctcss_n,       // Goertzel block length N samples
    input  wire [31:0]        cfg_ctcss_thresh,  // CTCSS detection power threshold
    input  wire [15:0]        cfg_rds_sym_samps, // Post-FIR samples per RDS bit, Q8.8 (250 kS/s: 210.53 -> 0xD287)

    // Outputs (at channel sample rate Fs_ch)
    output reg                audio_valid,
    output reg  signed [15:0] audio_l,           // AM / USB / LSB / NBFM / WBFM Left (or Mono before matrix)
    output reg  signed [15:0] audio_r,           // WBFM Right (mirrors audio_l in mono modes)
    output reg  signed [15:0] audio_mono,        // Raw Mono L+R in WBFM mode
    output reg                pilot_locked,
    output reg                ctcss_valid,
    output reg                ctcss_detected,
    output reg  [31:0]        ctcss_power,
    output reg                rds_bit_valid,
    output reg                rds_bit
);
    // -------------------------------------------------------------------------
    // 1. Sub-DDC Complex NCO + Mixer
    // -------------------------------------------------------------------------
    function automatic signed [15:0] sin_qwave;
        input [7:0] idx;
        begin
            case (idx)
                8'd0:   sin_qwave = 16'sd0;     8'd1:   sin_qwave = 16'sd402;
                8'd2:   sin_qwave = 16'sd804;   8'd3:   sin_qwave = 16'sd1206;
                8'd4:   sin_qwave = 16'sd1608;  8'd5:   sin_qwave = 16'sd2009;
                8'd6:   sin_qwave = 16'sd2410;  8'd7:   sin_qwave = 16'sd2811;
                8'd8:   sin_qwave = 16'sd3212;  8'd9:   sin_qwave = 16'sd3612;
                8'd10:  sin_qwave = 16'sd4011;  8'd11:  sin_qwave = 16'sd4410;
                8'd12:  sin_qwave = 16'sd4808;  8'd13:  sin_qwave = 16'sd5205;
                8'd14:  sin_qwave = 16'sd5602;  8'd15:  sin_qwave = 16'sd5998;
                8'd16:  sin_qwave = 16'sd6393;  8'd17:  sin_qwave = 16'sd6786;
                8'd18:  sin_qwave = 16'sd7179;  8'd19:  sin_qwave = 16'sd7571;
                8'd20:  sin_qwave = 16'sd7962;  8'd21:  sin_qwave = 16'sd8351;
                8'd22:  sin_qwave = 16'sd8739;  8'd23:  sin_qwave = 16'sd9126;
                8'd24:  sin_qwave = 16'sd9512;  8'd25:  sin_qwave = 16'sd9896;
                8'd26:  sin_qwave = 16'sd10278; 8'd27:  sin_qwave = 16'sd10659;
                8'd28:  sin_qwave = 16'sd11039; 8'd29:  sin_qwave = 16'sd11417;
                8'd30:  sin_qwave = 16'sd11793; 8'd31:  sin_qwave = 16'sd12167;
                8'd32:  sin_qwave = 16'sd12539; 8'd33:  sin_qwave = 16'sd12910;
                8'd34:  sin_qwave = 16'sd13279; 8'd35:  sin_qwave = 16'sd13645;
                8'd36:  sin_qwave = 16'sd14010; 8'd37:  sin_qwave = 16'sd14372;
                8'd38:  sin_qwave = 16'sd14732; 8'd39:  sin_qwave = 16'sd15090;
                8'd40:  sin_qwave = 16'sd15446; 8'd41:  sin_qwave = 16'sd15800;
                8'd42:  sin_qwave = 16'sd16151; 8'd43:  sin_qwave = 16'sd16499;
                8'd44:  sin_qwave = 16'sd16846; 8'd45:  sin_qwave = 16'sd17189;
                8'd46:  sin_qwave = 16'sd17530; 8'd47:  sin_qwave = 16'sd17869;
                8'd48:  sin_qwave = 16'sd18204; 8'd49:  sin_qwave = 16'sd18537;
                8'd50:  sin_qwave = 16'sd18868; 8'd51:  sin_qwave = 16'sd19195;
                8'd52:  sin_qwave = 16'sd19519; 8'd53:  sin_qwave = 16'sd19841;
                8'd54:  sin_qwave = 16'sd20159; 8'd55:  sin_qwave = 16'sd20475;
                8'd56:  sin_qwave = 16'sd20787; 8'd57:  sin_qwave = 16'sd21096;
                8'd58:  sin_qwave = 16'sd21403; 8'd59:  sin_qwave = 16'sd21705;
                8'd60:  sin_qwave = 16'sd22005; 8'd61:  sin_qwave = 16'sd22301;
                8'd62:  sin_qwave = 16'sd22594; 8'd63:  sin_qwave = 16'sd22884;
                8'd64:  sin_qwave = 16'sd23170; 8'd65:  sin_qwave = 16'sd23452;
                8'd66:  sin_qwave = 16'sd23731; 8'd67:  sin_qwave = 16'sd24007;
                8'd68:  sin_qwave = 16'sd24279; 8'd69:  sin_qwave = 16'sd24547;
                8'd70:  sin_qwave = 16'sd24811; 8'd71:  sin_qwave = 16'sd25072;
                8'd72:  sin_qwave = 16'sd25329; 8'd73:  sin_qwave = 16'sd25582;
                8'd74:  sin_qwave = 16'sd25832; 8'd75:  sin_qwave = 16'sd26077;
                8'd76:  sin_qwave = 16'sd26319; 8'd77:  sin_qwave = 16'sd26556;
                8'd78:  sin_qwave = 16'sd26790; 8'd79:  sin_qwave = 16'sd27019;
                8'd80:  sin_qwave = 16'sd27245; 8'd81:  sin_qwave = 16'sd27466;
                8'd82:  sin_qwave = 16'sd27683; 8'd83:  sin_qwave = 16'sd27896;
                8'd84:  sin_qwave = 16'sd28105; 8'd85:  sin_qwave = 16'sd28310;
                8'd86:  sin_qwave = 16'sd28510; 8'd87:  sin_qwave = 16'sd28706;
                8'd88:  sin_qwave = 16'sd28898; 8'd89:  sin_qwave = 16'sd29085;
                8'd90:  sin_qwave = 16'sd29268; 8'd91:  sin_qwave = 16'sd29447;
                8'd92:  sin_qwave = 16'sd29621; 8'd93:  sin_qwave = 16'sd29791;
                8'd94:  sin_qwave = 16'sd29956; 8'd95:  sin_qwave = 16'sd30117;
                8'd96:  sin_qwave = 16'sd30273; 8'd97:  sin_qwave = 16'sd30424;
                8'd98:  sin_qwave = 16'sd30571; 8'd99:  sin_qwave = 16'sd30714;
                8'd100: sin_qwave = 16'sd30852; 8'd101: sin_qwave = 16'sd30985;
                8'd102: sin_qwave = 16'sd31113; 8'd103: sin_qwave = 16'sd31237;
                8'd104: sin_qwave = 16'sd31356; 8'd105: sin_qwave = 16'sd31470;
                8'd106: sin_qwave = 16'sd31580; 8'd107: sin_qwave = 16'sd31685;
                8'd108: sin_qwave = 16'sd31785; 8'd109: sin_qwave = 16'sd31880;
                8'd110: sin_qwave = 16'sd31971; 8'd111: sin_qwave = 16'sd32057;
                8'd112: sin_qwave = 16'sd32137; 8'd113: sin_qwave = 16'sd32213;
                8'd114: sin_qwave = 16'sd32285; 8'd115: sin_qwave = 16'sd32351;
                8'd116: sin_qwave = 16'sd32412; 8'd117: sin_qwave = 16'sd32469;
                8'd118: sin_qwave = 16'sd32521; 8'd119: sin_qwave = 16'sd32567;
                8'd120: sin_qwave = 16'sd32609; 8'd121: sin_qwave = 16'sd32646;
                8'd122: sin_qwave = 16'sd32678; 8'd123: sin_qwave = 16'sd32705;
                8'd124: sin_qwave = 16'sd32728; 8'd125: sin_qwave = 16'sd32745;
                8'd126: sin_qwave = 16'sd32757; 8'd127: sin_qwave = 16'sd32765;
                default: sin_qwave = 16'sd32767;
            endcase
        end
    endfunction

    function automatic signed [15:0] lut_sin;
        input [31:0] ph;
        reg [1:0] q;
        reg [6:0] idx;
        reg [7:0] addr;
        reg signed [15:0] raw;
        begin
            q    = ph[31:30];
            idx  = ph[29:23];
            addr = q[0] ? (8'd128 - {1'b0, idx}) : {1'b0, idx};
            raw  = sin_qwave(addr);
            lut_sin = q[1] ? -raw : raw;
        end
    endfunction

    function automatic signed [15:0] lut_cos;
        input [31:0] ph;
        begin
            lut_cos = lut_sin(ph + 32'h4000_0000);
        end
    endfunction

    // The mixer's LO: the same table (512 points per turn) linearly interpolated on the next 8 phase bits, as in
    // kria_tx_mod. The bare table is 9 bits of phase: with a small offset (the Artix NCO's 24-bit residual, a few
    // Hz) its index steps every few thousand samples, and the phase sawtooth puts -50 dBc sidebands on every
    // strong signal in the stream (an airband neighbour 25 dB up cost 7 dB of SINAD). Interpolated, the worst
    // spur is below -90 dBc. The pilot PLL keeps the bare table (its own loop tracks the steps).
    function automatic signed [15:0] lut_sin_i;
        input [31:0] ph;
        reg signed [15:0] v0, v1;
        reg signed [25:0] d;
        begin
`ifdef MUTATE_MIX_NCO_9BIT
            lut_sin_i = lut_sin(ph);
`else
            v0 = lut_sin({ph[31:23], 23'd0});
            v1 = lut_sin({ph[31:23] + 9'd1, 23'd0});
            d  = ($signed({v1[15], v1}) - $signed({v0[15], v0})) * $signed({1'b0, ph[22:15]});
            lut_sin_i = v0 + (d >>> 8);
`endif
        end
    endfunction

    reg [31:0] mix_phase;
    reg        mix_valid;
    reg signed [15:0] mix_i, mix_q;
    reg signed [31:0] p_ic, p_qs, p_is, p_qc;
    // lo_c/lo_s hold cos/sin of mix_phase: computed when the phase advances, so the interpolation's multiply is
    // not in series with the mixer's (input samples may arrive on consecutive clocks)
    reg signed [15:0] lo_c, lo_s;
    wire [31:0] mix_phase_nx = mix_phase + cfg_nco_ftw;

    always @(posedge clk) begin
        if (rst) begin
            mix_phase <= 32'd0;
            mix_valid <= 1'b0;
            mix_i     <= 16'sd0;
            mix_q     <= 16'sd0;
            lo_c      <= 16'sd32767;
            lo_s      <= 16'sd0;
        end else begin
            mix_valid <= in_valid;
            if (in_valid) begin
                if (cfg_nco_ftw == 32'd0) begin
                    mix_i <= in_i;
                    mix_q <= in_q;
                end else begin
                    // Downconvert: (I + jQ) * (cos - j*sin) = (I*cos + Q*sin) + j*(Q*cos - I*sin)
                    p_ic  = $signed(in_i) * $signed(lo_c);
                    p_qs  = $signed(in_q) * $signed(lo_s);
                    p_qc  = $signed(in_q) * $signed(lo_c);
                    p_is  = $signed(in_i) * $signed(lo_s);
                    // rounded: a plain >>> 15 is a -0.5 LSB bias on every input sample, which the CIC's
                    // R^3 / 2^shift gain turns into a DC offset as large as the channel noise (NBFM lost 6.5 dB)
`ifdef MUTATE_MIX_TRUNCATE
                    mix_i <= (p_ic + p_qs) >>> 15;
                    mix_q <= (p_qc - p_is) >>> 15;
`else
                    mix_i <= (p_ic + p_qs + 32'sd16384) >>> 15;
                    mix_q <= (p_qc - p_is + 32'sd16384) >>> 15;
`endif
                    mix_phase <= mix_phase_nx;
                    lo_c      <= lut_sin_i(mix_phase_nx + 32'h4000_0000);
                    lo_s      <= lut_sin_i(mix_phase_nx);
                end
            end
        end
    end

    // -------------------------------------------------------------------------
    // 2. Decimating CIC, 3 or 5 stages (R = cfg_cic_decim)
    //    Three stages leave the folding bands next to each multiple of the output rate barely attenuated: an
    //    airband AM neighbour 25 kHz away at 24 kS/s has sidebands within 3 kHz of the first null, where three
    //    stages give only -59 dB (a +35 dB neighbour cost 5 dB of SINAD). Five stages give -98 dB there, for
    //    0.4 dB more droop at the channel edge. The integrators are shared (72 bits, enough for R^5 = 2^50 at
    //    R = 1040 plus the 16-bit input); the three-stage combs work modulo 2^48 on the third integrator.
    // -------------------------------------------------------------------------
    reg signed [71:0] cic_i1_i, cic_i2_i, cic_i3_i, cic_i4_i, cic_i5_i;
    reg signed [71:0] cic_i1_q, cic_i2_q, cic_i3_q, cic_i4_q, cic_i5_q;
    reg signed [47:0] cic_d1_i, cic_d2_i, cic_d3_i;
    reg signed [47:0] cic_d1_q, cic_d2_q, cic_d3_q;
    reg signed [71:0] cic_e1_i, cic_e2_i, cic_e3_i, cic_e4_i, cic_e5_i;
    reg signed [71:0] cic_e1_q, cic_e2_q, cic_e3_q, cic_e4_q, cic_e5_q;
    reg [15:0]        cic_cnt;
    reg               cic_out_valid;
    reg signed [15:0] cic_out_i, cic_out_q;
    reg signed [47:0] c1_i, c2_i, c3_i, c1_q, c2_q, c3_q, sc_i, sc_q;
    reg signed [71:0] f1_i, f2_i, f3_i, f4_i, f5_i, f1_q, f2_q, f3_q, f4_q, f5_q, sf_i, sf_q;

    function automatic signed [15:0] sat16_72;
        input signed [71:0] v;
        begin
            if (v > 72'sd32767)       sat16_72 = 16'sd32767;
            else if (v < -72'sd32768) sat16_72 = -16'sd32768;
            else                      sat16_72 = v[15:0];
        end
    endfunction

    function automatic signed [15:0] sat16_48;
        input signed [47:0] v;
        begin
            if (v > 48'sd32767)       sat16_48 = 16'sd32767;
            else if (v < -48'sd32768) sat16_48 = -16'sd32768;
            else                      sat16_48 = v[15:0];
        end
    endfunction

    always @(posedge clk) begin
        if (rst) begin
            cic_i1_i <= 72'sd0; cic_i2_i <= 72'sd0; cic_i3_i <= 72'sd0; cic_i4_i <= 72'sd0; cic_i5_i <= 72'sd0;
            cic_i1_q <= 72'sd0; cic_i2_q <= 72'sd0; cic_i3_q <= 72'sd0; cic_i4_q <= 72'sd0; cic_i5_q <= 72'sd0;
            cic_d1_i <= 48'sd0; cic_d2_i <= 48'sd0; cic_d3_i <= 48'sd0;
            cic_d1_q <= 48'sd0; cic_d2_q <= 48'sd0; cic_d3_q <= 48'sd0;
            cic_e1_i <= 72'sd0; cic_e2_i <= 72'sd0; cic_e3_i <= 72'sd0; cic_e4_i <= 72'sd0; cic_e5_i <= 72'sd0;
            cic_e1_q <= 72'sd0; cic_e2_q <= 72'sd0; cic_e3_q <= 72'sd0; cic_e4_q <= 72'sd0; cic_e5_q <= 72'sd0;
            cic_cnt       <= 16'd0;
            cic_out_valid <= 1'b0;
            cic_out_i     <= 16'sd0;
            cic_out_q     <= 16'sd0;
        end else begin
            cic_out_valid <= 1'b0;
            if (mix_valid) begin
                if (cfg_cic_decim <= 16'd1) begin
                    cic_out_valid <= 1'b1;
                    cic_out_i     <= mix_i;
                    cic_out_q     <= mix_q;
                end else begin
                    cic_i1_i <= cic_i1_i + {{56{mix_i[15]}}, mix_i};
                    cic_i2_i <= cic_i2_i + cic_i1_i;
                    cic_i3_i <= cic_i3_i + cic_i2_i;
                    cic_i4_i <= cic_i4_i + cic_i3_i;
                    cic_i5_i <= cic_i5_i + cic_i4_i;

                    cic_i1_q <= cic_i1_q + {{56{mix_q[15]}}, mix_q};
                    cic_i2_q <= cic_i2_q + cic_i1_q;
                    cic_i3_q <= cic_i3_q + cic_i2_q;
                    cic_i4_q <= cic_i4_q + cic_i3_q;
                    cic_i5_q <= cic_i5_q + cic_i4_q;

                    if (cic_cnt >= (cfg_cic_decim - 16'd1)) begin
                        cic_cnt <= 16'd0;
                        c1_i     = cic_i3_i[47:0] - cic_d1_i; cic_d1_i <= cic_i3_i[47:0];
                        c2_i     = c1_i     - cic_d2_i; cic_d2_i <= c1_i;
                        c3_i     = c2_i     - cic_d3_i; cic_d3_i <= c2_i;
                        c1_q     = cic_i3_q[47:0] - cic_d1_q; cic_d1_q <= cic_i3_q[47:0];
                        c2_q     = c1_q     - cic_d2_q; cic_d2_q <= c1_q;
                        c3_q     = c2_q     - cic_d3_q; cic_d3_q <= c2_q;
                        sc_i     = c3_i >>> cfg_cic_shift;
                        sc_q     = c3_q >>> cfg_cic_shift;
                        f1_i     = cic_i5_i - cic_e1_i; cic_e1_i <= cic_i5_i;
                        f2_i     = f1_i     - cic_e2_i; cic_e2_i <= f1_i;
                        f3_i     = f2_i     - cic_e3_i; cic_e3_i <= f2_i;
                        f4_i     = f3_i     - cic_e4_i; cic_e4_i <= f3_i;
                        f5_i     = f4_i     - cic_e5_i; cic_e5_i <= f4_i;
                        f1_q     = cic_i5_q - cic_e1_q; cic_e1_q <= cic_i5_q;
                        f2_q     = f1_q     - cic_e2_q; cic_e2_q <= f1_q;
                        f3_q     = f2_q     - cic_e3_q; cic_e3_q <= f2_q;
                        f4_q     = f3_q     - cic_e4_q; cic_e4_q <= f3_q;
                        f5_q     = f4_q     - cic_e5_q; cic_e5_q <= f4_q;
                        sf_i     = f5_i >>> cfg_cic_shift;
                        sf_q     = f5_q >>> cfg_cic_shift;
                        cic_out_i     <= cfg_cic_n5 ? sat16_72(sf_i) : sat16_48(sc_i);
                        cic_out_q     <= cfg_cic_n5 ? sat16_72(sf_q) : sat16_48(sc_q);
                        cic_out_valid <= 1'b1;
                    end else begin
                        cic_cnt <= cic_cnt + 16'd1;
                    end
                end
            end
        end
    end

    // -------------------------------------------------------------------------
    // 3. 31-Tap Symmetric Channel Selectivity Lowpass FIR (Q15 DC gain = 32768)
    //    Hamming-windowed sinc cutoff ~0.22 * Fs_cic (-53 dB adjacent-channel rej.)
    // -------------------------------------------------------------------------
    function automatic signed [15:0] lpf_coeff;
        input [3:0] sym_idx; // 0 = edge h[0]=h[30], ..., 15 = center h[15]
        begin
            case (sym_idx)
                4'd0:  lpf_coeff =  16'sd10;
                4'd1:  lpf_coeff =  16'sd14;
                4'd2:  lpf_coeff = -16'sd24;
                4'd3:  lpf_coeff = -16'sd78;
                4'd4:  lpf_coeff = -16'sd63;
                4'd5:  lpf_coeff =  16'sd92;
                4'd6:  lpf_coeff =  16'sd252;
                4'd7:  lpf_coeff =  16'sd145;
                4'd8:  lpf_coeff = -16'sd317;
                4'd9:  lpf_coeff = -16'sd644;
                4'd10: lpf_coeff = -16'sd188;
                4'd11: lpf_coeff =  16'sd1042;
                4'd12: lpf_coeff =  16'sd1868;
                4'd13: lpf_coeff =  16'sd418;
                4'd14: lpf_coeff = -16'sd4186;
                default: lpf_coeff = 16'sd0; // handle in center case
            endcase
        end
    endfunction

    // True Hamming-windowed sinc(fc=0.16), quantized Q15 (sum = 32768 = 0 dB DC gain, -73.9 dB @ 0.30*Fs)
    function automatic signed [15:0] ch_fir_c;
        input [3:0] k; // 0..15 symmetric
        begin
            case (k)
                4'd0:  ch_fir_c =  16'sd33;
                4'd1:  ch_fir_c =  16'sd67;
                4'd2:  ch_fir_c =  16'sd46;
                4'd3:  ch_fir_c = -16'sd70;
                4'd4:  ch_fir_c = -16'sd219;
                4'd5:  ch_fir_c = -16'sd190;
                4'd6:  ch_fir_c =  16'sd169;
                4'd7:  ch_fir_c =  16'sd628;
                4'd8:  ch_fir_c =  16'sd598;
                4'd9:  ch_fir_c = -16'sd294;
                4'd10: ch_fir_c = -16'sd1523;
                4'd11: ch_fir_c = -16'sd1699;
                4'd12: ch_fir_c =  16'sd396;
                4'd13: ch_fir_c =  16'sd4519;
                4'd14: ch_fir_c =  16'sd8694;
                4'd15: ch_fir_c =  16'sd10458;
            endcase
        end
    endfunction

    function automatic signed [37:0] fir_pair;
        input signed [15:0] a, b, c;
        reg signed [16:0] s;
        begin
            s = $signed({a[15], a}) + $signed({b[15], b});
            fir_pair = $signed(s) * $signed(c);
        end
    endfunction

    reg signed [15:0] fir_i [0:30];
    reg signed [15:0] fir_q [0:30];
    reg [7:0]         fir_dec_cnt;
    reg               ch_valid;
    reg signed [15:0] ch_i, ch_q;
    reg signed [37:0] acc_i, acc_q;
    integer           fi;

    always @(posedge clk) begin
        if (rst) begin
            for (fi = 0; fi < 31; fi = fi + 1) begin
                fir_i[fi] <= 16'sd0;
                fir_q[fi] <= 16'sd0;
            end
            fir_dec_cnt <= 8'd0;
            ch_valid    <= 1'b0;
            ch_i        <= 16'sd0;
            ch_q        <= 16'sd0;
        end else begin
            ch_valid <= 1'b0;
            if (cic_out_valid) begin
                if (cfg_fir_decim == 8'd0) begin
                    ch_valid <= 1'b1;
                    ch_i     <= cic_out_i;
                    ch_q     <= cic_out_q;
                end else begin
                    for (fi = 30; fi > 0; fi = fi - 1) begin
                        fir_i[fi] <= fir_i[fi - 1];
                        fir_q[fi] <= fir_q[fi - 1];
                    end
                    fir_i[0] <= cic_out_i;
                    fir_q[0] <= cic_out_q;

                    if (fir_dec_cnt >= (cfg_fir_decim - 8'd1)) begin
                        fir_dec_cnt <= 8'd0;
                        // 31-tap symmetric LPF evaluation using current sample at index 0
                        acc_i = $signed(fir_i[14]) * $signed(ch_fir_c(4'd15))
                              + fir_pair(cic_out_i, fir_i[29], ch_fir_c(4'd0))
                              + fir_pair(fir_i[0],  fir_i[28], ch_fir_c(4'd1))
                              + fir_pair(fir_i[1],  fir_i[27], ch_fir_c(4'd2))
                              + fir_pair(fir_i[2],  fir_i[26], ch_fir_c(4'd3))
                              + fir_pair(fir_i[3],  fir_i[25], ch_fir_c(4'd4))
                              + fir_pair(fir_i[4],  fir_i[24], ch_fir_c(4'd5))
                              + fir_pair(fir_i[5],  fir_i[23], ch_fir_c(4'd6))
                              + fir_pair(fir_i[6],  fir_i[22], ch_fir_c(4'd7))
                              + fir_pair(fir_i[7],  fir_i[21], ch_fir_c(4'd8))
                              + fir_pair(fir_i[8],  fir_i[20], ch_fir_c(4'd9))
                              + fir_pair(fir_i[9],  fir_i[19], ch_fir_c(4'd10))
                              + fir_pair(fir_i[10], fir_i[18], ch_fir_c(4'd11))
                              + fir_pair(fir_i[11], fir_i[17], ch_fir_c(4'd12))
                              + fir_pair(fir_i[12], fir_i[16], ch_fir_c(4'd13))
                              + fir_pair(fir_i[13], fir_i[15], ch_fir_c(4'd14));

                        acc_q = $signed(fir_q[14]) * $signed(ch_fir_c(4'd15))
                              + fir_pair(cic_out_q, fir_q[29], ch_fir_c(4'd0))
                              + fir_pair(fir_q[0],  fir_q[28], ch_fir_c(4'd1))
                              + fir_pair(fir_q[1],  fir_q[27], ch_fir_c(4'd2))
                              + fir_pair(fir_q[2],  fir_q[26], ch_fir_c(4'd3))
                              + fir_pair(fir_q[3],  fir_q[25], ch_fir_c(4'd4))
                              + fir_pair(fir_q[4],  fir_q[24], ch_fir_c(4'd5))
                              + fir_pair(fir_q[5],  fir_q[23], ch_fir_c(4'd6))
                              + fir_pair(fir_q[6],  fir_q[22], ch_fir_c(4'd7))
                              + fir_pair(fir_q[7],  fir_q[21], ch_fir_c(4'd8))
                              + fir_pair(fir_q[8],  fir_q[20], ch_fir_c(4'd9))
                              + fir_pair(fir_q[9],  fir_q[19], ch_fir_c(4'd10))
                              + fir_pair(fir_q[10], fir_q[18], ch_fir_c(4'd11))
                              + fir_pair(fir_q[11], fir_q[17], ch_fir_c(4'd12))
                              + fir_pair(fir_q[12], fir_q[16], ch_fir_c(4'd13))
                              + fir_pair(fir_q[13], fir_q[15], ch_fir_c(4'd14));

                        ch_i     <= sat16_48($signed({{10{acc_i[37]}}, acc_i}) >>> 15);
                        ch_q     <= sat16_48($signed({{10{acc_q[37]}}, acc_q}) >>> 15);
                        ch_valid <= 1'b1;
                    end else begin
                        fir_dec_cnt <= fir_dec_cnt + 8'd1;
                    end
                end
            end
        end
    end

    // -------------------------------------------------------------------------
    // 4. Shared Vectoring CORDIC (Magnitude for AM, atan2 for FM)
    // -------------------------------------------------------------------------
    wire               cor_valid;
    wire signed [15:0] cor_mag, cor_y_unused, cor_ang;

    kria_cordic #(.IN_W(16)) u_demod_cordic (
        .clk       (clk),
        .rst       (rst),
        .in_valid  (ch_valid),
        .in_mode   (1'b0),
        .in_x      (ch_i),
        .in_y      (ch_q),
        .in_angle  (16'sd0),
        .out_valid (cor_valid),
        .out_x     (cor_mag),
        .out_y     (cor_y_unused),
        .out_angle (cor_ang)
    );

    // -------------------------------------------------------------------------
    // 5. SSB Phasing Demodulator (31-tap Antisymmetric Hilbert FIR on ch_q)
    //    h[15+m] = 2/(pi*m) * hamming(m) for odd m = +/-1,3,5,7,9,11,13,15 (Q15)
    // -------------------------------------------------------------------------
    reg signed [15:0] ssb_i_dly [0:30];
    reg signed [15:0] ssb_q_dly [0:30];
    reg               ssb_valid;
    reg signed [15:0] ssb_out;
    reg signed [36:0] hilb_acc;
    reg signed [16:0] ssb_sum;
    integer           si;

    // Hamming-windowed Type-III Hilbert coefficients Q15 (h[15-m] = -h[15+m]):
    // m=1: 20598, m=3: 6416, m=5: 3328, m=7: 1858, m=9: 1002, m=11: 486, m=13: 204, m=15: 168
    always @(posedge clk) begin
        if (rst) begin
            for (si = 0; si < 31; si = si + 1) begin
                ssb_i_dly[si] <= 16'sd0;
                ssb_q_dly[si] <= 16'sd0;
            end
            ssb_valid <= 1'b0;
            ssb_out   <= 16'sd0;
        end else begin
            ssb_valid <= 1'b0;
            if (ch_valid) begin
                for (si = 30; si > 0; si = si - 1) begin
                    ssb_i_dly[si] <= ssb_i_dly[si - 1];
                    ssb_q_dly[si] <= ssb_q_dly[si - 1];
                end
                ssb_i_dly[0] <= ch_i;
                ssb_q_dly[0] <= ch_q;

                // Asymmetric odd offsets m = 1..15 around tap index 14 (current ch_q is tap 0):
                // h_hilbert[n] = (2/(pi*n))*w[n] -> y = sum_{m>0} h[m]*(x[n-m] - x[n+m])
                hilb_acc = ($signed(ssb_q_dly[15]) - $signed(ssb_q_dly[13])) * 37'sd20598
                         + ($signed(ssb_q_dly[17]) - $signed(ssb_q_dly[11])) * 37'sd6416
                         + ($signed(ssb_q_dly[19]) - $signed(ssb_q_dly[9]))  * 37'sd3328
                         + ($signed(ssb_q_dly[21]) - $signed(ssb_q_dly[7]))  * 37'sd1858
                         + ($signed(ssb_q_dly[23]) - $signed(ssb_q_dly[5]))  * 37'sd1002
                         + ($signed(ssb_q_dly[25]) - $signed(ssb_q_dly[3]))  * 37'sd486
                         + ($signed(ssb_q_dly[27]) - $signed(ssb_q_dly[1]))  * 37'sd204
                         + ($signed(ssb_q_dly[29]) - $signed(ch_q))          * 37'sd168;

                // USB = (I_dly - H{Q})/2, LSB = (I_dly + H{Q})/2
`ifdef MUTATE_SWAP_USB_LSB
                if (cfg_mode == 3'd1)
                    ssb_sum = $signed(ssb_i_dly[14]) + $signed(hilb_acc >>> 15);
                else
                    ssb_sum = $signed(ssb_i_dly[14]) - $signed(hilb_acc >>> 15);
`else
                if (cfg_mode == 3'd1)
                    ssb_sum = $signed(ssb_i_dly[14]) - $signed(hilb_acc >>> 15);
                else
                    ssb_sum = $signed(ssb_i_dly[14]) + $signed(hilb_acc >>> 15);
`endif
                ssb_out   <= ssb_sum >>> 1;
                ssb_valid <= 1'b1;
            end
        end
    end

    // -------------------------------------------------------------------------
    // 6. AM DC-Blocker + FM Discriminator / De-Emphasis / Pilot PLL / RDS / CTCSS
    // -------------------------------------------------------------------------
    reg signed [15:0] prev_ang;
    reg signed [15:0] am_prev_mag;
    reg signed [47:0] am_dc_y, tmp_dc;
    reg signed [31:0] fm_de_y, fm_lpf_l, fm_lpf_r;
    reg               post_cor_valid;
    reg signed [15:0] dphi_s;
    reg signed [31:0] tmp_fm;

    // 19 kHz Pilot Resonator (zero-gain DC, peaked @ 19 kHz via 2nd-order Goertzel/BPF)
    // and Type-II Pilot NCO PLL (runs on post_cor_valid pulses in WBFM mode)
    reg  [31:0] pilot_phase;
    reg  signed [31:0] pilot_acc_err, pilot_lock_lpf;
    reg  signed [15:0] pilot_bp_x1, pilot_bp_x2;
    reg  signed [47:0] pilot_bp_y1, pilot_bp_y2;
    reg  signed [31:0] lr_lpf;
    reg                rds_prev_sign;
    // RDS: 57 kHz product low-passed (two 1st-order sections, about 2.5 kHz at 250 kS/s), then integrated over
    // the four quarters of each bit. The bit clock is a Q8.8 accumulator against cfg_rds_sym_samps (the bit is a
    // fractional number of samples), pulled by an early-late gate on the bi-phase mid-bit transition, which is
    // there whatever the data: aligned, the second and third quarters cancel; early, they leave the sign of the
    // first half.
    reg  signed [31:0] rds_lp1, rds_lp2;
    reg  signed [31:0] rds_q0, rds_q1, rds_q2, rds_q3;
    reg  signed [17:0] rds_ph;          // Q8.8 samples into the bit (negative right after a delayed start)
    // gear shift: the loop starts anywhere in the bit (up to half a bit, 105 samples, from lock), so the first
    // bits correct by 8 samples, then 2, then half a sample, and from bit 112 a quarter sample, which keeps the
    // steady-state jitter to 0.1 % of a bit
    reg        [6:0]  rds_nbits;
    wire signed [17:0] rds_step = (rds_nbits < 7'd16) ? 18'sd2048 : (rds_nbits < 7'd48) ? 18'sd512 :
                                  (rds_nbits < 7'd112) ? 18'sd128 : 18'sd64;

    // Goertzel CTCSS Detector (active in NBFM mode 3'd3 on raw discriminator dphi)
    reg signed [31:0] g_s1, g_s2, g_s0;
    reg [15:0]        g_cnt;
    reg signed [47:0] g_p1, g_p2, g_p12, g_pow;

    wire signed [31:0] am_audio_w = am_dc_y >>> 15;

    always @(posedge clk) begin
        if (rst) begin
            prev_ang       <= 16'sd0;
            am_prev_mag    <= 16'sd0;
            am_dc_y        <= 32'sd0;
            fm_de_y        <= 32'sd0;
            fm_lpf_l       <= 32'sd0;
            fm_lpf_r       <= 32'sd0;
            post_cor_valid <= 1'b0;
            dphi_s         <= 16'sd0;

            pilot_phase    <= 32'd0;
            pilot_acc_err  <= 32'sd0;
            pilot_lock_lpf <= 32'sd0;
            pilot_bp_x1    <= 16'sd0;
            pilot_bp_x2    <= 16'sd0;
            pilot_bp_y1    <= 32'sd0;
            pilot_bp_y2    <= 32'sd0;
            lr_lpf         <= 32'sd0;
            rds_prev_sign  <= 1'b0;
            rds_lp1        <= 32'sd0;
            rds_lp2        <= 32'sd0;
            rds_q0         <= 32'sd0;
            rds_q1         <= 32'sd0;
            rds_q2         <= 32'sd0;
            rds_q3         <= 32'sd0;
            rds_ph         <= 18'sd0;
            rds_nbits      <= 7'd0;

            g_s1           <= 32'sd0;
            g_s2           <= 32'sd0;
            g_cnt          <= 16'd0;

            audio_valid    <= 1'b0;
            audio_l        <= 16'sd0;
            audio_r        <= 16'sd0;
            audio_mono     <= 16'sd0;
            pilot_locked   <= 1'b0;
            ctcss_valid    <= 1'b0;
            ctcss_detected <= 1'b0;
            ctcss_power    <= 32'd0;
            rds_bit_valid  <= 1'b0;
            rds_bit        <= 1'b0;
        end else begin
            post_cor_valid <= 1'b0;
            audio_valid    <= 1'b0;
            ctcss_valid    <= 1'b0;
            rds_bit_valid  <= 1'b0;

            if (ssb_valid && (cfg_mode == 3'd1 || cfg_mode == 3'd2)) begin
                audio_valid <= 1'b1;
                audio_l     <= ssb_out;
                audio_r     <= ssb_out;
                audio_mono  <= ssb_out;
            end

            if (cor_valid) begin : blk_demod
                reg signed [15:0] cur_dphi;
                reg signed [15:0] p_sin, p_cos, c38, c57;
                reg signed [47:0] bp_in, bp_out, bp_sig;
                reg signed [31:0] err_ph, lock_iir, acc_half;
                reg signed [31:0] rds_d, rds_e, rds_x;
                reg signed [17:0] rds_nph, rds_spb, rds_rem;
                reg signed [47:0] l_plus_r, l_minus_r;
                reg signed [31:0] rds_mix, prop_corr;
                reg signed [31:0] lr_demod, de_step;

                // 1. AM Envelope + DC-Block (alpha = 253/256)
                tmp_dc = (($signed({{32{cor_mag[15]}}, cor_mag}) - $signed({{32{am_prev_mag[15]}}, am_prev_mag})) <<< 15)
                       + ((am_dc_y * 48'sd253) >>> 8);
                am_dc_y     <= tmp_dc;
                am_prev_mag <= cor_mag;

                // 2. FM instantaneous frequency (phase delta wraps cleanly mod 2^16)
                cur_dphi = cor_ang - prev_ang;
                prev_ang <= cor_ang;
                dphi_s   <= cur_dphi;

                // De-emphasis / audio LPF: y <= y + alpha * (x - y)
                de_step = $signed(cfg_deemph_alpha) * ($signed(cur_dphi) - $signed(fm_de_y >>> 15));
                tmp_fm  = fm_de_y + de_step;
                fm_de_y <= tmp_fm;

                if (cfg_mode == 3'd0) begin
                    audio_valid <= 1'b1;
                    audio_l     <= sat16_48({{16{am_audio_w[31]}}, am_audio_w});
                    audio_r     <= sat16_48({{16{am_audio_w[31]}}, am_audio_w});
                    audio_mono  <= sat16_48({{16{am_audio_w[31]}}, am_audio_w});
                end else if (cfg_mode == 3'd3) begin
                    // NBFM audio + CTCSS Goertzel resonator
                    audio_valid <= 1'b1;
                    audio_l     <= sat16_48({{16{tmp_fm[31]}}, (tmp_fm >>> 15)});
                    audio_r     <= sat16_48({{16{tmp_fm[31]}}, (tmp_fm >>> 15)});
                    audio_mono  <= sat16_48({{16{tmp_fm[31]}}, (tmp_fm >>> 15)});

                    if (cfg_ctcss_n != 16'd0) begin
                        // g_s0 = x[n] + coeff * s1 - s2  (scaled Q8 sample)
                        g_s0 = ($signed(cur_dphi) >>> 4) + (($signed(cfg_ctcss_coeff) * g_s1) >>> 14) - g_s2;
                        if (g_cnt >= (cfg_ctcss_n - 16'd1)) begin
                            // Power = s1^2 + s2^2 - coeff*s1*s2
                            g_p1  = $signed(g_s1) * $signed(g_s1);
                            g_p2  = $signed(g_s0) * $signed(g_s0);
                            g_p12 = (($signed(g_s1) * $signed(g_s0)) >>> 14) * $signed(cfg_ctcss_coeff);
                            g_pow = (g_p1 + g_p2 - g_p12) >>> 10;
                            ctcss_power    <= (g_pow > 48'sd0) ? g_pow[31:0] : 32'd0;
                            ctcss_detected <= (g_pow > $signed({1'b0, cfg_ctcss_thresh}));
                            ctcss_valid    <= 1'b1;
                            g_s1 <= 32'sd0;
                            g_s2 <= 32'sd0;
                            g_cnt <= 16'd0;
                        end else begin
                            g_s2  <= g_s1;
                            g_s1  <= g_s0;
                            g_cnt <= g_cnt + 16'd1;
                        end
                    end
                end else if (cfg_mode == 3'd4) begin
                    // WBFM Stereo + 19 kHz Pilot PLL + 38 kHz L-R + 57 kHz RDS BPSK
                    p_sin = lut_sin(pilot_phase);
                    p_cos = lut_cos(pilot_phase);
                    c38   = lut_cos(pilot_phase << 1);
                    c57   = lut_cos((pilot_phase << 1) + pilot_phase);

                    // 2-pole resonator BPF around 19 kHz (r = 123/128, coeff = 2*cos(2*pi*19k/Fs_ch) Q14)
                    // Keep internal state in Q8 so low-amplitude startup never quantizes to 0.
                    bp_in  = $signed({{32{cur_dphi[15]}}, cur_dphi}) - $signed({{32{pilot_bp_x2[15]}}, pilot_bp_x2});
                    bp_out = (bp_in <<< 3)
                           + (((($signed({{32{cfg_ctcss_coeff[15]}}, cfg_ctcss_coeff}) * 48'sd123) >>> 7) * pilot_bp_y1) >>> 14)
                           - ((pilot_bp_y2 * 48'sd118) >>> 7);
                    bp_sig = bp_out >>> 8;
                    pilot_bp_x2 <= pilot_bp_x1;
                    pilot_bp_x1 <= cur_dphi;
                    pilot_bp_y2 <= pilot_bp_y1;
                    pilot_bp_y1 <= bp_out;

                    // Phase error when locking cos(pilot_phase) to bandpass pilot
                    // Precompute signed loop terms separately so unsigned pilot_phase cannot coerce >>> to >>
                    err_ph    = ($signed(bp_sig[15:0]) * $signed(-p_sin)) >>> 15;
                    prop_corr = err_ph * 32'sd4096;
                    acc_half  = pilot_acc_err >>> 1;
                    pilot_acc_err <= pilot_acc_err + (err_ph * 32'sd8);
                    pilot_phase   <= pilot_phase + cfg_pilot_ftw + prop_corr + acc_half;

                    // Lock detector on I = bp_sig * cos(pilot_phase)
                    lock_iir = ($signed(bp_sig[15:0]) * $signed(p_cos)) >>> 15;
                    pilot_lock_lpf <= pilot_lock_lpf + (((lock_iir > 0 ? lock_iir : -lock_iir) - pilot_lock_lpf) >>> 5);
                    pilot_locked   <= (pilot_lock_lpf > 32'sd48);

                    // Coherent L-R demod at 38 kHz + de-emphasis LPF
                    lr_demod  = ($signed(cur_dphi) * $signed(c38)) >>> 14;
                    de_step   = $signed(cfg_deemph_alpha) * ($signed(lr_demod) - $signed(lr_lpf >>> 15));
                    lr_lpf    <= lr_lpf + de_step;

                    l_plus_r  = $signed(tmp_fm) >>> 15;
                    l_minus_r = ($signed(lr_lpf) + $signed(de_step)) >>> 15;
                    audio_mono  <= sat16_48(l_plus_r);
                    audio_l     <= sat16_48(l_plus_r + l_minus_r);
                    audio_r     <= sat16_48(l_plus_r - l_minus_r);
                    audio_valid <= 1'b1;

                    // 57 kHz RDS: coherent product, low-pass, quarter integrals, bit clock with early-late gate
                    rds_mix = ($signed(cur_dphi) * $signed(c57)) >>> 15;
                    rds_lp1 <= rds_lp1 + ((($signed(rds_mix) <<< 8) - rds_lp1) >>> 4);
                    rds_lp2 <= rds_lp2 + ((rds_lp1 - rds_lp2) >>> 4);
                    rds_x    = rds_lp2 >>> 8;
                    rds_spb = $signed({2'b00, cfg_rds_sym_samps});
                    if (cfg_rds_sym_samps != 16'd0) begin
                        rds_nph = rds_ph + 18'sd256;
                        if (rds_nph >= rds_spb) begin
                            // end of the bit: decision on the halves, timing error from the middle quarters
                            rds_d   = rds_q0 + rds_q1 - rds_q2 - (rds_q3 + rds_x);
                            rds_e   = rds_q1 + rds_q2;
                            rds_rem = rds_nph - rds_spb;
                            rds_bit_valid <= 1'b1;
                            rds_bit       <= (rds_d >= 0) ^ rds_prev_sign;   // differential decoding
                            rds_prev_sign <= (rds_d >= 0);
                            rds_q0 <= 32'sd0; rds_q1 <= 32'sd0; rds_q2 <= 32'sd0; rds_q3 <= 32'sd0;
`ifdef MUTATE_RDS_NO_TIMING
                            rds_ph <= rds_rem;
`else
                            // early (the transition falls late in the window): the next bit starts rds_step
                            // later; late: rds_step sooner
                            if (rds_nbits != 7'd127) rds_nbits <= rds_nbits + 7'd1;
                            if (rds_e == 0)
                                rds_ph <= rds_rem;
                            else if ((rds_e >= 0) == (rds_d >= 0))
                                rds_ph <= rds_rem - rds_step;
                            else
                                rds_ph <= rds_rem + rds_step;
`endif
                        end else begin
                            rds_ph <= rds_nph;
                            if (rds_ph < (rds_spb >>> 2))
                                rds_q0 <= rds_q0 + rds_x;
                            else if (rds_ph < (rds_spb >>> 1))
                                rds_q1 <= rds_q1 + rds_x;
                            else if (rds_ph < (rds_spb >>> 1) + (rds_spb >>> 2))
                                rds_q2 <= rds_q2 + rds_x;
                            else
                                rds_q3 <= rds_q3 + rds_x;
                        end
                    end
                end
            end
        end
    end
endmodule
