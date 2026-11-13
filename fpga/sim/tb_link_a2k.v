// SPDX-License-Identifier: BSD-2-Clause
// Full Artix-7 -> Kria K26 Primitive Loopback Testbench (Verilog-2001):
//   - TX (Artix Bank 34): OSERDESE2 (8:1 DDR) + OBUFDS on LINK_RX_CLK, LINK_RX_D0, LINK_RX_D1
//   - Channel: routed PCB + Artix package delays from SIGNAL_INTEGRITY.md s3.4 / lvds_skew.py
//       LINK_RX_CLK = 678/677 ps, LINK_RX_D0 = 773/772 ps, LINK_RX_D1 = 717/717 ps
//     plus realistic +/-80 ps eye-edge setup/hold closure modeling at ISERDESE3 input.
//   - RX (Kria Bank 66 HP): IBUFDS -> IDELAYE3 (TIME, VAR_LOAD, EN_VTC=0 during load)
//     + IDELAYCTRL -> ISERDESE3 (1:8 DDR component mode) -> link_rx_train_fsm -> link_pcs_rx.
//
// Mutations (via xvlog -d):
//   MUTATE_BAD_SCRAMBLER : wrong scrambler polynomial tap in TX encoder
//   MUTATE_SKIP_CRC      : bypass CRC-32 validation in RX deframer
//   MUTATE_BAD_IDELAY    : mis-center IDELAYE3 D0 onto the clock transition edge (998 ps)

`timescale 1ns/1ps

module tb_link_a2k;
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
`ifdef MUTATE_BAD_IDELAY
    localparam integer BAD_IDELAY = 1;
