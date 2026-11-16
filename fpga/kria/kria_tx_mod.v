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

    reg [15:0]        div_cnt;
    wire              tx_can_step = en && (!m_axis_tvalid || m_axis_tready);
    wire              tick = tx_can_step &&
                             (ext_aud_en ? ext_aud_valid : (div_cnt >= cfg_samp_div));

    reg [31:0]        tone_ph, car_ph;
    reg signed [15:0] aud_dly [0:30];
    reg signed [36:0] hilb_acc;
    integer           hi;

    // 64-bit packet assembly {Q1, I1, Q0, I0}
    reg [31:0]        first_pair;
    reg               pair_half;
    reg [15:0]        pkt_word_idx;
    wire [15:0]       pkt_words_eff = (cfg_pkt_words == 16'd0) ? 16'd32 : cfg_pkt_words;

    always @(posedge clk) begin
        if (rst || !en) begin
            div_cnt      <= 16'd0;
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
        end else begin
            iq_valid <= 1'b0;
            if (m_axis_tvalid && m_axis_tready)
                m_axis_tvalid <= 1'b0;

            if (!ext_aud_en && tx_can_step) begin
                if (div_cnt >= cfg_samp_div) div_cnt <= 16'd0;
                else                         div_cnt <= div_cnt + 16'd1;
            end

            if (tick) begin : blk_mod
                reg signed [15:0] aud_cur, aud_sin, c_cos, c_sin;
                reg signed [15:0] bb_i, bb_q;
                reg signed [31:0] am_env, nbfm_df, mix_i_w, mix_q_w;
                reg signed [15:0] hilb_q, out_i_s, out_q_s;

                aud_cur = ext_aud_en ? ext_aud_sample : lut_cos(tone_ph);
                aud_sin = lut_sin(tone_ph);                 // the internal tone's quadrature (SSB)
                tone_ph <= tone_ph + cfg_tone_ftw;

                for (hi = 30; hi > 0; hi = hi - 1)
                    aud_dly[hi] <= aud_dly[hi - 1];
                aud_dly[0] <= aud_cur;

                hilb_acc = ($signed(aud_dly[15]) - $signed(aud_dly[13])) * 37'sd20598
                         + ($signed(aud_dly[17]) - $signed(aud_dly[11])) * 37'sd6416
                         + ($signed(aud_dly[19]) - $signed(aud_dly[9]))  * 37'sd3328
                         + ($signed(aud_dly[21]) - $signed(aud_dly[7]))  * 37'sd1858
                         + ($signed(aud_dly[23]) - $signed(aud_dly[5]))  * 37'sd1002
                         + ($signed(aud_dly[25]) - $signed(aud_dly[3]))  * 37'sd486
                         + ($signed(aud_dly[27]) - $signed(aud_dly[1]))  * 37'sd204
                         + ($signed(aud_dly[29]) - $signed(aud_cur))     * 37'sd168;
                hilb_q = hilb_acc >>> 15;

                // Carrier NCO phase update (FM adds instantaneous deviation to phase step)
                nbfm_df = (cfg_mode == 3'd2) ? (($signed(aud_cur) * $signed({1'b0, cfg_mod_param})) >>> 2) : 32'sd0;
                car_ph <= car_ph + cfg_carrier_ftw + nbfm_df;

                c_cos = lut_cos(car_ph);
                c_sin = lut_sin(car_ph);

                case (cfg_mode)
                    3'd0: begin // CW
                        bb_i = 16'sd16384;
                        bb_q = 16'sd0;
                    end
                    3'd1: begin // AM (carrier + m*aud, normalized so <= 1.0 peak)
                        am_env = 32'sd16384 + (($signed(aud_cur) * $signed({1'b0, cfg_mod_param})) >>> 16);
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
                        bb_i = (ext_aud_en ? aud_dly[14] : aud_cur) >>> 1;
`ifdef MUTATE_FLIP_USB_Q
                        bb_q = -((ext_aud_en ? hilb_q : aud_sin) >>> 1); // MUTATION: produces LSB instead of USB
`else
                        bb_q = (ext_aud_en ? hilb_q : aud_sin) >>> 1;
`endif
                    end
                    default: begin // 3'd4 LSB: m - j*H{m} -> +f_c - f_m
                        bb_i = (ext_aud_en ? aud_dly[14] : aud_cur) >>> 1;
                        bb_q = -((ext_aud_en ? hilb_q : aud_sin) >>> 1);
                    end
                endcase

                mix_i_w = ($signed(bb_i) * $signed(c_cos) - $signed(bb_q) * $signed(c_sin)) >>> 15;
                mix_q_w = ($signed(bb_i) * $signed(c_sin) + $signed(bb_q) * $signed(c_cos)) >>> 15;
                out_i_s = (mix_i_w * $signed({1'b0, cfg_amp_scale})) >>> 14;
                out_q_s = (mix_q_w * $signed({1'b0, cfg_amp_scale})) >>> 14;

                iq_valid <= 1'b1;
                iq_i     <= out_i_s;
                iq_q     <= out_q_s;

                if (!pair_half) begin
                    first_pair <= {out_q_s, out_i_s};
                    pair_half  <= 1'b1;
                end else begin
                    m_axis_tdata  <= {out_q_s, out_i_s, first_pair};
                    m_axis_tvalid <= 1'b1;
                    m_axis_tlast  <= (pkt_word_idx >= (pkt_words_eff - 16'd1));
                    pair_half     <= 1'b0;
                    if (pkt_word_idx >= (pkt_words_eff - 16'd1))
                        pkt_word_idx <= 16'd0;
                    else
                        pkt_word_idx <= pkt_word_idx + 16'd1;
                end
            end
        end
    end
endmodule
