// SPDX-License-Identifier: BSD-2-Clause
// 2-Lane PCS TX & RX Top-Level Wrappers (Plain Verilog-2001, no vendor primitives)
// Connects Packet Framer -> 2-Lane Striping -> 64b/66b Scrambler -> 66:8 Gearbox,
// and 8:66 Gearbox + Block Lock -> 64b/66b Descrambler -> AM Deskew -> Packet Deframer.

`timescale 1ns/1ps

module link_pcs_tx #(
    parameter AM_PERIOD     = 16384,
    parameter BAD_SCRAMBLER = 0
) (
    input  wire        clk,
    input  wire        rst,

    // Packet input interface
    input  wire        pkt_valid,
    output wire        pkt_ready,
    input  wire        pkt_sop,
    input  wire        pkt_eop,
    input  wire [7:0]  pkt_stream_id,
    input  wire [15:0] pkt_len,
    input  wire [31:0] pkt_seq,
    input  wire [63:0] pkt_timestamp,
    input  wire [63:0] pkt_data,
    input  wire [23:0] dropped_cnt,
    input  wire [15:0] local_status,

    // 8-bit SERDES parallel bytes for Lane 0 and Lane 1
    output wire [7:0]  tx_byte_l0,
    output wire [7:0]  tx_byte_l1
);
    wire        fr_valid, fr_ready;
    wire [1:0]  fr_sync;
    wire [63:0] fr_data;

    wire        l0_st_valid, l0_st_ready;
    wire [1:0]  l0_st_sync;
    wire [63:0] l0_st_data;

    wire        l1_st_valid, l1_st_ready;
    wire [1:0]  l1_st_sync;
    wire [63:0] l1_st_data;

    wire        l0_enc_valid, l0_gb_ready;
    wire [65:0] l0_enc_block;

    wire        l1_enc_valid, l1_gb_ready;
    wire [65:0] l1_enc_block;

    link_framer u_framer (
        .clk           (clk),
        .rst           (rst),
        .pkt_valid     (pkt_valid),
        .pkt_ready     (pkt_ready),
        .pkt_sop       (pkt_sop),
        .pkt_eop       (pkt_eop),
        .pkt_stream_id (pkt_stream_id),
        .pkt_len       (pkt_len),
        .pkt_seq       (pkt_seq),
        .pkt_timestamp (pkt_timestamp),
        .pkt_data      (pkt_data),
        .dropped_cnt   (dropped_cnt),
        .local_status  (local_status),
        .tx_valid      (fr_valid),
        .tx_ready      (fr_ready),
        .tx_sync       (fr_sync),
        .tx_data       (fr_data)
    );

    link_tx_lanes #(
        .AM_PERIOD (AM_PERIOD)
    ) u_tx_lanes (
        .clk      (clk),
        .rst      (rst),
        .in_valid (fr_valid),
        .in_ready (fr_ready),
        .in_sync  (fr_sync),
        .in_data  (fr_data),
        .l0_valid (l0_st_valid),
        .l0_ready (l0_st_ready),
        .l0_sync  (l0_st_sync),
        .l0_data  (l0_st_data),
        .l1_valid (l1_st_valid),
        .l1_ready (l1_st_ready),
        .l1_sync  (l1_st_sync),
        .l1_data  (l1_st_data)
    );

    link_64b66b_enc #(
        .BAD_SCRAMBLER (BAD_SCRAMBLER)
    ) u_enc_l0 (
        .clk       (clk),
        .rst       (rst),
        .in_valid  (l0_st_valid),
        .in_ready  (l0_st_ready),
        .in_sync   (l0_st_sync),
        .in_data   (l0_st_data),
        .out_valid (l0_enc_valid),
        .out_ready (l0_gb_ready),
        .out_block (l0_enc_block)
    );

    link_64b66b_enc #(
        .BAD_SCRAMBLER (BAD_SCRAMBLER)
    ) u_enc_l1 (
        .clk       (clk),
        .rst       (rst),
        .in_valid  (l1_st_valid),
        .in_ready  (l1_st_ready),
        .in_sync   (l1_st_sync),
        .in_data   (l1_st_data),
        .out_valid (l1_enc_valid),
        .out_ready (l1_gb_ready),
        .out_block (l1_enc_block)
    );

    link_gearbox_tx u_gb_tx_l0 (
        .clk      (clk),
        .rst      (rst),
        .in_valid (l0_enc_valid),
        .in_ready (l0_gb_ready),
        .in_block (l0_enc_block),
        .out_byte (tx_byte_l0)
    );

    link_gearbox_tx u_gb_tx_l1 (
        .clk      (clk),
        .rst      (rst),
        .in_valid (l1_enc_valid),
        .in_ready (l1_gb_ready),
        .in_block (l1_enc_block),
        .out_byte (tx_byte_l1)
    );
endmodule

module link_pcs_rx #(
    parameter DISABLE_DESKEW = 0,
    parameter SKIP_CRC       = 0
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        link_ready,

    // 8-bit SERDES parallel bytes from Lane 0 and Lane 1
    input  wire [7:0]  rx_byte_l0,
    input  wire [7:0]  rx_byte_l1,

    // Streaming packet output & validation
    output wire        out_valid,
    output wire        out_sop,
    output wire        out_eop,
    output wire [7:0]  out_stream_id,
    output wire [15:0] out_len,
    output wire [31:0] out_seq,
    output wire [63:0] out_timestamp,
    output wire [63:0] out_data,
    output wire        pkt_done_valid,
    output wire        pkt_done_ok,
    output wire        pkt_done_err,

    // Link status & error counters
    output wire        l0_block_lock,
    output wire        l1_block_lock,
    output wire        deskew_lock,
    output wire signed [7:0] skew_blocks,
    output wire [15:0] remote_status,
    output wire [23:0] remote_dropped_cnt,
    output wire [31:0] sh_err_cnt_l0,
    output wire [31:0] sh_err_cnt_l1,
    output wire [31:0] pkt_rx_cnt,
    output wire [31:0] crc_err_cnt,
    output wire        l0_rx_blk_valid,
    output wire        l0_rx_blk_ok,
    output wire        l1_rx_blk_valid,
    output wire        l1_rx_blk_ok
);
    wire        l0_gb_valid, l0_slip;
    wire [65:0] l0_gb_block;
    wire        l0_dec_valid, l0_sync_err;
    wire [1:0]  l0_dec_sync;
    wire [63:0] l0_dec_data;

    wire        l1_gb_valid, l1_slip;
    wire [65:0] l1_gb_block;
    wire        l1_dec_valid, l1_sync_err;
    wire [1:0]  l1_dec_sync;
    wire [63:0] l1_dec_data;

    // Training/eye-scan indicator: valid descrambled Idle (/I/) or Align (/A/) block
    wire l0_idle_ok  = (l0_dec_sync == 2'b10) && (l0_dec_data[7:0] == 8'h1E) && (l0_dec_data[63:24] == 40'd0);
    wire l0_align_ok = (l0_dec_sync == 2'b10) && (l0_dec_data[7:0] == 8'h4B) && (l0_dec_data[63:32] == 32'h9AC5_3C69);
    assign l0_rx_blk_valid = l0_dec_valid;
    assign l0_rx_blk_ok    = l0_dec_valid && !l0_sync_err && (l0_idle_ok || l0_align_ok);

    wire l1_idle_ok  = (l1_dec_sync == 2'b10) && (l1_dec_data[7:0] == 8'h1E) && (l1_dec_data[63:24] == 40'd0);
    wire l1_align_ok = (l1_dec_sync == 2'b10) && (l1_dec_data[7:0] == 8'h4B) && (l1_dec_data[63:32] == 32'h9AC5_3C69);
    assign l1_rx_blk_valid = l1_dec_valid;
    assign l1_rx_blk_ok    = l1_dec_valid && !l1_sync_err && (l1_idle_ok || l1_align_ok);

    wire        lanes_valid;
    wire [1:0]  lanes_sync;
    wire [63:0] lanes_data;
    wire [15:0] last_am_seq;

    link_gearbox_rx u_gb_rx_l0 (
        .clk       (clk),
        .rst       (rst),
        .in_byte   (rx_byte_l0),
        .rx_slip   (l0_slip),
        .out_valid (l0_gb_valid),
        .out_block (l0_gb_block)
    );

    link_block_lock u_bl_l0 (
        .clk        (clk),
        .rst        (rst),
        .rx_valid   (l0_gb_valid),
        .rx_sync    (l0_gb_block[1:0]),
        .block_lock (l0_block_lock),
        .rx_slip    (l0_slip),
        .sh_err_cnt (sh_err_cnt_l0)
    );

    link_64b66b_dec #(
        .BAD_SCRAMBLER (0)
    ) u_dec_l0 (
        .clk       (clk),
        .rst       (rst),
        .in_valid  (l0_gb_valid),
        .in_block  (l0_gb_block),
        .out_valid (l0_dec_valid),
        .out_sync  (l0_dec_sync),
        .out_data  (l0_dec_data),
        .sync_err  (l0_sync_err)
    );

    link_gearbox_rx u_gb_rx_l1 (
        .clk       (clk),
        .rst       (rst),
        .in_byte   (rx_byte_l1),
        .rx_slip   (l1_slip),
        .out_valid (l1_gb_valid),
        .out_block (l1_gb_block)
    );

    link_block_lock u_bl_l1 (
        .clk        (clk),
        .rst        (rst),
        .rx_valid   (l1_gb_valid),
        .rx_sync    (l1_gb_block[1:0]),
        .block_lock (l1_block_lock),
        .rx_slip    (l1_slip),
        .sh_err_cnt (sh_err_cnt_l1)
    );

    link_64b66b_dec #(
        .BAD_SCRAMBLER (0)
    ) u_dec_l1 (
        .clk       (clk),
        .rst       (rst),
        .in_valid  (l1_gb_valid),
        .in_block  (l1_gb_block),
        .out_valid (l1_dec_valid),
        .out_sync  (l1_dec_sync),
        .out_data  (l1_dec_data),
        .sync_err  (l1_sync_err)
    );

    link_rx_lanes #(
        .DISABLE_DESKEW (DISABLE_DESKEW)
    ) u_rx_lanes (
        .clk           (clk),
        .rst           (rst),
        .l0_block_lock (l0_block_lock),
        .l0_valid      (l0_dec_valid),
        .l0_sync       (l0_dec_sync),
        .l0_data       (l0_dec_data),
        .l1_block_lock (l1_block_lock),
        .l1_valid      (l1_dec_valid),
        .l1_sync       (l1_dec_sync),
        .l1_data       (l1_dec_data),
        .deskew_lock   (deskew_lock),
        .skew_blocks   (skew_blocks),
        .last_am_seq   (last_am_seq),
        .out_valid     (lanes_valid),
        .out_sync      (lanes_sync),
        .out_data      (lanes_data)
    );

    link_deframer #(
        .SKIP_CRC (SKIP_CRC)
    ) u_deframer (
        .clk                (clk),
        .rst                (rst || !link_ready),
        .rx_valid           (lanes_valid && link_ready),
        .rx_sync            (lanes_sync),
        .rx_data            (lanes_data),
        .out_valid          (out_valid),
        .out_sop            (out_sop),
        .out_eop            (out_eop),
        .out_stream_id      (out_stream_id),
        .out_len            (out_len),
        .out_seq            (out_seq),
        .out_timestamp      (out_timestamp),
        .out_data           (out_data),
        .pkt_done_valid     (pkt_done_valid),
        .pkt_done_ok        (pkt_done_ok),
        .pkt_done_err       (pkt_done_err),
        .remote_status      (remote_status),
        .remote_dropped_cnt (remote_dropped_cnt),
        .pkt_rx_cnt         (pkt_rx_cnt),
        .crc_err_cnt        (crc_err_cnt)
    );
endmodule

// Single-Lane PCS TX & RX Wrappers (e.g. Kria -> Artix LINK_TX_D0 downlink)
module link_pcs_single_tx #(
    parameter BAD_SCRAMBLER = 0
) (
    input  wire        clk,
    input  wire        rst,

    // Packet input interface
    input  wire        pkt_valid,
    output wire        pkt_ready,
    input  wire        pkt_sop,
    input  wire        pkt_eop,
    input  wire [7:0]  pkt_stream_id,
    input  wire [15:0] pkt_len,
    input  wire [31:0] pkt_seq,
    input  wire [63:0] pkt_timestamp,
    input  wire [63:0] pkt_data,
    input  wire [23:0] dropped_cnt,
    input  wire [15:0] local_status,

    // 8-bit SERDES parallel byte
    output wire [7:0]  tx_byte_l0
);
    wire        fr_valid, fr_ready;
    wire [1:0]  fr_sync;
    wire [63:0] fr_data;
    wire        enc_valid, gb_ready;
    wire [65:0] enc_block;

    link_framer u_framer (
        .clk           (clk),
        .rst           (rst),
        .pkt_valid     (pkt_valid),
        .pkt_ready     (pkt_ready),
        .pkt_sop       (pkt_sop),
        .pkt_eop       (pkt_eop),
        .pkt_stream_id (pkt_stream_id),
        .pkt_len       (pkt_len),
        .pkt_seq       (pkt_seq),
        .pkt_timestamp (pkt_timestamp),
        .pkt_data      (pkt_data),
        .dropped_cnt   (dropped_cnt),
        .local_status  (local_status),
        .tx_valid      (fr_valid),
        .tx_ready      (fr_ready),
        .tx_sync       (fr_sync),
        .tx_data       (fr_data)
    );

    link_64b66b_enc #(
        .BAD_SCRAMBLER (BAD_SCRAMBLER)
    ) u_enc_l0 (
        .clk       (clk),
        .rst       (rst),
        .in_valid  (fr_valid),
        .in_ready  (fr_ready),
        .in_sync   (fr_sync),
        .in_data   (fr_data),
        .out_valid (enc_valid),
        .out_ready (gb_ready),
        .out_block (enc_block)
    );

    link_gearbox_tx u_gb_tx_l0 (
        .clk      (clk),
        .rst      (rst),
        .in_valid (enc_valid),
        .in_ready (gb_ready),
        .in_block (enc_block),
        .out_byte (tx_byte_l0)
    );
endmodule

module link_pcs_single_rx #(
    parameter SKIP_CRC = 0
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        link_ready,

    input  wire [7:0]  rx_byte_l0,

    // Streaming packet output & validation
    output wire        out_valid,
    output wire        out_sop,
    output wire        out_eop,
    output wire [7:0]  out_stream_id,
    output wire [15:0] out_len,
    output wire [31:0] out_seq,
    output wire [63:0] out_timestamp,
    output wire [63:0] out_data,
    output wire        pkt_done_valid,
    output wire        pkt_done_ok,
    output wire        pkt_done_err,

    // Link status & error counters
    output wire        l0_block_lock,
    output wire [15:0] remote_status,
    output wire [23:0] remote_dropped_cnt,
    output wire [31:0] sh_err_cnt_l0,
    output wire [31:0] pkt_rx_cnt,
    output wire [31:0] crc_err_cnt,
    output wire        l0_rx_blk_valid,
    output wire        l0_rx_blk_ok
);
    wire        gb_valid, slip;
    wire [65:0] gb_block;
    wire        dec_valid, sync_err;
    wire [1:0]  dec_sync;
    wire [63:0] dec_data;

    wire l0_idle_ok  = (dec_sync == 2'b10) && (dec_data[7:0] == 8'h1E) && (dec_data[63:24] == 40'd0);
    wire l0_align_ok = (dec_sync == 2'b10) && (dec_data[7:0] == 8'h4B) && (dec_data[63:32] == 32'h9AC5_3C69);
    assign l0_rx_blk_valid = dec_valid;
    assign l0_rx_blk_ok    = dec_valid && !sync_err && (l0_idle_ok || l0_align_ok);

    link_gearbox_rx u_gb_rx_l0 (
        .clk       (clk),
        .rst       (rst),
        .in_byte   (rx_byte_l0),
        .rx_slip   (slip),
        .out_valid (gb_valid),
        .out_block (gb_block)
    );

    link_block_lock u_bl_l0 (
        .clk        (clk),
        .rst        (rst),
        .rx_valid   (gb_valid),
        .rx_sync    (gb_block[1:0]),
        .block_lock (l0_block_lock),
        .rx_slip    (slip),
        .sh_err_cnt (sh_err_cnt_l0)
    );

    link_64b66b_dec #(
        .BAD_SCRAMBLER (0)
    ) u_dec_l0 (
        .clk       (clk),
        .rst       (rst),
        .in_valid  (gb_valid),
        .in_block  (gb_block),
        .out_valid (dec_valid),
        .out_sync  (dec_sync),
        .out_data  (dec_data),
        .sync_err  (sync_err)
    );

    link_deframer #(
        .SKIP_CRC (SKIP_CRC)
    ) u_deframer (
        .clk                (clk),
        .rst                (rst || !link_ready),
        .rx_valid           (dec_valid && l0_block_lock && link_ready),
        .rx_sync            (dec_sync),
        .rx_data            (dec_data),
        .out_valid          (out_valid),
        .out_sop            (out_sop),
        .out_eop            (out_eop),
        .out_stream_id      (out_stream_id),
        .out_len            (out_len),
        .out_seq            (out_seq),
        .out_timestamp      (out_timestamp),
        .out_data           (out_data),
        .pkt_done_valid     (pkt_done_valid),
        .pkt_done_ok        (pkt_done_ok),
        .pkt_done_err       (pkt_done_err),
        .remote_status      (remote_status),
        .remote_dropped_cnt (remote_dropped_cnt),
        .pkt_rx_cnt         (pkt_rx_cnt),
        .crc_err_cnt        (crc_err_cnt)
    );
endmodule
