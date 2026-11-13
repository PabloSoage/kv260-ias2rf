// SPDX-License-Identifier: BSD-2-Clause
// Full Kria K26 -> Artix-7 Primitive Loopback Testbench (Verilog-2001):
//   - TX (Kria Bank 66 HP): link_pcs_single_tx -> OSERDESE3 (8:1 DDR) + OBUFDS on LINK_TX_CLK, LINK_TX_D0
//   - Channel:
//       * K26 SOM trace mid ([M] k26c/2.0/part0_pins.xml):
//           LINK_TX_CLK = 405/405 ps, LINK_TX_D0 = 408/408 ps
//       * KV260 carrier SOM240_1 -> J8 ([I] PINMAP.md): 180/180 ps common-mode
//       * Adapter PCB + Artix pkg ([M] lvds_skew.py / PINMAP.md):
//           LINK_TX_CLK = 661/665 ps, LINK_TX_D0 = 805/810 ps
//       * Net channel totals (D0 lags CLK by +147/+148 ps):
//           LINK_TX_CLK = 1246/1250 ps, LINK_TX_D0 = 1393/1398 ps
//     plus realistic +/-80 ps eye-edge setup/hold closure modeling at ISERDESE2 input.
//   - RX (Artix Bank 14 HR): IBUFDS (LVDS_25, DIFF_TERM="FALSE") ->
//       Clock: SRCC N13/P13 -> BUFIO + BUFR (BUFR_DIVIDE="4")
//       Data : IDELAYE2 (VAR_LOAD, 200 MHz IDELAYCTRL, 78 ps/tap) -> ISERDESE2 (8:1 DDR NETWORKING)
//     -> link_rx_train_fsm (32-tap single-lane eye centering) -> link_pcs_single_rx.
//
// Defines / Mutations (via xvlog -d):
//   RATE_800M / MUTATE_RATE_800M : run at 800 Mb/s (400 MHz DDR, 100 MHz CLKDIV)
//   MUTATE_BAD_SCRAMBLER         : wrong scrambler polynomial tap in TX encoder (FAIL)
//   MUTATE_SKIP_CRC              : bypass CRC-32 validation in RX deframer (FAIL)
//   MUTATE_BAD_IDELAY            : pin IDELAYE2 D0 onto the clock transition edge (FAIL)
//   MUTATE_NO_BUFR_DIV           : misconfigure BUFR_DIVIDE="2" instead of "4" (FAIL)

`timescale 1ns/1ps

module tb_link_k2a;
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
`ifdef MUTATE_NO_BUFR_DIV
    localparam [7:0] BUFR_DIV_STR = "2";
`else
    localparam [7:0] BUFR_DIV_STR = "4";
`endif

`ifdef RATE_800M
    localparam real    SER_HALF_PERIOD_NS = 1.250; // 400 MHz DDR = 800 Mb/s (1250 ps UI)
    localparam integer RATE_MBPS          = 800;
`elsif MUTATE_RATE_800M
    localparam real    SER_HALF_PERIOD_NS = 1.250;
    localparam integer RATE_MBPS          = 800;
