// SPDX-License-Identifier: BSD-2-Clause
// Packet Framer & Deframer with 64-bit PPS Timestamp, Sequence Counter,
// Dropped-Packet Counter, and IEEE 802.3 CRC-32 Trailer.

`timescale 1ns/1ps

module link_framer (
    input  wire        clk,
    input  wire        rst,

    // Packet input interface (64-bit word stream; hold START/TS metadata until first pkt_ready)
    input  wire        pkt_valid,
    output reg         pkt_ready,
    input  wire        pkt_sop,
    input  wire        pkt_eop,
    input  wire [7:0]  pkt_stream_id,
    input  wire [15:0] pkt_len,
    input  wire [31:0] pkt_seq,
    input  wire [63:0] pkt_timestamp,
    input  wire [63:0] pkt_data,
    input  wire [23:0] dropped_cnt,
    input  wire [15:0] local_status,

    // 66-bit unscrambled block output interface
    output reg         tx_valid,
    input  wire        tx_ready,
    output reg  [1:0]  tx_sync,
    output reg  [63:0] tx_data
);
    localparam [7:0] BTYPE_IDLE  = 8'h1E;
    localparam [7:0] BTYPE_START = 8'h78;
    localparam [7:0] BTYPE_TERM  = 8'hFF;

    localparam [1:0] ST_IDLE = 2'd0,
                     ST_TS   = 2'd1,
                     ST_DATA = 2'd2,
                     ST_TERM = 2'd3;

    reg  [1:0]  state;
    reg  [31:0] crc_reg;
    reg  [63:0] lat_ts;
    reg  [15:0] rem_bytes;
    reg  [23:0] lat_drop;

    reg  [63:0] masked_data;
    wire [63:0] crc_feed_word = (state == ST_IDLE) ? {pkt_seq, pkt_len, pkt_stream_id, BTYPE_START} :
                                (state == ST_TS)   ? lat_ts :
                                                     masked_data;
    wire [31:0] crc_init_or_reg = (state == ST_IDLE) ? 32'hFFFF_FFFF : crc_reg;
    wire [31:0] crc_next;

    link_crc32 u_crc (
        .crc_in  (crc_init_or_reg),
        .data_in (crc_feed_word),
        .crc_out (crc_next)
    );

    integer b;
    always @* begin
        for (b = 0; b < 8; b = b + 1) begin
            if (b < rem_bytes)
                masked_data[b*8 +: 8] = pkt_data[b*8 +: 8];
            else
                masked_data[b*8 +: 8] = 8'h00;
        end
    end

    always @* begin
        pkt_ready = 1'b0;
        tx_valid  = 1'b1;
        tx_sync   = 2'b10;
        tx_data   = {40'd0, local_status, BTYPE_IDLE};

        case (state)
            ST_IDLE: begin
                if (pkt_valid && pkt_sop) begin
                    tx_valid = 1'b1;
                    tx_sync  = 2'b10;
                    tx_data  = {pkt_seq, pkt_len, pkt_stream_id, BTYPE_START};
                end else begin
                    tx_valid = 1'b1;
                    tx_sync  = 2'b10;
                    tx_data  = {40'd0, local_status, BTYPE_IDLE};
                end
            end
            ST_TS: begin
                tx_valid = 1'b1;
                tx_sync  = 2'b01;
                tx_data  = lat_ts;
            end
            ST_DATA: begin
                tx_valid  = pkt_valid;
                tx_sync   = 2'b01;
                tx_data   = masked_data;
                pkt_ready = tx_ready;
            end
            ST_TERM: begin
                tx_valid = 1'b1;
                tx_sync  = 2'b10;
                tx_data  = {lat_drop, ~crc_reg, BTYPE_TERM};
            end
        endcase
    end

    always @(posedge clk) begin
        if (rst) begin
            state     <= ST_IDLE;
            crc_reg   <= 32'hFFFF_FFFF;
            lat_ts    <= 64'd0;
            rem_bytes <= 16'd0;
            lat_drop  <= 24'd0;
        end else begin
            case (state)
                ST_IDLE: begin
                    if (pkt_valid && pkt_sop && tx_ready) begin
                        lat_ts    <= pkt_timestamp;
                        rem_bytes <= pkt_len;
                        crc_reg   <= crc_next;
                        state     <= ST_TS;
                    end
                end
                ST_TS: begin
                    if (tx_ready) begin
                        crc_reg <= crc_next;
                        state   <= ST_DATA;
                    end
                end
                ST_DATA: begin
                    if (pkt_valid && pkt_ready) begin
                        crc_reg <= crc_next;
                        if (rem_bytes > 16'd8)
                            rem_bytes <= rem_bytes - 16'd8;
                        else
                            rem_bytes <= 16'd0;
                        if (pkt_eop) begin
                            lat_drop <= dropped_cnt;
                            state    <= ST_TERM;
                        end
                    end
                end
                ST_TERM: begin
                    if (tx_ready) begin
                        state <= ST_IDLE;
                    end
                end
            endcase
        end
    end
endmodule

module link_deframer #(
    parameter SKIP_CRC = 0
) (
    input  wire        clk,
    input  wire        rst,

    // 66-bit descrambled block stream from link_rx_lanes
    input  wire        rx_valid,
    input  wire [1:0]  rx_sync,
    input  wire [63:0] rx_data,

    // Streaming packet data + metadata
    output reg         out_valid,
    output reg         out_sop,
    output reg         out_eop,
    output reg  [7:0]  out_stream_id,
    output reg  [15:0] out_len,
    output reg  [31:0] out_seq,
    output reg  [63:0] out_timestamp,
    output reg  [63:0] out_data,

    // End-of-packet validation & diagnostics
    output reg         pkt_done_valid,
    output reg         pkt_done_ok,
    output reg         pkt_done_err,
    output reg  [15:0] remote_status,
    output reg  [23:0] remote_dropped_cnt,
    output reg  [31:0] pkt_rx_cnt,
    output reg  [31:0] crc_err_cnt
);
    localparam [7:0] BTYPE_IDLE  = 8'h1E;
    localparam [7:0] BTYPE_START = 8'h78;
    localparam [7:0] BTYPE_TERM  = 8'hFF;

    reg        in_pkt;
    reg        wait_ts;
    reg        first_word;
    reg        len_err;
    reg        proto_err;
    reg [15:0] exp_words;
    reg [15:0] word_idx;
    reg [31:0] crc_reg;

    wire [31:0] crc_init_or_reg = ((rx_sync == 2'b10) && (rx_data[7:0] == BTYPE_START)) ?
                                  32'hFFFF_FFFF : crc_reg;
    wire [31:0] crc_next;

    link_crc32 u_crc (
        .crc_in  (crc_init_or_reg),
        .data_in (rx_data),
        .crc_out (crc_next)
    );

    reg [15:0] start_len;
    reg [15:0] start_words;
    reg        crc_ok;
    reg        pkt_good;

    always @(posedge clk) begin
        if (rst) begin
            out_valid          <= 1'b0;
            out_sop            <= 1'b0;
            out_eop            <= 1'b0;
            out_stream_id      <= 8'd0;
            out_len            <= 16'd0;
            out_seq            <= 32'd0;
            out_timestamp      <= 64'd0;
            out_data           <= 64'd0;
            pkt_done_valid     <= 1'b0;
            pkt_done_ok        <= 1'b0;
            pkt_done_err       <= 1'b0;
            remote_status      <= 16'd0;
            remote_dropped_cnt <= 24'd0;
            pkt_rx_cnt         <= 32'd0;
            crc_err_cnt        <= 32'd0;
            in_pkt             <= 1'b0;
            wait_ts            <= 1'b0;
            first_word         <= 1'b0;
            len_err            <= 1'b0;
            proto_err          <= 1'b0;
            exp_words          <= 16'd0;
            word_idx           <= 16'd0;
            crc_reg            <= 32'hFFFF_FFFF;
        end else begin
            out_valid      <= 1'b0;
            out_sop        <= 1'b0;
            out_eop        <= 1'b0;
            pkt_done_valid <= 1'b0;
            pkt_done_ok    <= 1'b0;
            pkt_done_err   <= 1'b0;

            if (rx_valid) begin
                if ((rx_sync == 2'b10) && (rx_data[7:0] == BTYPE_IDLE)) begin
                    remote_status <= rx_data[23:8];
                    if (in_pkt) begin
                        // Unexpected IDLE interrupts active frame -> report error
                        in_pkt         <= 1'b0;
                        pkt_done_valid <= 1'b1;
                        pkt_done_err   <= 1'b1;
                        if (crc_err_cnt != 32'hFFFF_FFFF)
                            crc_err_cnt <= crc_err_cnt + 32'd1;
                    end
                end else if ((rx_sync == 2'b10) && (rx_data[7:0] == BTYPE_START)) begin
                    start_len   = rx_data[31:16];
                    start_words = (start_len + 16'd7) >> 3;
                    if (in_pkt) begin
                        // Previous packet never terminated cleanly
                        pkt_done_valid <= 1'b1;
                        pkt_done_err   <= 1'b1;
                        if (crc_err_cnt != 32'hFFFF_FFFF)
                            crc_err_cnt <= crc_err_cnt + 32'd1;
                    end
                    in_pkt        <= 1'b1;
                    wait_ts       <= 1'b1;
                    first_word    <= 1'b1;
                    out_stream_id <= rx_data[15:8];
                    out_len       <= start_len;
                    out_seq       <= rx_data[63:32];
                    exp_words     <= start_words;
                    word_idx      <= 16'd0;
                    len_err       <= (start_len == 16'd0) || (start_len > 16'd4096);
                    proto_err     <= 1'b0;
                    crc_reg       <= crc_next;
                end else if (in_pkt && wait_ts) begin
                    if (rx_sync == 2'b01) begin
                        out_timestamp <= rx_data;
                        crc_reg       <= crc_next;
                        wait_ts       <= 1'b0;
                    end else begin
                        proto_err      <= 1'b1;
                        in_pkt         <= 1'b0;
                        pkt_done_valid <= 1'b1;
                        pkt_done_err   <= 1'b1;
                        if (crc_err_cnt != 32'hFFFF_FFFF)
                            crc_err_cnt <= crc_err_cnt + 32'd1;
                    end
                end else if (in_pkt && !wait_ts) begin
                    if (rx_sync == 2'b01) begin
                        out_valid  <= 1'b1;
                        out_sop    <= first_word;
                        out_eop    <= ((word_idx + 16'd1) == exp_words);
                        out_data   <= rx_data;
                        first_word <= 1'b0;
                        word_idx   <= word_idx + 16'd1;
                        crc_reg    <= crc_next;
                        if (word_idx >= exp_words)
                            len_err <= 1'b1;
                    end else if ((rx_sync == 2'b10) && (rx_data[7:0] == BTYPE_TERM)) begin
                        remote_dropped_cnt <= rx_data[63:40];
                        crc_ok   = (SKIP_CRC != 0) ? 1'b1 : (rx_data[39:8] == ~crc_reg);
                        pkt_good = crc_ok && !len_err && !proto_err && (word_idx == exp_words);
                        in_pkt         <= 1'b0;
                        pkt_done_valid <= 1'b1;
                        if (pkt_good) begin
                            pkt_done_ok <= 1'b1;
                            if (pkt_rx_cnt != 32'hFFFF_FFFF)
                                pkt_rx_cnt <= pkt_rx_cnt + 32'd1;
                        end else begin
                            pkt_done_err <= 1'b1;
                            if (crc_err_cnt != 32'hFFFF_FFFF)
                                crc_err_cnt <= crc_err_cnt + 32'd1;
                        end
                    end else begin
                        in_pkt         <= 1'b0;
                        pkt_done_valid <= 1'b1;
                        pkt_done_err   <= 1'b1;
                        if (crc_err_cnt != 32'hFFFF_FFFF)
                            crc_err_cnt <= crc_err_cnt + 32'd1;
                    end
                end
            end
        end
    end
endmodule
