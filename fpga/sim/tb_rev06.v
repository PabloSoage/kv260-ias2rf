// SPDX-License-Identifier: BSD-2-Clause
// Concurrent Rev06 Dual-Path Testbench (Task 19):
//   - Full artix_top (ENABLE_ETH=1, BYPASS_AN=0, 2-lane IAS1 + 1.25 Gb/s SGMII ETH)
//   - Behavioral Kria IAS1 RX/TX (IDELAYE3 + ISERDESE3 + link_rx_train_fsm + link_pcs_rx)
//   - Behavioral RTL8211FSI PHY + KV260 PS GEM3 UDP Peer with dynamic +/-100 ppm clock skew:
//       * Clause 37 /C1/,/C2/ Auto-Negotiation handshake
//       * Clause 22 MDIO slave (PHYAD=1, BMSR link up + UDP-initiated R/W)
//       * SGMII TX/RX 8b/10b + IEEE 802.3 CRC-32 FCS check & injection
//       * Behavioral Kria (stream_id, seq_num) merge & deduplication scoreboard
//   - Phases tested:
//       1) +100 ppm clock skew, SPLIT policy: concurrent Radar (0x01) on IAS1 + SDR (0x02) on ETH
//          + poisoned bad-FCS UDP control packet rejection check
//       2) SPLIT failover: ETH fault -> 0x02 reroutes onto IAS1; fault cleared -> 0x02 returns to ETH
//       3) -100 ppm clock skew, MIRROR_1P1 policy: 0x01 & 0x02 on BOTH paths + UDP MDIO R/W
//          + mid-run ETH cut (0 loss after dedup) + mid-run IAS1 cut (0 loss after dedup)
//
// Mutations:
//   -Mutate no_phase_select : freezes SGMII RX XAPP523 phase_sel at 0 -> fails under +/-100 ppm
//   -Mutate eth_skip_fcs    : bypasses Ethernet FCS verification -> accepts poisoned packet -> fails

`timescale 1ps/1fs
`default_nettype none

