// SPDX-License-Identifier: Apache-2.0
// kria_dsp_out: the DSP suite's results as AXI-Stream packets for the A53s (18 Nov 2026, before the Rev08 tag)
//
// Until now the suite's results reached the PS only as status registers (the last audio pair, the last ADS-B
// word, the radar's peak), which no application can stream from. This block packs them, one stream id each:
//
//   8'h20  audio      64 words a packet; each word {flags[15:0], mono[15:0], right[15:0], left[15:0]},
//                     flags [0] 19 kHz pilot locked, [1] CTCSS detected, [2] an RDS bit arrived since the last
//                     word, [3] that bit. A packet that has waited AUD_FLUSH clocks for its next sample ends early.
//   8'h21  ADS-B      one packet a frame with a good CRC: word 0 = frame[111:48], word 1 = {frame[47:0], snr}.
//   8'h22  radar      one packet a CPI: a word per detection {power[31:0], cpi[15:0], 4'd0, dbin[3:0], 2'd0,
//                     rbin[5:0]}, at most 64, then the summary {8'hFF, cpi[15:0], detections[15:0], dropped[7:0],
//                     16'd0}, which carries tlast.
//   8'h23  radar map  every 2^map_log2 CPIs, the whole 64 x 16 map, two cells a word (the first in [31:0]), each
//                     {det, dbin[3:0], rbin[5:0], exponent[4:0], mantissa[15:0]}: power ~ 1.mantissa * 2^exponent.
//                     A map starts only when its FIFO has room for all of it; otherwise that CPI's map is skipped.
//
// Each source has its own FIFO; the arbiter sends whole packets, round robin. drop_cnt counts what was lost:
// samples or frames that met a full FIFO, detections beyond 64, skipped maps.

`timescale 1ns/1ps

module kria_dsp_sfifo #(parameter DW = 65, parameter AW = 8) (
    input  wire          clk,
    input  wire          rst,
    input  wire          wr_en,
    input  wire [DW-1:0] wr_data,
    output wire          full,
    output wire [AW+1:0] count,
    input  wire          rd_en,
    output reg  [DW-1:0] rd_data,
    output reg           rd_valid
);
    localparam DEPTH = 1 << AW;
    reg [DW-1:0] mem [0:DEPTH-1];
    reg [AW:0]   wp, rp;
    reg [DW-1:0] s1;
    reg          s1v;
    wire [AW:0]  used   = wp - rp;
    assign full  = (used == DEPTH);
    assign count = {1'b0, used} + s1v + rd_valid;

    wire take    = rd_en && rd_valid;
    wire q_free  = !rd_valid || take;
    wire s1_free = !s1v || q_free;
    wire fetch   = (wp != rp) && s1_free;

    always @(posedge clk) begin
        if (wr_en && !full) mem[wp[AW-1:0]] <= wr_data;
        if (fetch) s1 <= mem[rp[AW-1:0]];
        if (q_free) rd_data <= s1;
    end
    always @(posedge clk) begin
        if (rst) begin
            wp <= 0; rp <= 0; s1v <= 1'b0; rd_valid <= 1'b0;
        end else begin
            if (wr_en && !full) wp <= wp + 1'b1;
            if (q_free) rd_valid <= s1v;
            if (fetch) begin
                rp  <= rp + 1'b1;
                s1v <= 1'b1;
            end else if (q_free) begin
                s1v <= 1'b0;
            end
        end
    end
endmodule

module kria_dsp_out #(
    parameter AUD_WORDS = 64,
    parameter AUD_FLUSH = 32'd200000      // 2 ms at 100 MHz
) (
    input  wire               clk,
    input  wire               rst,
    input  wire               en,
    input  wire [3:0]         map_log2,

    input  wire               aud_valid,
    input  wire signed [15:0] aud_l,
    input  wire signed [15:0] aud_r,
    input  wire signed [15:0] aud_mono,
    input  wire               pilot_locked,
    input  wire               ctcss_det,
    input  wire               rds_valid,
    input  wire               rds_bit,

    input  wire               adsb_valid,
    input  wire               adsb_crc_ok,
    input  wire [111:0]       adsb_data,
    input  wire [15:0]        adsb_snr,

    input  wire               rd_valid,
    input  wire [5:0]         rd_rbin,
    input  wire [3:0]         rd_dbin,
    input  wire [31:0]        rd_pwr,
    input  wire               rd_det,
    input  wire               cpi_done,
    input  wire [15:0]        cpi_det_cnt,

    output wire [63:0]        m_tdata,
    output wire               m_tvalid,
    input  wire               m_tready,
    output wire               m_tlast,
    output wire [7:0]         m_tid,
    output reg  [15:0]        drop_cnt
);
    wire        srst = rst || !en;

    // ------------------------------------------------------------------ write side
    reg  [3:0]  f_we;
    reg  [64:0] wd0, wd1, wd2, wd3;     // {last, data}
    wire [3:0]  f_full;
    wire [9:0]  c0, c2;
    wire [7:0]  c1;
    wire [11:0] c3;
    reg  [3:0]  lost;

    // audio: a staging word, written when the next sample comes or the packet ends
    reg  [63:0] aud_hold;
    reg         aud_hold_v;
    reg  [6:0]  aud_n;                  // words of the current packet already written
    reg  [31:0] aud_idle;
    reg         rds_pend, rds_val;

    // ADS-B: the frame's second word goes on the next clock
    reg         ads_w1;
    reg  [63:0] ads_w1_data;

    // radar
    reg  [15:0] cpi_n;
    reg  [6:0]  det_n;
    reg  [7:0]  det_drop;
    reg         map_on;
    reg  [9:0]  map_cell;
    reg  [31:0] map_lo;
    reg         cpi_done_d;             // the summary goes one clock after the CPI's last cell

    function [31:0] map_word;               // {det, dbin, rbin, exponent, mantissa}
        input        det;
        input [3:0]  dbin;
        input [5:0]  rbin;
        input [31:0] p;
        integer k;
        reg [4:0]  e;
        reg [31:0] sh;
        begin
            e = 5'd0;
            for (k = 0; k < 32; k = k + 1)
                if (p[k]) e = k[4:0];
            sh   = p << (5'd31 - e);
`ifdef MUTATE_MAP_NO_NORMALISE
            sh   = p;
