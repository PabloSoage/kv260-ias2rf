// SPDX-License-Identifier: Apache-2.0
// Kria PL Multi-Mode Baseband TX Modulator (CW, AM, NBFM, USB, LSB -> IAS1 -> dac_sdr)
//
// Placed in Kria PL (XCK26, 4 DSP48E2) ahead of IAS1 downlink STREAM_ID 8'h12 so
// Artix AD9767 (dac_sdr) transmits CW, AM, NBFM, USB, or LSB without spending Artix DSP48s.

`timescale 1ns/1ps

module kria_tx_mod #(
    parameter [7:0] STREAM_ID = 8'h12
) (
    input  wire               clk,
    input  wire               rst,
    input  wire               en,

    // Configuration
    input  wire [2:0]         cfg_mode,        // 0=CW, 1=AM, 2=NBFM, 3=USB, 4=LSB
    input  wire [31:0]        cfg_carrier_ftw, // Digital IF offset wrt TX sample rate Fs_tx
    input  wire [31:0]        cfg_tone_ftw,    // Internal audio DDS FTW wrt Fs_tx
    input  wire [15:0]        cfg_mod_param,   // AM: Q15 mod depth (0..32767); NBFM: peak dev FTW >> 16
    input  wire [15:0]        cfg_amp_scale,   // Output scale Q15 (e.g. 28000)
    input  wire [15:0]        cfg_samp_div,    // Output I/Q sample period in clk cycles - 1 (e.g. 3 => 25 MSPS @ 100M)
    input  wire [15:0]        cfg_pkt_words,   // 64-bit words per packet (default 32 => 256 bytes = 64 IQ samples)

    // Optional external audio sample stream (overrides internal DDS when ext_aud_en=1)
    input  wire               ext_aud_en,
    input  wire               ext_aud_valid,
    input  wire signed [15:0] ext_aud_sample,

    // Single I/Q sample monitor (for unit verification & spectrum dump)
    output reg                iq_valid,
    output reg  signed [15:0] iq_i,
    output reg  signed [15:0] iq_q,

    // AXI4-Stream Master -> kria_pl_link s_axis_tx (64-bit {Q1, I1, Q0, I0})
    output reg  [63:0]        m_axis_tdata,
    output reg                m_axis_tvalid,
    input  wire               m_axis_tready,
    output reg                m_axis_tlast,
    output wire [7:0]         m_axis_tid,
    output wire [15:0]        m_axis_tuser
);
    assign m_axis_tid   = STREAM_ID;
    assign m_axis_tuser = {cfg_pkt_words[12:0], 3'b000}; // bytes = words * 8

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

    // sin of the 32-bit phase: quarter-wave table (512 points per turn) plus linear interpolation on the next
    // 8 phase bits. The bare table left phase-truncation spurs at -60 dBc; interpolated, the worst is below -90.
    function automatic signed [15:0] lut_sin_grid;
        input [8:0] p;                              // phase in 1/512 turn
        reg [7:0] addr;
        reg signed [15:0] raw;
        begin
            addr = p[7] ? (8'd128 - {1'b0, p[6:0]}) : {1'b0, p[6:0]};
            raw  = sin_qwave(addr);
            lut_sin_grid = p[8] ? -raw : raw;
        end
    endfunction

    function automatic signed [15:0] lut_sin;
        input [31:0] ph;
        reg signed [15:0] v0, v1;
        reg signed [25:0] d;
        begin
            v0 = lut_sin_grid(ph[31:23]);
            v1 = lut_sin_grid(ph[31:23] + 9'd1);
            d  = ($signed({v1[15], v1}) - $signed({v0[15], v0})) * $signed({1'b0, ph[22:15]});
            lut_sin = v0 + (d >>> 8);
        end
    endfunction

    function automatic signed [15:0] lut_cos;
        input [31:0] ph;
        begin
            lut_cos = lut_sin(ph + 32'h4000_0000);
        end
    endfunction

    // G-8 timing closure: the modulator is a pipeline (t1..t9) that takes one sample per tick and computes what
    // the former single-clock code did, in the same order: the tone phase advances at the tick, the carrier phase
    // where the FM deviation is known (t3), and every value meets the same operands. The packed words go through
    // an 8-word FIFO into m_axis; a tick is taken only while the samples in flight and in the FIFO fit (occ), so
    // backpressure never loses one. The word stream is the former one; it starts 10 clocks later.
    reg [15:0]        div_cnt;
    reg [4:0]         occ;                      // samples ticked whose word has not left m_axis
    wire              room = (occ < 5'd14);
    wire              tick = en && room && (ext_aud_en ? ext_aud_valid : (div_cnt >= cfg_samp_div));

    reg [31:0]        tone_ph, car_ph;
    reg signed [15:0] aud_dly [0:30];
    reg signed [36:0] hilb_acc;
    integer           hi;

    // 64-bit packet assembly {Q1, I1, Q0, I0}
    reg [31:0]        first_pair;
    reg               pair_half;
    reg [15:0]        pkt_word_idx;
    wire [15:0]       pkt_words_eff = (cfg_pkt_words == 16'd0) ? 16'd32 : cfg_pkt_words;

    // pipeline registers
    reg               t1_v, t2_v, t3_v, t4_v, t5_v, t6_v, t7_v, t8_v, t9_v;
    reg [31:0]        t1_ph;
    reg               t1_ext, t2_ext;
    reg signed [15:0] t1_xs, t2_xs;
    reg signed [15:0] t2_c0, t2_c1, t2_s0, t2_s1;
    reg [7:0]         t2_cf, t2_sf;
    reg signed [15:0] t3_aud, t3_ausin;
    reg signed [15:0] t4_aud, t4_ausin, t4_dly14;
    reg [31:0]        t4_cph;
    reg signed [36:0] t4_hp [0:7];
    reg signed [36:0] t5_hs [0:1];
    reg signed [15:0] t5_aud, t5_ausin, t5_dly14;
    reg signed [15:0] t5_c0, t5_c1, t5_s0, t5_s1;
    reg [7:0]         t5_cf, t5_sf;
    reg signed [15:0] t6_aud, t6_ausin, t6_dly14, t6_hilbq, t6_cos, t6_sin;
    reg signed [31:0] t7_ic, t7_qs, t7_is, t7_qc;
    reg signed [31:0] t8_mi, t8_mq;
    reg signed [15:0] t9_i, t9_q;

    function automatic signed [15:0] lerp8;
        input signed [15:0] v0, v1;
        input [7:0] fr;
        reg signed [25:0] d;
        begin
            d = ($signed({v1[15], v1}) - $signed({v0[15], v0})) * $signed({1'b0, fr});
            lerp8 = v0 + (d >>> 8);
        end
    endfunction

    // output FIFO
    reg  [64:0]       ofifo [0:7];
    reg  [3:0]        of_wp, of_rp;
    wire              of_empty = (of_wp == of_rp);
    reg               of_push;
    reg  [64:0]       of_din;
    wire              of_pop = !of_empty && (!m_axis_tvalid || m_axis_tready);
    wire              word_out = m_axis_tvalid && m_axis_tready;

    wire [31:0]       t1_ph_c = t1_ph + 32'h4000_0000;
    wire [31:0]       t4_cph_c = t4_cph + 32'h4000_0000;

    always @(posedge clk) begin
        if (rst || !en) begin
            div_cnt      <= 16'd0;
            occ          <= 5'd0;
            tone_ph      <= 32'd0;
            car_ph       <= 32'd0;
            for (hi = 0; hi < 31; hi = hi + 1)
                aud_dly[hi] <= 16'sd0;
            iq_valid     <= 1'b0;
            iq_i         <= 16'sd0;
            iq_q         <= 16'sd0;
            first_pair   <= 32'd0;
            pair_half    <= 1'b0;
            pkt_word_idx <= 16'd0;
            m_axis_tdata <= 64'd0;
            m_axis_tvalid<= 1'b0;
            m_axis_tlast <= 1'b0;
            t1_v <= 1'b0; t2_v <= 1'b0; t3_v <= 1'b0; t4_v <= 1'b0; t5_v <= 1'b0;
            t6_v <= 1'b0; t7_v <= 1'b0; t8_v <= 1'b0; t9_v <= 1'b0;
            of_wp <= 4'd0; of_rp <= 4'd0; of_push <= 1'b0;
        end else begin
            iq_valid <= 1'b0;

            if (!ext_aud_en && room) begin
                if (div_cnt >= cfg_samp_div) div_cnt <= 16'd0;
                else                         div_cnt <= div_cnt + 16'd1;
            end
            occ <= occ + {4'd0, tick} - (word_out ? 5'd2 : 5'd0);

            // t1: the tick: tone phase, external sample
            t1_v <= tick;
            if (tick) begin
                t1_ph   <= tone_ph;
                t1_ext  <= ext_aud_en;
                t1_xs   <= ext_aud_sample;
                tone_ph <= tone_ph + cfg_tone_ftw;
            end
            // t2: tone table points
            t2_v <= t1_v;
            if (t1_v) begin
                t2_ext <= t1_ext; t2_xs <= t1_xs;
                t2_c0 <= lut_sin_grid(t1_ph_c[31:23]); t2_c1 <= lut_sin_grid(t1_ph_c[31:23] + 9'd1); t2_cf <= t1_ph_c[22:15];
                t2_s0 <= lut_sin_grid(t1_ph[31:23]);   t2_s1 <= lut_sin_grid(t1_ph[31:23] + 9'd1);   t2_sf <= t1_ph[22:15];
            end
            // t3: audio sample and the tone's quadrature
            t3_v <= t2_v;
            if (t2_v) begin
                t3_aud   <= t2_ext ? t2_xs : lerp8(t2_c0, t2_c1, t2_cf);
                t3_ausin <= lerp8(t2_s0, t2_s1, t2_sf);
            end
            // t4: Hilbert products and delay line; carrier phase (FM adds the deviation to the step)
            t4_v <= t3_v;
            if (t3_v) begin : blk_t4
                reg signed [31:0] nbfm_df;
                for (hi = 30; hi > 0; hi = hi - 1)
                    aud_dly[hi] <= aud_dly[hi - 1];
                aud_dly[0] <= t3_aud;
                t4_hp[0] <= ($signed(aud_dly[15]) - $signed(aud_dly[13])) * 37'sd20598;
                t4_hp[1] <= ($signed(aud_dly[17]) - $signed(aud_dly[11])) * 37'sd6416;
                t4_hp[2] <= ($signed(aud_dly[19]) - $signed(aud_dly[9]))  * 37'sd3328;
                t4_hp[3] <= ($signed(aud_dly[21]) - $signed(aud_dly[7]))  * 37'sd1858;
                t4_hp[4] <= ($signed(aud_dly[23]) - $signed(aud_dly[5]))  * 37'sd1002;
                t4_hp[5] <= ($signed(aud_dly[25]) - $signed(aud_dly[3]))  * 37'sd486;
                t4_hp[6] <= ($signed(aud_dly[27]) - $signed(aud_dly[1]))  * 37'sd204;
                t4_hp[7] <= ($signed(aud_dly[29]) - $signed(t3_aud))      * 37'sd168;
                t4_dly14 <= aud_dly[14];
                t4_aud   <= t3_aud;
                t4_ausin <= t3_ausin;
                nbfm_df = (cfg_mode == 3'd2) ? (($signed(t3_aud) * $signed({1'b0, cfg_mod_param})) >>> 2) : 32'sd0;
                t4_cph  <= car_ph;
                car_ph  <= car_ph + cfg_carrier_ftw + nbfm_df;
            end
            // t5: Hilbert partial sums; carrier table points
            t5_v <= t4_v;
            if (t4_v) begin
                t5_hs[0] <= t4_hp[0] + t4_hp[1] + t4_hp[2] + t4_hp[3];
                t5_hs[1] <= t4_hp[4] + t4_hp[5] + t4_hp[6] + t4_hp[7];
                t5_aud <= t4_aud; t5_ausin <= t4_ausin; t5_dly14 <= t4_dly14;
                t5_c0 <= lut_sin_grid(t4_cph_c[31:23]); t5_c1 <= lut_sin_grid(t4_cph_c[31:23] + 9'd1); t5_cf <= t4_cph_c[22:15];
                t5_s0 <= lut_sin_grid(t4_cph[31:23]);   t5_s1 <= lut_sin_grid(t4_cph[31:23] + 9'd1);   t5_sf <= t4_cph[22:15];
            end
            // t6: Hilbert output; carrier cos/sin
            t6_v <= t5_v;
            if (t5_v) begin
                hilb_acc  = t5_hs[0] + t5_hs[1];
                t6_hilbq <= hilb_acc >>> 15;
                t6_aud <= t5_aud; t6_ausin <= t5_ausin; t6_dly14 <= t5_dly14;
                t6_cos <= lerp8(t5_c0, t5_c1, t5_cf);
                t6_sin <= lerp8(t5_s0, t5_s1, t5_sf);
            end
            // t7: baseband by mode, mixer products
            t7_v <= t6_v;
            if (t6_v) begin : blk_t7
                reg signed [15:0] bb_i, bb_q;
                reg signed [31:0] am_env;
                case (cfg_mode)
                    3'd0: begin // CW
                        bb_i = 16'sd16384;
                        bb_q = 16'sd0;
                    end
                    3'd1: begin // AM (carrier + m*aud, normalized so <= 1.0 peak)
                        am_env = 32'sd16384 + (($signed(t6_aud) * $signed({1'b0, cfg_mod_param})) >>> 16);
                        bb_i   = am_env[15:0];
                        bb_q   = 16'sd0;
                    end
                    3'd2: begin // NBFM (constant envelope)
                        bb_i = 16'sd16384;
                        bb_q = 16'sd0;
                    end
                    // SSB. The internal tone has an exact quadrature (cos + j sin of the tone DDS), so the opposite
                    // sideband is limited only by the table. External audio arrives at the audio rate and goes
                    // through the 31-tap Hilbert (aud_dly[14] is its centre); at 25 MSPS that filter is flat to
                    // DC for any audio tone and would give double sideband, hence the split.
                    3'd3: begin // USB: m + j*H{m} -> +f_c + f_m
                        bb_i = (ext_aud_en ? t6_dly14 : t6_aud) >>> 1;
`ifdef MUTATE_FLIP_USB_Q
                        bb_q = -((ext_aud_en ? t6_hilbq : t6_ausin) >>> 1); // MUTATION: produces LSB instead of USB
