// SPDX-License-Identifier: BSD-2-Clause
// Dual-Path Stream Router & Redundancy Failover Arbiter (Rev06)
//
// Connects two sensor packet streams:
//   - s0 (Radar DDC, stream_id = 0)
//   - s1 (SDR DDC / Telemetry, stream_id = 1)
// onto two independent uplinks:
//   - Port A: IAS1 2-lane PCS TX (link_pcs_tx)
//   - Port B: ETH  1G SGMII/UDP  (eth_mac_udp)
//
// Policies (policy[1:0], REDUNDANCY.md §2.4):
//   - 2'd0 STREAM_SPLIT (default): s0 -> IAS1, s1 -> ETH. If ias_fault,
//     fails s0+s1 over to ETH; if eth_fault, fails s1+s0 over to IAS1.
//   - 2'd1 MIRROR_1P1: mirrors active stream identically onto BOTH IAS1 and
//     ETH with matching (stream_id, seq_num, timestamp) for 0-loss Kria dedup.
//   - 2'd2 IAS_ONLY: all streams muxed onto IAS1 only.
//   - 2'd3 ETH_ONLY: all streams muxed onto ETH only.
//
// Strictly honors sop/eop packet boundaries before switching streams.

`timescale 1ns/1ps
`default_nettype none