`endif
            map_word = {det, dbin, rbin, e, sh[30:15]};
        end
    endfunction

    wire [31:0] cur_cell = map_word(rd_det, rd_dbin, rd_rbin, rd_pwr);
    wire [3:0]  map_mask = (4'd1 << map_log2) - 4'd1;
    wire        map_due  = ((cpi_n[3:0] & map_mask) == 4'd0);
    wire        map_room = (c3 <= 12'd512);

    always @(posedge clk) begin
        f_we <= 4'b0000;
        lost <= 4'b0000;
        if (srst) begin
            aud_hold_v <= 1'b0; aud_n <= 7'd0; aud_idle <= 32'd0; rds_pend <= 1'b0; rds_val <= 1'b0;
            ads_w1 <= 1'b0;
            cpi_n <= 16'd0; det_n <= 7'd0; det_drop <= 8'd0; map_on <= 1'b0; map_cell <= 10'd0;
            cpi_done_d <= 1'b0;
        end else begin
            // ---- audio
            if (rds_valid) begin
                rds_pend <= 1'b1;
                rds_val  <= rds_bit;
            end
            if (aud_valid) begin
                aud_idle <= 32'd0;
                if (aud_hold_v) begin
                    f_we[0] <= 1'b1;
                    wd0     <= {(aud_n == AUD_WORDS - 1), aud_hold};
                    aud_n   <= (aud_n == AUD_WORDS - 1) ? 7'd0 : aud_n + 7'd1;
                    lost[0] <= f_full[0];
                end
                aud_hold   <= {12'd0, rds_valid ? rds_bit : rds_val, rds_pend | rds_valid, ctcss_det, pilot_locked,
                               aud_mono, aud_r, aud_l};
                aud_hold_v <= 1'b1;
                rds_pend   <= 1'b0;
            end else if (aud_hold_v) begin
                aud_idle <= aud_idle + 32'd1;
                if (aud_idle >= AUD_FLUSH) begin       // the channel stopped: end the packet with what it has
                    f_we[0]    <= 1'b1;
                    wd0        <= {1'b1, aud_hold};
                    aud_n      <= 7'd0;
                    aud_hold_v <= 1'b0;
                    aud_idle   <= 32'd0;
                    lost[0]    <= f_full[0];
                end
            end
            // ---- ADS-B
            if (ads_w1) begin
                f_we[1] <= 1'b1;
                wd1     <= {1'b1, ads_w1_data};
                ads_w1  <= 1'b0;
            end else if (adsb_valid && adsb_crc_ok) begin
                if (c1 <= 8'd60) begin
                    f_we[1]     <= 1'b1;
                    wd1         <= {1'b0, adsb_data[111:48]};
                    ads_w1      <= 1'b1;
                    ads_w1_data <= {adsb_data[47:0], adsb_snr};
                end else begin
                    lost[1] <= 1'b1;
                end
            end
            // ---- radar: detections and the map
            if (rd_valid) begin
                if (map_cell == 10'd0) begin
                    map_on <= map_due && map_room;
                    if (map_due && !map_room) lost[3] <= 1'b1;
                end
                map_cell <= map_cell + 10'd1;
                if (map_cell[0] == 1'b0)
                    map_lo <= cur_cell;
                else if (map_on) begin
                    f_we[3] <= 1'b1;
                    wd3     <= {(map_cell == 10'd1023), cur_cell, map_lo};
                end
                if (rd_det) begin
                    if (det_n < 7'd64 && c2 <= 10'd190) begin
                        f_we[2] <= 1'b1;
                        wd2     <= {1'b0, rd_pwr, cpi_n, 4'd0, rd_dbin, 2'd0, rd_rbin};
                        det_n   <= det_n + 7'd1;
                    end else begin
                        det_drop <= det_drop + 8'd1;
                        lost[2]  <= 1'b1;
                    end
                end
            end
            cpi_done_d <= cpi_done;
            if (cpi_done_d) begin
                f_we[2]  <= 1'b1;
                wd2      <= {1'b1, 8'hFF, cpi_n, cpi_det_cnt, det_drop, 16'd0};
                cpi_n    <= cpi_n + 16'd1;
                det_n    <= 7'd0;
                det_drop <= 8'd0;
                map_on   <= 1'b0;
            end
        end
    end

    always @(posedge clk) begin
        if (rst) drop_cnt <= 16'd0;
        else if (|lost && drop_cnt != 16'hFFFF) drop_cnt <= drop_cnt + 16'd1;
    end

    // ------------------------------------------------------------------ the four FIFOs
    reg  [3:0]  f_re;
    wire [64:0] rd0, rd1, rd2, rd3;
    wire [3:0]  f_rv;
    kria_dsp_sfifo #(.DW(65), .AW(8))  u_f_aud (.clk(clk), .rst(srst), .wr_en(f_we[0]), .wr_data(wd0),
        .full(f_full[0]), .count(c0), .rd_en(f_re[0]), .rd_data(rd0), .rd_valid(f_rv[0]));
    kria_dsp_sfifo #(.DW(65), .AW(6))  u_f_ads (.clk(clk), .rst(srst), .wr_en(f_we[1]), .wr_data(wd1),
        .full(f_full[1]), .count(c1), .rd_en(f_re[1]), .rd_data(rd1), .rd_valid(f_rv[1]));
    kria_dsp_sfifo #(.DW(65), .AW(8))  u_f_det (.clk(clk), .rst(srst), .wr_en(f_we[2]), .wr_data(wd2),
        .full(f_full[2]), .count(c2), .rd_en(f_re[2]), .rd_data(rd2), .rd_valid(f_rv[2]));
    kria_dsp_sfifo #(.DW(65), .AW(10)) u_f_map (.clk(clk), .rst(srst), .wr_en(f_we[3]), .wr_data(wd3),
        .full(f_full[3]), .count(c3), .rd_en(f_re[3]), .rd_data(rd3), .rd_valid(f_rv[3]));

    // ------------------------------------------------------------------ packet arbiter, round robin
    reg  [7:0] p0, p1, p2, p3;          // complete packets waiting in each FIFO
    reg        busy;
    reg  [1:0] cur, rr;
    wire [3:0] has = {p3 != 8'd0, p2 != 8'd0, p1 != 8'd0, p0 != 8'd0};
    wire [64:0] rdc = (cur == 2'd0) ? rd0 : (cur == 2'd1) ? rd1 : (cur == 2'd2) ? rd2 : rd3;
    reg  [1:0] pick;
    reg        any;
    integer j;
    always @* begin
        any  = 1'b0;
        pick = rr;
        for (j = 3; j >= 0; j = j - 1)
            if (has[(rr + j) & 3]) begin
                any  = 1'b1;
                pick = (rr + j) & 3;
            end
    end

    assign m_tvalid = busy && f_rv[cur];
    assign m_tdata  = rdc[63:0];
    assign m_tlast  = rdc[64];
    assign m_tid    = (cur == 2'd0) ? 8'h20 : (cur == 2'd1) ? 8'h21 : (cur == 2'd2) ? 8'h22 : 8'h23;
    always @* begin
        f_re      = 4'b0000;
        f_re[cur] = busy && m_tready;
    end

    wire sent_last = m_tvalid && m_tready && m_tlast;
    always @(posedge clk) begin
        if (srst) begin
            busy <= 1'b0; cur <= 2'd0; rr <= 2'd0;
            p0 <= 8'd0; p1 <= 8'd0; p2 <= 8'd0; p3 <= 8'd0;
        end else begin
            p0 <= p0 + ((f_we[0] && !f_full[0] && wd0[64]) ? 8'd1 : 8'd0) - ((sent_last && cur == 2'd0) ? 8'd1 : 8'd0);
            p1 <= p1 + ((f_we[1] && !f_full[1] && wd1[64]) ? 8'd1 : 8'd0) - ((sent_last && cur == 2'd1) ? 8'd1 : 8'd0);
            p2 <= p2 + ((f_we[2] && !f_full[2] && wd2[64]) ? 8'd1 : 8'd0) - ((sent_last && cur == 2'd2) ? 8'd1 : 8'd0);
            p3 <= p3 + ((f_we[3] && !f_full[3] && wd3[64]) ? 8'd1 : 8'd0) - ((sent_last && cur == 2'd3) ? 8'd1 : 8'd0);
            if (!busy) begin
                if (any) begin
                    busy <= 1'b1;
                    cur  <= pick;
                end
            end else if (sent_last) begin
                busy <= 1'b0;
                rr   <= cur + 2'd1;
            end
        end
    end
endmodule
