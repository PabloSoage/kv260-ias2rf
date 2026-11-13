// SPDX-License-Identifier: BSD-2-Clause
// Testbench: Kria K26 AXI4-Stream & AXI4-Lite Wrapper (link_axis)
//
// Checks:
//   1. Uplink path: link_pcs_tx (2-lane) -> 1-bit error injection -> link_pcs_rx
//      -> link_axis -> AXI4-Stream Master RX (m_axis_rx_*) under aggressive random
//      m_axis_rx_tready back-pressure (~60% stalled cycles).
//   2. Verifies exact payload integrity, TLAST placement, TID stream ID, and TUSER[0]
//      CRC-error signaling on the corrupted packet.
//   3. Downlink path: AXI4-Stream Slave TX (s_axis_tx_*) -> link_axis ->
//      link_pcs_single_tx -> link_pcs_single_rx verifies command burst framing.
//   4. AXI4-Lite CSR read/write across 0x00..0x30 (LINK_CTRL, IDELAY_CTRL_L0/L1,
//      ERR_CNT_CRC, PKT_CNT_RX, DESKEW_STATUS, EYE_SCAN_L0/L1) + W1C error clear.
//
// Mutations:
//   -Mutate ignore_tready : drops m_axis_rx_tready back-pressure -> loses payload words