`else
                        bb_q = (ext_aud_en ? t6_hilbq : t6_ausin) >>> 1;
`endif
                    end
                    default: begin // 3'd4 LSB: m - j*H{m} -> +f_c - f_m
                        bb_i = (ext_aud_en ? t6_dly14 : t6_aud) >>> 1;
                        bb_q = -((ext_aud_en ? t6_hilbq : t6_ausin) >>> 1);
                    end
                endcase
                t7_ic <= $signed(bb_i) * $signed(t6_cos);
                t7_qs <= $signed(bb_q) * $signed(t6_sin);
                t7_is <= $signed(bb_i) * $signed(t6_sin);
                t7_qc <= $signed(bb_q) * $signed(t6_cos);
            end
            // t8: mixer sums
            t8_v <= t7_v;
            if (t7_v) begin
                t8_mi <= (t7_ic - t7_qs) >>> 15;
                t8_mq <= (t7_is + t7_qc) >>> 15;
            end
            // t9: output scale
            t9_v <= t8_v;
            if (t8_v) begin
                t9_i <= (t8_mi * $signed({1'b0, cfg_amp_scale})) >>> 14;
                t9_q <= (t8_mq * $signed({1'b0, cfg_amp_scale})) >>> 14;
            end
            // pack
            of_push <= 1'b0;
            if (t9_v) begin
                iq_valid <= 1'b1;
                iq_i     <= t9_i;
                iq_q     <= t9_q;
                if (!pair_half) begin
                    first_pair <= {t9_q, t9_i};
                    pair_half  <= 1'b1;
                end else begin
                    of_push   <= 1'b1;
                    of_din    <= {(pkt_word_idx >= (pkt_words_eff - 16'd1)), t9_q, t9_i, first_pair};
                    pair_half <= 1'b0;
                    if (pkt_word_idx >= (pkt_words_eff - 16'd1))
                        pkt_word_idx <= 16'd0;
                    else
                        pkt_word_idx <= pkt_word_idx + 16'd1;
                end
            end
            if (of_push) begin
                ofifo[of_wp[2:0]] <= of_din;
                of_wp <= of_wp + 4'd1;
            end
            if (word_out)
                m_axis_tvalid <= 1'b0;
            if (of_pop) begin
                {m_axis_tlast, m_axis_tdata} <= ofifo[of_rp[2:0]];
                m_axis_tvalid <= 1'b1;
                of_rp <= of_rp + 4'd1;
            end
        end
    end
endmodule
