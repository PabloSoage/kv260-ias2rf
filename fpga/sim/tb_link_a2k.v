// SPDX-License-Identifier: BSD-2-Clause
// Full Artix-7 -> Kria K26 Primitive Loopback Testbench (Verilog-2001):
//   - TX (Artix Bank 34): OSERDESE2 (8:1 DDR) + OBUFDS on LINK_RX_CLK, LINK_RX_D0, LINK_RX_D1
//   - Channel:
//       * Adapter PCB + Artix pkg ([M] lvds_skew.py / PINMAP.md):
//           LINK_RX_CLK = 678/677 ps, LINK_RX_D0 = 773/772 ps, LINK_RX_D1 = 717/717 ps
//       * KV260 carrier J8 -> SOM240_1 ([I] PINMAP.md): 180/180 ps common-mode
//       * K26 SOM trace mid ([M] k26c/2.0/part0_pins.xml):
//           LINK_RX_CLK = 413/413 ps, LINK_RX_D0 = 406/406 ps, LINK_RX_D1 = 405/405 ps
//       * Net channel totals (D0 = +88 ps vs CLK, D1 = +31 ps vs CLK -> 57 ps inter-lane skew):
//           LINK_RX_CLK = 1271/1270 ps, LINK_RX_D0 = 1359/1358 ps, LINK_RX_D1 = 1302/1302 ps
//     plus realistic +/-80 ps eye-edge setup/hold closure modeling at ISERDESE3 input.
//   - RX (Kria Bank 66 HP): IBUFDS -> IDELAYE3 (TIME, VAR_LOAD, EN_VTC=0 during load)
//     + IDELAYCTRL -> ISERDESE3 (1:8 DDR component mode) -> link_rx_train_fsm -> link_pcs_rx.
//
// Defines / Mutations (via xvlog -d):
//   RATE_800M / MUTATE_RATE_800M     : run at 800 Mb/s/lane (400 MHz DDR, 100 MHz CLKDIV)
//   SKEW_D1_300 / MUTATE_SKEW_D1_300 : add +300 ps skew on LINK_RX_D1 (bench still PASSes, tap1 shifts ~300 ps)
//   MUTATE_BAD_SCRAMBLER             : wrong scrambler polynomial tap in TX encoder (FAIL)
//   MUTATE_SKIP_CRC                  : bypass CRC-32 validation in RX deframer (FAIL)
//   MUTATE_BAD_IDELAY                : pin IDELAYE3 D0 onto the clock transition edge (FAIL)

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

`ifdef RATE_800M
    localparam real    SER_HALF_PERIOD_NS = 1.250; // 400 MHz DDR = 800 Mb/s/lane (1250 ps UI)
    localparam integer RATE_MBPS          = 800;
`elsif MUTATE_RATE_800M
    localparam real    SER_HALF_PERIOD_NS = 1.250;
    localparam integer RATE_MBPS          = 800;
`else
    localparam real    SER_HALF_PERIOD_NS = 1.000; // 500 MHz DDR = 1000 Mb/s/lane (1000 ps UI)
    localparam integer RATE_MBPS          = 1000;
`endif

`ifdef MUTATE_SKEW_D1_300
    localparam real    D1_EXTRA_SKEW_NS = 0.300;
    localparam integer SKEW_D1_300_EN   = 1;
`elsif SKEW_D1_300
    localparam real    D1_EXTRA_SKEW_NS = 0.300;
    localparam integer SKEW_D1_300_EN   = 1;
