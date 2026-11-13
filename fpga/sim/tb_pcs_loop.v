// SPDX-License-Identifier: BSD-2-Clause
// 2-Lane PCS Loopback Testbench (Plain Verilog-2001):
//   link_pcs_tx (AM_PERIOD=64) -> bit-level 2-lane channel (1.0 Gb/s DDR,
//   random per-lane bit phase + integer-UI skew + 56 ps sub-UI skew per
//   SIGNAL_INTEGRITY.md s3.4, random packet lengths up to 4096 B,
//   controlled bit-error bursts on 3 designated packets) -> link_pcs_rx.
//
// Mutations (via xvlog -d):
//   MUTATE_BAD_SCRAMBLER : wrong scrambler polynomial tap in TX encoder
//   MUTATE_SKIP_CRC      : bypass CRC-32 validation in RX deframer
//   MUTATE_NO_DESKEW     : disable elastic-buffer AM deskew in link_rx_lanes

`timescale 1ns/1ps

module tb_pcs_loop;
`ifdef MUTATE_BAD_SCRAMBLER
    localparam integer BAD_SCR = 1;
`else
    localparam integer BAD_SCR = 0;
`endif
`ifdef MUTATE_SKIP_CRC
    localparam integer SKIP_CRC = 1;
`else
    localparam integer SKIP_CRC = 0;
`endif
`ifdef MUTATE_NO_DESKEW
    localparam integer NO_DESKEW = 1;
