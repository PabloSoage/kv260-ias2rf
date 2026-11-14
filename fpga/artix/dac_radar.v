// SPDX-License-Identifier: BSD-2-Clause
// AD9708 8-bit Radar LFM Chirp Transmit Path with ODDR Center-Aligned Clock Forwarding
//
// AD9708 Rev. B Timing & Dynamic Specifications Quoted Verbatim (p. 3, Table "DIGITAL SPECIFICATIONS" & Fig. 1):
//   Maximum Output Update Rate (f_CLOCK) : 100 MSPS (Min), 125 MSPS (Typ)
//   Output Settling Time (t_ST, 0.1%)    : 35 ns (Typ)
//   Output Propagation Delay (t_PD)      : 1 ns (Typ)
//   Input Setup Time (t_S)               : 2.0 ns (Min) prior to rising edge of CLOCK
//   Input Hold Time (t_H)                : 1.5 ns (Min) after rising edge of CLOCK
//   Latch Pulsewidth (t_LPW)             : 3.5 ns (Min) high or low CLOCK duration
//   Data Coding                          : Straight offset binary DB[7:0] (0x80 = midscale)
//
// Clocking strategy:
//   Data DB[7:0] launches on posedge dac_clk; DACR_CLK is driven by an ODDR with inverted phase
//   (D1=0, D2=1) so its rising edge lands at T/2 (4.0 ns @ 125 MHz, 5.0 ns @ 100 MHz), satisfying
//   t_S >= 2.0 ns, t_H >= 1.5 ns, and t_LPW >= 3.5 ns with centered setup/hold eye margin.