`else
    localparam real    SER_HALF_PERIOD_NS = 1.000; // 500 MHz DDR = 1000 Mb/s (1000 ps UI)
    localparam integer RATE_MBPS          = 1000;
`endif

    localparam integer TOTAL_PKTS = 20;

    // -----------------------------------------------------------------------
    // Clocks:
    //   TX (Kria): 500 MHz (or 400 MHz) DDR serial clock + divide-by-4 CLKDIV
    //   RX (Artix IDELAYCTRL): 200 MHz REFCLK (per UG471)
    // -----------------------------------------------------------------------
    reg clk_ddr = 1'b0;
    always #(SER_HALF_PERIOD_NS) clk_ddr = ~clk_ddr;

    reg clk_200m = 1'b0;
    always #2.500 clk_200m = ~clk_200m;

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
    // Kria PCS TX (1-lane downlink on LINK_TX_D0)
    // -----------------------------------------------------------------------
    reg         tx_pkt_valid = 1'b0;
    wire        tx_pkt_ready;
    reg         tx_pkt_sop = 1'b0, tx_pkt_eop = 1'b0;
    reg  [7:0]  tx_pkt_sid = 8'd0;
    reg  [15:0] tx_pkt_len = 16'd0;
    reg  [31:0] tx_pkt_seq = 32'd0;
    reg  [63:0] tx_pkt_ts = 64'd0;
    reg  [63:0] tx_pkt_data = 64'd0;
    wire [7:0]  tx_byte_l0;
    reg         inject_tx_err = 1'b0;

    link_pcs_single_tx #(
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
        .dropped_cnt   (24'd1),
        .local_status  (16'h42A0),
        .tx_byte_l0    (tx_byte_l0)
    );

    wire [7:0] tx_byte_l0_wire = inject_tx_err ? (tx_byte_l0 ^ 8'h08) : tx_byte_l0;

    // -----------------------------------------------------------------------
    // Kria Bank 66 TX Primitives: 2 x OSERDESE3 (8:1 DDR) + OBUFDS (DIFF_SSTL12)
    // -----------------------------------------------------------------------
    wire ser_clk_se, ser_d0_se;
    wire pad_tx_clk_p, pad_tx_clk_n;
    wire pad_tx_d0_p,  pad_tx_d0_n;

    OSERDESE3 #(
        .DATA_WIDTH(8), .INIT(1'b0), .IS_CLKDIV_INVERTED(1'b0),
        .IS_CLK_INVERTED(1'b0), .IS_RST_INVERTED(1'b0),
        .ODDR_MODE("FALSE"), .OSERDES_D_BYPASS("FALSE"), .OSERDES_T_BYPASS("FALSE"),
        .SIM_DEVICE("ULTRASCALE_PLUS"), .SIM_VERSION(2.0)
    ) u_oserdes3_clk (
        .OQ(ser_clk_se), .T_OUT(),
        .CLK(clk_ddr), .CLKDIV(tx_clkdiv),
        .D(8'b10101010), .RST(tx_rst), .T(1'b0)
    );

    OSERDESE3 #(
        .DATA_WIDTH(8), .INIT(1'b0), .IS_CLKDIV_INVERTED(1'b0),
        .IS_CLK_INVERTED(1'b0), .IS_RST_INVERTED(1'b0),
        .ODDR_MODE("FALSE"), .OSERDES_D_BYPASS("FALSE"), .OSERDES_T_BYPASS("FALSE"),
        .SIM_DEVICE("ULTRASCALE_PLUS"), .SIM_VERSION(2.0)
    ) u_oserdes3_d0 (
        .OQ(ser_d0_se), .T_OUT(),
        .CLK(clk_ddr), .CLKDIV(tx_clkdiv),
        .D(tx_byte_l0_wire), .RST(tx_rst), .T(1'b0)
    );

    OBUFDS u_obuf_clk (.I(ser_clk_se), .O(pad_tx_clk_p), .OB(pad_tx_clk_n));
    OBUFDS u_obuf_d0  (.I(ser_d0_se),  .O(pad_tx_d0_p),  .OB(pad_tx_d0_n));

    // -----------------------------------------------------------------------
    // End-to-End Channel (3 transport-safe stages, each < 1.000 ns UI to prevent inertial pulse swallowing):
    //   1) K26 SOM Mid [M]:       LINK_TX_CLK = 405/405 ps, LINK_TX_D0 = 408/408 ps
    //   2) KV260 Carrier [I]:     180/180 ps common-mode
    //   3) Adapter+ArtixPkg [M]:  LINK_TX_CLK = 661/665 ps, LINK_TX_D0 = 805/810 ps
    //   Net channel totals (D0 lags CLK by +147/+148 ps):
    //        LINK_TX_CLK = 1246/1250 ps, LINK_TX_D0 = 1393/1398 ps
    // -----------------------------------------------------------------------
    wire #0.405 ch_som_clk_p  = pad_tx_clk_p;
    wire #0.405 ch_som_clk_n  = pad_tx_clk_n;
    wire #0.408 ch_som_d0_p   = pad_tx_d0_p;
    wire #0.408 ch_som_d0_n   = pad_tx_d0_n;

    wire #0.180 ch_car_clk_p  = ch_som_clk_p;
    wire #0.180 ch_car_clk_n  = ch_som_clk_n;
    wire #0.180 ch_car_d0_p   = ch_som_d0_p;
    wire #0.180 ch_car_d0_n   = ch_som_d0_n;

    wire #0.661 pad_rx_clk_p  = ch_car_clk_p;
    wire #0.665 pad_rx_clk_n  = ch_car_clk_n;
    wire #0.805 pad_rx_d0_p   = ch_car_d0_p;
    wire #0.810 pad_rx_d0_n   = ch_car_d0_n;

    // -----------------------------------------------------------------------
    // Artix-7 Bank 14 RX Primitives:
    //   IBUFDS (LVDS_25, DIFF_TERM="FALSE") -> BUFIO + BUFR ("4") -> IDELAYE2 -> ISERDESE2
    // -----------------------------------------------------------------------
    wire rx_clk_ibuf, rx_d0_ibuf;
    IBUFDS #(.DIFF_TERM("FALSE"), .IOSTANDARD("LVDS_25")) u_ibuf_clk (
        .I(pad_rx_clk_p), .IB(pad_rx_clk_n), .O(rx_clk_ibuf)
    );
    IBUFDS #(.DIFF_TERM("FALSE"), .IOSTANDARD("LVDS_25")) u_ibuf_d0 (
        .I(pad_rx_d0_p), .IB(pad_rx_d0_n), .O(rx_d0_ibuf)
    );

    wire rx_clk_bufio_raw;
    BUFIO u_bufio (.I(rx_clk_ibuf), .O(rx_clk_bufio_raw));

    // Model 7-series IDELAYE2 tap-0 intrinsic delay (600 ps) + BUFIO clock-tree insertion (350 ps)
    // in two < 1.000 ns stages so D0 sweeps across left edge (2..3), main eye (4..14 @ 1G), right edge (15..16).
    wire #0.600 rx_clk_bufio_s1 = rx_clk_bufio_raw;
    wire #0.350 rx_clk_bufio    = rx_clk_bufio_s1;

    wire rx_clkdiv;
    BUFR #(
        .BUFR_DIVIDE (BUFR_DIV_STR),
        .SIM_DEVICE  ("7SERIES")
    ) u_bufr (
        .O   (rx_clkdiv),
        .CE  (1'b1),
        .CLR (1'b0),
        .I   (rx_clk_bufio)
    );

    wire idelayctrl_rdy;
    IDELAYCTRL #(.SIM_DEVICE("7SERIES")) u_idelayctrl (
        .RDY    (idelayctrl_rdy),
        .REFCLK (clk_200m),
        .RST    (rx_rst)
    );

    wire       en_vtc, load_l0, load_l1_unused;
    wire [8:0] cntval_l0, cntval_l1_unused;
    wire       rx_d0_idelay;

    IDELAYE2 #(
        .CINVCTRL_SEL          ("FALSE"),
        .DELAY_SRC             ("IDATAIN"),
        .HIGH_PERFORMANCE_MODE ("TRUE"),
        .IDELAY_TYPE           ("VAR_LOAD"),
        .IDELAY_VALUE          (0),
        .PIPE_SEL              ("FALSE"),
        .REFCLK_FREQUENCY      (200.0),
        .SIGNAL_PATTERN        ("DATA")
    ) u_idelay_d0 (
        .CNTVALUEOUT (),
        .DATAOUT     (rx_d0_idelay),
        .C           (rx_clkdiv),
        .CE          (1'b0),
        .CINVCTRL    (1'b0),
        .CNTVALUEIN  (cntval_l0[4:0]),
        .DATAIN      (1'b0),
        .IDATAIN     (rx_d0_ibuf),
        .INC         (1'b0),
        .LD          (load_l0),
        .LDPIPEEN    (1'b0),
        .REGRST      (rx_rst)
    );

    // Realistic +/-80 ps setup/hold eye-edge model around rx_clk_bufio edges
    wire #0.081 rx_clk_check  = rx_clk_bufio;
    wire #0.082 rx_clk_sample = rx_clk_bufio;
    wire #0.080 rx_d0_pipe    = rx_d0_idelay;

    real last_d0_edge_ns = -100.0;
    always @(rx_d0_idelay) last_d0_edge_ns = $realtime;

    reg d0_eye_viol = 1'b0;
    reg [15:0] eye_prng = 16'hBEEF;
    always @(posedge rx_clk_check or negedge rx_clk_check) begin
        d0_eye_viol <= (($realtime - last_d0_edge_ns) <= 0.161);
        eye_prng    <= {eye_prng[14:0], eye_prng[15] ^ eye_prng[13] ^ eye_prng[12] ^ eye_prng[10]};
    end

    // Pseudorandom metastability corruption when transition lands inside +/-80 ps aperture
    wire rx_d0_to_iserdes = (d0_eye_viol && eye_prng[0]) ? ~rx_d0_pipe : rx_d0_pipe;

    wire q1, q2, q3, q4, q5, q6, q7, q8;
    ISERDESE2 #(
        .DATA_RATE         ("DDR"),
        .DATA_WIDTH        (8),
        .DYN_CLKDIV_INV_EN ("FALSE"),
        .DYN_CLK_INV_EN    ("FALSE"),
        .INIT_Q1           (1'b0),
        .INIT_Q2           (1'b0),
        .INIT_Q3           (1'b0),
        .INIT_Q4           (1'b0),
        .INTERFACE_TYPE    ("NETWORKING"),
        .IOBDELAY          ("IFD"),
        .IS_CLKB_INVERTED  (1'b0),
        .IS_CLKDIVP_INVERTED(1'b0),
        .IS_CLKDIV_INVERTED(1'b0),
        .IS_CLK_INVERTED   (1'b0),
        .IS_D_INVERTED     (1'b0),
        .IS_OCLKB_INVERTED (1'b0),
        .IS_OCLK_INVERTED  (1'b0),
        .NUM_CE            (1),
        .OFB_USED          ("FALSE"),
        .SERDES_MODE       ("MASTER"),
        .SRVAL_Q1          (1'b0),
        .SRVAL_Q2          (1'b0),
        .SRVAL_Q3          (1'b0),
        .SRVAL_Q4          (1'b0)
    ) u_iserdes_d0 (
        .O            (),
        .Q1           (q1),
        .Q2           (q2),
        .Q3           (q3),
        .Q4           (q4),
        .Q5           (q5),
        .Q6           (q6),
        .Q7           (q7),
        .Q8           (q8),
        .SHIFTOUT1    (),
        .SHIFTOUT2    (),
        .BITSLIP      (1'b0),
        .CE1          (1'b1),
        .CE2          (1'b1),
        .CLK          (rx_clk_sample),
        .CLKB         (~rx_clk_sample),
        .CLKDIV       (rx_clkdiv),
        .CLKDIVP      (1'b0),
        .D            (1'b0),
        .DDLY         (rx_d0_to_iserdes),
        .DYNCLKDIVSEL (1'b0),
        .DYNCLKSEL    (1'b0),
        .OCLK         (1'b0),
        .OCLKB        (1'b0),
        .OFB          (1'b0),
        .RST          (rx_rst),
        .SHIFTIN1     (1'b0),
        .SHIFTIN2     (1'b0)
    );

    // ISERDESE2 Q8 is oldest bit (LSB of TX byte), Q1 is newest bit (MSB of TX byte)
    wire [7:0] rx_byte_l0 = {q1, q2, q3, q4, q5, q6, q7, q8};

    // -----------------------------------------------------------------------
    // Artix Training FSM (32-tap IDELAYE2, single-lane) + PCS RX
    // -----------------------------------------------------------------------
    wire        rx_out_v, rx_out_sop, rx_out_eop;
    wire [7:0]  rx_out_sid;
    wire [15:0] rx_out_len;
    wire [31:0] rx_out_seq;
    wire [63:0] rx_out_ts, rx_out_data;
    wire        rx_done_v, rx_done_ok, rx_done_err;
    wire        l0_lock, link_up;
    wire [15:0] rem_stat;
    wire [23:0] rem_drop;
    wire [31:0] sh_err0, pkt_rx_cnt, crc_err_cnt;
    wire        l0_rx_blk_valid, l0_rx_blk_ok;
    wire [2:0]  train_state;
    wire [8:0]  eye_l0, eye_r0, eye_l1_unused, eye_r1_unused;

    link_rx_train_fsm #(
        .DEFAULT_CENTER_TAP (9'd9),
        .MAX_TAP            (9'd31),
        .TAP_STEP           (9'd1),
        .MIN_EYE_STEPS      (9'd7),
        .BAD_TAP            (9'd3),
        .WAIT_RESET_CYCLES  (16'd16),
        .TAP_SETTLE_CYCLES  (16'd24),
        .TAP_DWELL_CYCLES   (16'd1800),
        .LOCK_TIMEOUT       (16'd8192),
        .SINGLE_LANE        (1),
        .BAD_IDELAY         (BAD_IDELAY)
    ) u_train_fsm (
        .clk              (rx_clkdiv),
        .rst              (rx_rst),
        .retrain          (1'b0),
        .cfg_tap_override (1'b0),
        .cfg_tap_l0       (9'd9),
        .cfg_tap_l1       (9'd0),
        .rx_byte_l0       (rx_byte_l0),
        .rx_byte_l1       (8'd0),
        .l0_block_lock    (l0_lock),
        .l1_block_lock    (1'b1),
        .deskew_lock      (1'b1),
        .l0_rx_blk_valid  (l0_rx_blk_valid),
        .l0_rx_blk_ok     (l0_rx_blk_ok),
        .l1_rx_blk_valid  (1'b0),
        .l1_rx_blk_ok     (1'b1),
        .en_vtc           (en_vtc),
        .load_l0          (load_l0),
        .cntval_l0        (cntval_l0),
        .load_l1          (load_l1_unused),
        .cntval_l1        (cntval_l1_unused),
        .train_state      (train_state),
        .link_up          (link_up),
        .eye_left_l0      (eye_l0),
        .eye_right_l0     (eye_r0),
        .eye_left_l1      (eye_l1_unused),
        .eye_right_l1     (eye_r1_unused)
    );

    link_pcs_single_rx #(
        .SKIP_CRC (SKIP_CRC)
    ) u_pcs_rx (
        .clk                (rx_clkdiv),
        .rst                (rx_rst),
        .link_ready         (link_up),
        .rx_byte_l0         (rx_byte_l0),
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
        .remote_status      (rem_stat),
        .remote_dropped_cnt (rem_drop),
        .sh_err_cnt_l0      (sh_err0),
        .pkt_rx_cnt         (pkt_rx_cnt),
        .crc_err_cnt        (crc_err_cnt),
        .l0_rx_blk_valid    (l0_rx_blk_valid),
        .l0_rx_blk_ok       (l0_rx_blk_ok)
    );

    // -----------------------------------------------------------------------
    // Scoreboard
    // -----------------------------------------------------------------------
    reg [63:0] prng = 64'h1357_9BDF_2468_ACE0;
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

    initial begin
        fail_cnt = 0;
        tx_rst <= 1'b1;
        rx_rst <= 1'b1;

        // Wait past glbl.GSR (100 ns) before releasing TX reset
        #150;
        @(posedge tx_clkdiv);
        tx_rst <= 1'b0;

        // Clock RX primitives while rx_rst=1 so BUFIO, BUFR & IDELAYCTRL stabilize
        repeat (24) @(posedge tx_clkdiv);
        @(posedge rx_clkdiv);
        rx_rst <= 1'b0;

        // Wait for link_up (32-tap eye scan -> IDELAYE2 load -> block lock)
        cyc = 0;
        while ((!link_up) && (cyc < 35000)) begin
            @(posedge rx_clkdiv);
            cyc = cyc + 1;
        end
        $display("tb_link_k2a (%0d Mb/s, bufr_div=%0s): train_cyc=%0d link_up=%b l0=%b tap0=%0d (%0d ps)",
                 RATE_MBPS, BUFR_DIV_STR, cyc, link_up, l0_lock, cntval_l0, cntval_l0 * 78);

        if (!link_up) begin
            $display("FAIL: tb_link_k2a link_up failed (state=%0d l0=%b bufr_div=%0s)", train_state, l0_lock, BUFR_DIV_STR);
            $finish;
        end

        w0_width  = eye_r0 - eye_l0;
        w0_center = (eye_r0 + eye_l0) / 2;
        w0_err    = (cntval_l0 > w0_center) ? (cntval_l0 - w0_center) : (w0_center - cntval_l0);
        $display("tb_link_k2a eye D0: [%0d..%0d] ([%0d..%0d] ps) width=%0d (%0d ps) center=%0d (%0d ps) chosen=%0d (%0d ps)",
                 eye_l0, eye_r0, eye_l0*78, eye_r0*78, w0_width, w0_width*78, w0_center, w0_center*78, cntval_l0, cntval_l0*78);

        // Self-check IDELAYE2 centering within +/-10% of measured eye window
        if (w0_width < 7 || (w0_err * 10 > w0_width))
            fail_cnt = fail_cnt + 1;

        // Pre-generate TOTAL_PKTS packets (1..1024 B)
        for (p = 0; p < TOTAL_PKTS; p = p + 1) begin
            prng = next_rand(prng);
            exp_sid[p] = (p == 0) ? 8'h10 : ((p[0]) ? 8'h10 : 8'h7F);
            exp_err[p] = (p == 7); // Inject 1 deliberate bit error to verify end-to-end CRC rejection
            if (exp_err[p])
                exp_len[p] = 16'd256 + {8'd0, prng[7:0]};
            else
                exp_len[p] = 16'd8 + {7'd0, prng[8:0]};
            exp_seq[p] = p;
            prng = next_rand(prng);
            exp_ts[p]  = 64'h0000_0003_0000_0000 + {32'd0, prng[31:0]};
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

        // Send all TOTAL_PKTS packets on Kria side
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

        for (cyc = 0; cyc < 5000 && ((rx_good_pkts + rx_drop_pkts) < TOTAL_PKTS); cyc = cyc + 1)
            @(posedge rx_clkdiv);
        repeat (50) @(posedge rx_clkdiv);

        $display("tb_link_k2a stats: tx=%0d rx_good=%0d rx_drop=%0d crc_err=%0d mismatches=%0d rem_stat=%h rem_drop=%0d",
                 TOTAL_PKTS, rx_good_pkts, rx_drop_pkts, crc_err_cnt, payload_mismatches, rem_stat, rem_drop);

        if (rx_good_pkts !== (TOTAL_PKTS - 1)) fail_cnt = fail_cnt + 1;
        if (rx_drop_pkts !== 1)                fail_cnt = fail_cnt + 1;
        if (crc_err_cnt !== 32'd1)             fail_cnt = fail_cnt + 1;
        if (payload_mismatches !== 0)          fail_cnt = fail_cnt + 1;

        if (fail_cnt == 0)
            $display("PASS: tb_link_k2a rate=%0dM tx=%0d rx_good=%0d crc_err=%0d tap0=%0d",
                     RATE_MBPS, TOTAL_PKTS, rx_good_pkts, crc_err_cnt, cntval_l0);
        else
            $display("FAIL: tb_link_k2a rate=%0dM tx=%0d rx_good=%0d crc_err=%0d mismatches=%0d tap0=%0d",
                     RATE_MBPS, TOTAL_PKTS, rx_good_pkts, crc_err_cnt, payload_mismatches, cntval_l0);
        $finish;
    end
endmodule