`timescale 1ns/1ps

module tb_link_axis;

    reg clk = 1'b0;
    always #4.0 clk = ~clk; // 125 MHz parallel clock

    reg rst = 1'b1;

    reg [63:0] prng = 64'hCAFE_1234_9876_5431;
    function [63:0] next_rand(input [63:0] x);
        begin
            next_rand = {x[62:0], x[63] ^ x[62] ^ x[60] ^ x[59]};
        end
    endfunction

    reg [63:0] ts_cnt = 64'd0;
    always @(posedge clk) begin
        if (rst) ts_cnt <= 64'd0;
        else     ts_cnt <= ts_cnt + 64'd1;
    end

    // -------------------------------------------------------------------------
    // Uplink PCS Source (link_pcs_tx -> link_pcs_rx -> link_axis)
    // -------------------------------------------------------------------------
    reg         up_valid = 1'b0;
    wire        up_ready;
    reg         up_sop = 1'b0, up_eop = 1'b0;
    reg  [7:0]  up_sid = 8'd0;
    reg  [15:0] up_len = 16'd0;
    reg  [31:0] up_seq = 32'd0;
    reg  [63:0] up_ts = 64'd0, up_data = 64'd0;
    wire [7:0]  up_byte_l0, up_byte_l1;

    link_pcs_tx #(.AM_PERIOD(64)) u_up_tx (
        .clk           (clk),
        .rst           (rst),
        .pkt_valid     (up_valid),
        .pkt_ready     (up_ready),
        .pkt_sop       (up_sop),
        .pkt_eop       (up_eop),
        .pkt_stream_id (up_sid),
        .pkt_len       (up_len),
        .pkt_seq       (up_seq),
        .pkt_timestamp (up_ts),
        .pkt_data      (up_data),
        .dropped_cnt   (24'd3),
        .local_status  (16'h00A5),
        .tx_byte_l0    (up_byte_l0),
        .tx_byte_l1    (up_byte_l1)
    );

    reg [7:0] err_mask_l0 = 8'd0;
    wire [7:0] rx_byte_l0 = up_byte_l0 ^ err_mask_l0;
    wire [7:0] rx_byte_l1 = up_byte_l1;

    wire        pcs_rx_out_v, pcs_rx_out_sop, pcs_rx_out_eop;
    wire [7:0]  pcs_rx_out_sid;
    wire [15:0] pcs_rx_out_len;
    wire [31:0] pcs_rx_out_seq;
    wire [63:0] pcs_rx_out_ts, pcs_rx_out_data;
    wire        pcs_done_v, pcs_done_ok, pcs_done_err;
    wire        l0_lock, l1_lock, d_lock;
    wire signed [7:0] skew_blk;
    wire [15:0] rem_stat;
    wire [23:0] rem_drop;
    wire [31:0] sh_err0, sh_err1, pcs_pkt_cnt, pcs_crc_cnt;
    wire        l0_blk_v, l0_blk_ok, l1_blk_v, l1_blk_ok;

    wire pcs_ready = l0_lock && l1_lock && d_lock;

    link_pcs_rx u_up_rx (
        .clk                (clk),
        .rst                (rst),
        .link_ready         (pcs_ready),
        .rx_byte_l0         (rx_byte_l0),
        .rx_byte_l1         (rx_byte_l1),
        .out_valid          (pcs_rx_out_v),
        .out_sop            (pcs_rx_out_sop),
        .out_eop            (pcs_rx_out_eop),
        .out_stream_id      (pcs_rx_out_sid),
        .out_len            (pcs_rx_out_len),
        .out_seq            (pcs_rx_out_seq),
        .out_timestamp      (pcs_rx_out_ts),
        .out_data           (pcs_rx_out_data),
        .pkt_done_valid     (pcs_done_v),
        .pkt_done_ok        (pcs_done_ok),
        .pkt_done_err       (pcs_done_err),
        .l0_block_lock      (l0_lock),
        .l1_block_lock      (l1_lock),
        .deskew_lock        (d_lock),
        .skew_blocks        (skew_blk),
        .remote_status      (rem_stat),
        .remote_dropped_cnt (rem_drop),
        .sh_err_cnt_l0      (sh_err0),
        .sh_err_cnt_l1      (sh_err1),
        .pkt_rx_cnt         (pcs_pkt_cnt),
        .crc_err_cnt        (pcs_crc_cnt),
        .l0_rx_blk_valid    (l0_blk_v),
        .l0_rx_blk_ok       (l0_blk_ok),
        .l1_rx_blk_valid    (l1_blk_v),
        .l1_rx_blk_ok       (l1_blk_ok)
    );

    // -------------------------------------------------------------------------
    // DUT: link_axis
    // -------------------------------------------------------------------------
    wire [63:0] m_axis_rx_tdata;
    wire        m_axis_rx_tvalid;
    reg         m_axis_rx_tready = 1'b0;
    wire        m_axis_rx_tlast;
    wire [7:0]  m_axis_rx_tid;
    wire [0:0]  m_axis_rx_tuser;

    reg  [63:0] s_axis_tx_tdata  = 64'd0;
    reg         s_axis_tx_tvalid = 1'b0;
    wire        s_axis_tx_tready;
    reg         s_axis_tx_tlast  = 1'b0;
    reg  [7:0]  s_axis_tx_tid    = 8'h10;
    reg  [15:0] s_axis_tx_tuser  = 16'd0;

    reg  [7:0]  s_axi_awaddr  = 8'd0;
    reg         s_axi_awvalid = 1'b0;
    wire        s_axi_awready;
    reg  [31:0] s_axi_wdata   = 32'd0;
    reg  [3:0]  s_axi_wstrb   = 4'hF;
    reg         s_axi_wvalid  = 1'b0;
    wire        s_axi_wready;
    wire [1:0]  s_axi_bresp;
    wire        s_axi_bvalid;
    reg         s_axi_bready  = 1'b1;
    reg  [7:0]  s_axi_araddr  = 8'd0;
    reg         s_axi_arvalid = 1'b0;
    wire        s_axi_arready;
    wire [31:0] s_axi_rdata;
    wire [1:0]  s_axi_rresp;
    wire        s_axi_rvalid;
    reg         s_axi_rready  = 1'b1;

    wire        dn_valid;
    wire        dn_ready;
    wire        dn_sop, dn_eop;
    wire [7:0]  dn_sid;
    wire [15:0] dn_len;
    wire [31:0] dn_seq;
    wire [63:0] dn_ts, dn_data;

    wire        ctrl_soft_rst, ctrl_loopback_en, ctrl_retrain_pulse;
    wire        ctrl_tap_override_en, ctrl_prbs7_tx_en, ctrl_prbs7_rx_chk_en;
    wire [8:0]  cfg_tap_l0, cfg_tap_l1;
    wire        cfg_load_l0, cfg_load_l1;
    wire [31:0] last_rx_seq;
    wire [63:0] last_rx_ts;
    wire [15:0] last_rx_len;

    reg seen_retrain = 1'b0, seen_ld0 = 1'b0, seen_ld1 = 1'b0;
    always @(posedge clk) begin
        if (rst) begin
            seen_retrain <= 1'b0;
            seen_ld0     <= 1'b0;
            seen_ld1     <= 1'b0;
        end else begin
            if (ctrl_retrain_pulse) seen_retrain <= 1'b1;
            if (cfg_load_l0)        seen_ld0     <= 1'b1;
            if (cfg_load_l1)        seen_ld1     <= 1'b1;
        end
    end

    link_axis #(
        .RX_FIFO_DEPTH (256),
        .TX_FIFO_DEPTH (128)
    ) dut (
        .clk                  (clk),
        .rst                  (rst),
        .m_axis_rx_tdata      (m_axis_rx_tdata),
        .m_axis_rx_tvalid     (m_axis_rx_tvalid),
        .m_axis_rx_tready     (m_axis_rx_tready),
        .m_axis_rx_tlast      (m_axis_rx_tlast),
        .m_axis_rx_tid        (m_axis_rx_tid),
        .m_axis_rx_tuser      (m_axis_rx_tuser),
        .s_axis_tx_tdata      (s_axis_tx_tdata),
        .s_axis_tx_tvalid     (s_axis_tx_tvalid),
        .s_axis_tx_tready     (s_axis_tx_tready),
        .s_axis_tx_tlast      (s_axis_tx_tlast),
        .s_axis_tx_tid        (s_axis_tx_tid),
        .s_axis_tx_tuser      (s_axis_tx_tuser),
        .s_axi_awaddr         (s_axi_awaddr),
        .s_axi_awvalid        (s_axi_awvalid),
        .s_axi_awready        (s_axi_awready),
        .s_axi_wdata          (s_axi_wdata),
        .s_axi_wstrb          (s_axi_wstrb),
        .s_axi_wvalid         (s_axi_wvalid),
        .s_axi_wready         (s_axi_wready),
        .s_axi_bresp          (s_axi_bresp),
        .s_axi_bvalid         (s_axi_bvalid),
        .s_axi_bready         (s_axi_bready),
        .s_axi_araddr         (s_axi_araddr),
        .s_axi_arvalid        (s_axi_arvalid),
        .s_axi_arready        (s_axi_arready),
        .s_axi_rdata          (s_axi_rdata),
        .s_axi_rresp          (s_axi_rresp),
        .s_axi_rvalid         (s_axi_rvalid),
        .s_axi_rready         (s_axi_rready),
        .rx_out_valid         (pcs_rx_out_v),
        .rx_out_sop           (pcs_rx_out_sop),
        .rx_out_eop           (pcs_rx_out_eop),
        .rx_out_stream_id     (pcs_rx_out_sid),
        .rx_out_len           (pcs_rx_out_len),
        .rx_out_seq           (pcs_rx_out_seq),
        .rx_out_timestamp     (pcs_rx_out_ts),
        .rx_out_data          (pcs_rx_out_data),
        .rx_pkt_done_valid    (pcs_done_v),
        .rx_pkt_done_ok       (pcs_done_ok),
        .rx_pkt_done_err      (pcs_done_err),
        .tx_pkt_valid         (dn_valid),
        .tx_pkt_ready         (dn_ready),
        .tx_pkt_sop           (dn_sop),
        .tx_pkt_eop           (dn_eop),
        .tx_pkt_stream_id     (dn_sid),
        .tx_pkt_len           (dn_len),
        .tx_pkt_seq           (dn_seq),
        .tx_pkt_timestamp     (dn_ts),
        .tx_pkt_data          (dn_data),
        .timestamp_cnt        (ts_cnt),
        .ctrl_soft_rst        (ctrl_soft_rst),
        .ctrl_loopback_en     (ctrl_loopback_en),
        .ctrl_retrain_pulse   (ctrl_retrain_pulse),
        .ctrl_tap_override_en (ctrl_tap_override_en),
        .ctrl_prbs7_tx_en     (ctrl_prbs7_tx_en),
        .ctrl_prbs7_rx_chk_en (ctrl_prbs7_rx_chk_en),
        .cfg_tap_l0           (cfg_tap_l0),
        .cfg_load_l0          (cfg_load_l0),
        .cfg_tap_l1           (cfg_tap_l1),
        .cfg_load_l1          (cfg_load_l1),
        .st_train_state       (3'd5),
        .st_l0_block_lock     (l0_lock),
        .st_l1_block_lock     (l1_lock),
        .st_deskew_lock       (d_lock),
        .st_link_up           (pcs_ready),
        .st_idelayctrl_rdy    (1'b1),
        .st_remote_status     (rem_stat[7:0]),
        .active_tap_l0        (9'd200),
        .active_tap_l1        (9'd212),
        .pcs_sh_err_cnt_l0    (sh_err0),
        .pcs_sh_err_cnt_l1    (sh_err1),
        .tx_dropped_cnt       (rem_drop),
        .skew_blocks          (skew_blk),
        .am_seq               (16'h4B5A),
        .pcs_prbs_err_cnt     (32'd0),
        .eye_left_l0          (9'd120),
        .eye_right_l0         (9'd280),
        .eye_left_l1          (9'd136),
        .eye_right_l1         (9'd288),
        .last_rx_seq          (last_rx_seq),
        .last_rx_timestamp    (last_rx_ts),
        .last_rx_len          (last_rx_len)
    );

    // -------------------------------------------------------------------------
    // Downlink PCS Single-Lane Loopback (s_axis_tx -> link_axis -> single_tx -> single_rx)
    // -------------------------------------------------------------------------
    wire [7:0] dn_byte;
    link_pcs_single_tx u_dn_tx (
        .clk           (clk),
        .rst           (rst),
        .pkt_valid     (dn_valid),
        .pkt_ready     (dn_ready),
        .pkt_sop       (dn_sop),
        .pkt_eop       (dn_eop),
        .pkt_stream_id (dn_sid),
        .pkt_len       (dn_len),
        .pkt_seq       (dn_seq),
        .pkt_timestamp (dn_ts),
        .pkt_data      (dn_data),
        .dropped_cnt   (24'd0),
        .local_status  (16'h0001),
        .tx_byte_l0    (dn_byte)
    );

    wire        dn_rx_v, dn_rx_sop, dn_rx_eop, dn_done_v, dn_done_ok, dn_done_err, dn_lock;
    wire [7:0]  dn_rx_sid;
    wire [15:0] dn_rx_len;
    wire [31:0] dn_rx_seq;
    wire [63:0] dn_rx_ts, dn_rx_data;
    wire [15:0] dn_rem_stat;
    wire [23:0] dn_rem_drop;
    wire [31:0] dn_sh_err, dn_pkt_cnt, dn_crc_cnt;
    wire        dn_blk_v, dn_blk_ok;

    link_pcs_single_rx u_dn_rx (
        .clk                (clk),
        .rst                (rst),
        .link_ready         (dn_lock),
        .rx_byte_l0         (dn_byte),
        .out_valid          (dn_rx_v),
        .out_sop            (dn_rx_sop),
        .out_eop            (dn_rx_eop),
        .out_stream_id      (dn_rx_sid),
        .out_len            (dn_rx_len),
        .out_seq            (dn_rx_seq),
        .out_timestamp      (dn_rx_ts),
        .out_data           (dn_rx_data),
        .pkt_done_valid     (dn_done_v),
        .pkt_done_ok        (dn_done_ok),
        .pkt_done_err       (dn_done_err),
        .l0_block_lock      (dn_lock),
        .remote_status      (dn_rem_stat),
        .remote_dropped_cnt (dn_rem_drop),
        .sh_err_cnt_l0      (dn_sh_err),
        .pkt_rx_cnt         (dn_pkt_cnt),
        .crc_err_cnt        (dn_crc_cnt),
        .l0_rx_blk_valid    (dn_blk_v),
        .l0_rx_blk_ok       (dn_blk_ok)
    );

    // -------------------------------------------------------------------------
    // Random Back-Pressure Generator & AXI-Stream RX Scoreboard
    // -------------------------------------------------------------------------
    reg stall_enable = 1'b0;
    always @(posedge clk) begin
        if (rst) begin
            m_axis_rx_tready <= 1'b0;
        end else if (!stall_enable) begin
            m_axis_rx_tready <= 1'b0;
        end else begin
            prng <= next_rand(prng);
            // ~37% ready rate (aggressive >60% back-pressure stalls)
            m_axis_rx_tready <= (prng[2:0] < 3'd3);
        end
    end

    localparam integer NUM_PKTS = 8;
    reg [63:0] exp_pay   [0:NUM_PKTS-1][0:31];
    integer    exp_words [0:NUM_PKTS-1];
    reg [7:0]  exp_sid   [0:NUM_PKTS-1];
    reg        exp_err   [0:NUM_PKTS-1];

    integer axis_rx_pkts = 0;
    integer axis_rx_w    = 0;
    integer axis_mismatches = 0;

    always @(posedge clk) begin
        if (!rst && m_axis_rx_tvalid && m_axis_rx_tready) begin
            if (axis_rx_pkts < NUM_PKTS) begin
                if (m_axis_rx_tid !== exp_sid[axis_rx_pkts]) begin
                    $display("DBG_MIS tid pkt=%0d w=%0d got=%02x exp=%02x", axis_rx_pkts, axis_rx_w, m_axis_rx_tid, exp_sid[axis_rx_pkts]);
                    axis_mismatches <= axis_mismatches + 1;
                end
                if (!exp_err[axis_rx_pkts]) begin
                    if (m_axis_rx_tdata !== exp_pay[axis_rx_pkts][axis_rx_w]) begin
                        $display("DBG_MIS data pkt=%0d w=%0d got=%016x exp=%016x", axis_rx_pkts, axis_rx_w, m_axis_rx_tdata, exp_pay[axis_rx_pkts][axis_rx_w]);
                        axis_mismatches <= axis_mismatches + 1;
                    end
                end
                if (m_axis_rx_tlast) begin
                    if (!exp_err[axis_rx_pkts] && ((axis_rx_w + 1) !== exp_words[axis_rx_pkts])) begin
                        $display("DBG_MIS len pkt=%0d got_w=%0d exp_w=%0d", axis_rx_pkts, axis_rx_w + 1, exp_words[axis_rx_pkts]);
                        axis_mismatches <= axis_mismatches + 1;
                    end
                    if (m_axis_rx_tuser[0] !== exp_err[axis_rx_pkts]) begin
                        $display("DBG_MIS tuser pkt=%0d got=%0d exp=%0d", axis_rx_pkts, m_axis_rx_tuser[0], exp_err[axis_rx_pkts]);
                        axis_mismatches <= axis_mismatches + 1;
                    end
                    axis_rx_pkts <= axis_rx_pkts + 1;
                    axis_rx_w    <= 0;
                end else begin
                    axis_rx_w <= axis_rx_w + 1;
                end
            end
        end
    end

    // Monitor downlink RX command words
    integer dn_good_cnt = 0;
    reg [63:0] dn_cap_w0 = 64'd0, dn_cap_w1 = 64'd0;
    integer dn_w_idx = 0;
    always @(posedge clk) begin
        if (!rst) begin
            if (dn_rx_v) begin
                if (dn_rx_sop) dn_w_idx = 0;
                if (dn_w_idx == 0) dn_cap_w0 <= dn_rx_data;
                if (dn_w_idx == 1) dn_cap_w1 <= dn_rx_data;
                dn_w_idx = dn_w_idx + 1;
            end
            if (dn_done_v && dn_done_ok)
                dn_good_cnt <= dn_good_cnt + 1;
        end
    end

    // AXI4-Lite Master BFM tasks
    task axi_write32;
        input [7:0]  addr;
        input [31:0] data;
        integer t;
        begin
            @(posedge clk);
            s_axi_awaddr  <= addr;
            s_axi_awvalid <= 1'b1;
            s_axi_wdata   <= data;
            s_axi_wstrb   <= 4'hF;
            s_axi_wvalid  <= 1'b1;
            t = 0;
            while ((s_axi_awvalid || s_axi_wvalid) && t < 50) begin
                @(posedge clk);
                if (s_axi_awvalid && s_axi_awready) s_axi_awvalid <= 1'b0;
                if (s_axi_wvalid  && s_axi_wready)  s_axi_wvalid  <= 1'b0;
                t = t + 1;
            end
            t = 0;
            while (!s_axi_bvalid && t < 50) begin
                @(posedge clk);
                t = t + 1;
            end
            @(posedge clk);
        end
    endtask

    task axi_read32;
        input  [7:0]  addr;
        output [31:0] data;
        integer t;
        begin
            @(posedge clk);
            s_axi_araddr  <= addr;
            s_axi_arvalid <= 1'b1;
            t = 0;
            while (s_axi_arvalid && t < 50) begin
                @(posedge clk);
                if (s_axi_arvalid && s_axi_arready) s_axi_arvalid <= 1'b0;
                t = t + 1;
            end
            t = 0;
            while (!s_axi_rvalid && t < 50) begin
                @(posedge clk);
                t = t + 1;
            end
            data = s_axi_rdata;
            @(posedge clk);
        end
    endtask

    task check_eq;
        input [255:0] label;
        input [31:0]  got;
        input [31:0]  exp;
        begin
            if (got !== exp) begin
                $display("FAIL: tb_link_axis %0s got=0x%08x expected=0x%08x", label, got, exp);
                $finish;
            end
        end
    endtask

    integer p, w, cyc;
    reg [31:0] rval;

    initial begin
        repeat (10) @(posedge clk);
        rst = 1'b0;

        // Wait for uplink + downlink PCS lock
        cyc = 0;
        while (!(pcs_ready && dn_lock) && cyc < 5000) begin
            @(posedge clk);
            cyc = cyc + 1;
        end
        if (!(pcs_ready && dn_lock)) begin
            $display("FAIL: tb_link_axis PCS lock timeout");
            $finish;
        end

        // Build 8 uplink packets (packet 3 is 20 words and gets a 1-bit DATA flip -> CRC error)
        for (p = 0; p < NUM_PKTS; p = p + 1) begin
            exp_words[p] = (p == 3) ? 20 : (4 + (p * 2)); // 32..160 bytes
            exp_sid[p]   = 8'h01 + p[7:0];
            exp_err[p]   = (p == 3);
            for (w = 0; w < exp_words[p]; w = w + 1)
                exp_pay[p][w] = {16'hA500 + p[15:0], 16'h0010 + w[15:0], 32'h1122_3300 + w};
        end

        // Keep TREADY low during first 2 packets, then run random ~63% stalls
        for (p = 0; p < NUM_PKTS; p = p + 1) begin
            if (p == 2) stall_enable = 1'b1;
            if (p == 3) repeat (64) @(posedge clk);
            up_sid   <= exp_sid[p];
            up_len   <= exp_words[p] * 8;
            up_seq   <= p;
            up_ts    <= ts_cnt;
            up_valid <= 1'b1;
            up_sop   <= 1'b1;
            w = 0;
            while (w < exp_words[p]) begin
                up_data <= exp_pay[p][w];
                up_eop  <= (w == exp_words[p] - 1);
                @(posedge clk);
                if (up_valid && up_ready) begin
                    if (exp_err[p] && w == 12)
                        err_mask_l0 <= 8'h04;
                    else
                        err_mask_l0 <= 8'h00;
                    w = w + 1;
                    up_sop <= 1'b0;
                end else begin
                    err_mask_l0 <= 8'h00;
                end
            end
            up_valid    <= 1'b0;
            up_eop      <= 1'b0;
            err_mask_l0 <= 8'h00;
            repeat (6) @(posedge clk);
        end

        // Drain RX FIFO under random TREADY
        cyc = 0;
        while ((axis_rx_pkts < NUM_PKTS) && cyc < 2000) begin
            @(posedge clk);
            cyc = cyc + 1;
        end
        if (axis_rx_pkts !== NUM_PKTS) begin
            $display("FAIL: tb_link_axis expected %0d AXIS RX packets, got %0d", NUM_PKTS, axis_rx_pkts);
            $finish;
        end
        if (axis_mismatches != 0) begin
            $display("FAIL: tb_link_axis AXIS RX payload/TUSER mismatches=%0d", axis_mismatches);
            $finish;
        end

        // Verify AXI4-Lite CSR read/write (0x00..0x30)
        axi_read32(8'h18, rval); check_eq("ERR_CNT_CRC", rval, 32'd1);
        axi_read32(8'h1C, rval); check_eq("PKT_CNT_RX",  rval, 32'd7);
        axi_read32(8'h20, rval); check_eq("PKT_CNT_DROP", rval, 32'h0000_0003);
        axi_read32(8'h2C, rval); check_eq("EYE_SCAN_L0", rval, {7'd0, 9'd280, 7'd0, 9'd120});
        axi_read32(8'h30, rval); check_eq("EYE_SCAN_L1", rval, {7'd0, 9'd288, 7'd0, 9'd136});

        // Write LINK_CTRL (retrain + tap_override + W1C clear errors) and IDELAY_CTRL_L0/L1
        axi_write32(8'h08, 32'h8000_00C8);
        axi_write32(8'h0C, 32'h8000_00D4);
        axi_write32(8'h00, 32'h0000_004C);
        repeat (4) @(posedge clk);
        if (!seen_retrain || !seen_ld0 || !seen_ld1) begin
            $display("FAIL: tb_link_axis CSR pulse outputs missing");
            $finish;
        end
        axi_read32(8'h18, rval); check_eq("ERR_CNT_CRC_CLEARED", rval, 32'd0);
        axi_read32(8'h00, rval); check_eq("LINK_CTRL_READBACK",  rval, 32'h0000_0008);

        // Downlink AXI-Stream TX test (2-word command burst, auto byte length)
        @(posedge clk);
        s_axis_tx_tvalid <= 1'b1;
        s_axis_tx_tid    <= 8'h10;
        s_axis_tx_tuser  <= 16'd0;
        s_axis_tx_tdata  <= 64'h0102_0304_0506_0708;
        s_axis_tx_tlast  <= 1'b0;
        @(posedge clk);
        while (!s_axis_tx_tready) @(posedge clk);
        s_axis_tx_tdata  <= 64'hDEADBEEF_CAFEBABE;
        s_axis_tx_tlast  <= 1'b1;
        @(posedge clk);
        while (!s_axis_tx_tready) @(posedge clk);
        s_axis_tx_tvalid <= 1'b0;
        s_axis_tx_tlast  <= 1'b0;

        cyc = 0;
        while ((dn_good_cnt < 1) && cyc < 500) begin
            @(posedge clk);
            cyc = cyc + 1;
        end
        if (dn_good_cnt != 1 || dn_cap_w0 !== 64'h0102_0304_0506_0708 ||
            dn_cap_w1 !== 64'hDEADBEEF_CAFEBABE || dn_rx_sid !== 8'h10 || dn_rx_len !== 16'd16) begin
            $display("FAIL: tb_link_axis downlink TX verify failed (cnt=%0d sid=%02x len=%0d)",
                     dn_good_cnt, dn_rx_sid, dn_rx_len);
            $finish;
        end

        $display("PASS: tb_link_axis rx_pkts=%0d crc_errs=1 dn_tx=1 backpressure=ok", axis_rx_pkts);
        $finish;
    end

endmodule
