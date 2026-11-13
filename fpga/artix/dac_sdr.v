// SPDX-License-Identifier: BSD-2-Clause
// AD9767 Dual 14-bit Interleaved SDR Transmit Path (FIFO + Underrun Counter + Interleaver)
//
// AD9767 Interleaved Mode (MODE pin = 0 on PCB, 3.3 V LVCMOS Bank 34):
//   DACS_IQSEL   : 1 = DAC1 (I channel -> IF_TX_A), 0 = DAC2 (Q channel -> IF_TX_C)
//                  Must ONLY change when both DACS_IQWRT and DACS_IQCLK are low.
//   DACS_IQWRT   : Rising edge latches DACS_D[13:0] & DACS_IQSEL (t_S >= 2.0 ns, t_H >= 1.5 ns, t_LPW >= 3.5 ns)
//   DACS_IQCLK   : Internally divided by 2; rising edge occurs before or with IQWRT
//   DACS_IQRESET : High holds internal /2 divider in reset; on transition low, next rising IQCLK
//                  updates both DAC1 (I) and DAC2 (Q) outputs simultaneously, then every other IQCLK.
//
// Input interface (link_clk): 64-bit packed complex baseband words {Q1[15:0], I1[15:0], Q0[15:0], I0[15:0]},
// matching LINK_PROTOCOL Section 6.1 / sdr_ddc format; serialized 64 -> 32b across a Gray-coded BRAM
// async FIFO into dac_clk (two dac_clk cycles per I or Q word -> 4 dac_clk cycles per IQ pair).

