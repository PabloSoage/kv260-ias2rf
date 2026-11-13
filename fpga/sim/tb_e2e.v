// SPDX-License-Identifier: BSD-2-Clause
// End-to-End Integration Testbench (Task 9):
//   AD9484 Behavioral Model (inverted DCO + skew + +/-80 ps eye edge)
//   -> artix_top (adc_capture -> AERIS DDC -> link_pcs_tx -> OSERDESE2)
//   -> 3-Stage PCB/Pkg/SOM Channel Delays (PINMAP.md)
//   -> Kria RX (IBUFDS -> IDELAYE3 -> ISERDESE3 +/-80 ps aperture -> link_rx_train_fsm -> link_pcs_rx)
//   -> link_axis (AXI-Stream Master RX w/ PRNG TREADY backpressure + AXI-Lite CSR)
//   + Kria->Artix Downlink (link_pcs_single_tx -> OSERDESE3 -> 3-stage ch -> artix_top DL RX)
//
// Mutations:
//   -Mutate wrong_dco_phase : drops AD9484 DCO polarity compensation -> training fails (FAIL)
//   -Mutate ignore_tready   : link_axis advances RX FIFO ignoring tready=0 -> AXI-S protocol/pkt check fails (FAIL)

`timescale 1ns/1ps

module tb_e2e;

    localparam real PI = 3.14159265358979323846;
    localparam integer FFT_N = 64;

    // -------------------------------------------------------------------------
    // Clocks:
    //   Artix 100 MHz oscillator (fpga_clk_p/n)
    //   AD9484 400 MSPS sample clock & 200 MHz DDR DCO (centered for eye scan)
    //   Kria 300 MHz IDELAYCTRL REFCLK & 500/125 MHz Downlink TX clock
    // -------------------------------------------------------------------------
    reg fpga_clk_100m = 1'b0;
    always #5.000 fpga_clk_100m = ~fpga_clk_100m;

    reg clk_400m_adc = 1'b0;
    always #1.250 clk_400m_adc = ~clk_400m_adc;

    reg dco_true = 1'b0;
    initial begin
        dco_true = 1'b0;
        #1.750;
        forever #2.500 dco_true = ~dco_true;
    end

    reg kria_ref_300m = 1'b0;
    always #1.666 kria_ref_300m = ~kria_ref_300m;

    reg kria_tx_ddr = 1'b0;
    always #1.000 kria_tx_ddr = ~kria_tx_ddr;

    reg [1:0] kria_tx_div = 2'b00;
    reg       kria_tx_clk = 1'b0;
    always @(posedge kria_tx_ddr) begin
        kria_tx_div <= kria_tx_div + 2'd1;
        if (kria_tx_div == 2'd1)      kria_tx_clk <= 1'b1;
        else if (kria_tx_div == 2'd3) kria_tx_clk <= 1'b0;
    end

    // -------------------------------------------------------------------------
    // AD9484 Stimulus: 0xAA/0x55 checkerboard until ADC+link up, then 121.5625 MHz IF
    // With DDC NCO=120 MHz, CIC 4x -> 100 MSPS, POST_DECIM=4 -> 25 MSPS:
    //   +1.5625 MHz baseband tone = -4/64 bins -> expected DFT bin k = 60
    // -------------------------------------------------------------------------
    reg         adc_tone_mode = 1'b0;
    integer     sample_idx    = 0;
    reg  [7:0]  adc_sample_raw = 8'hAA;
    reg         adc_or_raw     = 1'b0;

    always @(posedge clk_400m_adc) begin
        if (!adc_tone_mode) begin
            adc_sample_raw <= sample_idx[0] ? 8'h55 : 8'hAA;
            adc_or_raw     <= 1'b0;
        end else begin
            // 121.5625 MHz at 400 MSPS => 121.5625 / 400 = 0.30390625 cycles/sample
            adc_sample_raw <= $rtoi(128.0 + 110.0 * $cos(2.0 * PI * 0.30390625 * sample_idx) + 0.5);
            adc_or_raw     <= 1'b0;
        end
        sample_idx <= sample_idx + 1;
    end

    reg [31:0] adc_prng = 32'hCAFE_BABE;
    always @(posedge clk_400m_adc)
        adc_prng <= {adc_prng[30:0], adc_prng[31] ^ adc_prng[21] ^ adc_prng[1] ^ adc_prng[0]};

    reg dco_board_del = 1'b0;
    always @(dco_true) dco_board_del <= #0.250 dco_true;

    wire adcr_dco_n_pin = ~dco_board_del;
    wire adcr_dco_p_pin =  dco_board_del;

    reg [7:0] d_skew_early  = 8'd0;
    reg [7:0] d_skew_center = 8'd0;
    reg [7:0] d_skew_late   = 8'd0;
    reg       or_skew       = 1'b0;

    localparam real BIT_DEL_0 = 0.160;
    localparam real BIT_DEL_1 = 0.175;
    localparam real BIT_DEL_2 = 0.190;
    localparam real BIT_DEL_3 = 0.205;
    localparam real BIT_DEL_4 = 0.220;
    localparam real BIT_DEL_5 = 0.230;
    localparam real BIT_DEL_6 = 0.242;
    localparam real BIT_DEL_7 = 0.255;

    always @(adc_sample_raw[0]) begin d_skew_early[0] <= #(BIT_DEL_0 - 0.080) adc_sample_raw[0]; d_skew_center[0] <= #BIT_DEL_0 adc_sample_raw[0]; d_skew_late[0] <= #(BIT_DEL_0 + 0.080) adc_sample_raw[0]; end
    always @(adc_sample_raw[1]) begin d_skew_early[1] <= #(BIT_DEL_1 - 0.080) adc_sample_raw[1]; d_skew_center[1] <= #BIT_DEL_1 adc_sample_raw[1]; d_skew_late[1] <= #(BIT_DEL_1 + 0.080) adc_sample_raw[1]; end
    always @(adc_sample_raw[2]) begin d_skew_early[2] <= #(BIT_DEL_2 - 0.080) adc_sample_raw[2]; d_skew_center[2] <= #BIT_DEL_2 adc_sample_raw[2]; d_skew_late[2] <= #(BIT_DEL_2 + 0.080) adc_sample_raw[2]; end
    always @(adc_sample_raw[3]) begin d_skew_early[3] <= #(BIT_DEL_3 - 0.080) adc_sample_raw[3]; d_skew_center[3] <= #BIT_DEL_3 adc_sample_raw[3]; d_skew_late[3] <= #(BIT_DEL_3 + 0.080) adc_sample_raw[3]; end
    always @(adc_sample_raw[4]) begin d_skew_early[4] <= #(BIT_DEL_4 - 0.080) adc_sample_raw[4]; d_skew_center[4] <= #BIT_DEL_4 adc_sample_raw[4]; d_skew_late[4] <= #(BIT_DEL_4 + 0.080) adc_sample_raw[4]; end
    always @(adc_sample_raw[5]) begin d_skew_early[5] <= #(BIT_DEL_5 - 0.080) adc_sample_raw[5]; d_skew_center[5] <= #BIT_DEL_5 adc_sample_raw[5]; d_skew_late[5] <= #(BIT_DEL_5 + 0.080) adc_sample_raw[5]; end
    always @(adc_sample_raw[6]) begin d_skew_early[6] <= #(BIT_DEL_6 - 0.080) adc_sample_raw[6]; d_skew_center[6] <= #BIT_DEL_6 adc_sample_raw[6]; d_skew_late[6] <= #(BIT_DEL_6 + 0.080) adc_sample_raw[6]; end
    always @(adc_sample_raw[7]) begin d_skew_early[7] <= #(BIT_DEL_7 - 0.080) adc_sample_raw[7]; d_skew_center[7] <= #BIT_DEL_7 adc_sample_raw[7]; d_skew_late[7] <= #(BIT_DEL_7 + 0.080) adc_sample_raw[7]; end
    always @(adc_or_raw)        begin or_skew <= #0.210 adc_or_raw; end

    wire [7:0] d_eye_viol = d_skew_early ^ d_skew_late;
    wire [7:0] adcr_d_p   = (d_eye_viol & {8{adc_prng[0]}}) ? ~d_skew_center : d_skew_center;
    wire [7:0] adcr_d_n   = ~adcr_d_p;
    wire       adcr_or_p  = or_skew;
    wire       adcr_or_n  = ~or_skew;

    // -------------------------------------------------------------------------
    // artix_top DUT (ADC_AUTO_TRAIN=1, LINK_AM_PERIOD=64, DDC_POST_DECIM=4)
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
    wire       eth_mdc, eth_mdio, eth_rst_n;
    pullup(eth_mdio);

    artix_top #(
        .DDC_POST_DECIM (4),
        .LINK_AM_PERIOD (64),
        .ADC_AUTO_TRAIN (1'b1),
        .ENABLE_ETH     (1'b0)
    ) u_artix (
        .fpga_clk_p    (fpga_clk_100m),
        .fpga_clk_n    (~fpga_clk_100m),
        .adcr_d_p      (adcr_d_p),
        .adcr_d_n      (adcr_d_n),
        .adcr_or_p     (adcr_or_p),
        .adcr_or_n     (adcr_or_n),
        .adcr_dco_n    (adcr_dco_n_pin),
        .adcr_dco_p    (adcr_dco_p_pin),
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
        .eth_sgrx_p    (1'b1),
        .eth_sgrx_n    (1'b0),
        .eth_mdc       (eth_mdc),
        .eth_mdio      (eth_mdio),
        .eth_rst_n     (eth_rst_n)
    );

    // -------------------------------------------------------------------------
    // Uplink 3-Stage Channel (Artix -> Kria, PINMAP.md)
    // -------------------------------------------------------------------------
    wire #0.678 ul_adap_clk_p = ul_tx_clk_p;
    wire #0.677 ul_adap_clk_n = ul_tx_clk_n;
    wire #0.773 ul_adap_d0_p  = ul_tx_d0_p;
    wire #0.772 ul_adap_d0_n  = ul_tx_d0_n;
    wire #0.717 ul_adap_d1_p  = ul_tx_d1_p;
    wire #0.717 ul_adap_d1_n  = ul_tx_d1_n;

    wire #0.180 ul_car_clk_p  = ul_adap_clk_p;
    wire #0.180 ul_car_clk_n  = ul_adap_clk_n;
    wire #0.180 ul_car_d0_p   = ul_adap_d0_p;
    wire #0.180 ul_car_d0_n   = ul_adap_d0_n;
    wire #0.180 ul_car_d1_p   = ul_adap_d1_p;
    wire #0.180 ul_car_d1_n   = ul_adap_d1_n;

    wire #0.413 kria_rx_clk_p = ul_car_clk_p;
    wire #0.413 kria_rx_clk_n = ul_car_clk_n;
    wire #0.406 kria_rx_d0_p  = ul_car_d0_p;
    wire #0.406 kria_rx_d0_n  = ul_car_d0_n;
    wire #0.405 kria_rx_d1_p  = ul_car_d1_p;
    wire #0.405 kria_rx_d1_n  = ul_car_d1_n;

    // -------------------------------------------------------------------------
    // Kria K26 RX Primitives: IBUFDS -> IDELAYE3 -> ISERDESE3 -> FSM + PCS + link_axis
    // -------------------------------------------------------------------------
    reg kria_rx_rst = 1'b1;
    reg kria_tx_rst = 1'b1;

    wire rx_clk_ibuf, rx_d0_ibuf, rx_d1_ibuf;
    IBUFDS u_kria_ibuf_clk (.I(kria_rx_clk_p), .IB(kria_rx_clk_n), .O(rx_clk_ibuf));
    IBUFDS u_kria_ibuf_d0  (.I(kria_rx_d0_p),  .IB(kria_rx_d0_n),  .O(rx_d0_ibuf));
    IBUFDS u_kria_ibuf_d1  (.I(kria_rx_d1_p),  .IB(kria_rx_d1_n),  .O(rx_d1_ibuf));

    wire #0.527 rx_clk_bufg = rx_clk_ibuf;

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

    wire #0.081 rx_clk_check  = rx_clk_bufg;
    wire #0.082 rx_clk_sample = rx_clk_bufg;
    wire #0.080 rx_d0_pipe    = rx_d0_idelay;
    wire #0.080 rx_d1_pipe    = rx_d1_idelay;

    real last_d0_edge_ns = -100.0;
    real last_d1_edge_ns = -100.0;
    always @(rx_d0_idelay) last_d0_edge_ns = $realtime;
    always @(rx_d1_idelay) last_d1_edge_ns = $realtime;

    reg        d0_eye_viol = 1'b0;
    reg        d1_eye_viol = 1'b0;
    reg [15:0] kria_eye_prng = 16'hACE1;
    always @(posedge rx_clk_check or negedge rx_clk_check) begin
        d0_eye_viol   <= (($realtime - last_d0_edge_ns) <= 0.161);
        d1_eye_viol   <= (($realtime - last_d1_edge_ns) <= 0.161);
        kria_eye_prng <= {kria_eye_prng[14:0],
                          kria_eye_prng[15] ^ kria_eye_prng[13] ^ kria_eye_prng[12] ^ kria_eye_prng[10]};
    end

    wire rx_d0_to_is = (d0_eye_viol && kria_eye_prng[0]) ? ~rx_d0_pipe : rx_d0_pipe;
    wire rx_d1_to_is = (d1_eye_viol && kria_eye_prng[1]) ? ~rx_d1_pipe : rx_d1_pipe;

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
    wire signed [7:0] skew_blk;
    wire [15:0] rem_stat;
    wire [23:0] rem_drop;
    wire [31:0] sh_err0, sh_err1, pkt_rx_cnt, crc_err_cnt;
    wire        l0_blk_v, l0_blk_ok, l1_blk_v, l1_blk_ok;
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
        .eye_left_l0      (eye_l0),
        .eye_right_l0     (eye_r0),
        .eye_left_l1      (eye_l1),
        .eye_right_l1     (eye_r1)
    );

    link_pcs_rx #(
        .DISABLE_DESKEW (0)
    ) u_kria_pcs_rx (
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
        .skew_blocks        (skew_blk),
        .remote_status      (rem_stat),
        .remote_dropped_cnt (rem_drop),
        .sh_err_cnt_l0      (sh_err0),
        .sh_err_cnt_l1      (sh_err1),
        .pkt_rx_cnt         (pkt_rx_cnt),
        .crc_err_cnt        (crc_err_cnt),
        .l0_rx_blk_valid    (l0_blk_v),
        .l0_rx_blk_ok       (l0_blk_ok),
        .l1_rx_blk_valid    (l1_blk_v),
        .l1_rx_blk_ok       (l1_blk_ok)
    );

    wire [63:0] m_axis_tdata;
    wire        m_axis_tvalid;
    reg         m_axis_tready = 1'b1;
    wire        m_axis_tlast;
    wire [7:0]  m_axis_tid;
    wire [0:0]  m_axis_tuser;
    wire [31:0] last_rx_seq;
    wire [63:0] last_rx_ts;
    wire [15:0] last_rx_len;

    reg  [7:0]  s_axi_araddr  = 8'h04;
    reg         s_axi_arvalid = 1'b0;
    wire        s_axi_arready;
    wire [31:0] s_axi_rdata;
    wire [1:0]  s_axi_rresp;
    wire        s_axi_rvalid;

    link_axis #(
        .RX_FIFO_DEPTH (256),
        .TX_FIFO_DEPTH (64)
    ) u_kria_axis (
        .clk                  (rx_clkdiv),
        .rst                  (kria_rx_rst),
        .m_axis_rx_tdata      (m_axis_tdata),
        .m_axis_rx_tvalid     (m_axis_tvalid),
        .m_axis_rx_tready     (m_axis_tready),
        .m_axis_rx_tlast      (m_axis_tlast),
        .m_axis_rx_tid        (m_axis_tid),
        .m_axis_rx_tuser      (m_axis_tuser),
        .s_axis_tx_tdata      (64'd0),
        .s_axis_tx_tvalid     (1'b0),
        .s_axis_tx_tready     (),
        .s_axis_tx_tlast      (1'b0),
        .s_axis_tx_tid        (8'd0),
        .s_axis_tx_tuser      (16'd0),
        .s_axi_awaddr         (8'd0),
        .s_axi_awvalid        (1'b0),
        .s_axi_awready        (),
        .s_axi_wdata          (32'd0),
        .s_axi_wstrb          (4'd0),
        .s_axi_wvalid         (1'b0),
        .s_axi_wready         (),
        .s_axi_bresp          (),
        .s_axi_bvalid         (),
        .s_axi_bready         (1'b1),
        .s_axi_araddr         (s_axi_araddr),
        .s_axi_arvalid        (s_axi_arvalid),
        .s_axi_arready        (s_axi_arready),
        .s_axi_rdata          (s_axi_rdata),
        .s_axi_rresp          (s_axi_rresp),
        .s_axi_rvalid         (s_axi_rvalid),
        .s_axi_rready         (1'b1),
        .rx_out_valid         (rx_out_v),
        .rx_out_sop           (rx_out_sop),
        .rx_out_eop           (rx_out_eop),
        .rx_out_stream_id     (rx_out_sid),
        .rx_out_len           (rx_out_len),
        .rx_out_seq           (rx_out_seq),
        .rx_out_timestamp     (rx_out_ts),
        .rx_out_data          (rx_out_data),
        .rx_pkt_done_valid    (rx_done_v),
        .rx_pkt_done_ok       (rx_done_ok),
        .rx_pkt_done_err      (rx_done_err),
        .tx_pkt_valid         (),
        .tx_pkt_ready         (1'b0),
        .tx_pkt_sop           (),
        .tx_pkt_eop           (),
        .tx_pkt_stream_id     (),
        .tx_pkt_len           (),
        .tx_pkt_seq           (),
        .tx_pkt_timestamp     (),
        .tx_pkt_data          (),
        .timestamp_cnt        (64'd0),
        .ctrl_soft_rst        (),
        .ctrl_loopback_en     (),
        .ctrl_retrain_pulse   (),
        .ctrl_tap_override_en (),
        .ctrl_prbs7_tx_en     (),
        .ctrl_prbs7_rx_chk_en (),
        .cfg_tap_l0           (),
        .cfg_load_l0          (),
        .cfg_tap_l1           (),
        .cfg_load_l1          (),
        .st_train_state       (train_state),
        .st_l0_block_lock     (l0_lock),
        .st_l1_block_lock     (l1_lock),
        .st_deskew_lock       (d_lock),
        .st_link_up           (kria_link_up),
        .st_idelayctrl_rdy    (idelayctrl_rdy),
        .st_remote_status     (rem_stat[7:0]),
        .active_tap_l0        (cntval_l0),
        .active_tap_l1        (cntval_l1),
        .pcs_sh_err_cnt_l0    (sh_err0),
        .pcs_sh_err_cnt_l1    (sh_err1),
        .tx_dropped_cnt       (rem_drop),
        .skew_blocks          (skew_blk),
        .am_seq               (16'd0),
        .pcs_prbs_err_cnt     (32'd0),
        .eye_left_l0          (eye_l0),
        .eye_right_l0         (eye_r0),
        .eye_left_l1          (eye_l1),
        .eye_right_l1         (eye_r1),
        .last_rx_seq          (last_rx_seq),
        .last_rx_timestamp    (last_rx_ts),
        .last_rx_len          (last_rx_len)
    );

    // -------------------------------------------------------------------------
    // Kria->Artix Downlink TX + 3-Stage Channel (K26 -> Artix)
    // -------------------------------------------------------------------------
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

    wire #0.405 dl_som_clk_p = dl_pad_clk_p; wire #0.405 dl_som_clk_n = dl_pad_clk_n;
    wire #0.408 dl_som_d0_p  = dl_pad_d0_p;  wire #0.408 dl_som_d0_n  = dl_pad_d0_n;
    wire #0.180 dl_car_clk_p = dl_som_clk_p; wire #0.180 dl_car_clk_n = dl_som_clk_n;
    wire #0.180 dl_car_d0_p  = dl_som_d0_p;  wire #0.180 dl_car_d0_n  = dl_som_d0_n;
    assign #0.661 dl_rx_clk_p = dl_car_clk_p;
    assign #0.665 dl_rx_clk_n = dl_car_clk_n;
    assign #0.805 dl_rx_d0_p  = dl_car_d0_p;
    assign #0.810 dl_rx_d0_n  = dl_car_d0_n;

    // -------------------------------------------------------------------------
    // AXI-Stream RX Monitor + Pseudo-Random TREADY + Protocol / Seq / DFT Check
    // -------------------------------------------------------------------------
    reg         tready_bp_enable = 1'b0;
    reg  [15:0] bp_lfsr          = 16'hB400;
    reg         hold_prev_stall  = 1'b0;
    reg  [63:0] prev_tdata       = 64'd0;
    reg         prev_tlast       = 1'b0;
    integer     proto_err_cnt    = 0;

    integer     beat_in_pkt      = 0;
    integer     good_pkt_cnt     = 0;
    integer     crc_fail_cnt     = 0;
    integer     len_fail_cnt     = 0;
    integer     seq_fail_cnt     = 0;
    integer     ts_fail_cnt      = 0;
    reg  [31:0] prev_rx_seq      = 32'd0;
    reg         have_prev_seq    = 1'b0;
    reg  [63:0] ts_before_pps    = 64'd0;
    reg  [63:0] ts_after_pps     = 64'd0;

    reg         capture_active   = 1'b0;
    integer     cap_samples      = 0;
    real        bb_i_buf [0:FFT_N-1];
    real        bb_q_buf [0:FFT_N-1];
    reg         cap_done         = 1'b0;

    always @(posedge rx_clkdiv) begin
        if (kria_rx_rst) begin
            m_axis_tready   <= 1'b1;
            hold_prev_stall <= 1'b0;
            beat_in_pkt     <= 0;
            good_pkt_cnt    <= 0;
            crc_fail_cnt    <= 0;
            len_fail_cnt    <= 0;
            seq_fail_cnt    <= 0;
            ts_fail_cnt     <= 0;
            have_prev_seq   <= 1'b0;
            cap_samples     <= 0;
            cap_done        <= 1'b0;
        end else begin
            // Verify AXI4-Stream hold invariant across stalled beats
            if (hold_prev_stall) begin
                if (!m_axis_tvalid || (m_axis_tdata !== prev_tdata) || (m_axis_tlast !== prev_tlast))
                    proto_err_cnt <= proto_err_cnt + 1;
            end
            hold_prev_stall <= (m_axis_tvalid && !m_axis_tready);
            prev_tdata      <= m_axis_tdata;
            prev_tlast      <= m_axis_tlast;

            // Backpressure PRNG during tone/packet streaming
            bp_lfsr <= {bp_lfsr[14:0], bp_lfsr[15] ^ bp_lfsr[13] ^ bp_lfsr[12] ^ bp_lfsr[10]};
            if (tready_bp_enable)
                m_axis_tready <= (bp_lfsr[1:0] != 2'b00); // 25% stall probability
            else
                m_axis_tready <= 1'b1;

            if (m_axis_tvalid && m_axis_tready) begin
                if (m_axis_tid != 8'h01)
                    len_fail_cnt <= len_fail_cnt + 1;

                if (capture_active && !cap_done) begin
                    if (cap_samples + 1 < FFT_N) begin
                        bb_i_buf[cap_samples]     = $signed(m_axis_tdata[15:0]);
                        bb_q_buf[cap_samples]     = $signed(m_axis_tdata[31:16]);
                        bb_i_buf[cap_samples + 1] = $signed(m_axis_tdata[47:32]);
                        bb_q_buf[cap_samples + 1] = $signed(m_axis_tdata[63:48]);
                        cap_samples <= cap_samples + 2;
                        if (cap_samples + 2 == FFT_N)
                            cap_done <= 1'b1;
                    end
                end

                if (m_axis_tlast) begin
                    if (beat_in_pkt != 7)
                        len_fail_cnt <= len_fail_cnt + 1;
                    if (m_axis_tuser[0])
                        crc_fail_cnt <= crc_fail_cnt + 1;
                    good_pkt_cnt <= good_pkt_cnt + 1;
                    beat_in_pkt  <= 0;
                    ts_after_pps <= last_rx_ts;

                    if (have_prev_seq && (last_rx_seq != prev_rx_seq + 32'd1))
                        seq_fail_cnt <= seq_fail_cnt + 1;
                    prev_rx_seq   <= last_rx_seq;
                    have_prev_seq <= 1'b1;
                end else begin
                    beat_in_pkt <= beat_in_pkt + 1;
                end
            end
        end
    end

    // -------------------------------------------------------------------------
    // Main E2E Orchestration & 64-pt Complex DFT Verification
    // -------------------------------------------------------------------------
    integer wait_cyc, flush_pkts, k, n, peak_k;
    real    angle, re_sum, im_sum, pwr, p_peak, p_sig, p_img, p_dc, img_rej_db;
    reg [31:0] csr_link_status;

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

        repeat (16) @(posedge kria_tx_clk);
        kria_tx_rst = 1'b0;
        repeat (16) @(posedge rx_clkdiv);
        kria_rx_rst = 1'b0;

        // 1. Wait for both Kria uplink link_up and Artix downlink pmod_spare2
        wait_cyc = 0;
        while (((kria_link_up !== 1'b1) || (pmod_spare2 !== 1'b1)) && wait_cyc < 60000) begin
            @(posedge rx_clkdiv);
            wait_cyc = wait_cyc + 1;
        end
        if ((kria_link_up !== 1'b1) || (pmod_spare2 !== 1'b1)) begin
            $display("FAIL: tb_e2e bringup timeout (kria_link_up=%0d spare2=%0d train_st=%0d tap=%0d len0=%0d len1=%0d l0=%0d l1=%0d d_lock=%0d crc_err=%0d)",
                     kria_link_up, pmod_spare2, train_state, u_kria_train.scan_tap,
                     u_kria_train.best_len0, u_kria_train.best_len1, l0_lock, l1_lock, d_lock, crc_err_cnt);
            $finish;
        end

        // Wait for Artix ADC training confirmation in remote_status[5]
        wait_cyc = 0;
        while ((rem_stat[5] !== 1'b1) && wait_cyc < 4000) begin
            @(posedge rx_clkdiv);
            wait_cyc = wait_cyc + 1;
        end
        if (rem_stat[5] !== 1'b1) begin
            $display("FAIL: tb_e2e ADC training timeout (kria_link_up=%0d adc_tr=%0d spare2=%0d train_st=%0d crc_err=%0d)",
                     kria_link_up, rem_stat[5], pmod_spare2, train_state, crc_err_cnt);
            $finish;
        end
        $display("tb_e2e bringup: link_up=1 tap0=%0d tap1=%0d skew=%0d rem_stat=%04x spare2=%0d",
                 cntval_l0, cntval_l1, skew_blk, rem_stat, pmod_spare2);

        // Read AXI-Lite CSR 0x04 to verify CSR interface reports link_up
        @(posedge rx_clkdiv);
        s_axi_araddr  <= 8'h04;
        s_axi_arvalid <= 1'b1;
        @(posedge rx_clkdiv);
        while (!s_axi_arready) @(posedge rx_clkdiv);
        s_axi_arvalid <= 1'b0;
        while (!s_axi_rvalid) @(posedge rx_clkdiv);
        csr_link_status = s_axi_rdata;
        if (!csr_link_status[0]) begin
            $display("FAIL: tb_e2e CSR 0x04 link_up=0 (rdata=%08x)", csr_link_status);
            $finish;
        end

        // Enable 121.5625 MHz IF tone & DDC streaming, wait 2 pre-PPS packets, then pulse PPS
        @(posedge clk_400m_adc);
        adc_tone_mode = 1'b1;
        @(posedge fpga_clk_100m);
        beam_strobe   = 1'b1;
        pmod_spare1   = 1'b0;

        flush_pkts = good_pkt_cnt + 2;
        wait_cyc = 0;
        while ((good_pkt_cnt < flush_pkts) && wait_cyc < 10000) begin
            @(posedge rx_clkdiv);
            wait_cyc = wait_cyc + 1;
        end
        if (good_pkt_cnt < flush_pkts) begin
            $display("FAIL: tb_e2e timeout waiting for pre-PPS packets (good_pkt_cnt=%0d)", good_pkt_cnt);
            $finish;
        end
        ts_before_pps = last_rx_ts;

        repeat (4) @(posedge fpga_clk_100m);
        pps_sync = 1'b1;
        repeat (4) @(posedge fpga_clk_100m);
        pps_sync = 1'b0;

        // Enable AXI-Stream backpressure and flush 24 packets so CIC/FIR/checkerboard clear completely
        tready_bp_enable = 1'b1;
        flush_pkts = good_pkt_cnt + 24;
        wait_cyc = 0;
        while ((good_pkt_cnt < flush_pkts) && wait_cyc < 60000) begin
            @(posedge rx_clkdiv);
            wait_cyc = wait_cyc + 1;
        end
        if (good_pkt_cnt < flush_pkts) begin
            $display("FAIL: tb_e2e timeout flushing initial packets (good_pkt_cnt=%0d)", good_pkt_cnt);
            $finish;
        end

        // Capture 64 continuous baseband samples across AXI-Stream with TREADY backpressure
        capture_active = 1'b1;
        wait_cyc = 0;
        while (!cap_done && wait_cyc < 30000) begin
            @(posedge rx_clkdiv);
            wait_cyc = wait_cyc + 1;
        end
        if (!cap_done) begin
            $display("FAIL: tb_e2e timeout capturing %0d FFT samples (cap=%0d)", FFT_N, cap_samples);
            $finish;
        end

        // Wait 2 more packets to let last_rx_ts reflect post-capture packet too
        flush_pkts = good_pkt_cnt + 2;
        wait_cyc = 0;
        while ((good_pkt_cnt < flush_pkts) && wait_cyc < 10000) begin
            @(posedge rx_clkdiv);
            wait_cyc = wait_cyc + 1;
        end

        // Compute 64-pt complex DFT
        p_peak = -1.0;
        peak_k = -1;
        p_sig  = 0.0;
        p_img  = 0.0;
        p_dc   = 0.0;

        for (k = 0; k < FFT_N; k = k + 1) begin
            re_sum = 0.0;
            im_sum = 0.0;
            for (n = 0; n < FFT_N; n = n + 1) begin
                angle  = -2.0 * PI * k * n / FFT_N;
                re_sum = re_sum + (bb_i_buf[n] * $cos(angle) - bb_q_buf[n] * $sin(angle));
                im_sum = im_sum + (bb_i_buf[n] * $sin(angle) + bb_q_buf[n] * $cos(angle));
            end
            pwr = re_sum * re_sum + im_sum * im_sum;
            if (k == 0)  p_dc  = pwr;
            if (k == 60) p_sig = pwr;
            if (k == 4)  p_img = pwr;
            if (k != 0 && pwr > p_peak) begin
                p_peak = pwr;
                peak_k = k;
            end
        end

        img_rej_db = 10.0 * $log10((p_sig + 1.0) / (p_img + 1.0));
        $display("tb_e2e dft: peak_k=%0d (exp 60) p_sig=%e p_img=%e p_dc=%e img_rej=%.2f dB pkts=%0d ts0=%016x ts1=%016x",
                 peak_k, p_sig, p_img, p_dc, img_rej_db, good_pkt_cnt, ts_before_pps, ts_after_pps);

        if (proto_err_cnt != 0) begin
            $display("FAIL: tb_e2e AXI-Stream TREADY/TVALID hold violation count=%0d", proto_err_cnt);
            $finish;
        end
        if (crc_fail_cnt != 0 || crc_err_cnt != 0) begin
            $display("FAIL: tb_e2e CRC errors detected (axis=%0d pcs=%0d)", crc_fail_cnt, crc_err_cnt);
            $finish;
        end
        if (len_fail_cnt != 0 || seq_fail_cnt != 0) begin
            $display("FAIL: tb_e2e packet framing/sequence error (len=%0d seq=%0d)", len_fail_cnt, seq_fail_cnt);
            $finish;
        end
        if (ts_after_pps[63:48] == 16'd0 || ts_after_pps <= ts_before_pps) begin
            $display("FAIL: tb_e2e PPS timestamp did not increment/epoch (before=%016x after=%016x)",
                     ts_before_pps, ts_after_pps);
            $finish;
        end
        if (peak_k != 60) begin
            $display("FAIL: tb_e2e peak_k=%0d expected 60 (img_rej=%.2f dB)", peak_k, img_rej_db);
            $finish;
        end
        if (img_rej_db < 35.0) begin
            $display("FAIL: tb_e2e image rejection %.2f dB < 35.0 dB", img_rej_db);
            $finish;
        end
        if (p_sig < 1.0e8) begin
            $display("FAIL: tb_e2e signal power %e too low", p_sig);
            $finish;
        end

        $display("PASS: tb_e2e peak_k=60 img_rej_db=%.2f pkts=%0d crc_err=0 seq_err=0 proto_err=0 ts=%016x",
                 img_rej_db, good_pkt_cnt, ts_after_pps);
        $finish;
    end

endmodule
