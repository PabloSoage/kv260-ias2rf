// SPDX-License-Identifier: BSD-2-Clause
// Dual-Channel AD9253 SDR Digital Down-Converter (NCO + CIC3 + Halfband FIR + Async FIFO + Packetizer)
// Consumes 14-bit dual-channel ADC samples in adc_clk (= adcs_clkdiv) domain, performs
// independent 32-bit complex NCO tuning, 3-stage CIC + 15-tap Halfband decimation (programmable ratio),
// packs {Q1, I1, Q0, I0} 64-bit words across a Gray-coded dual-clock BRAM FIFO into link_clk,
// and emits LINK_PROTOCOL.md Section 6.1 packets onto link_pcs_tx (Stream IDs 8'h04 / 8'h05).

`timescale 1ns/1ps

module sdr_ddc_nco (
    input  wire        clk,
    input  wire        rst,
    input  wire        ce,
    input  wire [31:0] ftw,
    output reg         out_valid,
    output reg  signed [15:0] cos_o,
    output reg  signed [15:0] sin_o
);
    reg [31:0] phase;

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

    function automatic signed [15:0] eval_sin;
        input [31:0] ph;
        reg   [1:0]  quad;
        reg   [6:0]  idx;
        reg   [5:0]  frac;
        reg   [7:0]  idx_a, idx_b;
        reg signed [15:0] va, vb;
        reg signed [23:0] interp;
        begin
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
            eval_sin = quad[1] ? -interp[15:0] : interp[15:0];
        end
    endfunction

    always @(posedge clk) begin
        if (rst) begin
            phase     <= 32'd0;
            out_valid <= 1'b0;
            cos_o     <= 16'sd32767;
            sin_o     <= 16'sd0;
        end else begin
            out_valid <= ce;
            if (ce) begin
                cos_o <= eval_sin(phase + 32'h4000_0000);
                sin_o <= eval_sin(phase);
                phase <= phase + ftw;
            end
        end
    end
endmodule

module sdr_ddc_ch #(
    parameter integer FIFO_AW = 9 // 512 x 64-bit deep dual-clock BRAM FIFO
) (
    input  wire        adc_clk,
    input  wire        adc_rst,
    input  wire        ch_en,
    input  wire        sample_valid,
    input  wire signed [13:0] sample_in,
    input  wire [31:0] nco_ftw,
    input  wire [15:0] decim_ratio,

    // Link-clock FWFT FIFO output
    input  wire        link_clk,
    input  wire        link_rst,
    output wire        fifo_valid,
    output wire [63:0] fifo_data,
    input  wire        fifo_ready,
    output wire [FIFO_AW:0] fifo_avail,
    output reg  [23:0] dropped_pairs_link
);
    localparam integer FIFO_DEPTH = (1 << FIFO_AW);

    // -------------------------------------------------------------------------
    // Dynamic CIC ratio & normalization shift (exact for 2^k, [0.5..1.0) otherwise)
    // -------------------------------------------------------------------------
    wire        use_hb = (decim_ratio >= 16'd4) && (decim_ratio[0] == 1'b0);
    wire [15:0] r_cic  = use_hb ? (decim_ratio >> 1) :
                         ((decim_ratio < 16'd2) ? 16'd2 : decim_ratio);

    reg [47:0] r_cic_cube;
    reg [5:0]  norm_shift;
    integer    b;

    always @(posedge adc_clk) begin
        r_cic_cube <= r_cic * r_cic * r_cic;
        norm_shift <= 6'd3;
        for (b = 3; b <= 36; b = b + 1) begin
            if (r_cic_cube > (48'd1 << (b - 1)))
                norm_shift <= b[5:0];
        end
    end

    // -------------------------------------------------------------------------
    // NCO & Complex Mixer (down-conversion: x * exp(-j*phi))
    // -------------------------------------------------------------------------
    wire               nco_valid;
    wire signed [15:0] nco_cos, nco_sin;
    reg  signed [13:0] sample_d1;
    reg                mix_valid;
    reg  signed [15:0] mix_i, mix_q;
    reg  signed [31:0] mult_i, mult_q;

    always @(posedge adc_clk) begin
        if (adc_rst)
            sample_d1 <= 14'sd0;
        else if (sample_valid && ch_en)
            sample_d1 <= sample_in;
    end

    sdr_ddc_nco u_nco (
        .clk       (adc_clk),
        .rst       (adc_rst),
        .ce        (sample_valid && ch_en),
        .ftw       (nco_ftw),
        .out_valid (nco_valid),
        .cos_o     (nco_cos),
        .sin_o     (nco_sin)
    );

    always @(posedge adc_clk) begin
        if (adc_rst) begin
            mix_valid <= 1'b0;
            mix_i     <= 16'sd0;
            mix_q     <= 16'sd0;
        end else begin
            mix_valid <= nco_valid;
            if (nco_valid) begin
                mult_i = $signed({sample_d1, 2'b00}) * nco_cos;
                mult_q = -$signed({sample_d1, 2'b00}) * nco_sin;
                mix_i  <= mult_i >>> 15;
                mix_q  <= mult_q >>> 15;
            end
        end
    end

    // -------------------------------------------------------------------------
    // 3-Stage CIC Decimator (N=3, M=1, 52-bit accumulators)
    // -------------------------------------------------------------------------
    reg signed [51:0] i1_i, i2_i, i3_i;
    reg signed [51:0] i1_q, i2_q, i3_q;
    reg [15:0]        cic_cnt;
    reg               cic_strobe;
    reg signed [51:0] c1_i_d, c2_i_d, c3_i_d;
    reg signed [51:0] c1_q_d, c2_q_d, c3_q_d;
    reg               cic_out_valid;
    reg signed [17:0] cic_out_i, cic_out_q;

    reg signed [51:0] d1_i, d2_i, d3_i;
    reg signed [51:0] d1_q, d2_q, d3_q;
    reg signed [51:0] scaled_i, scaled_q;

    always @(posedge adc_clk) begin
        if (adc_rst) begin
            i1_i <= 52'sd0; i2_i <= 52'sd0; i3_i <= 52'sd0;
            i1_q <= 52'sd0; i2_q <= 52'sd0; i3_q <= 52'sd0;
            c1_i_d <= 52'sd0; c2_i_d <= 52'sd0; c3_i_d <= 52'sd0;
            c1_q_d <= 52'sd0; c2_q_d <= 52'sd0; c3_q_d <= 52'sd0;
            cic_cnt       <= 16'd0;
            cic_strobe    <= 1'b0;
            cic_out_valid <= 1'b0;
            cic_out_i     <= 18'sd0;
            cic_out_q     <= 18'sd0;
        end else begin
            cic_strobe    <= 1'b0;
            cic_out_valid <= 1'b0;

            if (mix_valid) begin
                i1_i <= i1_i + {{36{mix_i[15]}}, mix_i};
                i2_i <= i2_i + i1_i;
                i3_i <= i3_i + i2_i;

                i1_q <= i1_q + {{36{mix_q[15]}}, mix_q};
                i2_q <= i2_q + i1_q;
                i3_q <= i3_q + i2_q;

                if (cic_cnt >= (r_cic - 16'd1)) begin
                    cic_cnt    <= 16'd0;
                    cic_strobe <= 1'b1;
                end else begin
                    cic_cnt <= cic_cnt + 16'd1;
                end
            end

            if (cic_strobe) begin
                d1_i   = i3_i - c1_i_d;
                c1_i_d <= i3_i;
                d2_i   = d1_i - c2_i_d;
                c2_i_d <= d1_i;
                d3_i   = d2_i - c3_i_d;
                c3_i_d <= d2_i;

                d1_q   = i3_q - c1_q_d;
                c1_q_d <= i3_q;
                d2_q   = d1_q - c2_q_d;
                c2_q_d <= d1_q;
                d3_q   = d2_q - c3_q_d;
                c3_q_d <= d2_q;

                scaled_i = d3_i >>> norm_shift;
                scaled_q = d3_q >>> norm_shift;
                cic_out_i     <= scaled_i[17:0];
                cic_out_q     <= scaled_q[17:0];
                cic_out_valid <= 1'b1;
            end
        end
    end

    // -------------------------------------------------------------------------
    // 15-Tap Symmetric Halfband Decimate-by-2 FIR (Q15 DC gain = 32768)
    // Used whenever decim_ratio >= 4 and even; bypassed otherwise.
    // Taps: h[+-1]=+10532, h[+-3]=-3240, h[+-5]=+1220, h[+-7]=-320, h[0]=16384
    // -------------------------------------------------------------------------
    function automatic signed [15:0] sat16;
        input signed [20:0] val;
        begin
            if (val > 21'sd32767)       sat16 = 16'sd32767;
            else if (val < -21'sd32768) sat16 = -16'sd32768;
            else                        sat16 = val[15:0];
        end
    endfunction

    reg signed [17:0] hb_i [0:14];
    reg signed [17:0] hb_q [0:14];
    reg               hb_phase;
    reg               iq_valid;
    reg signed [15:0] iq_i, iq_q;
    integer           k;

    reg signed [35:0] hb_acc_i, hb_acc_q;

    always @(posedge adc_clk) begin
        if (adc_rst) begin
            for (k = 0; k < 15; k = k + 1) begin
                hb_i[k] <= 18'sd0;
                hb_q[k] <= 18'sd0;
            end
            hb_phase <= 1'b0;
            iq_valid <= 1'b0;
            iq_i     <= 16'sd0;
            iq_q     <= 16'sd0;
        end else begin
            iq_valid <= 1'b0;
            if (cic_out_valid) begin
                if (!use_hb) begin
                    iq_valid <= 1'b1;
                    iq_i     <= sat16({{3{cic_out_i[17]}}, cic_out_i});
                    iq_q     <= sat16({{3{cic_out_q[17]}}, cic_out_q});
                end else begin
                    for (k = 14; k > 0; k = k - 1) begin
                        hb_i[k] <= hb_i[k - 1];
                        hb_q[k] <= hb_q[k - 1];
                    end
                    hb_i[0]  <= cic_out_i;
                    hb_q[0]  <= cic_out_q;
                    hb_phase <= ~hb_phase;

                    if (hb_phase == 1'b1) begin
                        // Compute using current incoming sample as index 0 and shifted delay line
                        hb_acc_i = ($signed(hb_i[6]) <<< 14) +
                                   $signed(18'sd10532) * ($signed(hb_i[5]) + $signed(hb_i[7])) -
                                   $signed(18'sd3240)  * ($signed(hb_i[3]) + $signed(hb_i[9])) +
                                   $signed(18'sd1220)  * ($signed(hb_i[1]) + $signed(hb_i[11])) -
                                   $signed(18'sd320)   * ($signed(cic_out_i) + $signed(hb_i[13])) +
                                   36'sd16384;
                        hb_acc_q = ($signed(hb_q[6]) <<< 14) +
                                   $signed(18'sd10532) * ($signed(hb_q[5]) + $signed(hb_q[7])) -
                                   $signed(18'sd3240)  * ($signed(hb_q[3]) + $signed(hb_q[9])) +
                                   $signed(18'sd1220)  * ($signed(hb_q[1]) + $signed(hb_q[11])) -
                                   $signed(18'sd320)   * ($signed(cic_out_q) + $signed(hb_q[13])) +
                                   36'sd16384;
                        iq_valid <= 1'b1;
                        iq_i     <= sat16(hb_acc_i[35:15]);
                        iq_q     <= sat16(hb_acc_q[35:15]);
                    end
                end
            end
        end
    end

    // -------------------------------------------------------------------------
    // 32-bit IQ -> 64-bit Pair Packer (little-endian: {Q1, I1, Q0, I0})
    // -------------------------------------------------------------------------
    reg [31:0] iq_half;
    reg        half_loaded;
    reg        wr_en;
    reg [63:0] wr_data;

    always @(posedge adc_clk) begin
        if (adc_rst) begin
            iq_half     <= 32'd0;
            half_loaded <= 1'b0;
            wr_en       <= 1'b0;
            wr_data     <= 64'd0;
        end else begin
            wr_en <= 1'b0;
            if (iq_valid) begin
                if (!half_loaded) begin
                    iq_half     <= {iq_q, iq_i};
                    half_loaded <= 1'b1;
                end else begin
                    wr_data     <= {iq_q, iq_i, iq_half};
                    wr_en       <= 1'b1;
                    half_loaded <= 1'b0;
                end
            end
        end
    end

    // -------------------------------------------------------------------------
    // Dual-Clock Gray-Coded BRAM Async FIFO + 2-Entry FWFT Bridge
    // -------------------------------------------------------------------------
    function automatic [FIFO_AW:0] bin2gray;
        input [FIFO_AW:0] bin;
        begin
            bin2gray = bin ^ (bin >> 1);
        end
    endfunction

    function automatic [FIFO_AW:0] gray2bin;
        input [FIFO_AW:0] g;
        integer idx;
        begin
            gray2bin[FIFO_AW] = g[FIFO_AW];
            for (idx = FIFO_AW - 1; idx >= 0; idx = idx - 1)
                gray2bin[idx] = gray2bin[idx + 1] ^ g[idx];
        end
    endfunction

    (* ram_style = "block" *)
    reg [63:0] mem [0:FIFO_DEPTH-1];

    reg [FIFO_AW:0] wr_ptr_bin, wr_ptr_gray;
    reg [FIFO_AW:0] rd_ptr_bin_sync1, rd_ptr_bin_sync2;
    reg [FIFO_AW:0] rd_ptr_gray_sync1, rd_ptr_gray_sync2;

    reg [FIFO_AW:0] rd_ptr_bin, rd_ptr_gray;
    reg [FIFO_AW:0] wr_ptr_gray_sync1, wr_ptr_gray_sync2;

    reg [23:0] dropped_pairs_adc;
    reg [23:0] drop_sync1, drop_sync2;

    wire [FIFO_AW:0] rd_ptr_bin_adc = gray2bin(rd_ptr_gray_sync2);
    wire             fifo_full      = (wr_ptr_gray == {~rd_ptr_gray_sync2[FIFO_AW:FIFO_AW-1], rd_ptr_gray_sync2[FIFO_AW-2:0]});

    always @(posedge adc_clk) begin
        if (adc_rst) begin
            wr_ptr_bin        <= {(FIFO_AW+1){1'b0}};
            wr_ptr_gray       <= {(FIFO_AW+1){1'b0}};
            rd_ptr_gray_sync1 <= {(FIFO_AW+1){1'b0}};
            rd_ptr_gray_sync2 <= {(FIFO_AW+1){1'b0}};
            dropped_pairs_adc <= 24'd0;
        end else begin
            rd_ptr_gray_sync1 <= rd_ptr_gray;
            rd_ptr_gray_sync2 <= rd_ptr_gray_sync1;
            if (wr_en) begin
                if (!fifo_full) begin
                    mem[wr_ptr_bin[FIFO_AW-1:0]] <= wr_data;
                    wr_ptr_bin  <= wr_ptr_bin + 1'b1;
                    wr_ptr_gray <= bin2gray(wr_ptr_bin + 1'b1);
                end else begin
                    dropped_pairs_adc <= dropped_pairs_adc + 24'd1;
                end
            end
        end
    end

    // Read side + 2-entry FWFT register queue in link_clk domain
    wire [FIFO_AW:0] wr_ptr_bin_link = gray2bin(wr_ptr_gray_sync2);
    wire             bram_empty      = (rd_ptr_bin == wr_ptr_bin_link);

    reg        bram_rd_vld;
    reg [63:0] bram_dout;

    reg [63:0] fwft_q0, fwft_q1;
    reg [1:0]  fwft_cnt;

    wire [FIFO_AW:0] bram_words   = wr_ptr_bin_link - rd_ptr_bin;
    // Only request from BRAM if total buffered + in-flight <= 2
    wire [1:0] inflight_sum = fwft_cnt + bram_rd_vld;
    wire       bram_rd_en   = !bram_empty && (inflight_sum < 2'd2);

    assign fifo_valid = (fwft_cnt != 2'd0);
    assign fifo_data  = fwft_q0;
    assign fifo_avail = bram_words + fwft_cnt + bram_rd_vld;

    always @(posedge link_clk) begin
        if (link_rst) begin
            wr_ptr_gray_sync1  <= {(FIFO_AW+1){1'b0}};
            wr_ptr_gray_sync2  <= {(FIFO_AW+1){1'b0}};
            rd_ptr_bin         <= {(FIFO_AW+1){1'b0}};
            rd_ptr_gray        <= {(FIFO_AW+1){1'b0}};
            bram_rd_vld        <= 1'b0;
            bram_dout          <= 64'd0;
            fwft_q0            <= 64'd0;
            fwft_q1            <= 64'd0;
            fwft_cnt           <= 2'd0;
            drop_sync1         <= 24'd0;
            drop_sync2         <= 24'd0;
            dropped_pairs_link <= 24'd0;
        end else begin
            wr_ptr_gray_sync1  <= wr_ptr_gray;
            wr_ptr_gray_sync2  <= wr_ptr_gray_sync1;
            drop_sync1         <= dropped_pairs_adc;
            drop_sync2         <= drop_sync1;
            dropped_pairs_link <= drop_sync2;

            // BRAM 1-cycle synchronous read
            bram_rd_vld <= bram_rd_en;
            if (bram_rd_en) begin
                bram_dout   <= mem[rd_ptr_bin[FIFO_AW-1:0]];
                rd_ptr_bin  <= rd_ptr_bin + 1'b1;
                rd_ptr_gray <= bin2gray(rd_ptr_bin + 1'b1);
            end

            // 2-entry FWFT queue push/pop
            case ({bram_rd_vld, (fifo_valid && fifo_ready)})
                2'b10: begin // push only
                    if (fwft_cnt == 2'd0)
                        fwft_q0 <= bram_dout;
                    else
                        fwft_q1 <= bram_dout;
                    fwft_cnt <= fwft_cnt + 2'd1;
                end
                2'b01: begin // pop only
                    fwft_q0  <= fwft_q1;
                    fwft_cnt <= fwft_cnt - 2'd1;
                end
                2'b11: begin // simultaneous push & pop
                    if (fwft_cnt == 2'd1) begin
                        fwft_q0 <= bram_dout;
                    end else begin
                        fwft_q0 <= fwft_q1;
                        fwft_q1 <= bram_dout;
                    end
                end
                default: ;
            endcase
        end
    end
endmodule

module sdr_ddc #(
    parameter [7:0] STREAM_ID_A = 8'h04,
    parameter [7:0] STREAM_ID_B = 8'h05,
    parameter integer FIFO_AW   = 9
) (
    // AD9253 capture clock domain (clk_div = 2*f_S)
    input  wire        adc_clk,
    input  wire        adc_rst,
    input  wire        sample_valid,
    input  wire signed [13:0] sample_a,
    input  wire signed [13:0] sample_b,

    // Runtime configuration (quasi-static or synced from link_clk)
    input  wire [1:0]  ch_enable,      // [0]=Ch A, [1]=Ch B
    input  wire [31:0] nco_ftw_a,
    input  wire [31:0] nco_ftw_b,
    input  wire [15:0] decim_ratio,    // >= 2 (even >= 4 engages Halfband FIR)
    input  wire [9:0]  words_per_pkt,  // 64-bit words per packet (1..512; pkt_len = 8*words_per_pkt)

    // Link TX packetizer interface (link_clk = 125 MHz)
    input  wire        link_clk,
    input  wire        link_rst,
    input  wire [63:0] timestamp_cnt,
    output reg         pkt_valid,
    input  wire        pkt_ready,
    output reg         pkt_sop,
    output reg         pkt_eop,
    output reg  [7:0]  pkt_stream_id,
    output reg  [15:0] pkt_len,
    output reg  [31:0] pkt_seq,
    output reg  [63:0] pkt_timestamp,
    output wire [63:0] pkt_data,
    output wire [23:0] dropped_cnt
);
    wire               vld_a, vld_b;
    wire [63:0]        dat_a, dat_b;
    wire               rdy_a, rdy_b;
    wire [FIFO_AW:0]   avail_a, avail_b;
    wire [23:0]        drop_a, drop_b;

    sdr_ddc_ch #(.FIFO_AW(FIFO_AW)) u_ch_a (
        .adc_clk            (adc_clk),
        .adc_rst            (adc_rst),
        .ch_en              (ch_enable[0]),
        .sample_valid       (sample_valid),
        .sample_in          (sample_a),
        .nco_ftw            (nco_ftw_a),
        .decim_ratio        (decim_ratio),
        .link_clk           (link_clk),
        .link_rst           (link_rst),
        .fifo_valid         (vld_a),
        .fifo_data          (dat_a),
        .fifo_ready         (rdy_a),
        .fifo_avail         (avail_a),
        .dropped_pairs_link (drop_a)
    );

    sdr_ddc_ch #(.FIFO_AW(FIFO_AW)) u_ch_b (
        .adc_clk            (adc_clk),
        .adc_rst            (adc_rst),
        .ch_en              (ch_enable[1]),
        .sample_valid       (sample_valid),
        .sample_in          (sample_b),
        .nco_ftw            (nco_ftw_b),
        .decim_ratio        (decim_ratio),
        .link_clk           (link_clk),
        .link_rst           (link_rst),
        .fifo_valid         (vld_b),
        .fifo_data          (dat_b),
        .fifo_ready         (rdy_b),
        .fifo_avail         (avail_b),
        .dropped_pairs_link (drop_b)
    );

    assign dropped_cnt = drop_a + drop_b;

    // -------------------------------------------------------------------------
    // Round-Robin Packetizer Arbiter (link_clk)
    // -------------------------------------------------------------------------
    localparam [1:0] TX_IDLE = 2'd0,
                     TX_SEND = 2'd1;

    wire [9:0] eff_words = (words_per_pkt == 10'd0) ? 10'd16 :
                           (words_per_pkt > 10'd512) ? 10'd512 : words_per_pkt;

    wire ready_a = ch_enable[0] && (avail_a >= {1'b0, eff_words});
    wire ready_b = ch_enable[1] && (avail_b >= {1'b0, eff_words});

    reg [1:0]  tx_state;
    reg        cur_ch;       // 0 = Ch A, 1 = Ch B
    reg        rr_pref;      // round-robin next preference
    reg [9:0]  word_idx;
    reg [9:0]  pkt_words_lat;
    reg [31:0] seq_a, seq_b;

    assign rdy_a    = (tx_state == TX_SEND) && (cur_ch == 1'b0) && pkt_ready && pkt_valid;
    assign rdy_b    = (tx_state == TX_SEND) && (cur_ch == 1'b1) && pkt_ready && pkt_valid;
    assign pkt_data = (cur_ch == 1'b0) ? dat_a : dat_b;

    always @* begin
        pkt_valid     = (tx_state == TX_SEND) && ((cur_ch == 1'b0) ? vld_a : vld_b);
        pkt_sop       = (tx_state == TX_SEND) && (word_idx == 10'd0);
        pkt_eop       = (tx_state == TX_SEND) && (word_idx == (pkt_words_lat - 10'd1));
        pkt_stream_id = (cur_ch == 1'b0) ? STREAM_ID_A : STREAM_ID_B;
        pkt_len       = {3'b000, pkt_words_lat, 3'b000};
        pkt_seq       = (cur_ch == 1'b0) ? seq_a : seq_b;
    end

    always @(posedge link_clk) begin
        if (link_rst) begin
            tx_state      <= TX_IDLE;
            cur_ch        <= 1'b0;
            rr_pref       <= 1'b0;
            word_idx      <= 10'd0;
            pkt_words_lat <= 10'd16;
            pkt_timestamp <= 64'd0;
            seq_a         <= 32'd0;
            seq_b         <= 32'd0;
        end else begin
            case (tx_state)
                TX_IDLE: begin
                    if (ready_a || ready_b) begin
                        if ((rr_pref == 1'b0 && ready_a) || !ready_b) begin
                            cur_ch  <= 1'b0;
                            rr_pref <= 1'b1;
                        end else begin
                            cur_ch  <= 1'b1;
                            rr_pref <= 1'b0;
                        end
                        pkt_words_lat <= eff_words;
                        pkt_timestamp <= timestamp_cnt;
                        word_idx      <= 10'd0;
                        tx_state      <= TX_SEND;
                    end
                end

                TX_SEND: begin
                    if (pkt_valid && pkt_ready) begin
                        if (word_idx == (pkt_words_lat - 10'd1)) begin
                            if (cur_ch == 1'b0)
                                seq_a <= seq_a + 32'd1;
                            else
                                seq_b <= seq_b + 32'd1;
                            tx_state <= TX_IDLE;
                        end else begin
                            word_idx <= word_idx + 10'd1;
                        end
                    end
                end

                default: tx_state <= TX_IDLE;
            endcase
        end
    end
endmodule