`timescale 1ns/1ps

module dac_sdr #(
    parameter integer FIFO_AW = 9 // 512 x 32-bit deep dual-clock BRAM FIFO
) (
    // Link RX / Host TX stream interface (link_clk = 125 MHz)
    input  wire        link_clk,
    input  wire        link_rst,
    input  wire        s_valid,
    output wire        s_ready,
    input  wire [63:0] s_data,        // {Q1[15:0], I1[15:0], Q0[15:0], I0[15:0]}

    // DAC transmit clock domain (e.g. 125 MHz -> 31.25 MSPS complex IQ / 62.5 MHz IQCLK)
    input  wire        dac_clk,
    input  wire        dac_rst,
    input  wire        tx_enable,

    // Status & diagnostics
    output reg  [31:0] underflow_cnt, // Counts IQ sample intervals where tx_enable=1 & FIFO empty
    output wire [FIFO_AW:0] fifo_level_link,

    // AD9767 Interleaved Pins (Bank 34 LVCMOS33)
    output reg  [13:0] dacs_d,
    output wire        dacs_iqclk,
    output wire        dacs_iqwrt,
    output reg         dacs_iqsel,
    output reg         dacs_iqreset
);
    localparam integer FIFO_DEPTH = (1 << FIFO_AW);

    // -------------------------------------------------------------------------
    // 64-bit -> 32-bit Unpacker + Gray-Coded Dual-Clock BRAM Async FIFO
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
    reg [63:0] mem [0:FIFO_DEPTH-1]; // Dual packed IQ pairs: {Q1[15:0], I1[15:0], Q0[15:0], I0[15:0]}

    reg [FIFO_AW:0] wr_ptr_bin, wr_ptr_gray;
    reg [FIFO_AW:0] rd_ptr_gray_sync1, rd_ptr_gray_sync2;

    reg [FIFO_AW:0] rd_ptr_bin, rd_ptr_gray;
    reg [FIFO_AW:0] wr_ptr_gray_sync1, wr_ptr_gray_sync2;

    wire [FIFO_AW:0] rd_ptr_bin_link = gray2bin(rd_ptr_gray_sync2);
    assign fifo_level_link = wr_ptr_bin - rd_ptr_bin_link;

    wire fifo_full = (wr_ptr_bin == {~rd_ptr_bin_link[FIFO_AW], rd_ptr_bin_link[FIFO_AW-1:0]});

    // Accept one 64-bit (2x IQ) word every link_clk cycle without backpressure bubbles
    assign s_ready = !fifo_full;

    always @(posedge link_clk) begin
        if (link_rst) begin
            wr_ptr_bin        <= {(FIFO_AW+1){1'b0}};
            wr_ptr_gray       <= {(FIFO_AW+1){1'b0}};
            rd_ptr_gray_sync1 <= {(FIFO_AW+1){1'b0}};
            rd_ptr_gray_sync2 <= {(FIFO_AW+1){1'b0}};
        end else begin
            rd_ptr_gray_sync1 <= rd_ptr_gray;
            rd_ptr_gray_sync2 <= rd_ptr_gray_sync1;

            if (s_valid && !fifo_full) begin
                mem[wr_ptr_bin[FIFO_AW-1:0]] <= s_data;
                wr_ptr_bin  <= wr_ptr_bin + 1'b1;
                wr_ptr_gray <= bin2gray(wr_ptr_bin + 1'b1);
            end
        end
    end

    // -------------------------------------------------------------------------
    // Read Side & Interleaved AD9767 Serializer (dac_clk domain)
    // -------------------------------------------------------------------------
    wire [FIFO_AW:0] wr_ptr_bin_dac = gray2bin(wr_ptr_gray_sync2);
    wire             fifo_empty     = (rd_ptr_bin == wr_ptr_bin_dac);

    reg [1:0]  ph; // 0: I setup, 1: I strobe, 2: Q setup, 3: Q strobe
    reg        sync_done;
    reg [63:0] rd_word_reg;
    reg        rd_has_word;
    reg        half_sel;   // 0 = lower 32b (pair 0), 1 = upper 32b (pair 1)
    reg [13:0] cur_i_s, cur_q_s;
    reg        iqclk_d1, iqclk_d2;
    reg        iqwrt_d1, iqwrt_d2;

    wire [31:0] active_pair = half_sel ? rd_word_reg[63:32] : rd_word_reg[31:0];

    // Map signed 14-bit [-8192..+8191] -> unsigned straight offset binary [0..16383]
    function automatic [13:0] to_offset14;
        input signed [13:0] s;
        begin
            to_offset14 = {~s[13], s[12:0]};
        end
    endfunction

    always @(posedge dac_clk) begin
        if (dac_rst || !tx_enable) begin
            wr_ptr_gray_sync1 <= {(FIFO_AW+1){1'b0}};
            wr_ptr_gray_sync2 <= {(FIFO_AW+1){1'b0}};
            rd_ptr_bin        <= {(FIFO_AW+1){1'b0}};
            rd_ptr_gray       <= {(FIFO_AW+1){1'b0}};
            underflow_cnt     <= 32'd0;
            ph                <= 2'd0;
            sync_done         <= 1'b0;
            rd_word_reg       <= 64'd0;
            rd_has_word       <= 1'b0;
            half_sel          <= 1'b0;
            cur_i_s           <= 14'sd0;
            cur_q_s           <= 14'sd0;
            dacs_d            <= 14'h2000;
            dacs_iqsel        <= 1'b1;
            dacs_iqreset      <= 1'b1;
            iqclk_d1          <= 1'b0;
            iqclk_d2          <= 1'b0;
            iqwrt_d1          <= 1'b0;
            iqwrt_d2          <= 1'b0;
        end else begin
            wr_ptr_gray_sync1 <= wr_ptr_gray;
            wr_ptr_gray_sync2 <= wr_ptr_gray_sync1;
            ph <= ph + 2'd1;

            case (ph)
                2'd0: begin
                    // ph=0 (at t=0T): launch I & IQSEL=1 now; schedule I strobe on ODDR for next cycle (t=1T..1.5T)
                    if (!sync_done) begin
                        dacs_iqreset <= 1'b1;
                        cur_i_s      <= 14'sd0;
                        cur_q_s      <= 14'sd0;
                        dacs_d       <= 14'h2000;
                    end else begin
                        dacs_iqreset <= 1'b0;
                        if (rd_has_word) begin
                            cur_i_s <= $signed(active_pair[15:2]);
                            cur_q_s <= $signed(active_pair[31:18]);
`ifdef MUTATE_IQ_SWAP
                            dacs_d  <= to_offset14($signed(active_pair[31:18]));
`else
                            dacs_d  <= to_offset14($signed(active_pair[15:2]));
`endif
                        end else begin
                            cur_i_s       <= 14'sd0;
                            cur_q_s       <= 14'sd0;
                            dacs_d        <= 14'h2000;
                            underflow_cnt <= underflow_cnt + 32'd1;
                        end
                    end

                    dacs_iqsel <= 1'b1; // 1 = DAC1 (I)