`timescale 1ns/1ps

module dac_radar (
    input  wire        dac_clk,
    input  wire        dac_rst,

    // Chirp waveform parameters
    input  wire        chirp_enable,
    input  wire        chirp_trig,     // Rising edge / level trigger for single-shot (when pri_len == 0)
    input  wire [31:0] f0_ftw,         // Start frequency tuning word (delta phase per dac_clk)
    input  wire signed [31:0] df_ftw,  // Chirp slope step (delta FTW per dac_clk; >0 up-chirp)
    input  wire [31:0] pulse_len,      // Chirp duration in dac_clk cycles
    input  wire [31:0] pri_len,        // PRI in dac_clk cycles (0 = trigger-only single-shot)
    input  wire [7:0]  amp_scale,      // 0..255 amplitude scaling (255 = full scale)

    // Status
    output reg         chirp_active,
    output reg  [31:0] pulse_cnt,

    // AD9708 pins (Bank 34 LVCMOS33)
    output wire        dacr_clk,
    output reg  [7:0]  dacr_d
);
    // -------------------------------------------------------------------------
    // Quarter-wave 129-entry signed cosine/sine LUT (same Q15 table as DDC)
    // -------------------------------------------------------------------------
    function automatic signed [15:0] sin_qwave;
        input [7:0] idx;
        begin
            case (idx)
                8'd0: sin_qwave = 16'sd0;
                8'd1: sin_qwave = 16'sd402;
                8'd2: sin_qwave = 16'sd804;
                8'd3: sin_qwave = 16'sd1206;
                8'd4: sin_qwave = 16'sd1608;
                8'd5: sin_qwave = 16'sd2009;
                8'd6: sin_qwave = 16'sd2410;
                8'd7: sin_qwave = 16'sd2811;
                8'd8: sin_qwave = 16'sd3212;
                8'd9: sin_qwave = 16'sd3612;
                8'd10: sin_qwave = 16'sd4011;
                8'd11: sin_qwave = 16'sd4410;
                8'd12: sin_qwave = 16'sd4808;
                8'd13: sin_qwave = 16'sd5205;
                8'd14: sin_qwave = 16'sd5602;
                8'd15: sin_qwave = 16'sd5998;
                8'd16: sin_qwave = 16'sd6393;
                8'd17: sin_qwave = 16'sd6786;
                8'd18: sin_qwave = 16'sd7179;
                8'd19: sin_qwave = 16'sd7571;
                8'd20: sin_qwave = 16'sd7962;
                8'd21: sin_qwave = 16'sd8351;
                8'd22: sin_qwave = 16'sd8739;
                8'd23: sin_qwave = 16'sd9126;
                8'd24: sin_qwave = 16'sd9512;
                8'd25: sin_qwave = 16'sd9896;
                8'd26: sin_qwave = 16'sd10278;
                8'd27: sin_qwave = 16'sd10659;
                8'd28: sin_qwave = 16'sd11039;
                8'd29: sin_qwave = 16'sd11417;
                8'd30: sin_qwave = 16'sd11793;
                8'd31: sin_qwave = 16'sd12167;
                8'd32: sin_qwave = 16'sd12539;
                8'd33: sin_qwave = 16'sd12910;
                8'd34: sin_qwave = 16'sd13279;
                8'd35: sin_qwave = 16'sd13645;
                8'd36: sin_qwave = 16'sd14010;
                8'd37: sin_qwave = 16'sd14372;
                8'd38: sin_qwave = 16'sd14732;
                8'd39: sin_qwave = 16'sd15090;
                8'd40: sin_qwave = 16'sd15446;
                8'd41: sin_qwave = 16'sd15800;
                8'd42: sin_qwave = 16'sd16151;
                8'd43: sin_qwave = 16'sd16499;
                8'd44: sin_qwave = 16'sd16846;
                8'd45: sin_qwave = 16'sd17189;
                8'd46: sin_qwave = 16'sd17530;
                8'd47: sin_qwave = 16'sd17869;
                8'd48: sin_qwave = 16'sd18204;
                8'd49: sin_qwave = 16'sd18537;
                8'd50: sin_qwave = 16'sd18868;
                8'd51: sin_qwave = 16'sd19195;
                8'd52: sin_qwave = 16'sd19519;
                8'd53: sin_qwave = 16'sd19841;
                8'd54: sin_qwave = 16'sd20159;
                8'd55: sin_qwave = 16'sd20475;
                8'd56: sin_qwave = 16'sd20787;
                8'd57: sin_qwave = 16'sd21096;
                8'd58: sin_qwave = 16'sd21403;
                8'd59: sin_qwave = 16'sd21705;
                8'd60: sin_qwave = 16'sd22005;
                8'd61: sin_qwave = 16'sd22301;
                8'd62: sin_qwave = 16'sd22594;
                8'd63: sin_qwave = 16'sd22884;
                8'd64: sin_qwave = 16'sd23170;
                8'd65: sin_qwave = 16'sd23452;
                8'd66: sin_qwave = 16'sd23731;
                8'd67: sin_qwave = 16'sd24007;
                8'd68: sin_qwave = 16'sd24279;
                8'd69: sin_qwave = 16'sd24547;
                8'd70: sin_qwave = 16'sd24811;
                8'd71: sin_qwave = 16'sd25072;
                8'd72: sin_qwave = 16'sd25329;
                8'd73: sin_qwave = 16'sd25582;
                8'd74: sin_qwave = 16'sd25832;
                8'd75: sin_qwave = 16'sd26077;
                8'd76: sin_qwave = 16'sd26319;
                8'd77: sin_qwave = 16'sd26556;
                8'd78: sin_qwave = 16'sd26790;
                8'd79: sin_qwave = 16'sd27019;
                8'd80: sin_qwave = 16'sd27245;
                8'd81: sin_qwave = 16'sd27466;
                8'd82: sin_qwave = 16'sd27683;
                8'd83: sin_qwave = 16'sd27896;
                8'd84: sin_qwave = 16'sd28105;
                8'd85: sin_qwave = 16'sd28310;
                8'd86: sin_qwave = 16'sd28510;
                8'd87: sin_qwave = 16'sd28706;
                8'd88: sin_qwave = 16'sd28898;
                8'd89: sin_qwave = 16'sd29085;
                8'd90: sin_qwave = 16'sd29268;
                8'd91: sin_qwave = 16'sd29447;
                8'd92: sin_qwave = 16'sd29621;
                8'd93: sin_qwave = 16'sd29791;
                8'd94: sin_qwave = 16'sd29956;
                8'd95: sin_qwave = 16'sd30117;
                8'd96: sin_qwave = 16'sd30273;
                8'd97: sin_qwave = 16'sd30424;
                8'd98: sin_qwave = 16'sd30571;
                8'd99: sin_qwave = 16'sd30714;
                8'd100: sin_qwave = 16'sd30852;
                8'd101: sin_qwave = 16'sd30985;
                8'd102: sin_qwave = 16'sd31113;
                8'd103: sin_qwave = 16'sd31237;
                8'd104: sin_qwave = 16'sd31356;
                8'd105: sin_qwave = 16'sd31470;
                8'd106: sin_qwave = 16'sd31580;
                8'd107: sin_qwave = 16'sd31685;
                8'd108: sin_qwave = 16'sd31785;
                8'd109: sin_qwave = 16'sd31880;
                8'd110: sin_qwave = 16'sd31971;
                8'd111: sin_qwave = 16'sd32057;
                8'd112: sin_qwave = 16'sd32137;
                8'd113: sin_qwave = 16'sd32213;
                8'd114: sin_qwave = 16'sd32285;
                8'd115: sin_qwave = 16'sd32351;
                8'd116: sin_qwave = 16'sd32412;
                8'd117: sin_qwave = 16'sd32469;
                8'd118: sin_qwave = 16'sd32521;
                8'd119: sin_qwave = 16'sd32567;
                8'd120: sin_qwave = 16'sd32609;
                8'd121: sin_qwave = 16'sd32646;
                8'd122: sin_qwave = 16'sd32678;
                8'd123: sin_qwave = 16'sd32705;
                8'd124: sin_qwave = 16'sd32728;
                8'd125: sin_qwave = 16'sd32745;
                8'd126: sin_qwave = 16'sd32757;
                8'd127: sin_qwave = 16'sd32765;
                default: sin_qwave = 16'sd32767;
            endcase
        end
    endfunction

    function automatic signed [15:0] eval_cos;
        input [31:0] ph_in;
        reg   [31:0] ph;
        reg   [1:0]  quad;
        reg   [6:0]  idx;
        reg   [5:0]  frac;
        reg   [7:0]  idx_a, idx_b;
        reg signed [15:0] va, vb;
        reg signed [23:0] interp;
        begin
            ph   = ph_in + 32'h4000_0000;
            quad = ph[31:30];
            idx  = ph[29:23];
            frac = ph[22:17];
            if (quad[0] == 1'b0) begin
                idx_a = {1'b0, idx};
                idx_b = {1'b0, idx} + 8'd1;
            end else begin
                idx_a = 8'd128 - {1'b0, idx};
                idx_b = 8'd127 - {1'b0, idx};
            end
            va     = sin_qwave(idx_a);
            vb     = sin_qwave(idx_b);
            interp = va + (((vb - va) * $signed({1'b0, frac})) >>> 6);
            eval_cos = quad[1] ? -interp[15:0] : interp[15:0];
        end
    endfunction

    // -------------------------------------------------------------------------
    // LFM Chirp Generator (3-stage pipelined NCO + amp scaling for 125+ MHz)
    // -------------------------------------------------------------------------
    reg        trig_d;
    wire       trig_rise = chirp_trig && !trig_d;
    reg [31:0] pri_cnt;
    reg [31:0] sample_cnt;
    reg [31:0] freq_acc;
    reg [31:0] phase_acc;
    reg        gen_active;

`ifdef MUTATE_CHIRP_SLOPE_SIGN
    wire signed [31:0] eff_df_ftw = -df_ftw;
