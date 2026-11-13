// SPDX-License-Identifier: BSD-2-Clause
// 2-Lane Striping TX and Elastic-Buffer AM Deskew RX
// Interleaves even/odd 66-bit blocks across Lane 0 and Lane 1, and inserts
// periodic Alignment Markers (BTYPE_ALIGN = 8'h4B) every AM_PERIOD block pairs.

`timescale 1ns/1ps

module link_tx_lanes #(
    parameter AM_PERIOD = 16384
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        in_valid,
    output wire        in_ready,
    input  wire [1:0]  in_sync,
    input  wire [63:0] in_data,

    output reg         l0_valid,
    input  wire        l0_ready,
    output reg  [1:0]  l0_sync,
    output reg  [63:0] l0_data,

    output reg         l1_valid,
    input  wire        l1_ready,
    output reg  [1:0]  l1_sync,
    output reg  [63:0] l1_data
);
    localparam [7:0]  BTYPE_IDLE  = 8'h1E;
    localparam [7:0]  BTYPE_ALIGN = 8'h4B;
    localparam [31:0] AM_MAGIC    = 32'h9A_C5_3C_69;

    reg        have_0, have_1;
    reg [65:0] blk_0, blk_1;
    reg [15:0] am_cnt;
    reg [15:0] am_seq;

    wire       both_out_free = (!l0_valid || l0_ready) && (!l1_valid || l1_ready);
    wire       need_am       = (am_cnt >= (AM_PERIOD - 1));
    wire       have_pair     = have_0 && have_1;

    assign in_ready = !have_pair;

    always @(posedge clk) begin
        if (rst) begin
            have_0   <= 1'b0;
            have_1   <= 1'b0;
            blk_0    <= 66'd0;
            blk_1    <= 66'd0;
            am_cnt   <= 16'd0;
            am_seq   <= 16'd0;
            l0_valid <= 1'b0;
            l0_sync  <= 2'b00;
            l0_data  <= 64'd0;
            l1_valid <= 1'b0;
            l1_sync  <= 2'b00;
            l1_data  <= 64'd0;
        end else begin
            // Default clear valid once consumed by encoders
            if (l0_valid && l0_ready && l1_valid && l1_ready) begin
                l0_valid <= 1'b0;
                l1_valid <= 1'b0;
            end

            // Emit either periodic Alignment Marker pair or assembled even/odd block pair
            if (both_out_free) begin
                if (need_am) begin
                    l0_valid <= 1'b1;
                    l0_sync  <= 2'b10;
                    l0_data  <= {AM_MAGIC, am_seq, 8'd0, BTYPE_ALIGN};
                    l1_valid <= 1'b1;
                    l1_sync  <= 2'b10;
                    l1_data  <= {AM_MAGIC, am_seq, 8'd1, BTYPE_ALIGN};
                    am_cnt   <= 16'd0;
                    am_seq   <= am_seq + 16'd1;
                end else if (have_pair) begin
                    l0_valid <= 1'b1;
                    l0_sync  <= blk_0[1:0];
                    l0_data  <= blk_0[65:2];
                    l1_valid <= 1'b1;
                    l1_sync  <= blk_1[1:0];
                    l1_data  <= blk_1[65:2];
                    have_0   <= 1'b0;
                    have_1   <= 1'b0;
                    am_cnt   <= am_cnt + 16'd1;
                end else if (!in_valid) begin
                    // If upstream is temporarily idle, emit idle blocks on both lanes
                    l0_valid <= 1'b1;
                    l0_sync  <= 2'b10;
                    l0_data  <= {56'd0, BTYPE_IDLE};
                    l1_valid <= 1'b1;
                    l1_sync  <= 2'b10;
                    l1_data  <= {56'd0, BTYPE_IDLE};
                    am_cnt   <= am_cnt + 16'd1;
                end
            end

            // Accept incoming block into pair assembly buffer
            if (in_valid && in_ready) begin
                if (!have_0) begin
                    blk_0  <= {in_data, in_sync};
                    have_0 <= 1'b1;
                end else if (!have_1) begin
                    blk_1  <= {in_data, in_sync};
                    have_1 <= 1'b1;
                end
            end else if (both_out_free && have_pair && !need_am && in_valid && !have_pair) begin
                // unreachable, handled above
            end
        end
    end
endmodule

module link_rx_lanes #(
    parameter DISABLE_DESKEW = 0
) (
    input  wire        clk,
    input  wire        rst,

    input  wire        l0_block_lock,
    input  wire        l0_valid,
    input  wire [1:0]  l0_sync,
    input  wire [63:0] l0_data,

    input  wire        l1_block_lock,
    input  wire        l1_valid,
    input  wire [1:0]  l1_sync,
    input  wire [63:0] l1_data,

    output reg         deskew_lock,
    output reg  signed [7:0] skew_blocks,
    output reg  [15:0] last_am_seq,

    output reg         out_valid,
    output reg  [1:0]  out_sync,
    output reg  [63:0] out_data
);
    localparam [7:0]  BTYPE_IDLE  = 8'h1E;
    localparam [7:0]  BTYPE_ALIGN = 8'h4B;
    localparam [31:0] AM_MAGIC    = 32'h9A_C5_3C_69;

    reg [65:0] fifo0 [0:31];
    reg [65:0] fifo1 [0:31];
    reg [4:0]  wp0, rp0;
    reg [4:0]  wp1, rp1;

    reg        am0_seen, am1_seen;
    reg [15:0] am0_seq,  am1_seq;
    reg [4:0]  am0_wp,   am1_wp;
    reg        rd_phase; // 0 = Lane 0 next, 1 = Lane 1 next

    wire is_am0 = l0_valid && (l0_sync == 2'b10) &&
                  (l0_data[7:0] == BTYPE_ALIGN) && (l0_data[63:32] == AM_MAGIC) &&
                  (l0_data[15:8] == 8'd0);
    wire is_am1 = l1_valid && (l1_sync == 2'b10) &&
                  (l1_data[7:0] == BTYPE_ALIGN) && (l1_data[63:32] == AM_MAGIC) &&
                  (l1_data[15:8] == 8'd1);

    wire [4:0] occ0 = wp0 - rp0;
    wire [4:0] occ1 = wp1 - rp1;
    wire       both_nonempty = (wp0 != rp0) && (wp1 != rp1);

    wire [4:0] age0 = wp0 - am0_wp;
    wire [4:0] age1 = wp1 - am1_wp;

    reg  [65:0] cur_blk;
    reg         cur_is_am;
    reg  [4:0]  rp0_init;
    reg  [4:0]  rp1_init;
    reg  [4:0]  occ0_init;
    reg  [4:0]  occ1_init;

    integer k;

    always @(posedge clk) begin
        if (rst) begin
            wp0         <= 5'd0;
            rp0         <= 5'd0;
            wp1         <= 5'd0;
            rp1         <= 5'd0;
            am0_seen    <= 1'b0;
            am1_seen    <= 1'b0;
            am0_seq     <= 16'd0;
            am1_seq     <= 16'd0;
            am0_wp      <= 5'd0;
            am1_wp      <= 5'd0;
            deskew_lock <= 1'b0;
            skew_blocks <= 8'sd0;
            last_am_seq <= 16'd0;
            rd_phase    <= 1'b0;
            out_valid   <= 1'b0;
            out_sync    <= 2'b00;
            out_data    <= 64'd0;
            for (k = 0; k < 32; k = k + 1) begin
                fifo0[k] <= 66'd0;
                fifo1[k] <= 66'd0;
            end
        end else if (!l0_block_lock || !l1_block_lock) begin
            // Clear elastic buffers while waiting for both lanes to achieve block lock
            wp0         <= 5'd0;
            rp0         <= 5'd0;
            wp1         <= 5'd0;
            rp1         <= 5'd0;
            am0_seen    <= 1'b0;
            am1_seen    <= 1'b0;
            deskew_lock <= 1'b0;
            rd_phase    <= 1'b0;
            out_valid   <= 1'b0;
        end else begin
            out_valid <= 1'b0;

            // Independent per-lane FIFO writes (drop AMs? No, store everything, track AM positions)
            if (l0_valid) begin
                fifo0[wp0] <= {l0_data, l0_sync};
                wp0        <= wp0 + 5'd1;
                if (is_am0) begin
                    am0_seen <= 1'b1;
                    am0_seq  <= l0_data[31:16];
                    am0_wp   <= wp0;
                end
            end

            if (l1_valid) begin
                fifo1[wp1] <= {l1_data, l1_sync};
                wp1        <= wp1 + 5'd1;
                if (is_am1) begin
                    am1_seen <= 1'b1;
                    am1_seq  <= l1_data[31:16];
                    am1_wp   <= wp1;
                end
            end

            if (!deskew_lock) begin
                if (DISABLE_DESKEW != 0) begin
                    // Mutation mode: bypass AM alignment and read both FIFOs from index 0
                    if ((wp0 >= 5'd2) && (wp1 >= 5'd2)) begin
                        rp0         <= 5'd0;
                        rp1         <= 5'd0;
                        deskew_lock <= 1'b1;
                        rd_phase    <= 1'b0;
                        skew_blocks <= 8'sd0;
                    end
                end else if (am0_seen && am1_seen && (am0_seq == am1_seq) &&
                             (age0 < 5'd28) && (age1 < 5'd28)) begin
                    rp0_init    = am0_wp + 5'd1;
                    rp1_init    = am1_wp + 5'd1;
                    occ0_init   = wp0 - rp0_init;
                    occ1_init   = wp1 - rp1_init;
                    rp0         <= rp0_init;
                    rp1         <= rp1_init;
                    deskew_lock <= 1'b1;
                    rd_phase    <= 1'b0;
                    last_am_seq <= am0_seq;
                    skew_blocks <= $signed({3'd0, occ0_init}) - $signed({3'd0, occ1_init});
                    am0_seen    <= 1'b0;
                    am1_seen    <= 1'b0;
                end
            end else begin
                // Read strictly alternating Lane 0 (even) -> Lane 1 (odd) pairs when both ready
                if (rd_phase == 1'b0) begin
                    if (both_nonempty) begin
                        cur_blk = fifo0[rp0];
                        cur_is_am = (cur_blk[1:0] == 2'b10) && (cur_blk[9:2] == BTYPE_ALIGN) &&
                                    (cur_blk[65:34] == AM_MAGIC);
                        rp0      <= rp0 + 5'd1;
                        rd_phase <= 1'b1;
                        if (cur_is_am) begin
                            last_am_seq <= cur_blk[33:18];
                        end else begin
                            out_valid <= 1'b1;
                            out_sync  <= cur_blk[1:0];
                            out_data  <= cur_blk[65:2];
                        end
                    end
                end else begin
                    // rd_phase == 1'b1: finish the paired Lane 1 read immediately
                    cur_blk = fifo1[rp1];
                    cur_is_am = (cur_blk[1:0] == 2'b10) && (cur_blk[9:2] == BTYPE_ALIGN) &&
                                (cur_blk[65:34] == AM_MAGIC);
                    rp1      <= rp1 + 5'd1;
                    rd_phase <= 1'b0;
                    if (!cur_is_am) begin
                        out_valid <= 1'b1;
                        out_sync  <= cur_blk[1:0];
                        out_data  <= cur_blk[65:2];
                    end
                end
            end
        end
    end
endmodule