`ifdef MUTATE_DAC_CLK_EDGE_WRONG
                    iqclk_d1 <= 1'b0; iqclk_d2 <= 1'b0;
                    iqwrt_d1 <= 1'b0; iqwrt_d2 <= 1'b0;
`else
                    iqclk_d1 <= 1'b1; iqclk_d2 <= 1'b0;
                    iqwrt_d1 <= 1'b1; iqwrt_d2 <= 1'b0;
`endif
                end

                2'd1: begin
                    // ph=1 (at t=1T): advance half_sel or synchronously prefetch next 64-bit BRAM word
                    if (sync_done) begin
                        if (rd_has_word && (half_sel == 1'b0)) begin
                            // Stay on current 64-bit word and advance to upper 32-bit IQ pair
                            half_sel <= 1'b1;
                        end else if (!fifo_empty) begin
                            rd_word_reg <= mem[rd_ptr_bin[FIFO_AW-1:0]];
                            rd_ptr_bin  <= rd_ptr_bin + 1'b1;
                            rd_ptr_gray <= bin2gray(rd_ptr_bin + 1'b1);
                            rd_has_word <= 1'b1;
                            half_sel    <= 1'b0;
                        end else begin
                            rd_has_word <= 1'b0;
                            half_sel    <= 1'b0;
                        end
                    end else begin
                        rd_has_word <= 1'b0;
                        half_sel    <= 1'b0;
                    end
`ifdef MUTATE_DAC_CLK_EDGE_WRONG
                    // Rising edge at t=2T coincides with Q/IQSEL change (t_S = 0 violation)
                    iqclk_d1 <= 1'b1; iqclk_d2 <= 1'b0;
                    iqwrt_d1 <= 1'b1; iqwrt_d2 <= 1'b0;
`else
                    iqclk_d1 <= 1'b0; iqclk_d2 <= 1'b1;
                    iqwrt_d1 <= 1'b0; iqwrt_d2 <= 1'b0;
`endif
                end

                2'd2: begin
                    // ph=2 (at t=2T): launch Q & IQSEL=0 now (both IQCLK & IQWRT fell at 1.5T); schedule Q strobe ODDR for t=3T
`ifdef MUTATE_IQ_SWAP
                    dacs_d <= to_offset14(cur_i_s);
`else
                    dacs_d <= to_offset14(cur_q_s);
`endif
                    dacs_iqsel <= 1'b0; // 0 = DAC2 (Q)
`ifdef MUTATE_DAC_CLK_EDGE_WRONG
                    iqclk_d1 <= 1'b0; iqclk_d2 <= 1'b0;
                    iqwrt_d1 <= 1'b0; iqwrt_d2 <= 1'b0;
`else
                    iqclk_d1 <= 1'b1; iqclk_d2 <= 1'b0;
                    iqwrt_d1 <= 1'b1; iqwrt_d2 <= 1'b0;
`endif
                end

                2'd3: begin
                    // ph=3 (at t=3T): Q strobe active on pins now; schedule I setup ODDR (IQCLK rises at 0.5T, IQWRT low 0T..1T)
                    if (!sync_done)
                        sync_done <= 1'b1;
`ifdef MUTATE_DAC_CLK_EDGE_WRONG
                    // Rising edge at t=0T coincides with I/IQSEL change (t_S = 0 violation)
                    iqclk_d1 <= 1'b1; iqclk_d2 <= 1'b0;
                    iqwrt_d1 <= 1'b1; iqwrt_d2 <= 1'b0;
`else
                    iqclk_d1 <= 1'b0; iqclk_d2 <= 1'b1;
                    iqwrt_d1 <= 1'b0; iqwrt_d2 <= 1'b0;
`endif
                end
            endcase
        end
    end

    ODDR #(
        .DDR_CLK_EDGE ("SAME_EDGE"),
        .INIT         (1'b0),
        .SRTYPE       ("SYNC")
    ) u_oddr_iqclk (
        .Q  (dacs_iqclk),
        .C  (dac_clk),
        .CE (1'b1),
        .D1 (iqclk_d1),
        .D2 (iqclk_d2),
        .R  (1'b0),
        .S  (1'b0)
    );

    ODDR #(
        .DDR_CLK_EDGE ("SAME_EDGE"),
        .INIT         (1'b0),
        .SRTYPE       ("SYNC")
    ) u_oddr_iqwrt (
        .Q  (dacs_iqwrt),
        .C  (dac_clk),
        .CE (1'b1),
        .D1 (iqwrt_d1),
        .D2 (iqwrt_d2),
        .R  (1'b0),
        .S  (1'b0)
    );
endmodule