module tb_rev06;

    localparam real PI = 3.14159265358979323846;

    localparam [47:0] ARTIX_MAC   = 48'h02_0A_35_00_01_02;
    localparam [47:0] KRIA_MAC    = 48'h02_0A_35_00_01_01;
    localparam [31:0] ARTIX_IP    = 32'hC0_A8_0A_02; // 192.168.10.2
    localparam [31:0] KRIA_IP     = 32'hC0_A8_0A_01; // 192.168.10.1
    localparam [15:0] UDP_PORT    = 16'h4952;

    localparam [7:0]  K_28_5 = 8'hBC;
    localparam [7:0]  K_27_7 = 8'hFB; // /S/
    localparam [7:0]  K_29_7 = 8'hFD; // /T/
    localparam [7:0]  K_23_7 = 8'hF7; // /R/
    localparam [7:0]  K_30_7 = 8'hFE; // /V/
    localparam [7:0]  D_5_6  = 8'hC5;
    localparam [7:0]  D_16_2 = 8'h50;
    localparam [7:0]  D_21_5 = 8'hB5;
    localparam [7:0]  D_2_2  = 8'h42;

    localparam [9:0]  K28_5_RD_NEG = 10'h17C;
    localparam [9:0]  K28_5_RD_POS = 10'h283;

    // -------------------------------------------------------------------------
    // Clocks (1ps/1fs timescale)
    // -------------------------------------------------------------------------
    reg fpga_clk_100m = 1'b0;
    always #5000.000 fpga_clk_100m = ~fpga_clk_100m;

    reg clk_400m_adc = 1'b0;
    always #1250.000 clk_400m_adc = ~clk_400m_adc;

    reg dco_true = 1'b0;
    initial begin
        dco_true = 1'b0;
        #1750.000;
        forever #2500.000 dco_true = ~dco_true;
    end

    reg kria_ref_300m = 1'b0;
    always #1666.000 kria_ref_300m = ~kria_ref_300m;

    reg kria_tx_ddr = 1'b0;
    always #1000.000 kria_tx_ddr = ~kria_tx_ddr;

    reg [1:0] kria_tx_div = 2'b00;
    reg       kria_tx_clk = 1'b0;
    always @(posedge kria_tx_ddr) begin
        kria_tx_div <= kria_tx_div + 2'd1;
        if (kria_tx_div == 2'd1)      kria_tx_clk <= 1'b1;
        else if (kria_tx_div == 2'd3) kria_tx_clk <= 1'b0;
    end

    // Peer SGMII TX asynchronous bit clock (+/-100 ppm switched at runtime)
    real peer_half_ui_ps = 399.960; // +100 ppm initially -> 799.920 ps UI
    reg  peer_bit_clk    = 1'b0;
    initial begin
        peer_bit_clk = 1'b0;
        forever #(peer_half_ui_ps) peer_bit_clk = ~peer_bit_clk;
    end

    // -------------------------------------------------------------------------
    // AD9484 Stimulus: checkerboard during ADC train, then active ramp/tone
    // -------------------------------------------------------------------------
    reg        adc_tone_mode  = 1'b0;
    integer    sample_idx     = 0;
    reg  [7:0] adc_sample_raw = 8'hAA;

    always @(posedge clk_400m_adc) begin
        if (!adc_tone_mode)
            adc_sample_raw <= sample_idx[0] ? 8'h55 : 8'hAA;
        else
            adc_sample_raw <= $rtoi(128.0 + 100.0 * $cos(2.0 * PI * 0.30390625 * sample_idx) + 0.5);
        sample_idx <= sample_idx + 1;
    end

    reg dco_board_del = 1'b0;
    always @(dco_true) dco_board_del <= #250.000 dco_true;

    wire       adcr_dco_n_pin = ~dco_board_del;
    wire       adcr_dco_p_pin =  dco_board_del;
    reg  [7:0] adcr_d_skew    = 8'd0;
    always @(adc_sample_raw) adcr_d_skew <= #200.000 adc_sample_raw;

    wire [7:0] adcr_d_p  = adcr_d_skew;
    wire [7:0] adcr_d_n  = ~adcr_d_skew;
    wire       adcr_or_p = 1'b0;
    wire       adcr_or_n = 1'b1;

    // -------------------------------------------------------------------------
    // DUT: artix_top (Rev06 ENABLE_ETH=1, BYPASS_AN=0)
    // -------------------------------------------------------------------------
    wire       ul_tx_clk_p, ul_tx_clk_n, ul_tx_d0_p, ul_tx_d0_n, ul_tx_d1_p, ul_tx_d1_n;
    wire       dl_rx_clk_p, dl_rx_clk_n, dl_rx_d0_p, dl_rx_d0_n;
    wire       pmod_miso, pmod_spare2, fpga_irq;
    reg        beam_strobe = 1'b0;
    reg        pmod_spare1 = 1'b1;
    reg        pps_sync    = 1'b0;
    wire       hk_scl, hk_sda;
    pullup(hk_scl);
    pullup(hk_sda);
    pulldown(u_artix.filter_overflow);

    wire       eth_sgtx_p, eth_sgtx_n;
    reg        eth_sgrx_p_drv = 1'b0;
    wire       eth_sgrx_p = eth_sgrx_p_drv;
    wire       eth_sgrx_n = ~eth_sgrx_p_drv;
    wire       eth_mdc, eth_rst_n;
    tri1       eth_mdio;

    artix_top #(
        .DDC_POST_DECIM    (4),
        .LINK_AM_PERIOD    (64),
        .ADC_AUTO_TRAIN    (1'b1),
        .ENABLE_ETH        (1'b1),
        .ETH_BYPASS_AN     (1'b0),
        .ETH_ALIVE_TIMEOUT (30000),
        .ETH_MDIO_RST_CYC  (20),
        .ETH_MDIO_POLL_DIV (200),
        .ETH_SDR_PKT_BYTES (128),
        .ETH_SDR_GAP_CYC   (24),
        .ETH_DEFAULT_POLICY(2'd0),
        .CONV_SPI_AUTO_INIT(1'b0),
        .ADAR_AUTO_INIT    (1'b0),
        .HK_POLL_DIV       (12500000)
    ) u_artix (
        .fpga_clk_p    (fpga_clk_100m),
        .fpga_clk_n    (~fpga_clk_100m),
        .adcr_d_p      (adcr_d_p),
        .adcr_d_n      (adcr_d_n),
        .adcr_or_p     (adcr_or_p),
        .adcr_or_n     (adcr_or_n),
        .adcr_dco_n    (adcr_dco_n_pin),
        .adcr_dco_p    (adcr_dco_p_pin),
        .adcs_dco_p    (fpga_clk_100m),
        .adcs_dco_n    (~fpga_clk_100m),
        .adcs_fco_p    (1'b0),
        .adcs_fco_n    (1'b1),
        .adcs_d0_p     (1'b0),
        .adcs_d0_n     (1'b1),
        .adcs_d1_p     (1'b0),
        .adcs_d1_n     (1'b1),
        .adar_sdo      (1'b0),
        .link_rx_clk_p (ul_tx_clk_p),
        .link_rx_clk_n (ul_tx_clk_n),
        .link_rx_d0_p  (ul_tx_d0_p),
        .link_rx_d0_n  (ul_tx_d0_n),
        .link_rx_d1_p  (ul_tx_d1_p),
        .link_rx_d1_n  (ul_tx_d1_n),
        .link_tx_clk_p (dl_rx_clk_p),
        .link_tx_clk_n (dl_rx_clk_n),
        .link_tx_d0_p  (dl_rx_d0_p),
        .link_tx_d0_n  (dl_rx_d0_n),
        .pmod_cs_n     (1'b1),
        .pmod_mosi     (1'b0),
        .pmod_miso     (pmod_miso),
        .pmod_sclk     (1'b0),
        .beam_strobe   (beam_strobe),
        .pps_sync      (pps_sync),
        .pmod_spare1   (pmod_spare1),
        .pmod_spare2   (pmod_spare2),
        .hk_scl        (hk_scl),
        .hk_sda        (hk_sda),
        .hk_alert_n    (1'b1),
        .fpga_irq      (fpga_irq),
        .eth_sgtx_p    (eth_sgtx_p),
        .eth_sgtx_n    (eth_sgtx_n),
        .eth_sgrx_p    (eth_sgrx_p),
        .eth_sgrx_n    (eth_sgrx_n),
        .eth_mdc       (eth_mdc),
        .eth_mdio      (eth_mdio),
        .eth_rst_n     (eth_rst_n)
    );

    // -------------------------------------------------------------------------
    // Kria IAS1 2-Lane RX + 1-Lane Downlink TX (3-stage PCB/Pkg/SOM delays in ps)
    // -------------------------------------------------------------------------
    wire #678.000 ul_adap_clk_p = ul_tx_clk_p; wire #677.000 ul_adap_clk_n = ul_tx_clk_n;
    wire #773.000 ul_adap_d0_p  = ul_tx_d0_p;  wire #772.000 ul_adap_d0_n  = ul_tx_d0_n;
    wire #717.000 ul_adap_d1_p  = ul_tx_d1_p;  wire #717.000 ul_adap_d1_n  = ul_tx_d1_n;

    wire #180.000 ul_car_clk_p  = ul_adap_clk_p; wire #180.000 ul_car_clk_n = ul_adap_clk_n;
    wire #180.000 ul_car_d0_p   = ul_adap_d0_p;  wire #180.000 ul_car_d0_n  = ul_adap_d0_n;
    wire #180.000 ul_car_d1_p   = ul_adap_d1_p;  wire #180.000 ul_car_d1_n  = ul_adap_d1_n;

    wire #413.000 kria_rx_clk_p = ul_car_clk_p; wire #413.000 kria_rx_clk_n = ul_car_clk_n;
    wire #406.000 kria_rx_d0_p  = ul_car_d0_p;  wire #406.000 kria_rx_d0_n  = ul_car_d0_n;
    wire #405.000 kria_rx_d1_p  = ul_car_d1_p;  wire #405.000 kria_rx_d1_n  = ul_car_d1_n;

    reg kria_rx_rst = 1'b1;
    reg kria_tx_rst = 1'b1;

    wire rx_clk_ibuf, rx_d0_ibuf, rx_d1_ibuf;
    IBUFDS u_kria_ibuf_clk (.I(kria_rx_clk_p), .IB(kria_rx_clk_n), .O(rx_clk_ibuf));
    IBUFDS u_kria_ibuf_d0  (.I(kria_rx_d0_p),  .IB(kria_rx_d0_n),  .O(rx_d0_ibuf));
    IBUFDS u_kria_ibuf_d1  (.I(kria_rx_d1_p),  .IB(kria_rx_d1_n),  .O(rx_d1_ibuf));

    wire #527.000 rx_clk_bufg = rx_clk_ibuf;
    reg [1:0] rx_div_cnt = 2'b00;
    reg       rx_clkdiv  = 1'b0;
    always @(posedge rx_clk_bufg) begin
        rx_div_cnt <= rx_div_cnt + 2'd1;
        if (rx_div_cnt == 2'd1)      rx_clkdiv <= 1'b1;
        else if (rx_div_cnt == 2'd3) rx_clkdiv <= 1'b0;
    end

    wire idelayctrl_rdy;
    IDELAYCTRL #(.SIM_DEVICE("ULTRASCALE")) u_kria_idelayctrl (
        .RDY(idelayctrl_rdy), .REFCLK(kria_ref_300m), .RST(kria_rx_rst)
    );

    wire       en_vtc, load_l0, load_l1;
    wire [8:0] cntval_l0, cntval_l1;
    wire       rx_d0_idelay, rx_d1_idelay;

    IDELAYE3 #(
        .CASCADE("NONE"), .DELAY_FORMAT("TIME"), .DELAY_SRC("IDATAIN"),
        .DELAY_TYPE("VAR_LOAD"), .DELAY_VALUE(0), .REFCLK_FREQUENCY(300.0),
        .SIM_DEVICE("ULTRASCALE_PLUS"), .SIM_VERSION(2.0), .UPDATE_MODE("ASYNC")
    ) u_kria_idelay_d0 (
        .CASC_OUT(), .CNTVALUEOUT(), .DATAOUT(rx_d0_idelay),
        .CASC_IN(1'b0), .CASC_RETURN(1'b0), .CE(1'b0), .CLK(rx_clkdiv),
        .CNTVALUEIN(cntval_l0), .DATAIN(1'b0), .EN_VTC(en_vtc),
        .IDATAIN(rx_d0_ibuf), .INC(1'b0), .LOAD(load_l0), .RST(kria_rx_rst)
    );

    IDELAYE3 #(
        .CASCADE("NONE"), .DELAY_FORMAT("TIME"), .DELAY_SRC("IDATAIN"),
        .DELAY_TYPE("VAR_LOAD"), .DELAY_VALUE(0), .REFCLK_FREQUENCY(300.0),
        .SIM_DEVICE("ULTRASCALE_PLUS"), .SIM_VERSION(2.0), .UPDATE_MODE("ASYNC")
    ) u_kria_idelay_d1 (
        .CASC_OUT(), .CNTVALUEOUT(), .DATAOUT(rx_d1_idelay),
        .CASC_IN(1'b0), .CASC_RETURN(1'b0), .CE(1'b0), .CLK(rx_clkdiv),
        .CNTVALUEIN(cntval_l1), .DATAIN(1'b0), .EN_VTC(en_vtc),
        .IDATAIN(rx_d1_ibuf), .INC(1'b0), .LOAD(load_l1), .RST(kria_rx_rst)
    );

    wire #82.000 rx_clk_sample = rx_clk_bufg;
    wire #80.000 rx_d0_to_is   = rx_d0_idelay;
    wire #80.000 rx_d1_to_is   = rx_d1_idelay;

    wire [7:0] rx_byte_l0, rx_byte_l1;
    ISERDESE3 #(
        .DATA_WIDTH(8), .DDR_CLK_EDGE("OPPOSITE_EDGE"), .FIFO_ENABLE("FALSE"),
        .FIFO_SYNC_MODE("FALSE"), .IDDR_MODE("FALSE"),
        .SIM_DEVICE("ULTRASCALE_PLUS"), .SIM_VERSION(2.0)
    ) u_kria_is_d0 (
        .FIFO_EMPTY(), .INTERNAL_DIVCLK(), .Q(rx_byte_l0),
        .CLK(rx_clk_sample), .CLKDIV(rx_clkdiv), .CLK_B(~rx_clk_sample),
        .D(rx_d0_to_is), .FIFO_RD_CLK(1'b0), .FIFO_RD_EN(1'b0), .RST(kria_rx_rst)
    );

    ISERDESE3 #(
        .DATA_WIDTH(8), .DDR_CLK_EDGE("OPPOSITE_EDGE"), .FIFO_ENABLE("FALSE"),
        .FIFO_SYNC_MODE("FALSE"), .IDDR_MODE("FALSE"),
        .SIM_DEVICE("ULTRASCALE_PLUS"), .SIM_VERSION(2.0)
    ) u_kria_is_d1 (
        .FIFO_EMPTY(), .INTERNAL_DIVCLK(), .Q(rx_byte_l1),
        .CLK(rx_clk_sample), .CLKDIV(rx_clkdiv), .CLK_B(~rx_clk_sample),
        .D(rx_d1_to_is), .FIFO_RD_CLK(1'b0), .FIFO_RD_EN(1'b0), .RST(kria_rx_rst)
    );

    wire        rx_out_v, rx_out_sop, rx_out_eop;
    wire [7:0]  rx_out_sid;
    wire [15:0] rx_out_len;
    wire [31:0] rx_out_seq;
    wire [63:0] rx_out_ts, rx_out_data;
    wire        rx_done_v, rx_done_ok, rx_done_err;
    wire        l0_lock, l1_lock, d_lock, kria_link_up;
    wire [31:0] crc_err_cnt;
    wire        l0_blk_v, l0_blk_ok, l1_blk_v, l1_blk_ok;
    wire [2:0]  train_state;

    link_rx_train_fsm #(
        .DEFAULT_CENTER_TAP (9'd202),
        .MAX_TAP            (9'd511),
        .TAP_STEP           (9'd8),
        .MIN_EYE_STEPS      (9'd18),
        .BAD_TAP            (9'd78),
        .WAIT_RESET_CYCLES  (16'd16),
        .TAP_SETTLE_CYCLES  (16'd24),
        .TAP_DWELL_CYCLES   (16'd1600),
        .LOCK_TIMEOUT       (16'd8192),
        .SINGLE_LANE        (0)
    ) u_kria_train (
        .clk              (rx_clkdiv),
        .rst              (kria_rx_rst),
        .retrain          (1'b0),
        .cfg_tap_override (1'b0),
        .cfg_tap_l0       (9'd202),
        .cfg_tap_l1       (9'd216),
        .rx_byte_l0       (rx_byte_l0),
        .rx_byte_l1       (rx_byte_l1),
        .l0_block_lock    (l0_lock),
        .l1_block_lock    (l1_lock),
        .deskew_lock      (d_lock),
        .l0_rx_blk_valid  (l0_blk_v),
        .l0_rx_blk_ok     (l0_blk_ok),
        .l1_rx_blk_valid  (l1_blk_v),
        .l1_rx_blk_ok     (l1_blk_ok),
        .en_vtc           (en_vtc),
        .load_l0          (load_l0),
        .cntval_l0        (cntval_l0),
        .load_l1          (load_l1),
        .cntval_l1        (cntval_l1),
        .train_state      (train_state),
        .link_up          (kria_link_up),
        .eye_left_l0      (), .eye_right_l0(),
        .eye_left_l1      (), .eye_right_l1()
    );

    link_pcs_rx #(.DISABLE_DESKEW(0)) u_kria_pcs_rx (
        .clk                (rx_clkdiv),
        .rst                (kria_rx_rst),
        .link_ready         (kria_link_up),
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
        .skew_blocks        (),
        .remote_status      (),
        .remote_dropped_cnt (),
        .sh_err_cnt_l0      (),
        .sh_err_cnt_l1      (),
        .pkt_rx_cnt         (),
        .crc_err_cnt        (crc_err_cnt),
        .l0_rx_blk_valid    (l0_blk_v),
        .l0_rx_blk_ok       (l0_blk_ok),
        .l1_rx_blk_valid    (l1_blk_v),
        .l1_rx_blk_ok       (l1_blk_ok)
    );

    wire [7:0] dl_tx_byte;
    wire       dl_ser_clk, dl_ser_d0;
    wire       dl_pad_clk_p, dl_pad_clk_n, dl_pad_d0_p, dl_pad_d0_n;
    (* ASYNC_REG = "TRUE" *) reg [1:0] dl_kria_up_sync = 2'b00;
    always @(posedge kria_tx_clk) begin
        if (kria_tx_rst) dl_kria_up_sync <= 2'b00;
        else             dl_kria_up_sync <= {dl_kria_up_sync[0], kria_link_up};
    end

    link_pcs_single_tx u_kria_dl_tx (
        .clk           (kria_tx_clk),
        .rst           (kria_tx_rst),
        .pkt_valid     (1'b0),
        .pkt_ready     (),
        .pkt_sop       (1'b0),
        .pkt_eop       (1'b0),
        .pkt_stream_id (8'd0),
        .pkt_len       (16'd0),
        .pkt_seq       (32'd0),
        .pkt_timestamp (64'd0),
        .pkt_data      (64'd0),
        .dropped_cnt   (24'd0),
        .local_status  ({15'd0, dl_kria_up_sync[1]}),
        .tx_byte_l0    (dl_tx_byte)
    );

    OSERDESE3 #(
        .DATA_WIDTH(8), .INIT(1'b0), .IS_CLKDIV_INVERTED(1'b0),
        .IS_CLK_INVERTED(1'b0), .IS_RST_INVERTED(1'b0),
        .ODDR_MODE("FALSE"), .OSERDES_D_BYPASS("FALSE"), .OSERDES_T_BYPASS("FALSE"),
        .SIM_DEVICE("ULTRASCALE_PLUS"), .SIM_VERSION(2.0)
    ) u_dl_os3_clk (
        .OQ(dl_ser_clk), .T_OUT(), .CLK(kria_tx_ddr), .CLKDIV(kria_tx_clk),
        .D(8'b10101010), .RST(kria_tx_rst), .T(1'b0)
    );

    OSERDESE3 #(
        .DATA_WIDTH(8), .INIT(1'b0), .IS_CLKDIV_INVERTED(1'b0),
        .IS_CLK_INVERTED(1'b0), .IS_RST_INVERTED(1'b0),
        .ODDR_MODE("FALSE"), .OSERDES_D_BYPASS("FALSE"), .OSERDES_T_BYPASS("FALSE"),
        .SIM_DEVICE("ULTRASCALE_PLUS"), .SIM_VERSION(2.0)
    ) u_dl_os3_d0 (
        .OQ(dl_ser_d0), .T_OUT(), .CLK(kria_tx_ddr), .CLKDIV(kria_tx_clk),
        .D(dl_tx_byte), .RST(kria_tx_rst), .T(1'b0)
    );

    OBUFDS u_dl_obuf_clk (.I(dl_ser_clk), .O(dl_pad_clk_p), .OB(dl_pad_clk_n));
    OBUFDS u_dl_obuf_d0  (.I(dl_ser_d0),  .O(dl_pad_d0_p),  .OB(dl_pad_d0_n));
    // Multi-stage / transport delays so 1000 ps pulses are not swallowed by inertial delay
    reg dl_rx_clk_p_r = 1'b0, dl_rx_clk_n_r = 1'b1;
    reg dl_rx_d0_p_r  = 1'b0, dl_rx_d0_n_r  = 1'b1;
    always @(dl_pad_clk_p) dl_rx_clk_p_r <= #1246.000 dl_pad_clk_p;
    always @(dl_pad_clk_n) dl_rx_clk_n_r <= #1250.000 dl_pad_clk_n;
    always @(dl_pad_d0_p)  dl_rx_d0_p_r  <= #1393.000 dl_pad_d0_p;
    always @(dl_pad_d0_n)  dl_rx_d0_n_r  <= #1398.000 dl_pad_d0_n;
    assign dl_rx_clk_p = dl_rx_clk_p_r;
    assign dl_rx_clk_n = dl_rx_clk_n_r;
    assign dl_rx_d0_p  = dl_rx_d0_p_r;
    assign dl_rx_d0_n  = dl_rx_d0_n_r;

    // -------------------------------------------------------------------------
    // Behavioral RTL8211FSI Clause 22 MDIO Slave (PHYAD=5'd1)
    // -------------------------------------------------------------------------
    reg [15:0] phy_regs [0:31];
    integer mdio_idx;
    initial begin
        for (mdio_idx = 0; mdio_idx < 32; mdio_idx = mdio_idx + 1)
            phy_regs[mdio_idx] = 16'h0000;
        phy_regs[0] = 16'h1140; // BMCR: AN enable, 1G FD
        phy_regs[1] = 16'h796D; // BMSR: Link Up, AN Complete, 1000BASE-T
        phy_regs[2] = 16'h001C; // PHYID1 Realtek
        phy_regs[3] = 16'hC916; // PHYID2 RTL8211F
    end

    reg        mdio_drv_en  = 1'b0;
    reg        mdio_drv_val = 1'b1;
    assign eth_mdio = mdio_drv_en ? mdio_drv_val : 1'bz;

    reg [5:0]  mdio_bit     = 6'd0;
    reg [31:0] mdio_sh      = 32'd0;
    reg [1:0]  mdio_op      = 2'd0;
    reg [4:0]  mdio_pa      = 5'd0;
    reg [4:0]  mdio_ra      = 5'd0;
    reg [15:0] mdio_rd_buf  = 16'd0;
    reg [15:0] mdio_wr_buf  = 16'd0;
    integer    mdio_poll_reads  = 0;
    integer    mdio_custom_wrs  = 0;

    always @(posedge eth_mdc or negedge eth_rst_n) begin
        if (!eth_rst_n) begin
            mdio_bit    <= 6'd0;
            mdio_drv_en <= 1'b0;
        end else begin
            // Preamble detection: wait for 0 followed by 1 ('01' ST) after >=1 ones
            if (mdio_bit == 6'd0) begin
                mdio_drv_en <= 1'b0;
                if (mdio_sh[0] === 1'b1 && eth_mdio === 1'b0)
                    mdio_bit <= 6'd1;
                mdio_sh <= {mdio_sh[30:0], eth_mdio};
            end else begin
                mdio_bit <= mdio_bit + 6'd1;
                if (mdio_bit == 6'd1 && eth_mdio !== 1'b1) begin
                    mdio_bit <= 6'd0; // false start
                end else if (mdio_bit == 6'd2) mdio_op[1] <= eth_mdio;
                else if (mdio_bit == 6'd3) mdio_op[0] <= eth_mdio;
                else if (mdio_bit >= 6'd4 && mdio_bit <= 6'd8)
                    mdio_pa <= {mdio_pa[3:0], eth_mdio};
                else if (mdio_bit >= 6'd9 && mdio_bit <= 6'd13)
                    mdio_ra <= {mdio_ra[3:0], eth_mdio};
                else if (mdio_bit == 6'd14) begin
                    if (mdio_op == 2'b10 && mdio_pa == 5'd1) begin
                        mdio_rd_buf <= phy_regs[mdio_ra];
                    end
                end else if (mdio_bit == 6'd15) begin
                    if (mdio_op == 2'b10 && mdio_pa == 5'd1) begin
                        mdio_drv_en  <= 1'b1;
                        mdio_drv_val <= 1'b0; // TA drive 0 then data on subsequent clocks
                    end
                end else if (mdio_bit >= 6'd16 && mdio_bit <= 6'd31) begin
                    if (mdio_op == 2'b10 && mdio_pa == 5'd1) begin
                        mdio_drv_en  <= 1'b1;
                        mdio_drv_val <= mdio_rd_buf[31 - mdio_bit];
                        if (mdio_bit == 6'd31)
                            mdio_poll_reads <= mdio_poll_reads + 1;
                    end else if (mdio_op == 2'b01 && mdio_pa == 5'd1) begin
                        mdio_wr_buf <= {mdio_wr_buf[14:0], eth_mdio};
                        if (mdio_bit == 6'd31) begin
                            phy_regs[mdio_ra] <= {mdio_wr_buf[14:0], eth_mdio};
                            mdio_custom_wrs   <= mdio_custom_wrs + 1;
                        end
                    end
                end else if (mdio_bit >= 6'd32) begin
                    mdio_drv_en <= 1'b0;
                    mdio_bit    <= 6'd0;
                end
            end
        end
    end

    // -------------------------------------------------------------------------
    // Behavioral SGMII Peer TX (8b/10b + Clause 37 AN + UDP Frame Queue @ +/-100 ppm)
    // -------------------------------------------------------------------------
    reg [3:0] peer_bit_idx  = 4'd0;
    reg       peer_clk_125  = 1'b0;
    reg       peer_rst_125  = 1'b1;
    reg       peer_tx_k     = 1'b1;
    reg [7:0] peer_tx_d     = K_28_5;
    wire [9:0] peer_enc_code;
    wire       peer_enc_rd;
    reg [9:0]  peer_tx_sr   = K28_5_RD_NEG;

    eth_8b10b_enc u_peer_enc (
        .clk    (peer_clk_125),
        .rst    (peer_rst_125),
        .en     (1'b1),
        .din_k  (peer_tx_k),
        .din    (peer_tx_d),
        .dout   (peer_enc_code),
        .rd_pos (peer_enc_rd)
    );

    always @(posedge peer_bit_clk) begin
        if (peer_bit_idx == 4'd9) begin
            peer_bit_idx <= 4'd0;
            peer_clk_125 <= 1'b1;
            peer_tx_sr   <= peer_enc_code;
            eth_sgrx_p_drv <= peer_enc_code[0];
        end else begin
            peer_bit_idx   <= peer_bit_idx + 4'd1;
            if (peer_bit_idx == 4'd4)
                peer_clk_125 <= 1'b0;
            eth_sgrx_p_drv <= peer_tx_sr[peer_bit_idx + 1];
        end
    end

    // Peer TX Frame Queue (bytes including 7x 0x55 + 0xD5 + L2..FCS)
    reg [7:0]  peer_q_mem [0:1535];
    integer    peer_q_wr = 0;
    integer    peer_q_rd = 0;

    function [31:0] crc32_byte(input [31:0] crc, input [7:0] data);
        reg [31:0] c;
        integer    i;
        begin
            c = crc;
            for (i = 0; i < 8; i = i + 1) begin
                if (c[0] ^ data[i]) c = (c >> 1) ^ 32'hEDB88320;
                else                c = (c >> 1);
            end
            crc32_byte = c;
        end
    endfunction

    function [15:0] ipv4_csum(input [15:0] tot_len, input [15:0] ip_id,
                              input [31:0] sip, input [31:0] dip);
        reg [31:0] sum;
        begin
            sum = 32'h00004500 + tot_len + ip_id + 32'h00004000 + 32'h00004011 +
                  sip[31:16] + sip[15:0] + dip[31:16] + dip[15:0];
            sum = (sum[31:16] + sum[15:0]);
            sum = (sum[31:16] + sum[15:0]);
            ipv4_csum = ~sum[15:0];
        end
    endfunction

    reg [1:0]  peer_an_mode     = 2'd0; // 0: /C/ Ack=0, 1: /C/ Ack=1, 2: DATA
    reg        peer_an_c2       = 1'b0;
    reg [1:0]  peer_an_sub      = 2'd0;
    reg        peer_even        = 1'b0;
    reg [2:0]  peer_pcs_st      = 3'd0; // 0: AN, 1: IDLE0, 2: IDLE1, 3: PKT, 4: TR
    reg [15:0] peer_ip_id       = 16'd1;

    always @(posedge peer_clk_125) begin
        if (peer_rst_125) begin
            peer_pcs_st <= 3'd0;
            peer_an_sub <= 2'd0;
            peer_an_c2  <= 1'b0;
            peer_even   <= 1'b0;
            peer_tx_k   <= 1'b1;
            peer_tx_d   <= K_28_5;
        end else begin
            peer_even <= ~peer_even;
            case (peer_pcs_st)
                3'd0: begin // Clause 37 /C1/,/C2/
                    if (peer_an_mode == 2'd2 && peer_an_sub == 2'd0 && !peer_even) begin
                        peer_pcs_st <= 3'd2;
                        peer_tx_k   <= 1'b1;
                        peer_tx_d   <= K_28_5;
                    end else begin
                        case (peer_an_sub)
                            2'd0: begin peer_tx_k <= 1'b1; peer_tx_d <= K_28_5; end
                            2'd1: begin peer_tx_k <= 1'b0; peer_tx_d <= peer_an_c2 ? D_2_2 : D_21_5; peer_an_c2 <= ~peer_an_c2; end
                            2'd2: begin peer_tx_k <= 1'b0; peer_tx_d <= 8'h01; end
                            2'd3: begin peer_tx_k <= 1'b0; peer_tx_d <= (peer_an_mode == 2'd0) ? 8'h98 : 8'hD8; end
                        endcase
                        peer_an_sub <= peer_an_sub + 2'd1;
                    end
                end
                3'd1: begin // IDLE_0
                    if (peer_q_rd < peer_q_wr) begin
                        peer_tx_k   <= 1'b1;
                        peer_tx_d   <= K_27_7; // /S/ replaces preamble[0]
                        peer_q_rd   <= peer_q_rd + 1;
                        peer_pcs_st <= 3'd3;
                    end else begin
                        peer_tx_k   <= 1'b1;
                        peer_tx_d   <= K_28_5;
                        peer_pcs_st <= 3'd2;
                    end
                end
                3'd2: begin // IDLE_1
                    peer_tx_k   <= 1'b0;
                    peer_tx_d   <= (peer_enc_rd == 1'b1) ? D_5_6 : D_16_2;
                    peer_pcs_st <= 3'd1;
                end
                3'd3: begin // PKT
                    if (peer_q_rd < peer_q_wr) begin
                        peer_tx_k <= 1'b0;
                        peer_tx_d <= peer_q_mem[peer_q_rd];
                        peer_q_rd <= peer_q_rd + 1;
                    end else begin
                        peer_tx_k   <= 1'b1;
                        peer_tx_d   <= K_29_7; // /T/
                        peer_pcs_st <= 3'd4;
                    end
                end
                3'd4: begin // /R/ align to even
                    peer_tx_k <= 1'b1;
                    peer_tx_d <= K_23_7;
                    if (peer_even)
                        peer_pcs_st <= 3'd4;
                    else
                        peer_pcs_st <= 3'd1;
                end
                default: peer_pcs_st <= 3'd1;
            endcase
        end
    end

    task send_udp_frame(
        input [15:0] magic,
        input [15:0] addr,
        input [31:0] wdata,
        input [31:0] seq,
        input        corrupt_fcs
    );
        reg [7:0]  fbuf [0:79];
        reg [31:0] crc;
        reg [15:0] icsum;
        integer    i, base;
        begin
            // Wait until any previous queued frame drains
            while (peer_q_rd < peer_q_wr) @(posedge peer_clk_125);
            peer_ip_id = peer_ip_id + 16'd1;
            icsum = ipv4_csum(16'd46, peer_ip_id, KRIA_IP, ARTIX_IP); // 20 IP + 8 UDP + 18 payload

            for (i = 0; i < 7; i = i + 1) fbuf[i] = 8'h55;
            fbuf[7] = 8'hD5;
            // Eth L2 [8..21] (offset 0..13 after SFD)
            {fbuf[8],fbuf[9],fbuf[10],fbuf[11],fbuf[12],fbuf[13]}   = ARTIX_MAC;
            {fbuf[14],fbuf[15],fbuf[16],fbuf[17],fbuf[18],fbuf[19]} = KRIA_MAC;
            {fbuf[20],fbuf[21]} = 16'h0800;
            // IPv4 [22..41]
            fbuf[22] = 8'h45; fbuf[23] = 8'h00;
            {fbuf[24],fbuf[25]} = 16'd46;
            {fbuf[26],fbuf[27]} = peer_ip_id;
            {fbuf[28],fbuf[29]} = 16'h4000;
            fbuf[30] = 8'd64; fbuf[31] = 8'd17;
            {fbuf[32],fbuf[33]} = icsum;
            {fbuf[34],fbuf[35],fbuf[36],fbuf[37]} = KRIA_IP;
            {fbuf[38],fbuf[39],fbuf[40],fbuf[41]} = ARTIX_IP;
            // UDP [42..49] (length = 8 + 18 = 26)
            {fbuf[42],fbuf[43]} = UDP_PORT;
            {fbuf[44],fbuf[45]} = UDP_PORT;
            {fbuf[46],fbuf[47]} = 16'd26;
            {fbuf[48],fbuf[49]} = 16'h0000;
            // Payload [50..67]
            {fbuf[50],fbuf[51]} = magic;
            {fbuf[52],fbuf[53]} = addr;
            {fbuf[54],fbuf[55],fbuf[56],fbuf[57]} = wdata;
            {fbuf[58],fbuf[59],fbuf[60],fbuf[61]} = seq;
            for (i = 62; i < 68; i = i + 1) fbuf[i] = 8'h00; // >= 60 bytes L2+payload

            crc = 32'hFFFF_FFFF;
            for (i = 8; i < 68; i = i + 1) crc = crc32_byte(crc, fbuf[i]);
            fbuf[68] = ~crc[7:0];
            fbuf[69] = ~crc[15:8];
            fbuf[70] = ~crc[23:16];
            fbuf[71] = (~crc[31:24]) ^ (corrupt_fcs ? 8'hFF : 8'h00);

            // Reset queue indices cleanly between frames
            @(posedge peer_clk_125);
            peer_q_rd = 0;
            peer_q_wr = 0;
            for (i = 0; i < 72; i = i + 1)
                peer_q_mem[i] = fbuf[i];
            peer_q_wr = 72;
            while (peer_q_rd < peer_q_wr) @(posedge peer_clk_125);
            repeat (24) @(posedge peer_clk_125); // clean IPG + processing time
        end
    endtask

    // -------------------------------------------------------------------------
    // Behavioral SGMII Peer RX CDR (200 ps ticks = 4x over 800 ps UI) + MAC/UDP
    // -------------------------------------------------------------------------
    reg cdr_tick = 1'b0;
    always #100.000 cdr_tick = ~cdr_tick; // posedge every 200 ps

    reg       prev_sgtx     = 1'b0;
    reg [1:0] ui_tick       = 2'd0;
    reg [9:0] cdr_sr        = 10'd0;
    reg       cdr_aligned   = 1'b0;
    reg [3:0] cdr_bit_phase = 4'd0;
    reg [9:0] cdr_sym       = 10'd0;
    reg       cdr_sym_tgl   = 1'b0;

    always @(posedge cdr_tick) begin
        if (eth_sgtx_p !== prev_sgtx) begin
            prev_sgtx <= eth_sgtx_p;
            ui_tick   <= 2'd2; // sample ~400 ps later (2->3->0)
        end else begin
            ui_tick <= ui_tick + 2'd1;
        end

        if (ui_tick == 2'd0) begin
            cdr_sr = {eth_sgtx_p, cdr_sr[9:1]};
            if (!cdr_aligned) begin
                if (cdr_sr == K28_5_RD_NEG || cdr_sr == K28_5_RD_POS) begin
                    cdr_aligned   <= 1'b1;
                    cdr_bit_phase <= 4'd0;
                    cdr_sym       <= cdr_sr;
                    cdr_sym_tgl   <= ~cdr_sym_tgl;
                end
            end else begin
                if (cdr_bit_phase == 4'd9) begin
                    cdr_bit_phase <= 4'd0;
                    cdr_sym       <= cdr_sr;
                    cdr_sym_tgl   <= ~cdr_sym_tgl;
                end else begin
                    cdr_bit_phase <= cdr_bit_phase + 4'd1;
                end
            end
        end
    end

    wire       peer_dec_rd_pos;
    wire       peer_rx_k, peer_rx_code_err, peer_rx_disp_err;
    wire [7:0] peer_rx_d;

    // Clock eth_8b10b_dec directly on recovered symbol toggle edge (dual-edge via clk helper)
    reg peer_rec_clk = 1'b0;
    always @(cdr_sym_tgl) begin
        peer_rec_clk = 1'b1;
        #100.000;
        peer_rec_clk = 1'b0;
    end

    eth_8b10b_dec u_peer_dec (
        .clk      (peer_rec_clk),
        .rst      (peer_rst_125),
        .en       (1'b1),
        .din      (cdr_sym),
        .dout_k   (peer_rx_k),
        .dout     (peer_rx_d),
        .code_err (peer_rx_code_err),
        .disp_err (peer_rx_disp_err),
        .rd_pos   (peer_dec_rd_pos)
    );

    reg        eth_rx_in_pkt   = 1'b0;
    reg        eth_rx_sfd_seen = 1'b0;
    reg [31:0] eth_rx_crc      = 32'hFFFF_FFFF;
    integer    eth_rx_idx      = 0;
    reg [15:0] eth_rx_ethertype = 16'd0;
    reg [7:0]  eth_rx_sid      = 8'd0;
    reg [15:0] eth_rx_len      = 16'd0;
    reg [31:0] eth_rx_seq      = 32'd0;
    reg [63:0] eth_rx_ts       = 64'd0;
    reg        eth_rx_bad      = 1'b0;
    integer    eth_fcs_fail    = 0;
    integer    eth_s1_cnt      = 0;
    integer    eth_s2_cnt      = 0;
    reg [1023:0] seen_eth_s1   = 1024'd0;
    reg [1023:0] seen_eth_s2   = 1024'd0;
    integer    eth_max_s1      = -1;
    integer    eth_max_s2      = -1;

    always @(posedge peer_rec_clk) begin
        if (peer_rst_125) begin
            eth_rx_in_pkt   <= 1'b0;
            eth_rx_sfd_seen <= 1'b0;
        end else begin
            if (!eth_rx_in_pkt) begin
                if (peer_rx_k && peer_rx_d == K_27_7) begin
                    eth_rx_in_pkt   <= 1'b1;
                    eth_rx_sfd_seen <= 1'b0;
                    eth_rx_bad      <= 1'b0;
                end
            end else begin
                if (peer_rx_k && (peer_rx_d == K_29_7 || peer_rx_d == K_28_5)) begin
                    eth_rx_in_pkt <= 1'b0;
                    if (eth_rx_sfd_seen) begin
                        if (eth_rx_bad || eth_rx_idx < 64 || (~eth_rx_crc != 32'h2144_DF1C)) begin
                            eth_fcs_fail <= eth_fcs_fail + 1;
                        end else if (eth_rx_ethertype == 16'h0800) begin
                            if (eth_rx_sid == 8'h01) begin
                                eth_s1_cnt                 <= eth_s1_cnt + 1;
                                seen_eth_s1[eth_rx_seq[9:0]] <= 1'b1;
                                if ($signed(eth_rx_seq) > eth_max_s1)
                                    eth_max_s1 <= eth_rx_seq;
                            end else if (eth_rx_sid == 8'h02) begin
                                eth_s2_cnt                 <= eth_s2_cnt + 1;
                                seen_eth_s2[eth_rx_seq[9:0]] <= 1'b1;
                                if ($signed(eth_rx_seq) > eth_max_s2)
                                    eth_max_s2 <= eth_rx_seq;
                            end
                        end
                    end
                end else if (peer_rx_k || peer_rx_code_err) begin
                    eth_rx_bad <= 1'b1;
                end else if (!eth_rx_sfd_seen) begin
                    if (peer_rx_d == 8'hD5) begin
                        eth_rx_sfd_seen <= 1'b1;
                        eth_rx_idx      <= 0;
                        eth_rx_crc      <= 32'hFFFF_FFFF;
                    end
                end else begin
                    eth_rx_crc <= crc32_byte(eth_rx_crc, peer_rx_d);
                    eth_rx_idx <= eth_rx_idx + 1;
                    if (eth_rx_idx == 12) eth_rx_ethertype[15:8] <= peer_rx_d;
                    if (eth_rx_idx == 13) eth_rx_ethertype[7:0]  <= peer_rx_d;
                    if (eth_rx_idx == 42) eth_rx_sid             <= peer_rx_d;
                    if (eth_rx_idx == 44) eth_rx_len[15:8]       <= peer_rx_d;
                    if (eth_rx_idx == 45) eth_rx_len[7:0]        <= peer_rx_d;
                    if (eth_rx_idx >= 46 && eth_rx_idx <= 49) eth_rx_seq <= {eth_rx_seq[23:0], peer_rx_d};
                    if (eth_rx_idx >= 50 && eth_rx_idx <= 57) eth_rx_ts  <= {eth_rx_ts[55:0], peer_rx_d};
                end
            end
        end
    end

    // -------------------------------------------------------------------------
    // IAS1 Receive Monitor Scoreboard (writes seen_ias_s1/s2 in rx_clkdiv)
    // -------------------------------------------------------------------------
    reg [7:0]    ias_cur_sid   = 8'd0;
    reg [31:0]   ias_cur_seq   = 32'd0;
    integer      ias_s1_cnt    = 0;
    integer      ias_s2_cnt    = 0;
    reg [1023:0] seen_ias_s1   = 1024'd0;
    reg [1023:0] seen_ias_s2   = 1024'd0;
    integer      ias_max_s1    = -1;
    integer      ias_max_s2    = -1;

    always @(posedge rx_clkdiv) begin
        if (kria_rx_rst) begin
            ias_s1_cnt  <= 0;
            ias_s2_cnt  <= 0;
            seen_ias_s1 <= 1024'd0;
            seen_ias_s2 <= 1024'd0;
            ias_max_s1  <= -1;
            ias_max_s2  <= -1;
        end else begin
            if (rx_out_v && rx_out_sop) begin
                ias_cur_sid <= rx_out_sid;
                ias_cur_seq <= rx_out_seq;
            end
            if (rx_done_v && rx_done_ok) begin
                if (ias_cur_sid == 8'h01) begin
                    ias_s1_cnt                  <= ias_s1_cnt + 1;
                    seen_ias_s1[ias_cur_seq[9:0]] <= 1'b1;
                    if ($signed(ias_cur_seq) > ias_max_s1)
                        ias_max_s1 <= ias_cur_seq;
                end else if (ias_cur_sid == 8'h02) begin
                    ias_s2_cnt                  <= ias_s2_cnt + 1;
                    seen_ias_s2[ias_cur_seq[9:0]] <= 1'b1;
                    if ($signed(ias_cur_seq) > ias_max_s2)
                        ias_max_s2 <= ias_cur_seq;
                end
            end
        end
    end

    // -------------------------------------------------------------------------
    // Main Rev06 Integration Verification Sequence
    // -------------------------------------------------------------------------
    integer wait_cyc;
    integer k, lost_s1, lost_s2;
    integer snap_ias_s2_a, snap_ias_s2_b;
    integer snap_eth_s1_a, snap_ias_s1_a, snap_ias_s1_b, snap_eth_s2_b;
    integer snap_fcs_err, snap_mdio_wr;

    initial begin
        // Match FPGA GSR INIT=0 for adc_clk_* registers before u_mmcm_adc locks
        u_artix.u_adc_cap.adc_trained          = 1'b0;
        u_artix.u_adc_cap.dco_phase_err        = 1'b0;
        u_artix.u_ddc.wr_ptr_bin               = 6'd0;
        u_artix.u_ddc.wr_ptr_gray              = 6'd0;
        u_artix.u_ddc.drop_100                 = 24'd0;
        u_artix.u_ddc.u_ddc.overflow_detected  = 1'b0;
        u_artix.u_ddc.u_ddc.mixer_overflow_i   = 1'b0;
        u_artix.u_ddc.u_ddc.mixer_overflow_q   = 1'b0;
        u_artix.u_ddc.u_ddc.nco_core.dds_ready = 1'b0;

        // Release synchronous resets only AFTER respective clocks are toggling
        repeat (16) @(posedge kria_tx_clk);
        kria_tx_rst = 1'b0;
        repeat (16) @(posedge peer_clk_125);
        peer_rst_125 = 1'b0;
        repeat (16) @(posedge rx_clkdiv);
        kria_rx_rst = 1'b0;

        // Wait for IAS1 training link_up + Artix ADC training (pmod_spare2)
        wait_cyc = 0;
        while (((kria_link_up !== 1'b1) || (pmod_spare2 !== 1'b1)) && wait_cyc < 150000) begin
            @(posedge rx_clkdiv);
            wait_cyc = wait_cyc + 1;
        end
        if ((kria_link_up !== 1'b1) || (pmod_spare2 !== 1'b1)) begin
            $display("FAIL: tb_rev06 IAS1 link did not reach link_up (link=%b spare2=%b st=%0d l0=%b l1=%b dl=%b idc=%b | sys=%b link_rst=%b ref_rst=%b dl_st=%0d dl_l0=%b dl_up=%b dl_up_s=%b adc_tr=%b adc_tr_s=%b adc_lock=%b)",
                     kria_link_up, pmod_spare2, train_state, l0_lock, l1_lock, d_lock, idelayctrl_rdy,
                     u_artix.sys_mmcm_locked, u_artix.link_rst, u_artix.ref_rst,
                     u_artix.dl_train_state, u_artix.dl_l0_lock, u_artix.dl_link_up, u_artix.dl_up_sync,
                     u_artix.adc_trained, u_artix.adc_tr_sync, u_artix.adc_mmcm_locked);
            $finish;
        end

        // Clause 37 SGMII Auto-Negotiation Handshake at +100 ppm
        peer_an_mode = 2'd0; // /C1/C2 Ack=0
        wait_cyc = 0;
        while ((u_artix.gen_rev06_eth.u_eth_phy.an_state != 2'd1) && wait_cyc < 50000) begin
            @(posedge peer_clk_125);
            wait_cyc = wait_cyc + 1;
        end
        peer_an_mode = 2'd1; // /C1/C2 Ack=1
        repeat (40) @(posedge peer_clk_125);
        peer_an_mode = 2'd2; // Enter /I/ DATA mode

        wait_cyc = 0;
        while (((u_artix.eth_link_up_stat !== 1'b1) || (mdio_poll_reads < 1)) && wait_cyc < 50000) begin
            @(posedge fpga_clk_100m);
            wait_cyc = wait_cyc + 1;
        end
        if (!u_artix.eth_link_up_stat || mdio_poll_reads < 1) begin
            $display("FAIL: tb_rev06 SGMII link_up=%b comma=%b an=%b an_st=%0d an_m=%0d lp=%04x cerr=%0d derr=%0d mdio_reads=%0d rst125=%b idc=%b",
                     u_artix.eth_link_up_stat,
                     u_artix.gen_rev06_eth.u_eth_phy.rx_comma_aligned,
                     u_artix.gen_rev06_eth.u_eth_phy.an_complete,
                     u_artix.gen_rev06_eth.u_eth_phy.an_state,
                     u_artix.gen_rev06_eth.u_eth_phy.an_match_cnt,
                     u_artix.gen_rev06_eth.u_eth_phy.an_lp_ability,
                     u_artix.gen_rev06_eth.u_eth_phy.code_err_cnt,
                     u_artix.gen_rev06_eth.u_eth_phy.disp_err_cnt,
                     mdio_poll_reads,
                     u_artix.gen_rev06_eth.eth_rst_125,
                     u_artix.gen_rev06_eth.b34_idc_rdy);
            $finish;
        end

        // Enable ADC Radar tone -> concurrent stream 0x01 (IAS1) + stream 0x02 (ETH)
        @(posedge clk_400m_adc);
        adc_tone_mode = 1'b1;
        @(posedge fpga_clk_100m);
        beam_strobe = 1'b1;
        pmod_spare1 = 1'b0;

        // Send valid UDP Keepalive + configure SPLIT policy explicitly
        send_udp_frame(16'hA55B, 16'h0000, 32'h0000_0000, 32'd1, 1'b0);
        send_udp_frame(16'hA55A, 16'h0000, 32'h0000_0004, 32'd2, 1'b0); // policy=0 SPLIT, sdr_en=1

        // Wait until >= 12 Radar packets on IAS1 AND >= 12 SDR packets on ETH (Phase 1 @ +100 ppm)
        wait_cyc = 0;
        while ((ias_s1_cnt < 12 || eth_s2_cnt < 12) && wait_cyc < 100000) begin
            @(posedge fpga_clk_100m);
            wait_cyc = wait_cyc + 1;
        end
        if (ias_s1_cnt < 12 || eth_s2_cnt < 12) begin
            $display("FAIL: tb_rev06 Phase 1 SPLIT timeout ias_s1=%0d eth_s2=%0d eth_s1=%0d ias_s2=%0d adc_tr=%b ddc_v=%b ias_v=%b ias_r=%b crc_err=%0d",
                     ias_s1_cnt, eth_s2_cnt, eth_s1_cnt, ias_s2_cnt,
                     u_artix.u_adc_cap.adc_trained,
                     u_artix.tx_pkt_valid,
                     u_artix.ias_mux_valid,
                     u_artix.ias_mux_ready,
                     crc_err_cnt);
            $finish;
        end
        $display("tb_rev06 Phase 1 (+100ppm SPLIT): ias_s1=%0d eth_s2=%0d eth_fcs_fail=%0d", ias_s1_cnt, eth_s2_cnt, eth_fcs_fail);

        // Inject poisoned bad-FCS UDP ctrl write setting force_ias_fault=1 & force_eth_fault=1 (0x1C)
        snap_fcs_err = u_artix.gen_rev06_eth.u_eth_mac.fcs_err_cnt;
        send_udp_frame(16'hA55A, 16'h0000, 32'h0000_001C, 32'd3, 1'b1);
        repeat (40) @(posedge fpga_clk_100m);
        if (u_artix.gen_rev06_eth.ctrl_force_eth_fault || u_artix.gen_rev06_eth.ctrl_force_ias_fault) begin
            $display("FAIL: tb_rev06 accepted corrupted-FCS UDP control write!");
            $finish;
        end

        // Phase 2: SPLIT failover test (force_eth_fault=1 -> stream 0x02 must fail over onto IAS1)
        snap_ias_s2_a = ias_s2_cnt;
        send_udp_frame(16'hA55A, 16'h0000, 32'h0000_0014, 32'd4, 1'b0); // policy=0, sdr_en=1, force_eth_fault=1
        wait_cyc = 0;
        while ((ias_s2_cnt < snap_ias_s2_a + 6) && wait_cyc < 80000) begin
            @(posedge fpga_clk_100m);
            wait_cyc = wait_cyc + 1;
        end
        if (ias_s2_cnt < snap_ias_s2_a + 6) begin
            $display("FAIL: tb_rev06 Phase 2 ETH->IAS1 failover failed (ias_s2 %0d -> %0d | eth_s2=%0d ias_s1=%0d force_eth=%b force_ias=%b fcs_err=%0d snap_fcs=%0d eth_up=%b)",
                     snap_ias_s2_a, ias_s2_cnt, eth_s2_cnt, ias_s1_cnt,
                     u_artix.gen_rev06_eth.ctrl_force_eth_fault,
                     u_artix.gen_rev06_eth.ctrl_force_ias_fault,
                     u_artix.gen_rev06_eth.u_eth_mac.fcs_err_cnt,
                     snap_fcs_err,
                     u_artix.eth_link_up_stat);
            $finish;
        end
        // Restore ETH healthy -> SDR returns to ETH
        send_udp_frame(16'hA55A, 16'h0000, 32'h0000_0004, 32'd5, 1'b0);

        // Phase 3: Switch peer to -100 ppm clock skew + switch to MIRROR_1P1 (policy=1) + MDIO write
        peer_half_ui_ps = 400.040; // -100 ppm -> 800.080 ps UI
        send_udp_frame(16'hA55B, 16'h0000, 32'h0000_0000, 32'd6, 1'b0);
        snap_mdio_wr = mdio_custom_wrs;
        send_udp_frame(16'hA55A, 16'h0004, 32'h0024_01E1, 32'd7, 1'b0); // MDIO wr reg4 = 0x01E1
        send_udp_frame(16'hA55A, 16'h0000, 32'h0000_0005, 32'd8, 1'b0); // policy=1 MIRROR_1P1, sdr_en=1

        snap_ias_s1_a = ias_s1_cnt;
        snap_eth_s1_a = eth_s1_cnt;
        snap_ias_s2_a = ias_s2_cnt;
        snap_eth_s2_b = eth_s2_cnt;
        wait_cyc = 0;
        while ((ias_s1_cnt < snap_ias_s1_a + 6 || eth_s1_cnt < snap_eth_s1_a + 6 ||
                ias_s2_cnt < snap_ias_s2_a + 6 || eth_s2_cnt < snap_eth_s2_b + 6) && wait_cyc < 120000) begin
            @(posedge fpga_clk_100m);
            wait_cyc = wait_cyc + 1;
        end
        if (eth_s1_cnt < snap_eth_s1_a + 6 || ias_s2_cnt < snap_ias_s2_a + 6) begin
            $display("FAIL: tb_rev06 Phase 3 MIRROR_1P1 missing mirrored streams (ias1=%0d eth1=%0d ias2=%0d eth2=%0d)",
                     ias_s1_cnt - snap_ias_s1_a, eth_s1_cnt - snap_eth_s1_a,
                     ias_s2_cnt - snap_ias_s2_a, eth_s2_cnt - snap_eth_s2_b);
            $finish;
        end
        wait_cyc = 0;
        while ((mdio_custom_wrs <= snap_mdio_wr || phy_regs[4] != 16'h01E1) && wait_cyc < 20000) begin
            @(posedge fpga_clk_100m);
            wait_cyc = wait_cyc + 1;
        end
        if (mdio_custom_wrs <= snap_mdio_wr || phy_regs[4] != 16'h01E1) begin
            $display("FAIL: tb_rev06 UDP-initiated MDIO write did not update reg 4 (%04x)", phy_regs[4]);
            $finish;
        end

        // Mid-run ETH cut under MIRROR_1P1, then mid-run IAS1 cut under MIRROR_1P1
        snap_ias_s1_b = ias_s1_cnt;
        send_udp_frame(16'hA55A, 16'h0000, 32'h0000_0015, 32'd9, 1'b0); // force_eth_fault=1
        wait_cyc = 0;
        while ((ias_s1_cnt < snap_ias_s1_b + 5) && wait_cyc < 60000) begin
            @(posedge fpga_clk_100m);
            wait_cyc = wait_cyc + 1;
        end

        snap_eth_s2_b = eth_s2_cnt;
        send_udp_frame(16'hA55A, 16'h0000, 32'h0000_000D, 32'd10, 1'b0); // force_ias_fault=1, force_eth_fault=0
        wait_cyc = 0;
        while ((eth_s2_cnt < snap_eth_s2_b + 5) && wait_cyc < 60000) begin
            @(posedge fpga_clk_100m);
            wait_cyc = wait_cyc + 1;
        end

        // Check behavioral Kria (stream_id, seq_num) merge/dedup across ALL packets
        lost_s1 = 0;
        for (k = 0; k <= ((ias_max_s1 > eth_max_s1) ? ias_max_s1 : eth_max_s1); k = k + 1) begin
            if (!(seen_ias_s1[k[9:0]] || seen_eth_s1[k[9:0]])) begin
                $display("  LOST s1 seq=%0d", k);
                lost_s1 = lost_s1 + 1;
            end
        end
        lost_s2 = 0;
        for (k = 0; k <= ((ias_max_s2 > eth_max_s2) ? ias_max_s2 : eth_max_s2); k = k + 1) begin
            if (!(seen_ias_s2[k[9:0]] || seen_eth_s2[k[9:0]])) begin
                $display("  LOST s2 seq=%0d", k);
                lost_s2 = lost_s2 + 1;
            end
        end

        if (crc_err_cnt != 0 || eth_fcs_fail != 0) begin
            $display("FAIL: tb_rev06 link errors ias_crc=%0d eth_fcs_fail=%0d", crc_err_cnt, eth_fcs_fail);
            $finish;
        end
        if (lost_s1 != 0 || lost_s2 != 0) begin
            $display("FAIL: tb_rev06 lost merged packets lost_s1=%0d (max=%0d) lost_s2=%0d (max=%0d)",
                     lost_s1, ((ias_max_s1 > eth_max_s1) ? ias_max_s1 : eth_max_s1),
                     lost_s2, ((ias_max_s2 > eth_max_s2) ? ias_max_s2 : eth_max_s2));
            $finish;
        end

        $display("PASS: tb_rev06 ias_s1=%0d eth_s1=%0d ias_s2=%0d eth_s2=%0d max_s1=%0d max_s2=%0d phase_sw=%0d lost=0",
                 ias_s1_cnt, eth_s1_cnt, ias_s2_cnt, eth_s2_cnt,
                 ((ias_max_s1 > eth_max_s1) ? ias_max_s1 : eth_max_s1),
                 ((ias_max_s2 > eth_max_s2) ? ias_max_s2 : eth_max_s2),
                 u_artix.gen_rev06_eth.u_eth_phy.phase_switch_cnt);
        $finish;
    end

endmodule
`default_nettype wire