`else
    wire signed [31:0] eff_df_ftw = df_ftw;
`endif

    // Stage 1: quarter-wave table lookup
    wire [31:0] ph_off   = phase_acc + 32'h4000_0000;
    wire [1:0]  st0_quad = ph_off[31:30];
    wire [6:0]  st0_idx  = ph_off[29:23];
    wire [5:0]  st0_frac = ph_off[22:17];
    wire [7:0]  st0_ia   = (st0_quad[0] == 1'b0) ? {1'b0, st0_idx} : (8'd128 - {1'b0, st0_idx});
    wire [7:0]  st0_ib   = (st0_quad[0] == 1'b0) ? ({1'b0, st0_idx} + 8'd1) : (8'd127 - {1'b0, st0_idx});

    reg signed [15:0] s1_va, s1_vb;
    reg        [5:0]  s1_frac;
    reg               s1_quad1;
    reg        [7:0]  s1_amp;
    reg               s1_active;

    // Stage 2a: signed delta-lookup multiply (absorbed cleanly into DSP48E1 D-A*B + PREG=1)
    reg signed [22:0] s1b_prod;
    reg signed [15:0] s1b_va;
    reg               s1b_quad1;
    reg        [7:0]  s1b_amp;
    reg               s1b_active;

    // Stage 2b: add base sample + apply quadrant sign -> signed cos
    wire signed [16:0] s1b_sum = s1b_va + $signed(s1b_prod[22:6]);
    reg  signed [15:0] s2_cos;
    reg         [7:0]  s2_amp;
    reg                s2_active;

    // Stage 3: amplitude scaling -> unsigned 8-bit DAC code aligned with chirp_active
    (* use_dsp = "no" *) wire signed [24:0] s2_scaled = s2_cos * $signed({1'b0, s2_amp});
    wire signed [7:0]  s2_s8     = s2_scaled[23:16];
    wire        [7:0]  s2_u8     = {~s2_s8[7], s2_s8[6:0]};

    always @(posedge dac_clk) begin
        if (dac_rst || !chirp_enable) begin
            trig_d       <= 1'b0;
            gen_active   <= 1'b0;
            chirp_active <= 1'b0;
            pri_cnt      <= 32'd0;
            sample_cnt   <= 32'd0;
            pulse_cnt    <= 32'd0;
            freq_acc     <= 32'd0;
            phase_acc    <= 32'd0;
            s1_va        <= 16'sd0;
            s1_vb        <= 16'sd0;
            s1_frac      <= 6'd0;
            s1_quad1     <= 1'b0;
            s1_amp       <= 8'd0;
            s1_active    <= 1'b0;
            s1b_prod     <= 23'sd0;
            s1b_va       <= 16'sd0;
            s1b_quad1    <= 1'b0;
            s1b_amp      <= 8'd0;
            s1b_active   <= 1'b0;
            s2_cos       <= 16'sd0;
            s2_amp       <= 8'd0;
            s2_active    <= 1'b0;
            dacr_d       <= 8'h80;
        end else begin
            trig_d <= chirp_trig;

            if (!gen_active) begin
                if (trig_rise || ((pri_len != 32'd0) && (pri_cnt == 32'd0))) begin
                    gen_active <= (pulse_len != 32'd0);
                    sample_cnt <= 32'd0;
                    freq_acc   <= f0_ftw;
                    phase_acc  <= 32'd0;
                    pri_cnt    <= (pri_len > 32'd1) ? (pri_len - 32'd1) : 32'd0;
                    pulse_cnt  <= pulse_cnt + 32'd1;
                end else if (pri_cnt != 32'd0) begin
                    pri_cnt <= pri_cnt - 32'd1;
                end
            end else begin
                if (pri_cnt != 32'd0)
                    pri_cnt <= pri_cnt - 32'd1;

                if ((sample_cnt + 32'd1) >= pulse_len) begin
                    gen_active <= 1'b0;
                end else begin
                    sample_cnt <= sample_cnt + 32'd1;
                    freq_acc   <= $signed(freq_acc) + eff_df_ftw;
                    phase_acc  <= phase_acc + freq_acc;
                end
            end

            // Pipeline advance
            s1_va      <= sin_qwave(st0_ia);
            s1_vb      <= sin_qwave(st0_ib);
            s1_frac    <= st0_frac;
            s1_quad1   <= st0_quad[1];
            s1_amp     <= amp_scale;
            s1_active  <= gen_active;

            s1b_prod   <= (s1_vb - s1_va) * $signed({1'b0, s1_frac});
            s1b_va     <= s1_va;
            s1b_quad1  <= s1_quad1;
            s1b_amp    <= s1_amp;
            s1b_active <= s1_active;

            s2_cos     <= s1b_quad1 ? -s1b_sum[15:0] : s1b_sum[15:0];
            s2_amp     <= s1b_amp;
            s2_active  <= s1b_active;

            chirp_active <= s2_active;
            dacr_d       <= s2_active ? s2_u8 : 8'h80;
        end
    end

    // -------------------------------------------------------------------------
    // Center-aligned AD9708 CLOCK Forwarding via ODDR
    // -------------------------------------------------------------------------
`ifdef MUTATE_DAC_CLK_EDGE_WRONG
    localparam [0:0] CLK_D1 = 1'b1;
    localparam [0:0] CLK_D2 = 1'b0;
`else
    localparam [0:0] CLK_D1 = 1'b0;
    localparam [0:0] CLK_D2 = 1'b1;
`endif

    ODDR #(
        .DDR_CLK_EDGE ("SAME_EDGE"),
        .INIT         (1'b0),
        .SRTYPE       ("SYNC")
    ) u_oddr_dacr_clk (
        .Q  (dacr_clk),
        .C  (dac_clk),
        .CE (1'b1),
        .D1 (CLK_D1),
        .D2 (CLK_D2),
        .R  (1'b0),
        .S  (1'b0)
    );
endmodule