`else
    localparam real    D1_EXTRA_SKEW_NS = 0.000;
    localparam integer SKEW_D1_300_EN   = 0;
`endif

    localparam integer TOTAL_PKTS = 20;

    // -----------------------------------------------------------------------
    // Clocks:
    //   TX: 500 MHz (or 400 MHz) DDR serial clock + divide-by-4 CLKDIV (125 / 100 MHz)
    //   RX IDELAYCTRL REFCLK: 300 MHz (per UG571 TIME mode)
    // -----------------------------------------------------------------------
    reg clk_ddr = 1'b0;
    always #(SER_HALF_PERIOD_NS) clk_ddr = ~clk_ddr;

    reg clk_300m = 1'b0;
    always #1.666 clk_300m = ~clk_300m;

    reg [1:0] tx_div_cnt = 2'b00;
    reg       tx_clkdiv  = 1'b0;
    always @(posedge clk_ddr) begin
        tx_div_cnt <= tx_div_cnt + 2'd1;
        if (tx_div_cnt == 2'd1)      tx_clkdiv <= 1'b1;
        else if (tx_div_cnt == 2'd3) tx_clkdiv <= 1'b0;
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
        .clk           (tx_clkdiv),
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
        .CLK(clk_ddr), .CLKDIV(tx_clkdiv),
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
        .CLK(clk_ddr), .CLKDIV(tx_clkdiv),
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
        .CLK(clk_ddr), .CLKDIV(tx_clkdiv),
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
    // End-to-End Channel (3 transport-safe stages, each < 1.000 ns UI to prevent inertial pulse swallowing):
    //   1) Adapter PCB + Artix pkg ([M] lvds_skew.py / PINMAP.md):
    //        LINK_RX_CLK = 678/677 ps, LINK_RX_D0 = 773/772 ps, LINK_RX_D1 = 717/717 ps
    //   2) KV260 Carrier J8 -> SOM240_1 ([I] PINMAP.md): 180/180 ps common-mode
    //   3) K26 SOM trace mid ([M] k26c/2.0/part0_pins.xml):
    //        LINK_RX_CLK = 413/413 ps, LINK_RX_D0 = 406/406 ps, LINK_RX_D1 = 405/405 ps
    //   Net totals (D0 = +88 ps vs CLK, D1 = +31 ps vs CLK -> 57 ps inter-lane skew):
    //        LINK_RX_CLK = 1271/1270 ps, LINK_RX_D0 = 1359/1358 ps, LINK_RX_D1 = 1302/1302 ps [+ D1_EXTRA_SKEW_NS]
    // -----------------------------------------------------------------------
    wire #0.678 ch_adap_clk_p = pad_tx_clk_p;
    wire #0.677 ch_adap_clk_n = pad_tx_clk_n;
    wire #0.773 ch_adap_d0_p  = pad_tx_d0_p;
    wire #0.772 ch_adap_d0_n  = pad_tx_d0_n;
    wire #0.717 ch_adap_d1_p  = pad_tx_d1_p;
    wire #0.717 ch_adap_d1_n  = pad_tx_d1_n;

    wire #0.180 ch_car_clk_p  = ch_adap_clk_p;
    wire #0.180 ch_car_clk_n  = ch_adap_clk_n;
    wire #0.180 ch_car_d0_p   = ch_adap_d0_p;
    wire #0.180 ch_car_d0_n   = ch_adap_d0_n;
    wire #0.180 ch_car_d1_p   = ch_adap_d1_p;
    wire #0.180 ch_car_d1_n   = ch_adap_d1_n;

    wire #0.413 pad_rx_clk_p  = ch_car_clk_p;
    wire #0.413 pad_rx_clk_n  = ch_car_clk_n;
    wire #0.406 pad_rx_d0_p   = ch_car_d0_p;
    wire #0.406 pad_rx_d0_n   = ch_car_d0_n;
    wire #0.405 ch_som_d1_p   = ch_car_d1_p;
    wire #0.405 ch_som_d1_n   = ch_car_d1_n;

    wire #(D1_EXTRA_SKEW_NS) pad_rx_d1_p = ch_som_d1_p;
    wire #(D1_EXTRA_SKEW_NS) pad_rx_d1_n = ch_som_d1_n;

    // -----------------------------------------------------------------------
    // Kria K26 RX Primitives: IBUFDS -> IDELAYE3 (TIME, VAR_LOAD) -> ISERDESE3
    // -----------------------------------------------------------------------
    wire rx_clk_ibuf, rx_d0_ibuf, rx_d1_ibuf;
    IBUFDS u_ibuf_clk (.I(pad_rx_clk_p), .IB(pad_rx_clk_n), .O(rx_clk_ibuf));
    IBUFDS u_ibuf_d0  (.I(pad_rx_d0_p),  .IB(pad_rx_d0_n),  .O(rx_d0_ibuf));
    IBUFDS u_ibuf_d1  (.I(pad_rx_d1_p),  .IB(pad_rx_d1_n),  .O(rx_d1_ibuf));

    // UltraScale+ BUFGCE clock-tree insertion delay relative to direct IOB IDELAY path
    // (127 ps IDELAYE3 tap-0 intrinsic balance + 400 ps BUFGCE clock distribution delay)
    // puts both left and right transition edges of D0, D1, and D1+300ps inside [0..511].
    wire #0.527 rx_clk_bufg = rx_clk_ibuf;

    // BUFGCE_DIV divide-by-4 clock derived from forwarded LINK_RX_CLK
    reg [1:0] rx_div_cnt = 2'b00;
    reg       rx_clkdiv  = 1'b0;
    always @(posedge rx_clk_bufg) begin
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
    // rx_clk_check (+81 ps) evaluates window [t_clk - 80 ps .. t_clk + 80 ps] before
    // rx_clk_sample (+82 ps) clocks ISERDESE3 on rx_d*_pipe (+80 ps).
    wire #0.081 rx_clk_check  = rx_clk_bufg;
    wire #0.082 rx_clk_sample = rx_clk_bufg;
    wire #0.080 rx_d0_pipe    = rx_d0_idelay;
    wire #0.080 rx_d1_pipe    = rx_d1_idelay;

    real last_d0_edge_ns = -100.0;
    real last_d1_edge_ns = -100.0;
    always @(rx_d0_idelay) last_d0_edge_ns = $realtime;
    always @(rx_d1_idelay) last_d1_edge_ns = $realtime;

    reg d0_eye_viol = 1'b0;
    reg d1_eye_viol = 1'b0;
    reg [15:0] eye_prng = 16'hACE1;
    always @(posedge rx_clk_check or negedge rx_clk_check) begin
        d0_eye_viol <= (($realtime - last_d0_edge_ns) <= 0.161);
        d1_eye_viol <= (($realtime - last_d1_edge_ns) <= 0.161);
        eye_prng    <= {eye_prng[14:0], eye_prng[15] ^ eye_prng[13] ^ eye_prng[12] ^ eye_prng[10]};
    end

    // Pseudorandom metastability corruption when transition lands inside +/-80 ps aperture
    wire rx_d0_to_iserdes = (d0_eye_viol && eye_prng[0]) ? ~rx_d0_pipe : rx_d0_pipe;
    wire rx_d1_to_iserdes = (d1_eye_viol && eye_prng[1]) ? ~rx_d1_pipe : rx_d1_pipe;

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
    wire        l0_rx_blk_valid, l0_rx_blk_ok, l1_rx_blk_valid, l1_rx_blk_ok;
    wire [2:0]  train_state;
    wire [8:0]  eye_l0, eye_r0, eye_l1, eye_r1;

    link_rx_train_fsm #(
        .DEFAULT_CENTER_TAP (9'd202),
        .MAX_TAP            (9'd511),
        .TAP_STEP           (9'd8),
        .MIN_EYE_STEPS      (9'd18),
        .BAD_TAP            (9'd78),
        .WAIT_RESET_CYCLES  (16'd16),
        .TAP_SETTLE_CYCLES  (16'd24),
        .TAP_DWELL_CYCLES   (16'd1800),
        .LOCK_TIMEOUT       (16'd8192),
        .SINGLE_LANE        (0),
        .BAD_IDELAY         (BAD_IDELAY)
    ) u_train_fsm (
        .clk              (rx_clkdiv),
        .rst              (rx_rst),
        .retrain          (1'b0),
        .cfg_tap_override (1'b0),
        .cfg_tap_l0       (9'd202),
        .cfg_tap_l1       (9'd216),
        .rx_byte_l0       (rx_byte_l0),
        .rx_byte_l1       (rx_byte_l1),
        .l0_block_lock    (l0_lock),
        .l1_block_lock    (l1_lock),
        .deskew_lock      (d_lock),
        .l0_rx_blk_valid  (l0_rx_blk_valid),
        .l0_rx_blk_ok     (l0_rx_blk_ok),
        .l1_rx_blk_valid  (l1_rx_blk_valid),
        .l1_rx_blk_ok     (l1_rx_blk_ok),
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
        .link_ready         (link_up),
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
        .crc_err_cnt        (crc_err_cnt),
        .l0_rx_blk_valid    (l0_rx_blk_valid),
        .l0_rx_blk_ok       (l0_rx_blk_ok),
        .l1_rx_blk_valid    (l1_rx_blk_valid),
        .l1_rx_blk_ok       (l1_rx_blk_ok)
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
    integer w0_width, w0_center, w0_err;
    integer w1_width, w1_center, w1_err;
    integer skew_ps;

    initial begin
        fail_cnt = 0;
        tx_rst <= 1'b1;
        rx_rst <= 1'b1;

        // Wait past glbl.GSR (100 ns) before releasing TX reset
        #150;
        @(posedge tx_clkdiv);
        tx_rst <= 1'b0;

        // Clock RX primitives for 20 cycles with rx_rst=1 so rx_clkdiv & IDELAYCTRL stabilize
        repeat (20) @(posedge tx_clkdiv);
        @(posedge rx_clkdiv);
        rx_rst <= 1'b0;

        // Wait for link_up (eye scan -> IDELAY load -> block lock -> deskew)
        cyc = 0;
        while ((!link_up) && (cyc < 60000)) begin
            @(posedge rx_clkdiv);
            cyc = cyc + 1;
        end
        $display("tb_link_a2k (%0d Mb/s, skew_d1_300=%0d): train_cyc=%0d link_up=%b l0=%b l1=%b d_lock=%b tap0=%0d (%0d ps) tap1=%0d (%0d ps) skew_blocks=%0d",
                 RATE_MBPS, SKEW_D1_300_EN, cyc, link_up, l0_lock, l1_lock, d_lock,
                 cntval_l0, cntval_l0 * 4, cntval_l1, cntval_l1 * 4, skew_blk);

        if (!link_up) begin
            $display("FAIL: tb_link_a2k link_up failed (state=%0d l0=%b l1=%b d_lock=%b)", train_state, l0_lock, l1_lock, d_lock);
            $finish;
        end

        w0_width  = eye_r0 - eye_l0;
        w0_center = (eye_r0 + eye_l0) / 2;
        w0_err    = (cntval_l0 > w0_center) ? (cntval_l0 - w0_center) : (w0_center - cntval_l0);
        w1_width  = eye_r1 - eye_l1;
        w1_center = (eye_r1 + eye_l1) / 2;
        w1_err    = (cntval_l1 > w1_center) ? (cntval_l1 - w1_center) : (w1_center - cntval_l1);
        skew_ps   = ($signed({1'b0, cntval_l1}) - $signed({1'b0, cntval_l0})) * 4;

        $display("tb_link_a2k eye L0: [%0d..%0d] ([%0d..%0d] ps) width=%0d (%0d ps) center=%0d (%0d ps) chosen=%0d (%0d ps)",
                 eye_l0, eye_r0, eye_l0*4, eye_r0*4, w0_width, w0_width*4, w0_center, w0_center*4, cntval_l0, cntval_l0*4);
        $display("tb_link_a2k eye L1: [%0d..%0d] ([%0d..%0d] ps) width=%0d (%0d ps) center=%0d (%0d ps) chosen=%0d (%0d ps) tap1-tap0=%0d ps",
                 eye_l1, eye_r1, eye_l1*4, eye_r1*4, w1_width, w1_width*4, w1_center, w1_center*4, cntval_l1, cntval_l1*4, skew_ps);

        // Self-check eye centering within +/-10% of measured window width
        if (w0_width < 150 || (w0_err * 10 > w0_width)) fail_cnt = fail_cnt + 1;
        if (w1_width < 150 || (w1_err * 10 > w1_width)) fail_cnt = fail_cnt + 1;
        if (SKEW_D1_300_EN == 0) begin
            // Nominal D1 leads D0 by 57 ps -> tap1 must be > tap0 (~+57 ps)
            if (skew_ps < 24 || skew_ps > 96) fail_cnt = fail_cnt + 1;
        end else begin
            // +300 ps added to D1 -> tap1 moves by -300 ps relative to baseline (+57 ps) => ~-243 ps
            if (skew_ps > -190 || skew_ps < -300) fail_cnt = fail_cnt + 1;
        end

        // Pre-generate TOTAL_PKTS packets (1..1024 B)
        for (p = 0; p < TOTAL_PKTS; p = p + 1) begin
            prng = next_rand(prng);
            exp_sid[p] = 8'h01 + p[1:0];
            exp_err[p] = (p == 7); // Inject 1 deliberate error packet to verify end-to-end CRC rejection
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
                @(posedge tx_clkdiv);
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
            repeat (6) @(posedge tx_clkdiv);
        end

        for (cyc = 0; cyc < 4000 && ((rx_good_pkts + rx_drop_pkts) < TOTAL_PKTS); cyc = cyc + 1)
            @(posedge rx_clkdiv);
        repeat (50) @(posedge rx_clkdiv);

        $display("tb_link_a2k stats: tx=%0d rx_good=%0d rx_drop=%0d crc_err=%0d mismatches=%0d rem_stat=%h rem_drop=%0d l0=%b l1=%b d_lock=%b sh0=%0d sh1=%0d pkt_rx=%0d",
                 TOTAL_PKTS, rx_good_pkts, rx_drop_pkts, crc_err_cnt, payload_mismatches, rem_stat, rem_drop, l0_lock, l1_lock, d_lock, sh_err0, sh_err1, pkt_rx_cnt);

        if (rx_good_pkts !== (TOTAL_PKTS - 1)) fail_cnt = fail_cnt + 1;
        if (rx_drop_pkts !== 1)                fail_cnt = fail_cnt + 1;
        if (crc_err_cnt !== 32'd1)             fail_cnt = fail_cnt + 1;
        if (payload_mismatches !== 0)          fail_cnt = fail_cnt + 1;

        if (fail_cnt == 0)
            $display("PASS: tb_link_a2k rate=%0dM skew_d1_300=%0d tx=%0d rx_good=%0d crc_err=%0d tap0=%0d tap1=%0d",
                     RATE_MBPS, SKEW_D1_300_EN, TOTAL_PKTS, rx_good_pkts, crc_err_cnt, cntval_l0, cntval_l1);
        else
            $display("FAIL: tb_link_a2k rate=%0dM skew_d1_300=%0d tx=%0d rx_good=%0d crc_err=%0d mismatches=%0d tap0=%0d tap1=%0d",
                     RATE_MBPS, SKEW_D1_300_EN, TOTAL_PKTS, rx_good_pkts, crc_err_cnt, payload_mismatches, cntval_l0, cntval_l1);
        $finish;
    end
endmodule
