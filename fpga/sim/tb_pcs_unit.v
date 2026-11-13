// SPDX-License-Identifier: BSD-2-Clause
// Unit Testbench for PCS Submodules (Verilog-2001):
//   1. link_crc32 (IEEE 802.3 CRC-32 vectors)
//   2. link_64b66b_enc + link_64b66b_dec (Clause 49 self-sync round-trip)
//   3. link_gearbox_tx + link_gearbox_rx + link_block_lock (all 8 bit offsets)
//   4. link_tx_lanes + link_rx_lanes (2-lane striping & 4-block AM deskew)
//   5. link_framer + link_deframer (1..4096B packets + CRC rejection)

`timescale 1ns/1ps

module tb_pcs_unit;
    reg clk = 1'b0;
    always #4.0 clk = ~clk; // 125 MHz parallel clock

    integer fail_cnt = 0;

    // -----------------------------------------------------------------------
    // 1. CRC-32 Unit Test
    // -----------------------------------------------------------------------
    reg  [31:0] crc_in_r;
    reg  [63:0] crc_data_r;
    wire [31:0] crc_out_w;

    link_crc32 u_t1_crc (
        .crc_in  (crc_in_r),
        .data_in (crc_data_r),
        .crc_out (crc_out_w)
    );

    // -----------------------------------------------------------------------
    // 2. Scrambler / Descrambler Unit Test
    // -----------------------------------------------------------------------
    reg         t2_rst = 1'b1;
    reg         t2_in_valid = 1'b0;
    reg  [1:0]  t2_in_sync = 2'b01;
    reg  [63:0] t2_in_data = 64'd0;
    wire        t2_in_ready;
    wire        t2_enc_valid;
    wire [65:0] t2_enc_block;
    wire        t2_dec_valid;
    wire [1:0]  t2_dec_sync;
    wire [63:0] t2_dec_data;
    wire        t2_sync_err;

    link_64b66b_enc u_t2_enc (
        .clk       (clk),
        .rst       (t2_rst),
        .in_valid  (t2_in_valid),
        .in_ready  (t2_in_ready),
        .in_sync   (t2_in_sync),
        .in_data   (t2_in_data),
        .out_valid (t2_enc_valid),
        .out_ready (1'b1),
        .out_block (t2_enc_block)
    );

    link_64b66b_dec u_t2_dec (
        .clk       (clk),
        .rst       (t2_rst),
        .in_valid  (t2_enc_valid),
        .in_block  (t2_enc_block),
        .out_valid (t2_dec_valid),
        .out_sync  (t2_dec_sync),
        .out_data  (t2_dec_data),
        .sync_err  (t2_sync_err)
    );

    // -----------------------------------------------------------------------
    // 3. Gearbox TX / RX + Block Lock Unit Test (arbitrary bit shift 0..7)
    // -----------------------------------------------------------------------
    reg         t3_rst = 1'b1;
    reg  [2:0]  t3_shift = 3'd0;
    reg         t3_enc_valid = 1'b0;
    reg  [1:0]  t3_in_sync = 2'b01;
    reg  [63:0] t3_in_data = 64'd0;
    wire        t3_enc_ready, t3_gb_tx_ready, t3_enc_out_valid;
    wire [65:0] t3_enc_block;
    wire [7:0]  t3_tx_byte;

    link_64b66b_enc u_t3_enc (
        .clk       (clk),
        .rst       (t3_rst),
        .in_valid  (t3_enc_valid),
        .in_ready  (t3_enc_ready),
        .in_sync   (t3_in_sync),
        .in_data   (t3_in_data),
        .out_valid (t3_enc_out_valid),
        .out_ready (t3_gb_tx_ready),
        .out_block (t3_enc_block)
    );

    link_gearbox_tx u_t3_gb_tx (
        .clk      (clk),
        .rst      (t3_rst),
        .in_valid (t3_enc_out_valid),
        .in_ready (t3_gb_tx_ready),
        .in_block (t3_enc_block),
        .out_byte (t3_tx_byte)
    );

    reg  [7:0] t3_prev_byte = 8'd0;
    always @(posedge clk) begin
        if (t3_rst) t3_prev_byte <= 8'd0;
        else        t3_prev_byte <= t3_tx_byte;
    end
    wire [15:0] t3_window = {t3_tx_byte, t3_prev_byte};
    wire [7:0]  t3_rx_byte = t3_window[t3_shift +: 8];

    wire        t3_gb_rx_valid, t3_slip, t3_lock, t3_dec_valid, t3_dec_serr;
    wire [65:0] t3_gb_rx_block;
    wire [31:0] t3_sh_errs;
    wire [1:0]  t3_dec_sync;
    wire [63:0] t3_dec_data;

    link_gearbox_rx u_t3_gb_rx (
        .clk       (clk),
        .rst       (t3_rst),
        .in_byte   (t3_rx_byte),
        .rx_slip   (t3_slip),
        .out_valid (t3_gb_rx_valid),
        .out_block (t3_gb_rx_block)
    );

    link_block_lock u_t3_bl (
        .clk        (clk),
        .rst        (t3_rst),
        .rx_valid   (t3_gb_rx_valid),
        .rx_sync    (t3_gb_rx_block[1:0]),
        .block_lock (t3_lock),
        .rx_slip    (t3_slip),
        .sh_err_cnt (t3_sh_errs)
    );

    link_64b66b_dec u_t3_dec (
        .clk       (clk),
        .rst       (t3_rst),
        .in_valid  (t3_gb_rx_valid),
        .in_block  (t3_gb_rx_block),
        .out_valid (t3_dec_valid),
        .out_sync  (t3_dec_sync),
        .out_data  (t3_dec_data),
        .sync_err  (t3_dec_serr)
    );

    // -----------------------------------------------------------------------
    // 4. 2-Lane Striping + 4-Block Skew Deskew Unit Test
    // -----------------------------------------------------------------------
    reg         t4_rst = 1'b1;
    reg         t4_in_valid = 1'b0;
    wire        t4_in_ready;
    reg  [1:0]  t4_in_sync = 2'b01;
    reg  [63:0] t4_in_data = 64'd0;

    wire        t4_l0_v, t4_l1_v;
    wire [1:0]  t4_l0_s, t4_l1_s;
    wire [63:0] t4_l0_d, t4_l1_d;
    reg         t4_ready_gate = 1'b0;

    link_tx_lanes #(.AM_PERIOD(32)) u_t4_tx (
        .clk      (clk),
        .rst      (t4_rst),
        .in_valid (t4_in_valid),
        .in_ready (t4_in_ready),
        .in_sync  (t4_in_sync),
        .in_data  (t4_in_data),
        .l0_valid (t4_l0_v),
        .l0_ready (t4_ready_gate),
        .l0_sync  (t4_l0_s),
        .l0_data  (t4_l0_d),
        .l1_valid (t4_l1_v),
        .l1_ready (t4_ready_gate),
        .l1_sync  (t4_l1_s),
        .l1_data  (t4_l1_d)
    );

    // Emit one pair every 8 cycles (like 66:8 gearbox rate) and delay Lane 1 by 4 blocks
    reg [2:0]  t4_div = 3'd0;
    reg [65:0] t4_l1_delay [0:3];
    reg        t4_l1_delay_v [0:3];
    integer    di;
    always @(posedge clk) begin
        if (t4_rst) begin
            t4_div        <= 3'd0;
            t4_ready_gate <= 1'b0;
            for (di = 0; di < 4; di = di + 1) begin
                t4_l1_delay[di]   <= 66'd0;
                t4_l1_delay_v[di] <= 1'b0;
            end
        end else begin
            t4_div        <= t4_div + 3'd1;
            t4_ready_gate <= (t4_div == 3'd7);
            if (t4_l1_v && t4_ready_gate) begin
                t4_l1_delay[0] <= {t4_l1_d, t4_l1_s};
                t4_l1_delay_v[0] <= 1'b1;
                for (di = 1; di < 4; di = di + 1) begin
                    t4_l1_delay[di]   <= t4_l1_delay[di - 1];
                    t4_l1_delay_v[di] <= t4_l1_delay_v[di - 1];
                end
            end
        end
    end

    wire        t4_l0_fire = t4_l0_v && t4_ready_gate;
    wire        t4_l1_fire = t4_l1_v && t4_ready_gate && t4_l1_delay_v[3];
    wire [1:0]  t4_l1_skew_s = t4_l1_delay[3][1:0];
    wire [63:0] t4_l1_skew_d = t4_l1_delay[3][65:2];

    wire        t4_deskew_lock, t4_out_v;
    wire signed [7:0] t4_skew_blocks;
    wire [15:0] t4_am_seq;
    wire [1:0]  t4_out_s;
    wire [63:0] t4_out_d;

    link_rx_lanes u_t4_rx (
        .clk           (clk),
        .rst           (t4_rst),
        .l0_block_lock (1'b1),
        .l0_valid      (t4_l0_fire),
        .l0_sync       (t4_l0_s),
        .l0_data       (t4_l0_d),
        .l1_block_lock (1'b1),
        .l1_valid      (t4_l1_fire),
        .l1_sync       (t4_l1_skew_s),
        .l1_data       (t4_l1_skew_d),
        .deskew_lock   (t4_deskew_lock),
        .skew_blocks   (t4_skew_blocks),
        .last_am_seq   (t4_am_seq),
        .out_valid     (t4_out_v),
        .out_sync      (t4_out_s),
        .out_data      (t4_out_d)
    );

    // -----------------------------------------------------------------------
    // 5. Framer / Deframer Unit Test
    // -----------------------------------------------------------------------
    reg         t5_rst = 1'b1;
    reg         t5_pkt_valid = 1'b0;
    wire        t5_pkt_ready;
    reg         t5_pkt_sop = 1'b0, t5_pkt_eop = 1'b0;
    reg  [7:0]  t5_pkt_sid = 8'd0;
    reg  [15:0] t5_pkt_len = 16'd0;
    reg  [31:0] t5_pkt_seq = 32'd0;
    reg  [63:0] t5_pkt_ts = 64'd0;
    reg  [63:0] t5_pkt_data = 64'd0;
    reg  [23:0] t5_dropped = 24'd7;
    wire        t5_tx_v, t5_out_v, t5_out_sop, t5_out_eop;
    wire [1:0]  t5_tx_s;
    wire [63:0] t5_tx_d;
    reg         t5_corrupt_wire = 1'b0;
    wire [63:0] t5_wire_d = t5_corrupt_wire ? (t5_tx_d ^ 64'h0000_0000_0001_0000) : t5_tx_d;

    wire [7:0]  t5_out_sid;
    wire [15:0] t5_out_len;
    wire [31:0] t5_out_seq;
    wire [63:0] t5_out_ts, t5_out_data;
    wire        t5_done_v, t5_done_ok, t5_done_err;
    wire [15:0] t5_rstat;
    wire [23:0] t5_rdrop;
    wire [31:0] t5_rx_cnt, t5_crc_err;

    link_framer u_t5_fr (
        .clk           (clk),
        .rst           (t5_rst),
        .pkt_valid     (t5_pkt_valid),
        .pkt_ready     (t5_pkt_ready),
        .pkt_sop       (t5_pkt_sop),
        .pkt_eop       (t5_pkt_eop),
        .pkt_stream_id (t5_pkt_sid),
        .pkt_len       (t5_pkt_len),
        .pkt_seq       (t5_pkt_seq),
        .pkt_timestamp (t5_pkt_ts),
        .pkt_data      (t5_pkt_data),
        .dropped_cnt   (t5_dropped),
        .local_status  (16'hA501),
        .tx_valid      (t5_tx_v),
        .tx_ready      (1'b1),
        .tx_sync       (t5_tx_s),
        .tx_data       (t5_tx_d)
    );

    link_deframer u_t5_df (
        .clk                (clk),
        .rst                (t5_rst),
        .rx_valid           (t5_tx_v),
        .rx_sync            (t5_tx_s),
        .rx_data            (t5_wire_d),
        .out_valid          (t5_out_v),
        .out_sop            (t5_out_sop),
        .out_eop            (t5_out_eop),
        .out_stream_id      (t5_out_sid),
        .out_len            (t5_out_len),
        .out_seq            (t5_out_seq),
        .out_timestamp      (t5_out_ts),
        .out_data           (t5_out_data),
        .pkt_done_valid     (t5_done_v),
        .pkt_done_ok        (t5_done_ok),
        .pkt_done_err       (t5_done_err),
        .remote_status      (t5_rstat),
        .remote_dropped_cnt (t5_rdrop),
        .pkt_rx_cnt         (t5_rx_cnt),
        .crc_err_cnt        (t5_crc_err)
    );

    // Test execution
    integer idx, cyc, shift_val;
    reg [65:0] t2_exp_q [0:1023];
    integer    t2_wp, t2_rp;
    reg [63:0] t3_tag;
    reg [63:0] prng = 64'hCAFE_BABE_1234_5678;

    function [63:0] next_rand(input [63:0] x);
        begin
            next_rand = {x[62:0], x[63] ^ x[62] ^ x[60] ^ x[59]};
        end
    endfunction

    reg [63:0] t5_exp_words [0:511];
    integer    t5_w_idx, t5_nwords, t5_b;
    reg [15:0] lengths [0:6];

    task send_check_pkt(input [7:0] sid, input [15:0] len, input [31:0] seq, input [63:0] ts, input inject_err);
        integer w, wait_cyc, rx_w;
        reg err_seen;
        begin
            t5_nwords = (len + 7) >> 3;
            for (w = 0; w < t5_nwords; w = w + 1) begin
                prng = next_rand(prng);
                t5_exp_words[w] = prng;
                if (w == t5_nwords - 1) begin
                    for (t5_b = 0; t5_b < 8; t5_b = t5_b + 1) begin
                        if ((w * 8 + t5_b) >= len)
                            t5_exp_words[w][t5_b*8 +: 8] = 8'h00;
                    end
                end
            end

            t5_pkt_sid   <= sid;
            t5_pkt_len   <= len;
            t5_pkt_seq   <= seq;
            t5_pkt_ts    <= ts;
            t5_pkt_valid <= 1'b1;
            t5_pkt_sop   <= 1'b1;
            w = 0;
            rx_w = 0;
            err_seen = 1'b0;

            for (wait_cyc = 0; wait_cyc < t5_nwords + 20; wait_cyc = wait_cyc + 1) begin
                t5_pkt_data    <= t5_exp_words[w];
                t5_pkt_eop     <= (w == t5_nwords - 1);
                t5_corrupt_wire = inject_err && (w == 1) && t5_pkt_valid && t5_pkt_ready;
                @(posedge clk);
                if (t5_pkt_valid && t5_pkt_ready) begin
                    if (w < t5_nwords - 1) begin
                        w = w + 1;
                        t5_pkt_sop <= 1'b0;
                    end else begin
                        t5_pkt_valid <= 1'b0;
                        t5_pkt_sop   <= 1'b0;
                        t5_pkt_eop   <= 1'b0;
                    end
                end
                if (t5_out_v) begin
                    if (!inject_err) begin
                        if (t5_out_data !== t5_exp_words[rx_w]) begin
                            $display("T5 FAIL: len=%0d word=%0d got=%h exp=%h", len, rx_w, t5_out_data, t5_exp_words[rx_w]);
                            fail_cnt = fail_cnt + 1;
                        end
                    end
                    rx_w = rx_w + 1;
                end
                if (t5_done_v) begin
                    err_seen = 1'b1;
                    if (!inject_err && !t5_done_ok) begin
                        $display("T5 FAIL: expected OK on len=%0d seq=%0d", len, seq);
                        fail_cnt = fail_cnt + 1;
                    end
                    if (inject_err && !t5_done_err) begin
                        $display("T5 FAIL: expected CRC err on injected packet");
                        fail_cnt = fail_cnt + 1;
                    end
                    if (!inject_err && (t5_out_sid !== sid || t5_out_len !== len || t5_out_seq !== seq || t5_out_ts !== ts)) begin
                        $display("T5 FAIL: metadata mismatch sid=%h len=%0d seq=%h ts=%h", t5_out_sid, t5_out_len, t5_out_seq, t5_out_ts);
                        fail_cnt = fail_cnt + 1;
                    end
                end
            end
            t5_corrupt_wire <= 1'b0;
            if (!err_seen) begin
                $display("T5 FAIL: timeout waiting for pkt_done len=%0d", len);
                fail_cnt = fail_cnt + 1;
            end
        end
    endtask

    initial begin
        // --- T1: CRC-32 check ---
        crc_in_r   = 32'hFFFF_FFFF;
        crc_data_r = 64'h3837_3635_3433_3231; // "12345678"
        #1;
        if ((~crc_out_w) !== 32'h9AE0_DAAF) begin
            $display("T1 FAIL: crc32('12345678') got=%h exp=9ae0daaf", ~crc_out_w);
            fail_cnt = fail_cnt + 1;
        end
        crc_in_r   = crc_out_w;
        crc_data_r = 64'h0000_0000_0000_0039; // "9\0\0\0\0\0\0\0"
        #1;
        if ((~crc_out_w) !== 32'h0E8C_1A27) begin
            $display("T1 FAIL: crc32(16B) got=%h exp=0e8c1a27", ~crc_out_w);
            fail_cnt = fail_cnt + 1;
        end
        $display("T1 CRC-32 done (fail_cnt=%0d)", fail_cnt);

        // --- T2: Scrambler / Descrambler ---
        t2_rst = 1'b1;
        repeat (5) @(posedge clk);
        t2_rst = 1'b0;
        t2_wp = 0; t2_rp = 0;
        for (idx = 0; idx < 300; idx = idx + 1) begin
            prng = next_rand(prng);
            t2_in_valid <= 1'b1;
            t2_in_sync  <= (idx[0]) ? 2'b10 : 2'b01;
            t2_in_data  <= prng;
            t2_exp_q[t2_wp] = {prng, (idx[0] ? 2'b10 : 2'b01)};
            t2_wp = t2_wp + 1;
            @(posedge clk);
            if (t2_dec_valid) begin
                if ({t2_dec_data, t2_dec_sync} !== t2_exp_q[t2_rp] || t2_sync_err) begin
                    $display("T2 FAIL: block=%0d got={%h,%b} exp={%h,%b}", t2_rp, t2_dec_data, t2_dec_sync, t2_exp_q[t2_rp][65:2], t2_exp_q[t2_rp][1:0]);
                    fail_cnt = fail_cnt + 1;
                end
                t2_rp = t2_rp + 1;
            end
        end
        t2_in_valid <= 1'b0;
        repeat (10) begin
            @(posedge clk);
            if (t2_dec_valid && (t2_rp < t2_wp)) begin
                if ({t2_dec_data, t2_dec_sync} !== t2_exp_q[t2_rp]) fail_cnt = fail_cnt + 1;
                t2_rp = t2_rp + 1;
            end
        end
        if (t2_rp != t2_wp) begin
            $display("T2 FAIL: drained %0d/%0d blocks", t2_rp, t2_wp);
            fail_cnt = fail_cnt + 1;
        end
        $display("T2 Scrambler/Descrambler done (fail_cnt=%0d)", fail_cnt);

        // --- T3: Gearbox + Block Lock across all 8 bit shifts ---
        for (shift_val = 0; shift_val < 8; shift_val = shift_val + 1) begin
            t3_shift     <= shift_val[2:0];
            t3_rst       <= 1'b1;
            t3_enc_valid <= 1'b1;
            t3_in_sync   <= 2'b10;
            t3_in_data   <= 64'h0000_0000_0000_001E;
            repeat (6) @(posedge clk);
            t3_rst <= 1'b0;
            t3_tag = 64'hA500_0000_0000_0001;
            for (cyc = 0; cyc < 2500 && !t3_lock; cyc = cyc + 1) begin
                if (t3_enc_ready) begin
                    t3_in_sync <= 2'b01;
                    t3_in_data <= t3_tag;
                    t3_tag = t3_tag + 64'd1;
                end
                @(posedge clk);
            end
            if (!t3_lock) begin
                $display("T3 FAIL: did not lock for shift=%0d", shift_val);
                fail_cnt = fail_cnt + 1;
            end else begin
                // Check next 20 blocks increment cleanly by +1
                idx = 0;
                t3_tag = 64'd0;
                for (cyc = 0; cyc < 300 && idx < 16; cyc = cyc + 1) begin
                    if (t3_enc_ready) begin
                        t3_in_sync <= 2'b01;
                        t3_in_data <= t3_in_data + 64'd1;
                    end
                    @(posedge clk);
                    if (t3_dec_valid) begin
                        if (t3_dec_sync !== 2'b01) begin
                            $display("T3 FAIL: bad sync after lock shift=%0d sync=%b", shift_val, t3_dec_sync);
                            fail_cnt = fail_cnt + 1;
                        end else if (t3_tag != 64'd0 && (t3_dec_data !== t3_tag + 64'd1)) begin
                            $display("T3 FAIL: data discontinuity shift=%0d got=%h exp=%h", shift_val, t3_dec_data, t3_tag + 64'd1);
                            fail_cnt = fail_cnt + 1;
                        end
                        t3_tag = t3_dec_data;
                        idx = idx + 1;
                    end
                end
            end
        end
        $display("T3 Gearbox/BlockLock done (fail_cnt=%0d)", fail_cnt);

        // --- T4: 2-Lane Striping & 4-Block Skew Deskew ---
        t4_rst      <= 1'b1;
        t4_in_valid <= 1'b0;
        repeat (6) @(posedge clk);
        t4_rst <= 1'b0;
        t4_in_valid <= 1'b1;
        t4_in_sync  <= 2'b01;
        t4_in_data  <= 64'h0100_0000_0000_0000;
        t3_tag = 64'd0;
        idx = 0;
        for (cyc = 0; cyc < 5000; cyc = cyc + 1) begin
            @(posedge clk);
            if (t4_in_ready)
                t4_in_data <= t4_in_data + 64'd1;
            if (t4_out_v) begin
                if (t4_out_s == 2'b01 && (t4_out_d[63:56] == 8'h01)) begin
                    if (t3_tag != 64'd0 && (t4_out_d !== t3_tag + 64'd1)) begin
                        $display("T4 FAIL: out-of-order block got=%h exp=%h", t4_out_d, t3_tag + 64'd1);
                        fail_cnt = fail_cnt + 1;
                    end
                    t3_tag = t4_out_d;
                    idx = idx + 1;
                end
            end
        end
        if (!t4_deskew_lock || (t4_skew_blocks !== 8'sd4) || (idx < 40)) begin
            $display("T4 FAIL: deskew_lock=%b skew_blocks=%0d rx_cnt=%0d", t4_deskew_lock, t4_skew_blocks, idx);
            fail_cnt = fail_cnt + 1;
        end
        $display("T4 2-Lane Deskew done (skew=%0d rx_cnt=%0d fail_cnt=%0d)", t4_skew_blocks, idx, fail_cnt);

        // --- T5: Framer / Deframer (1..4096 B + CRC rejection) ---
        lengths[0] = 16'd1;
        lengths[1] = 16'd7;
        lengths[2] = 16'd8;
        lengths[3] = 16'd9;
        lengths[4] = 16'd64;
        lengths[5] = 16'd512;
        lengths[6] = 16'd4096;

        t5_rst <= 1'b1;
        repeat (5) @(posedge clk);
        t5_rst <= 1'b0;
        repeat (2) @(posedge clk);

        for (idx = 0; idx < 7; idx = idx + 1) begin
            send_check_pkt(8'h01 + idx[7:0], lengths[idx], 32'h0000_1000 + idx, 64'h1122_3344_5566_7700 + idx, 1'b0);
        end
        // Error injection packet
        send_check_pkt(8'h7F, 16'd64, 32'hDEAD_0001, 64'h9988_7766_5544_3322, 1'b1);

        if (t5_rx_cnt !== 32'd7 || t5_crc_err !== 32'd1 || t5_rstat !== 16'hA501 || t5_rdrop !== 24'd7) begin
            $display("T5 FAIL: rx_cnt=%0d crc_err=%0d rstat=%h rdrop=%0d", t5_rx_cnt, t5_crc_err, t5_rstat, t5_rdrop);
            fail_cnt = fail_cnt + 1;
        end
        $display("T5 Framer/Deframer done (fail_cnt=%0d)", fail_cnt);

        if (fail_cnt == 0)
            $display("PASS: tb_pcs_unit all 5 unit suites passed (rx_cnt=%0d crc_err=%0d skew=%0d)", t5_rx_cnt, t5_crc_err, t4_skew_blocks);
        else
            $display("FAIL: tb_pcs_unit fail_cnt=%0d", fail_cnt);
        $finish;
    end
endmodule