`else
    localparam integer BAD_IDELAY = 0;
`endif

    localparam integer TOTAL_PKTS = 20;

    // -----------------------------------------------------------------------
    // Clocks:
    //   TX: 500 MHz DDR serial clock + 125 MHz CLKDIV
    //   RX IDELAYCTRL REFCLK: 300 MHz (per UG571 TIME mode)
    // -----------------------------------------------------------------------
    reg clk_500m = 1'b0;
    always #1.0 clk_500m = ~clk_500m;

    reg clk_300m = 1'b0;
    always #1.666 clk_300m = ~clk_300m;

    reg [1:0] tx_div_cnt = 2'b00;
    reg       tx_clk_125m = 1'b0;
    always @(posedge clk_500m) begin
        tx_div_cnt <= tx_div_cnt + 2'd1;
        if (tx_div_cnt == 2'd1)      tx_clk_125m <= 1'b1;
        else if (tx_div_cnt == 2'd3) tx_clk_125m <= 1'b0;
    end

    reg tx_rst = 1'b1;
    reg rx_rst = 1'b1;

    // -----------------------------------------------------------------------
    // Artix PCS TX
    // -----------------------------------------------------------------------
    reg         tx_pkt_valid = 1'b0;
    wire        tx_pkt_ready;
    reg         tx_pkt_sop = 1'b0, tx_pkt_eop = 1'b0;
    reg  [7:0]  tx_pkt_sid = 8'd0;
    reg  [15:0] tx_pkt_len = 16'd0;
    reg  [31:0] tx_pkt_seq = 32'd0;
    reg  [63:0] tx_pkt_ts = 64'd0;
    reg  [63:0] tx_pkt_data = 64'd0;
    wire [7:0]  tx_byte_l0, tx_byte_l1;
    reg         inject_tx_err = 1'b0;

    link_pcs_tx #(
        .AM_PERIOD     (64),
        .BAD_SCRAMBLER (BAD_SCR)
    ) u_pcs_tx (
        .clk           (tx_clk_125m),
        .rst           (tx_rst),
        .pkt_valid     (tx_pkt_valid),
        .pkt_ready     (tx_pkt_ready),
        .pkt_sop       (tx_pkt_sop),
        .pkt_eop       (tx_pkt_eop),
        .pkt_stream_id (tx_pkt_sid),
        .pkt_len       (tx_pkt_len),
        .pkt_seq       (tx_pkt_seq),
        .pkt_timestamp (tx_pkt_ts),
        .pkt_data      (tx_pkt_data),
        .dropped_cnt   (24'd2),
        .local_status  (16'hA2C0),
        .tx_byte_l0    (tx_byte_l0),
        .tx_byte_l1    (tx_byte_l1)
    );

    wire [7:0] tx_byte_l0_wire = inject_tx_err ? (tx_byte_l0 ^ 8'h04) : tx_byte_l0;

    // -----------------------------------------------------------------------
    // Artix-7 TX Primitives: 3 x OSERDESE2 (8:1 DDR) + OBUFDS
    // -----------------------------------------------------------------------
    wire ser_clk_se, ser_d0_se, ser_d1_se;
    wire pad_tx_clk_p, pad_tx_clk_n;
    wire pad_tx_d0_p,  pad_tx_d0_n;
    wire pad_tx_d1_p,  pad_tx_d1_n;

    OSERDESE2 #(
        .DATA_RATE_OQ("DDR"), .DATA_RATE_TQ("DDR"), .DATA_WIDTH(8),
        .SERDES_MODE("MASTER"), .TRISTATE_WIDTH(1)
    ) u_oserdes_clk (
        .OFB(), .OQ(ser_clk_se), .SHIFTOUT1(), .SHIFTOUT2(), .TBYTEOUT(), .TFB(), .TQ(),
        .CLK(clk_500m), .CLKDIV(tx_clk_125m),
        .D1(1'b0), .D2(1'b1), .D3(1'b0), .D4(1'b1),
        .D5(1'b0), .D6(1'b1), .D7(1'b0), .D8(1'b1),
        .OCE(1'b1), .RST(tx_rst), .SHIFTIN1(1'b0), .SHIFTIN2(1'b0),
        .T1(1'b0), .T2(1'b0), .T3(1'b0), .T4(1'b0), .TBYTEIN(1'b0), .TCE(1'b0)
    );

    OSERDESE2 #(
        .DATA_RATE_OQ("DDR"), .DATA_RATE_TQ("DDR"), .DATA_WIDTH(8),
        .SERDES_MODE("MASTER"), .TRISTATE_WIDTH(1)
    ) u_oserdes_d0 (
        .OFB(), .OQ(ser_d0_se), .SHIFTOUT1(), .SHIFTOUT2(), .TBYTEOUT(), .TFB(), .TQ(),
        .CLK(clk_500m), .CLKDIV(tx_clk_125m),
        .D1(tx_byte_l0_wire[0]), .D2(tx_byte_l0_wire[1]),
        .D3(tx_byte_l0_wire[2]), .D4(tx_byte_l0_wire[3]),
        .D5(tx_byte_l0_wire[4]), .D6(tx_byte_l0_wire[5]),
        .D7(tx_byte_l0_wire[6]), .D8(tx_byte_l0_wire[7]),
        .OCE(1'b1), .RST(tx_rst), .SHIFTIN1(1'b0), .SHIFTIN2(1'b0),
        .T1(1'b0), .T2(1'b0), .T3(1'b0), .T4(1'b0), .TBYTEIN(1'b0), .TCE(1'b0)
    );

    OSERDESE2 #(
        .DATA_RATE_OQ("DDR"), .DATA_RATE_TQ("DDR"), .DATA_WIDTH(8),
        .SERDES_MODE("MASTER"), .TRISTATE_WIDTH(1)
    ) u_oserdes_d1 (
        .OFB(), .OQ(ser_d1_se), .SHIFTOUT1(), .SHIFTOUT2(), .TBYTEOUT(), .TFB(), .TQ(),
        .CLK(clk_500m), .CLKDIV(tx_clk_125m),
        .D1(tx_byte_l1[0]), .D2(tx_byte_l1[1]),
        .D3(tx_byte_l1[2]), .D4(tx_byte_l1[3]),
        .D5(tx_byte_l1[4]), .D6(tx_byte_l1[5]),
        .D7(tx_byte_l1[6]), .D8(tx_byte_l1[7]),
        .OCE(1'b1), .RST(tx_rst), .SHIFTIN1(1'b0), .SHIFTIN2(1'b0),
        .T1(1'b0), .T2(1'b0), .T3(1'b0), .T4(1'b0), .TBYTEIN(1'b0), .TCE(1'b0)
    );

    OBUFDS u_obuf_clk (.I(ser_clk_se), .O(pad_tx_clk_p), .OB(pad_tx_clk_n));
    OBUFDS u_obuf_d0  (.I(ser_d0_se),  .O(pad_tx_d0_p),  .OB(pad_tx_d0_n));
    OBUFDS u_obuf_d1  (.I(ser_d1_se),  .O(pad_tx_d1_p),  .OB(pad_tx_d1_n));

    // -----------------------------------------------------------------------
    // Channel: Routed PCB + Artix package delays (lvds_skew.py / SIGNAL_INTEGRITY.md s3.4)
    //   LINK_RX_CLK: P=678 ps, N=677 ps
    //   LINK_RX_D0:  P=773 ps, N=772 ps (+95 ps vs CLK)
    //   LINK_RX_D1:  P=717 ps, N=717 ps (+39 ps vs CLK, 56 ps vs D0)
    // -----------------------------------------------------------------------
    wire #0.678 pad_rx_clk_p = pad_tx_clk_p;
    wire #0.677 pad_rx_clk_n = pad_tx_clk_n;
    wire #0.773 pad_rx_d0_p  = pad_tx_d0_p;
    wire #0.772 pad_rx_d0_n  = pad_tx_d0_n;
    wire #0.717 pad_rx_d1_p  = pad_tx_d1_p;
    wire #0.717 pad_rx_d1_n  = pad_tx_d1_n;

    // -----------------------------------------------------------------------
    // Kria K26 RX Primitives: IBUFDS -> IDELAYE3 (TIME, VAR_LOAD) -> ISERDESE3
    // -----------------------------------------------------------------------
    wire rx_clk_ibuf, rx_d0_ibuf, rx_d1_ibuf;
    IBUFDS u_ibuf_clk (.I(pad_rx_clk_p), .IB(pad_rx_clk_n), .O(rx_clk_ibuf));
    IBUFDS u_ibuf_d0  (.I(pad_rx_d0_p),  .IB(pad_rx_d0_n),  .O(rx_d0_ibuf));
    IBUFDS u_ibuf_d1  (.I(pad_rx_d1_p),  .IB(pad_rx_d1_n),  .O(rx_d1_ibuf));

    // BUFGCE_DIV divide-by-4 clock derived from forwarded LINK_RX_CLK
    reg [1:0] rx_div_cnt = 2'b00;
    reg       rx_clkdiv  = 1'b0;
    always @(posedge rx_clk_ibuf) begin
        rx_div_cnt <= rx_div_cnt + 2'd1;
        if (rx_div_cnt == 2'd1)      rx_clkdiv <= 1'b1;
        else if (rx_div_cnt == 2'd3) rx_clkdiv <= 1'b0;
    end

    wire idelayctrl_rdy;
    IDELAYCTRL #(.SIM_DEVICE("ULTRASCALE")) u_idelayctrl (
        .RDY    (idelayctrl_rdy),
        .REFCLK (clk_300m),
        .RST    (rx_rst)
    );

    wire       en_vtc, load_l0, load_l1;
    wire [8:0] cntval_l0, cntval_l1;
    wire       rx_d0_idelay, rx_d1_idelay;

    IDELAYE3 #(
        .CASCADE("NONE"), .DELAY_FORMAT("TIME"), .DELAY_SRC("IDATAIN"),
        .DELAY_TYPE("VAR_LOAD"), .DELAY_VALUE(0), .REFCLK_FREQUENCY(300.0),
        .SIM_DEVICE("ULTRASCALE_PLUS"), .SIM_VERSION(2.0), .UPDATE_MODE("ASYNC")
    ) u_idelay_d0 (
        .CASC_OUT(), .CNTVALUEOUT(), .DATAOUT(rx_d0_idelay),
        .CASC_IN(1'b0), .CASC_RETURN(1'b0), .CE(1'b0), .CLK(rx_clkdiv),
        .CNTVALUEIN(cntval_l0), .DATAIN(1'b0), .EN_VTC(en_vtc),
        .IDATAIN(rx_d0_ibuf), .INC(1'b0), .LOAD(load_l0), .RST(rx_rst)
    );

    IDELAYE3 #(
        .CASCADE("NONE"), .DELAY_FORMAT("TIME"), .DELAY_SRC("IDATAIN"),
        .DELAY_TYPE("VAR_LOAD"), .DELAY_VALUE(0), .REFCLK_FREQUENCY(300.0),
        .SIM_DEVICE("ULTRASCALE_PLUS"), .SIM_VERSION(2.0), .UPDATE_MODE("ASYNC")
    ) u_idelay_d1 (
        .CASC_OUT(), .CNTVALUEOUT(), .DATAOUT(rx_d1_idelay),
        .CASC_IN(1'b0), .CASC_RETURN(1'b0), .CE(1'b0), .CLK(rx_clkdiv),
        .CNTVALUEIN(cntval_l1), .DATAIN(1'b0), .EN_VTC(en_vtc),
        .IDATAIN(rx_d1_ibuf), .INC(1'b0), .LOAD(load_l1), .RST(rx_rst)
    );

    // Realistic +/-80 ps setup/hold eye-edge model (160 ps aperture around clk edge)
    // Common-mode +80 ps delay puts lookahead 80 ps ahead of ISERDESE3 inputs.
    wire #0.080 rx_clk_sample = rx_clk_ibuf;
    wire #0.080 rx_d0_pipe    = rx_d0_idelay;
    wire #0.080 rx_d1_pipe    = rx_d1_idelay;

    real last_d0_edge_ns = -100.0;
    real last_d1_edge_ns = -100.0;
    always @(rx_d0_idelay) last_d0_edge_ns = $realtime;
    always @(rx_d1_idelay) last_d1_edge_ns = $realtime;

    reg d0_eye_viol = 1'b0;
    reg d1_eye_viol = 1'b0;
    always @(posedge rx_clk_sample or negedge rx_clk_sample) begin
        d0_eye_viol <= (($realtime - last_d0_edge_ns) <= 0.160);
        d1_eye_viol <= (($realtime - last_d1_edge_ns) <= 0.160);
    end

    wire rx_d0_to_iserdes = d0_eye_viol ? ~rx_d0_pipe : rx_d0_pipe;
    wire rx_d1_to_iserdes = d1_eye_viol ? ~rx_d1_pipe : rx_d1_pipe;

    wire [7:0] rx_byte_l0, rx_byte_l1;

    ISERDESE3 #(
        .DATA_WIDTH(8), .DDR_CLK_EDGE("OPPOSITE_EDGE"), .FIFO_ENABLE("FALSE"),
        .FIFO_SYNC_MODE("FALSE"), .IDDR_MODE("FALSE"),
        .SIM_DEVICE("ULTRASCALE_PLUS"), .SIM_VERSION(2.0)
    ) u_iserdes_d0 (
        .FIFO_EMPTY(), .INTERNAL_DIVCLK(), .Q(rx_byte_l0),
        .CLK(rx_clk_sample), .CLKDIV(rx_clkdiv), .CLK_B(~rx_clk_sample),
        .D(rx_d0_to_iserdes), .FIFO_RD_CLK(1'b0), .FIFO_RD_EN(1'b0), .RST(rx_rst)
    );

    ISERDESE3 #(
        .DATA_WIDTH(8), .DDR_CLK_EDGE("OPPOSITE_EDGE"), .FIFO_ENABLE("FALSE"),
        .FIFO_SYNC_MODE("FALSE"), .IDDR_MODE("FALSE"),
        .SIM_DEVICE("ULTRASCALE_PLUS"), .SIM_VERSION(2.0)
    ) u_iserdes_d1 (
        .FIFO_EMPTY(), .INTERNAL_DIVCLK(), .Q(rx_byte_l1),
        .CLK(rx_clk_sample), .CLKDIV(rx_clkdiv), .CLK_B(~rx_clk_sample),
        .D(rx_d1_to_iserdes), .FIFO_RD_CLK(1'b0), .FIFO_RD_EN(1'b0), .RST(rx_rst)
    );

    // -----------------------------------------------------------------------
    // Kria Training FSM + PCS RX
    // -----------------------------------------------------------------------
    wire        rx_out_v, rx_out_sop, rx_out_eop;
    wire [7:0]  rx_out_sid;
    wire [15:0] rx_out_len;
    wire [31:0] rx_out_seq;
    wire [63:0] rx_out_ts, rx_out_data;
    wire        rx_done_v, rx_done_ok, rx_done_err;
    wire        l0_lock, l1_lock, d_lock, link_up;
    wire signed [7:0] skew_blk;
    wire [15:0] rem_stat;
    wire [23:0] rem_drop;
    wire [31:0] sh_err0, sh_err1, pkt_rx_cnt, crc_err_cnt;
    wire [2:0]  train_state;
    wire [8:0]  eye_l0, eye_r0, eye_l1, eye_r1;

    link_rx_train_fsm #(
        .DEFAULT_CENTER_TAP (9'd76),
        .TAP_STEP           (9'd64),
        .WAIT_RESET_CYCLES  (16'd16),
        .TAP_DWELL_CYCLES   (16'd120),
        .LOCK_TIMEOUT       (16'd4096),
        .BAD_IDELAY         (BAD_IDELAY)
    ) u_train_fsm (
        .clk              (rx_clkdiv),
        .rst              (rx_rst),
        .retrain          (1'b0),
        .cfg_tap_override (1'b0),
        .cfg_tap_l0       (9'd76),
        .cfg_tap_l1       (9'd76),
        .rx_byte_l0       (rx_byte_l0),
        .rx_byte_l1       (rx_byte_l1),
        .l0_block_lock    (l0_lock),
        .l1_block_lock    (l1_lock),
        .deskew_lock      (d_lock),
        .en_vtc           (en_vtc),
        .load_l0          (load_l0),
        .cntval_l0        (cntval_l0),
        .load_l1          (load_l1),
        .cntval_l1        (cntval_l1),
        .train_state      (train_state),
        .link_up          (link_up),
        .eye_left_l0      (eye_l0),
        .eye_right_l0     (eye_r0),
        .eye_left_l1      (eye_l1),
        .eye_right_l1     (eye_r1)
    );

    link_pcs_rx #(
        .DISABLE_DESKEW (0),
        .SKIP_CRC       (SKIP_CRC)
    ) u_pcs_rx (
        .clk                (rx_clkdiv),
        .rst                (rx_rst),
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
    // Scoreboard
    // -----------------------------------------------------------------------
    reg [63:0] prng = 64'h9E37_79B9_7F4A_7C15;
    function [63:0] next_rand(input [63:0] x);
        begin
            next_rand = {x[62:0], x[63] ^ x[62] ^ x[60] ^ x[59]};
        end
    endfunction

    reg [7:0]  exp_sid [0:TOTAL_PKTS-1];
    reg [15:0] exp_len [0:TOTAL_PKTS-1];
    reg [31:0] exp_seq [0:TOTAL_PKTS-1];
    reg [63:0] exp_ts  [0:TOTAL_PKTS-1];
    reg        exp_err [0:TOTAL_PKTS-1];
    reg [63:0] exp_pay [0:TOTAL_PKTS-1][0:127];

    reg [63:0] cur_rx_buf [0:127];
    integer    cur_rx_w = 0;
    integer    rx_good_pkts = 0;
    integer    rx_drop_pkts = 0;
    integer    payload_mismatches = 0;

    integer widx;
    always @(posedge rx_clkdiv) begin
        if (rx_rst) begin
            cur_rx_w <= 0;
        end else begin
            if (rx_out_v) begin
                if (rx_out_sop) cur_rx_w = 0;
                if (cur_rx_w < 128)
                    cur_rx_buf[cur_rx_w] = rx_out_data;
                cur_rx_w = cur_rx_w + 1;
            end
            if (rx_done_v) begin
                if (rx_done_ok) begin
                    rx_good_pkts = rx_good_pkts + 1;
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
                cur_rx_w = 0;
            end
        end
    end

    integer p, w, nw, b, cyc, fail_cnt;

    initial begin
        fail_cnt = 0;
        tx_rst <= 1'b1;
        rx_rst <= 1'b1;

        // Wait past glbl.GSR (100 ns) before releasing TX reset
        #150;
        @(posedge tx_clk_125m);
        tx_rst <= 1'b0;

        // Clock RX primitives for 20 cycles with rx_rst=1 so rx_clkdiv & IDELAYCTRL stabilize
        repeat (20) @(posedge tx_clk_125m);
        @(posedge rx_clkdiv);
        rx_rst <= 1'b0;

        // Wait for link_up (eye scan -> IDELAY load -> block lock -> deskew)
        cyc = 0;
        while ((!link_up) && (cyc < 10000)) begin
            @(posedge rx_clkdiv);
            cyc = cyc + 1;
        end
        $display("tb_link_a2k: train_cyc=%0d link_up=%b l0=%b l1=%b d_lock=%b tap0=%0d tap1=%0d skew_blocks=%0d",
                 cyc, link_up, l0_lock, l1_lock, d_lock, cntval_l0, cntval_l1, skew_blk);

        if (!link_up) begin
            $display("FAIL: tb_link_a2k link_up failed (state=%0d l0=%b l1=%b d_lock=%b)", train_state, l0_lock, l1_lock, d_lock);
            $finish;
        end

        // Pre-generate TOTAL_PKTS packets (1..1024 B)
        for (p = 0; p < TOTAL_PKTS; p = p + 1) begin
            prng = next_rand(prng);
            exp_sid[p] = 8'h01 + p[1:0];
            exp_err[p] = (p == 7); // Inject 1 error packet to verify end-to-end CRC rejection
            if (exp_err[p])
                exp_len[p] = 16'd256 + {8'd0, prng[7:0]};
            else
                exp_len[p] = 16'd16 + {7'd0, prng[8:0]};
            exp_seq[p] = p;
            prng = next_rand(prng);
            exp_ts[p]  = 64'h0000_0002_0000_0000 + {32'd0, prng[31:0]};
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

        // Send all TOTAL_PKTS packets on Artix side
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
                @(posedge tx_clk_125m);
                if (tx_pkt_valid && tx_pkt_ready) begin
                    // Inject 1 SERDES byte bit error mid-packet for p==7
                    inject_tx_err <= (exp_err[p] && (w == 16));
                    w = w + 1;
                    tx_pkt_sop <= 1'b0;
                end else begin
                    inject_tx_err <= 1'b0;
                end
            end
            inject_tx_err <= 1'b0;
            tx_pkt_valid  <= 1'b0;
            tx_pkt_eop    <= 1'b0;
            repeat (6) @(posedge tx_clk_125m);
        end

        for (cyc = 0; cyc < 4000 && ((rx_good_pkts + rx_drop_pkts) < TOTAL_PKTS); cyc = cyc + 1)
            @(posedge rx_clkdiv);
        repeat (50) @(posedge rx_clkdiv);

        $display("tb_link_a2k stats: tx=%0d rx_good=%0d rx_drop=%0d crc_err=%0d mismatches=%0d rem_stat=%h rem_drop=%0d",
                 TOTAL_PKTS, rx_good_pkts, rx_drop_pkts, crc_err_cnt, payload_mismatches, rem_stat, rem_drop);

        if (rx_good_pkts !== (TOTAL_PKTS - 1)) fail_cnt = fail_cnt + 1;
        if (rx_drop_pkts !== 1)                fail_cnt = fail_cnt + 1;
        if (crc_err_cnt !== 32'd1)             fail_cnt = fail_cnt + 1;
        if (payload_mismatches !== 0)          fail_cnt = fail_cnt + 1;

        if (fail_cnt == 0)
            $display("PASS: tb_link_a2k tx=%0d rx_good=%0d crc_err=%0d tap0=%0d tap1=%0d",
                     TOTAL_PKTS, rx_good_pkts, crc_err_cnt, cntval_l0, cntval_l1);
        else
            $display("FAIL: tb_link_a2k tx=%0d rx_good=%0d crc_err=%0d mismatches=%0d",
                     TOTAL_PKTS, rx_good_pkts, crc_err_cnt, payload_mismatches);
        $finish;
    end
endmodule