`else
    localparam integer NO_DESKEW = 0;
`endif

    localparam integer TOTAL_PKTS       = 28;
    localparam integer LOCK_BOUND_CYC   = 10000;
    localparam integer PHASE_L0_BITS    = 3;
    localparam integer PHASE_L1_BITS    = 157; // > 2 blocks integer-UI skew between L0 and L1

    // Clocks: 1.0 GHz serial bit clock (1.0 ns UI = 500 MHz DDR) and 125 MHz CLKDIV
    reg clk_ui  = 1'b0;
    always #0.5 clk_ui = ~clk_ui;

    reg [2:0] div_cnt = 3'd0;
    reg       clk_125m = 1'b0;
    always @(posedge clk_ui) begin
        div_cnt <= div_cnt + 3'd1;
        if (div_cnt == 3'd3)      clk_125m <= 1'b1;
        else if (div_cnt == 3'd7) clk_125m <= 1'b0;
    end

    reg rst = 1'b1;

    // PCS TX signals
    reg         tx_pkt_valid = 1'b0;
    wire        tx_pkt_ready;
    reg         tx_pkt_sop = 1'b0, tx_pkt_eop = 1'b0;
    reg  [7:0]  tx_pkt_sid = 8'd0;
    reg  [15:0] tx_pkt_len = 16'd0;
    reg  [31:0] tx_pkt_seq = 32'd0;
    reg  [63:0] tx_pkt_ts = 64'd0;
    reg  [63:0] tx_pkt_data = 64'd0;
    reg  [23:0] tx_dropped_cnt = 24'd5;
    wire [7:0]  tx_byte_l0, tx_byte_l1;

    link_pcs_tx #(
        .AM_PERIOD     (64),
        .BAD_SCRAMBLER (BAD_SCR)
    ) u_pcs_tx (
        .clk           (clk_125m),
        .rst           (rst),
        .pkt_valid     (tx_pkt_valid),
        .pkt_ready     (tx_pkt_ready),
        .pkt_sop       (tx_pkt_sop),
        .pkt_eop       (tx_pkt_eop),
        .pkt_stream_id (tx_pkt_sid),
        .pkt_len       (tx_pkt_len),
        .pkt_seq       (tx_pkt_seq),
        .pkt_timestamp (tx_pkt_ts),
        .pkt_data      (tx_pkt_data),
        .dropped_cnt   (tx_dropped_cnt),
        .local_status  (16'h5A02),
        .tx_byte_l0    (tx_byte_l0),
        .tx_byte_l1    (tx_byte_l1)
    );

    // -----------------------------------------------------------------------
    // Bit-level 2-lane channel model:
    //   - Serialize 8 bits/byte @ 1.0 ns UI
    //   - Per-lane integer-UI phase delay (L0=3 UI, L1=157 UI)
    //   - +56 ps sub-UI skew between Lane 0 and Lane 1 (SIGNAL_INTEGRITY.md s3.4)
    //   - Controlled bit error injection signal (inject_bit_err_l0)
    // -----------------------------------------------------------------------
    reg [7:0] sr_tx0 = 8'd0, sr_tx1 = 8'd0;
    reg [2:0] bit_idx = 3'd0;
    reg [PHASE_L0_BITS:0]  pipe0 = 0;
    reg [PHASE_L1_BITS:0]  pipe1 = 0;
    reg       inject_bit_err_l0 = 1'b0;

    always @(posedge clk_ui) begin
        bit_idx <= bit_idx + 3'd1;
        if (bit_idx == 3'd7) begin
            sr_tx0 <= tx_byte_l0;
            sr_tx1 <= tx_byte_l1;
        end else begin
            sr_tx0 <= sr_tx0 >> 1;
            sr_tx1 <= sr_tx1 >> 1;
        end
        pipe0 <= {pipe0[PHASE_L0_BITS-1:0], sr_tx0[0] ^ inject_bit_err_l0};
        pipe1 <= {pipe1[PHASE_L1_BITS-1:0], sr_tx1[0]};
    end

    wire       chan_l0_serial = pipe0[PHASE_L0_BITS];
    wire #0.056 chan_l1_serial = pipe1[PHASE_L1_BITS]; // 56 ps sub-UI inter-lane skew

    // RX deserializer sampling aligned near eye center on delayed channel
    reg [7:0] rx_sh0 = 8'd0, rx_sh1 = 8'd0;
    reg [7:0] rx_byte_l0 = 8'd0, rx_byte_l1 = 8'd0;
    reg [2:0] rx_bit_idx = 3'd0;
    always @(negedge clk_ui) begin
        rx_sh0 <= {chan_l0_serial, rx_sh0[7:1]};
        rx_sh1 <= {chan_l1_serial, rx_sh1[7:1]};
        if (rx_bit_idx == 3'd7) begin
            rx_byte_l0 <= {chan_l0_serial, rx_sh0[7:1]};
            rx_byte_l1 <= {chan_l1_serial, rx_sh1[7:1]};
        end
        rx_bit_idx <= rx_bit_idx + 3'd1;
    end

    // PCS RX
    wire        rx_out_v, rx_out_sop, rx_out_eop;
    wire [7:0]  rx_out_sid;
    wire [15:0] rx_out_len;
    wire [31:0] rx_out_seq;
    wire [63:0] rx_out_ts, rx_out_data;
    wire        rx_done_v, rx_done_ok, rx_done_err;
    wire        l0_lock, l1_lock, d_lock;
    wire signed [7:0] skew_blk;
    wire [15:0] rem_stat;
    wire [23:0] rem_drop;
    wire [31:0] sh_err0, sh_err1, pkt_rx_cnt, crc_err_cnt;

    link_pcs_rx #(
        .DISABLE_DESKEW (NO_DESKEW),
        .SKIP_CRC       (SKIP_CRC)
    ) u_pcs_rx (
        .clk                (clk_125m),
        .rst                (rst),
        .rx_byte_l0         (rx_byte_l0),
        .rx_byte_l1         (rx_byte_l1),
        .out_valid          (rx_out_v),
        .out_sop            (rx_out_sop),
        .out_eop            (rx_out_eop),
        .out_stream_id      (rx_out_sid),
        .out_len            (rx_out_len),
        .out_seq            (rx_out_seq),
        .out_timestamp      (rx_out_ts),
        .out_data           (rx_out_data),
        .pkt_done_valid     (rx_done_v),
        .pkt_done_ok        (rx_done_ok),
        .pkt_done_err       (rx_done_err),
        .l0_block_lock      (l0_lock),
        .l1_block_lock      (l1_lock),
        .deskew_lock        (d_lock),
        .skew_blocks        (skew_blk),
        .remote_status      (rem_stat),
        .remote_dropped_cnt (rem_drop),
        .sh_err_cnt_l0      (sh_err0),
        .sh_err_cnt_l1      (sh_err1),
        .pkt_rx_cnt         (pkt_rx_cnt),
        .crc_err_cnt        (crc_err_cnt)
    );

    // -----------------------------------------------------------------------
    // Packet scoreboard & traffic generator
    // -----------------------------------------------------------------------
    reg [63:0] prng = 64'h1357_2468_ACE0_FDB9;
    function [63:0] next_rand(input [63:0] x);
        begin
            next_rand = {x[62:0], x[63] ^ x[62] ^ x[60] ^ x[59]};
        end
    endfunction

    // Expected packet queue indexed by pkt_idx
    reg [7:0]  exp_sid  [0:TOTAL_PKTS-1];
    reg [15:0] exp_len  [0:TOTAL_PKTS-1];
    reg [31:0] exp_seq  [0:TOTAL_PKTS-1];
    reg [63:0] exp_ts   [0:TOTAL_PKTS-1];
    reg        exp_err  [0:TOTAL_PKTS-1];
    reg [63:0] exp_pay  [0:TOTAL_PKTS-1][0:511];

    reg [63:0] cur_rx_buf [0:511];
    integer    cur_rx_w = 0;
    integer    rx_pkt_idx = 0;
    integer    rx_good_pkts = 0;
    integer    rx_drop_pkts = 0;
    integer    payload_mismatches = 0;
    integer    lock_cyc = 0;

    // Concurrent RX scoreboard monitor
    integer widx;
    always @(posedge clk_125m) begin
        if (rst) begin
            cur_rx_w <= 0;
        end else begin
            if (rx_out_v) begin
                if (rx_out_sop) cur_rx_w = 0;
                if (cur_rx_w < 512)
                    cur_rx_buf[cur_rx_w] = rx_out_data;
                cur_rx_w = cur_rx_w + 1;
            end
            if (rx_done_v) begin
                if (rx_done_ok) begin
                    rx_good_pkts = rx_good_pkts + 1;
                    // Match against exp[rx_out_seq] (sequences are 0..TOTAL_PKTS-1)
                    if (rx_out_seq < TOTAL_PKTS) begin
                        if (rx_out_sid !== exp_sid[rx_out_seq] ||
                            rx_out_len !== exp_len[rx_out_seq] ||
                            rx_out_ts  !== exp_ts[rx_out_seq]  ||
                            cur_rx_w   !== ((exp_len[rx_out_seq] + 7) >> 3)) begin
                            payload_mismatches = payload_mismatches + 1;
                        end else begin
                            for (widx = 0; widx < cur_rx_w; widx = widx + 1) begin
                                if (cur_rx_buf[widx] !== exp_pay[rx_out_seq][widx])
                                    payload_mismatches = payload_mismatches + 1;
                            end
                        end
                    end else begin
                        payload_mismatches = payload_mismatches + 1;
                    end
                end else if (rx_done_err) begin
                    rx_drop_pkts = rx_drop_pkts + 1;
                end
                rx_pkt_idx = rx_pkt_idx + 1;
                cur_rx_w = 0;
            end
        end
    end

    integer p, w, nw, b, cyc, fail_cnt;
    integer err_inj_target;

    initial begin
        fail_cnt = 0;
        rst <= 1'b1;
        repeat (16) @(posedge clk_125m);
        rst <= 1'b0;

        // Wait for Clause 49 block lock and 2-lane AM deskew within LOCK_BOUND_CYC
        lock_cyc = 0;
        while ((!(l0_lock && l1_lock && d_lock)) && (lock_cyc < LOCK_BOUND_CYC)) begin
            @(posedge clk_125m);
            lock_cyc = lock_cyc + 1;
        end
        $display("tb_pcs_loop: lock_cyc=%0d l0=%b l1=%b deskew=%b skew_blocks=%0d",
                 lock_cyc, l0_lock, l1_lock, d_lock, skew_blk);

        if (!(l0_lock && l1_lock && d_lock)) begin
            $display("FAIL: tb_pcs_loop did not achieve lock within %0d cycles", LOCK_BOUND_CYC);
            $finish;
        end

        // Pre-generate TOTAL_PKTS random packets (including a 4096-byte max packet)
        for (p = 0; p < TOTAL_PKTS; p = p + 1) begin
            prng = next_rand(prng);
            exp_sid[p] = (p[1:0] == 2'b00) ? 8'h01 :
                         (p[1:0] == 2'b01) ? 8'h02 :
                         (p[1:0] == 2'b10) ? 8'h03 : 8'h11;
            exp_err[p] = (p == 3) || (p == 12) || (p == 21); // 3 packets receive injected bit errors
            if (p == 5)
                exp_len[p] = 16'd4096;
            else if (exp_err[p])
                exp_len[p] = 16'd256 + {8'd0, prng[7:0]}; // 256..511 B so mid-packet flip lands inside DATA
            else
                exp_len[p] = 16'd8 + {7'd0, prng[8:0]}; // 8..519 bytes
            exp_seq[p] = p;
            prng = next_rand(prng);
            exp_ts[p]  = 64'h0000_0001_0000_0000 + {32'd0, prng[31:0]};
            nw = (exp_len[p] + 7) >> 3;
            for (w = 0; w < nw; w = w + 1) begin
                prng = next_rand(prng);
                exp_pay[p][w] = prng;
                if (w == nw - 1) begin
                    for (b = 0; b < 8; b = b + 1)
                        if ((w * 8 + b) >= exp_len[p])
                            exp_pay[p][w][b*8 +: 8] = 8'h00;
                end
            end
        end

        // Transmit all TOTAL_PKTS packets
        for (p = 0; p < TOTAL_PKTS; p = p + 1) begin
            nw = (exp_len[p] + 7) >> 3;
            tx_pkt_sid   <= exp_sid[p];
            tx_pkt_len   <= exp_len[p];
            tx_pkt_seq   <= exp_seq[p];
            tx_pkt_ts    <= exp_ts[p];
            tx_pkt_valid <= 1'b1;
            tx_pkt_sop   <= 1'b1;
            w = 0;
            while (w < nw) begin
                tx_pkt_data <= exp_pay[p][w];
                tx_pkt_eop  <= (w == nw - 1);
                @(posedge clk_125m);
                if (tx_pkt_valid && tx_pkt_ready) begin
                    // Flip 1 channel bit mid-packet (w==16) so it lands deterministically inside DATA
                    if (exp_err[p] && (w == 16)) begin
                        @(posedge clk_ui);
                        inject_bit_err_l0 <= 1'b1;
                        @(posedge clk_ui);
                        inject_bit_err_l0 <= 1'b0;
                    end
                    w = w + 1;
                    tx_pkt_sop <= 1'b0;
                end
            end
            tx_pkt_valid <= 1'b0;
            tx_pkt_eop   <= 1'b0;
            repeat (4) @(posedge clk_125m);
        end

        // Drain receiver pipeline
        for (cyc = 0; cyc < 4000 && ((rx_good_pkts + rx_drop_pkts) < TOTAL_PKTS); cyc = cyc + 1)
            @(posedge clk_125m);
        repeat (50) @(posedge clk_125m);

        $display("tb_pcs_loop stats: tx_pkts=%0d rx_good=%0d rx_drop=%0d crc_err_cnt=%0d payload_mismatches=%0d sh_err_l0=%0d sh_err_l1=%0d lock_cyc=%0d skew_blocks=%0d",
                 TOTAL_PKTS, rx_good_pkts, rx_drop_pkts, crc_err_cnt, payload_mismatches, sh_err0, sh_err1, lock_cyc, skew_blk);

        if (rx_good_pkts !== (TOTAL_PKTS - 3)) fail_cnt = fail_cnt + 1;
        if (rx_drop_pkts !== 3)                fail_cnt = fail_cnt + 1;
        if (crc_err_cnt !== 32'd3)             fail_cnt = fail_cnt + 1;
        if (payload_mismatches !== 0)          fail_cnt = fail_cnt + 1;

        if (fail_cnt == 0)
            $display("PASS: tb_pcs_loop tx=%0d rx_good=%0d crc_err=%0d lock_cyc=%0d", TOTAL_PKTS, rx_good_pkts, crc_err_cnt, lock_cyc);
        else
            $display("FAIL: tb_pcs_loop tx=%0d rx_good=%0d crc_err=%0d mismatches=%0d", TOTAL_PKTS, rx_good_pkts, crc_err_cnt, payload_mismatches);
        $finish;
    end
endmodule