module dual_path_mux (
    input  wire        clk,
    input  wire        rst,

    input  wire [1:0]  policy,       // 0=STREAM_SPLIT, 1=MIRROR_1P1, 2=IAS_ONLY, 3=ETH_ONLY
    input  wire        ias_healthy,
    input  wire        eth_healthy,

    // Stream 0 input (Radar, stream_id=0)
    input  wire        s0_valid,
    output reg         s0_ready,
    input  wire        s0_sop,
    input  wire        s0_eop,
    input  wire [7:0]  s0_stream_id,
    input  wire [15:0] s0_len,
    input  wire [31:0] s0_seq,
    input  wire [63:0] s0_timestamp,
    input  wire [63:0] s0_data,

    // Stream 1 input (SDR / Telemetry, stream_id=1)
    input  wire        s1_valid,
    output reg         s1_ready,
    input  wire        s1_sop,
    input  wire        s1_eop,
    input  wire [7:0]  s1_stream_id,
    input  wire [15:0] s1_len,
    input  wire [31:0] s1_seq,
    input  wire [63:0] s1_timestamp,
    input  wire [63:0] s1_data,

    // Output A -> IAS1 link_pcs_tx
    output reg         ias_valid,
    input  wire        ias_ready,
    output reg         ias_sop,
    output reg         ias_eop,
    output reg  [7:0]  ias_stream_id,
    output reg  [15:0] ias_len,
    output reg  [31:0] ias_seq,
    output reg  [63:0] ias_timestamp,
    output reg  [63:0] ias_data,

    // Output B -> ETH eth_mac_udp
    output reg         eth_valid,
    input  wire        eth_ready,
    output reg         eth_sop,
    output reg         eth_eop,
    output reg  [7:0]  eth_stream_id,
    output reg  [15:0] eth_len,
    output reg  [31:0] eth_seq,
    output reg  [63:0] eth_timestamp,
    output reg  [63:0] eth_data,

    output reg  [31:0] failover_cnt
);

    localparam [1:0] POL_SPLIT  = 2'd0,
                     POL_MIRROR = 2'd1,
                     POL_IAS    = 2'd2,
                     POL_ETH    = 2'd3;

    // -------------------------------------------------------------------------
    // Store-and-forward packet FIFOs (1 per TX port) so neither IAS1 link nor
    // SGMII MAC ever sees a mid-packet valid gap (prevents BTYPE_IDLE errors).
    // -------------------------------------------------------------------------
    reg        ias_fifo_push_valid;
    reg        ias_fifo_push_sop;
    reg        ias_fifo_push_eop;
    reg [7:0]  ias_fifo_push_stream_id;
    reg [15:0] ias_fifo_push_len;
    reg [31:0] ias_fifo_push_seq;
    reg [63:0] ias_fifo_push_timestamp;
    reg [63:0] ias_fifo_push_data;
    reg        ias_fifo_abort;
    wire       ias_fifo_push_ready;

    reg        eth_fifo_push_valid;
    reg        eth_fifo_push_sop;
    reg        eth_fifo_push_eop;
    reg [7:0]  eth_fifo_push_stream_id;
    reg [15:0] eth_fifo_push_len;
    reg [31:0] eth_fifo_push_seq;
    reg [63:0] eth_fifo_push_timestamp;
    reg [63:0] eth_fifo_push_data;
    reg        eth_fifo_abort;
    wire       eth_fifo_push_ready;

    wire        ias_pop_valid, ias_pop_sop, ias_pop_eop;
    wire [7:0]  ias_pop_stream_id;
    wire [15:0] ias_pop_len;
    wire [31:0] ias_pop_seq;
    wire [63:0] ias_pop_timestamp;
    wire [63:0] ias_pop_data;

    wire        eth_pop_valid, eth_pop_sop, eth_pop_eop;
    wire [7:0]  eth_pop_stream_id;
    wire [15:0] eth_pop_len;
    wire [31:0] eth_pop_seq;
    wire [63:0] eth_pop_timestamp;
    wire [63:0] eth_pop_data;

    dual_path_sf_fifo #(
        .DATA_ADDR_W (10),
        .META_ADDR_W (5)
    ) u_fifo_ias (
        .clk               (clk),
        .rst               (rst),
        .push_valid        (ias_fifo_push_valid),
        .push_sop          (ias_fifo_push_sop),
        .push_eop          (ias_fifo_push_eop),
        .push_stream_id    (ias_fifo_push_stream_id),
        .push_len          (ias_fifo_push_len),
        .push_seq          (ias_fifo_push_seq),
        .push_timestamp    (ias_fifo_push_timestamp),
        .push_data         (ias_fifo_push_data),
        .push_abort        (ias_fifo_abort),
        .push_ready        (ias_fifo_push_ready),
        .out_valid         (ias_pop_valid),
        .out_sop           (ias_pop_sop),
        .out_eop           (ias_pop_eop),
        .out_stream_id     (ias_pop_stream_id),
        .out_len           (ias_pop_len),
        .out_seq           (ias_pop_seq),
        .out_timestamp     (ias_pop_timestamp),
        .out_data          (ias_pop_data),
        .out_ready         (ias_ready)
    );

    dual_path_sf_fifo #(
        .DATA_ADDR_W (10),
        .META_ADDR_W (5)
    ) u_fifo_eth (
        .clk               (clk),
        .rst               (rst),
        .push_valid        (eth_fifo_push_valid),
        .push_sop          (eth_fifo_push_sop),
        .push_eop          (eth_fifo_push_eop),
        .push_stream_id    (eth_fifo_push_stream_id),
        .push_len          (eth_fifo_push_len),
        .push_seq          (eth_fifo_push_seq),
        .push_timestamp    (eth_fifo_push_timestamp),
        .push_data         (eth_fifo_push_data),
        .push_abort        (eth_fifo_abort),
        .push_ready        (eth_fifo_push_ready),
        .out_valid         (eth_pop_valid),
        .out_sop           (eth_pop_sop),
        .out_eop           (eth_pop_eop),
        .out_stream_id     (eth_pop_stream_id),
        .out_len           (eth_pop_len),
        .out_seq           (eth_pop_seq),
        .out_timestamp     (eth_pop_timestamp),
        .out_data          (eth_pop_data),
        .out_ready         (eth_ready)
    );

    // Track active ingress packet locks per port (0=none, 1=s0, 2=s1)
    reg [1:0] ias_in_lock, eth_in_lock;
    reg [1:0] mir_lock;
    reg       mir_lock_ias, mir_lock_eth;
    reg       rr_ias, rr_eth, rr_mir;
    reg       prev_failover;
    reg       drop_s0, drop_s1;

    wire failover_active = (policy == POL_SPLIT) && (!ias_healthy || !eth_healthy);

    wire split_busy  = (ias_in_lock != 2'd0) || (eth_in_lock != 2'd0);
    wire mir_mode    = (mir_lock != 2'd0) || ((policy == POL_MIRROR) && !split_busy);

    wire allow_new_split = (policy != POL_MIRROR);
    wire want_s0_ias = allow_new_split && (
                           (policy == POL_SPLIT && ias_healthy) ||
                           (policy == POL_IAS));
    wire want_s0_eth = allow_new_split && (
                           (policy == POL_SPLIT && !ias_healthy && eth_healthy) ||
                           (policy == POL_ETH));
    wire want_s1_eth = allow_new_split && (
                           (policy == POL_SPLIT && eth_healthy) ||
                           (policy == POL_ETH));
    wire want_s1_ias = allow_new_split && (
                           (policy == POL_SPLIT && !eth_healthy && ias_healthy) ||
                           (policy == POL_IAS));

    // Only begin a new packet on SOP when the source is not locked to another port or draining
    wire s0_avail_ias = want_s0_ias && !drop_s0 && s0_valid && s0_sop && (eth_in_lock != 2'd1);
    wire s1_avail_ias = want_s1_ias && !drop_s1 && s1_valid && s1_sop && (eth_in_lock != 2'd2);
    wire s0_avail_eth = want_s0_eth && !drop_s0 && s0_valid && s0_sop && (ias_in_lock != 2'd1);
    wire s1_avail_eth = want_s1_eth && !drop_s1 && s1_valid && s1_sop && (ias_in_lock != 2'd2);
    wire s0_avail_mir = !drop_s0 && s0_valid && s0_sop;
    wire s1_avail_mir = !drop_s1 && s1_valid && s1_sop;

    reg [1:0] ias_in_sel, eth_in_sel, mir_sel;
    reg       mir_en_ias, mir_en_eth, mir_targets_ok, mir_xfer;
    reg       mir_valid, mir_sop, mir_eop;
    reg [7:0]  mir_stream_id;
    reg [15:0] mir_len;
    reg [31:0] mir_seq;
    reg [63:0] mir_timestamp;
    reg [63:0] mir_data;

    always @(*) begin
        // FIFO pop outputs drive external module outputs directly
        ias_valid     = ias_pop_valid;
        ias_sop       = ias_pop_sop;
        ias_eop       = ias_pop_eop;
        ias_stream_id = ias_pop_stream_id;
        ias_len       = ias_pop_len;
        ias_seq       = ias_pop_seq;
        ias_timestamp = ias_pop_timestamp;
        ias_data      = ias_pop_data;

        eth_valid     = eth_pop_valid;
        eth_sop       = eth_pop_sop;
        eth_eop       = eth_pop_eop;
        eth_stream_id = eth_pop_stream_id;
        eth_len       = eth_pop_len;
        eth_seq       = eth_pop_seq;
        eth_timestamp = eth_pop_timestamp;
        eth_data      = eth_pop_data;

        // Defaults
        ias_in_sel     = 2'd0;
        eth_in_sel     = 2'd0;
        mir_sel        = 2'd0;
        mir_en_ias     = 1'b0;
        mir_en_eth     = 1'b0;
        mir_targets_ok = 1'b0;
        mir_xfer       = 1'b0;
        mir_valid      = 1'b0;
        mir_sop        = 1'b0;
        mir_eop        = 1'b0;
        mir_stream_id  = 8'd0;
        mir_len        = 16'd0;
        mir_seq        = 32'd0;
        mir_timestamp  = 64'd0;
        mir_data       = 64'd0;

        ias_fifo_push_valid     = 1'b0;
        ias_fifo_push_sop       = 1'b0;
        ias_fifo_push_eop       = 1'b0;
        ias_fifo_push_stream_id = 8'd0;
        ias_fifo_push_len       = 16'd0;
        ias_fifo_push_seq       = 32'd0;
        ias_fifo_push_timestamp = 64'd0;
        ias_fifo_push_data      = 64'd0;
        ias_fifo_abort          = 1'b0;

        eth_fifo_push_valid     = 1'b0;
        eth_fifo_push_sop       = 1'b0;
        eth_fifo_push_eop       = 1'b0;
        eth_fifo_push_stream_id = 8'd0;
        eth_fifo_push_len       = 16'd0;
        eth_fifo_push_seq       = 32'd0;
        eth_fifo_push_timestamp = 64'd0;
        eth_fifo_push_data      = 64'd0;
        eth_fifo_abort          = 1'b0;

        s0_ready = 1'b0;
        s1_ready = 1'b0;

        if (mir_mode) begin
            // 1+1 Active-Active Mirror for BOTH s0 (0x01) and s1 (0x02)
            if (mir_lock != 2'd0) begin
                mir_sel    = mir_lock;
                // Keep finishing already-started targets cleanly unless FIFO is full while unhealthy
                mir_en_ias = mir_lock_ias && (ias_healthy || ias_fifo_push_ready);
                mir_en_eth = mir_lock_eth && (eth_healthy || eth_fifo_push_ready);
                if (mir_lock_ias && !ias_healthy && !ias_fifo_push_ready) ias_fifo_abort = 1'b1;
                if (mir_lock_eth && !eth_healthy && !eth_fifo_push_ready) eth_fifo_abort = 1'b1;
            end else begin
                if (s0_avail_mir && s1_avail_mir)
                    mir_sel = rr_mir ? 2'd2 : 2'd1;
                else if (s0_avail_mir)
                    mir_sel = 2'd1;
                else if (s1_avail_mir)
                    mir_sel = 2'd2;
                else
                    mir_sel = 2'd0;
                mir_en_ias = ias_healthy;
                mir_en_eth = eth_healthy;
            end

            if (mir_sel == 2'd1) begin
                mir_valid     = s0_valid;
                mir_sop       = s0_sop;
                mir_eop       = s0_eop;
                mir_stream_id = s0_stream_id;
                mir_len       = s0_len;
                mir_seq       = s0_seq;
                mir_timestamp = s0_timestamp;
                mir_data      = s0_data;
            end else if (mir_sel == 2'd2) begin
                mir_valid     = s1_valid;
                mir_sop       = s1_sop;
                mir_eop       = s1_eop;
                mir_stream_id = s1_stream_id;
                mir_len       = s1_len;
                mir_seq       = s1_seq;
                mir_timestamp = s1_timestamp;
                mir_data      = s1_data;
            end

            mir_targets_ok = (mir_en_ias || mir_en_eth) &&
                             (!mir_en_ias || ias_fifo_push_ready) &&
                             (!mir_en_eth || eth_fifo_push_ready);
            mir_xfer = (mir_sel != 2'd0) && mir_valid && mir_targets_ok;

            ias_fifo_push_valid     = mir_xfer && mir_en_ias;
            ias_fifo_push_sop       = mir_sop;
            ias_fifo_push_eop       = mir_eop;
            ias_fifo_push_stream_id = mir_stream_id;
            ias_fifo_push_len       = mir_len;
            ias_fifo_push_seq       = mir_seq;
            ias_fifo_push_timestamp = mir_timestamp;
            ias_fifo_push_data      = mir_data;

            eth_fifo_push_valid     = mir_xfer && mir_en_eth;
            eth_fifo_push_sop       = mir_sop;
            eth_fifo_push_eop       = mir_eop;
            eth_fifo_push_stream_id = mir_stream_id;
            eth_fifo_push_len       = mir_len;
            eth_fifo_push_seq       = mir_seq;
            eth_fifo_push_timestamp = mir_timestamp;
            eth_fifo_push_data      = mir_data;

            s0_ready = drop_s0 || ((mir_sel == 2'd1) && mir_targets_ok);
            s1_ready = drop_s1 || ((mir_sel == 2'd2) && mir_targets_ok);
        end else begin
            // Split / IAS-only / ETH-only independent ingress arbitration
            if (ias_in_lock != 2'd0) begin
                ias_in_sel = ias_in_lock;
            end else if (s0_avail_ias && s1_avail_ias) begin
                ias_in_sel = rr_ias ? 2'd2 : 2'd1;
            end else if (s0_avail_ias) begin
                ias_in_sel = 2'd1;
            end else if (s1_avail_ias) begin
                ias_in_sel = 2'd2;
            end

            if (eth_in_lock != 2'd0) begin
                eth_in_sel = eth_in_lock;
            end else if (s0_avail_eth && s1_avail_eth) begin
                eth_in_sel = rr_eth ? 2'd2 : 2'd1;
            end else if (s0_avail_eth) begin
                eth_in_sel = 2'd1;
            end else if (s1_avail_eth) begin
                eth_in_sel = 2'd2;
            end

            if (ias_in_lock != 2'd0 && !ias_healthy && !ias_fifo_push_ready && (policy == POL_SPLIT)) begin
                ias_fifo_abort = 1'b1;
                ias_in_sel     = 2'd0;
            end
            if (eth_in_lock != 2'd0 && !eth_healthy && !eth_fifo_push_ready && (policy == POL_SPLIT)) begin
                eth_fifo_abort = 1'b1;
                eth_in_sel     = 2'd0;
            end

            ias_fifo_push_valid     = ((ias_in_sel == 2'd1) ? s0_valid :
                                       (ias_in_sel == 2'd2) ? s1_valid : 1'b0) &&
                                      ias_fifo_push_ready;
            ias_fifo_push_sop       = (ias_in_sel == 2'd1) ? s0_sop       : s1_sop;
            ias_fifo_push_eop       = (ias_in_sel == 2'd1) ? s0_eop       : s1_eop;
            ias_fifo_push_stream_id = (ias_in_sel == 2'd1) ? s0_stream_id : s1_stream_id;
            ias_fifo_push_len       = (ias_in_sel == 2'd1) ? s0_len       : s1_len;
            ias_fifo_push_seq       = (ias_in_sel == 2'd1) ? s0_seq       : s1_seq;
            ias_fifo_push_timestamp = (ias_in_sel == 2'd1) ? s0_timestamp : s1_timestamp;
            ias_fifo_push_data      = (ias_in_sel == 2'd1) ? s0_data      : s1_data;

            eth_fifo_push_valid     = ((eth_in_sel == 2'd1) ? s0_valid :
                                       (eth_in_sel == 2'd2) ? s1_valid : 1'b0) &&
                                      eth_fifo_push_ready;
            eth_fifo_push_sop       = (eth_in_sel == 2'd1) ? s0_sop       : s1_sop;
            eth_fifo_push_eop       = (eth_in_sel == 2'd1) ? s0_eop       : s1_eop;
            eth_fifo_push_stream_id = (eth_in_sel == 2'd1) ? s0_stream_id : s1_stream_id;
            eth_fifo_push_len       = (eth_in_sel == 2'd1) ? s0_len       : s1_len;
            eth_fifo_push_seq       = (eth_in_sel == 2'd1) ? s0_seq       : s1_seq;
            eth_fifo_push_timestamp = (eth_in_sel == 2'd1) ? s0_timestamp : s1_timestamp;
            eth_fifo_push_data      = (eth_in_sel == 2'd1) ? s0_data      : s1_data;

            s0_ready = drop_s0 ||
                       ((ias_in_sel == 2'd1) && ias_fifo_push_ready) ||
                       ((eth_in_sel == 2'd1) && eth_fifo_push_ready);
            s1_ready = drop_s1 ||
                       ((ias_in_sel == 2'd2) && ias_fifo_push_ready) ||
                       ((eth_in_sel == 2'd2) && eth_fifo_push_ready);
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            ias_in_lock   <= 2'd0;
            eth_in_lock   <= 2'd0;
            mir_lock      <= 2'd0;
            mir_lock_ias  <= 1'b0;
            mir_lock_eth  <= 1'b0;
            rr_ias        <= 1'b0;
            rr_eth        <= 1'b0;
            rr_mir        <= 1'b0;
            failover_cnt  <= 32'd0;
            prev_failover <= 1'b0;
            drop_s0       <= 1'b0;
            drop_s1       <= 1'b0;
        end else begin
            prev_failover <= failover_active;
            if (failover_active && !prev_failover)
                failover_cnt <= failover_cnt + 32'd1;

            if (drop_s0 && s0_valid && s0_eop)
                drop_s0 <= 1'b0;
            if (drop_s1 && s1_valid && s1_eop)
                drop_s1 <= 1'b0;

            if (mir_mode) begin
                if (mir_xfer) begin
                    if (mir_eop) begin
                        mir_lock     <= 2'd0;
                        mir_lock_ias <= 1'b0;
                        mir_lock_eth <= 1'b0;
                        rr_mir       <= ~rr_mir;
                    end else if (mir_sop) begin
                        mir_lock     <= mir_sel;
                        mir_lock_ias <= mir_en_ias;
                        mir_lock_eth <= mir_en_eth;
                    end
                end else if (mir_lock != 2'd0) begin
                    if (mir_lock_ias && !ias_healthy && !ias_fifo_push_ready) mir_lock_ias <= 1'b0;
                    if (mir_lock_eth && !eth_healthy && !eth_fifo_push_ready) mir_lock_eth <= 1'b0;
                    if (!mir_en_ias && !mir_en_eth) begin
                        if (mir_lock == 2'd1) drop_s0 <= 1'b1;
                        if (mir_lock == 2'd2) drop_s1 <= 1'b1;
                        mir_lock <= 2'd0;
                    end
                end
            end else begin
                if (ias_fifo_abort) begin
                    if (ias_in_lock == 2'd1) drop_s0 <= 1'b1;
                    if (ias_in_lock == 2'd2) drop_s1 <= 1'b1;
                    ias_in_lock <= 2'd0;
                end else if (ias_fifo_push_valid) begin
                    if (ias_fifo_push_eop) begin
                        ias_in_lock <= 2'd0;
                        rr_ias      <= ~rr_ias;
                    end else if (ias_fifo_push_sop) begin
                        ias_in_lock <= ias_in_sel;
                    end
                end

                if (eth_fifo_abort) begin
                    if (eth_in_lock == 2'd1) drop_s0 <= 1'b1;
                    if (eth_in_lock == 2'd2) drop_s1 <= 1'b1;
                    eth_in_lock <= 2'd0;
                end else if (eth_fifo_push_valid) begin
                    if (eth_fifo_push_eop) begin
                        eth_in_lock <= 2'd0;
                        rr_eth      <= ~rr_eth;
                    end else if (eth_fifo_push_sop) begin
                        eth_in_lock <= eth_in_sel;
                    end
                end
            end
        end
    end

endmodule

module dual_path_sf_fifo #(
    parameter integer DATA_ADDR_W = 10,
    parameter integer META_ADDR_W = 5
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        push_valid,
    input  wire        push_sop,
    input  wire        push_eop,
    input  wire [7:0]  push_stream_id,
    input  wire [15:0] push_len,
    input  wire [31:0] push_seq,
    input  wire [63:0] push_timestamp,
    input  wire [63:0] push_data,
    input  wire        push_abort,
    output wire        push_ready,
    output reg         out_valid,
    output wire        out_sop,
    output wire        out_eop,
    output wire [7:0]  out_stream_id,
    output wire [15:0] out_len,
    output wire [31:0] out_seq,
    output wire [63:0] out_timestamp,
    output wire [63:0] out_data,
    input  wire        out_ready
);

    localparam integer DATA_DEPTH = (1 << DATA_ADDR_W);
    localparam integer META_DEPTH = (1 << META_ADDR_W);

    reg [65:0]  data_mem [0:DATA_DEPTH-1];
    reg [119:0] meta_mem [0:META_DEPTH-1];

    reg [DATA_ADDR_W:0] wr_ptr, rd_ptr, pkt_base_ptr;
    reg [META_ADDR_W:0] meta_wr_ptr, meta_rd_ptr;

    wire [DATA_ADDR_W:0] data_used = wr_ptr - rd_ptr;
    wire [META_ADDR_W:0] meta_used = meta_wr_ptr - meta_rd_ptr;

    wire data_full = (data_used >= DATA_DEPTH[DATA_ADDR_W:0]);
    wire meta_full = (meta_used >= META_DEPTH[META_ADDR_W:0]);
    assign push_ready = !data_full && !meta_full;

    wire do_push = push_valid && push_ready;
    reg [119:0] in_hdr;
    wire [119:0] live_hdr = {push_stream_id, push_len, push_seq, push_timestamp};
    wire [119:0] commit_hdr = push_sop ? live_hdr : in_hdr;

    reg        pop_state;
    reg [65:0] bram_q;
    reg [119:0] hdr_q;
    wire meta_empty = (meta_wr_ptr == meta_rd_ptr);

    assign out_sop = bram_q[65];
    assign out_eop = bram_q[64];
    assign out_data = bram_q[63:0];
    assign {out_stream_id, out_len, out_seq, out_timestamp} = hdr_q;

    always @(posedge clk) begin
        if (rst) begin
            wr_ptr       <= {(DATA_ADDR_W+1){1'b0}};
            rd_ptr       <= {(DATA_ADDR_W+1){1'b0}};
            pkt_base_ptr <= {(DATA_ADDR_W+1){1'b0}};
            meta_wr_ptr  <= {(META_ADDR_W+1){1'b0}};
            meta_rd_ptr  <= {(META_ADDR_W+1){1'b0}};
            in_hdr       <= 120'd0;
            pop_state    <= 1'b0;
            out_valid    <= 1'b0;
            bram_q       <= 66'd0;
            hdr_q        <= 120'd0;
        end else begin
            // Ingress write / abort
            if (push_abort) begin
                wr_ptr <= pkt_base_ptr;
            end else if (do_push) begin
                data_mem[wr_ptr[DATA_ADDR_W-1:0]] <= {push_sop, push_eop, push_data};
                wr_ptr <= wr_ptr + {{DATA_ADDR_W{1'b0}}, 1'b1};
                if (push_sop)
                    in_hdr <= live_hdr;
                if (push_eop) begin
                    meta_mem[meta_wr_ptr[META_ADDR_W-1:0]] <= commit_hdr;
                    meta_wr_ptr  <= meta_wr_ptr + {{META_ADDR_W{1'b0}}, 1'b1};
                    pkt_base_ptr <= wr_ptr + {{DATA_ADDR_W{1'b0}}, 1'b1};
                end
            end

            // Egress store-and-forward pop
            if (!pop_state) begin
                out_valid <= 1'b0;
                if (!meta_empty) begin
                    bram_q    <= data_mem[rd_ptr[DATA_ADDR_W-1:0]];
                    hdr_q     <= meta_mem[meta_rd_ptr[META_ADDR_W-1:0]];
                    rd_ptr    <= rd_ptr + {{DATA_ADDR_W{1'b0}}, 1'b1};
                    pop_state <= 1'b1;
                    out_valid <= 1'b1;
                end
            end else if (out_ready) begin
                if (bram_q[64]) begin
                    meta_rd_ptr <= meta_rd_ptr + {{META_ADDR_W{1'b0}}, 1'b1};
                    pop_state   <= 1'b0;
                    out_valid   <= 1'b0;
                end else begin
                    bram_q <= data_mem[rd_ptr[DATA_ADDR_W-1:0]];
                    rd_ptr <= rd_ptr + {{DATA_ADDR_W{1'b0}}, 1'b1};
                end
            end
        end
    end

endmodule
`default_nettype wire
