// SPDX-License-Identifier: Apache-2.0
// Verification Testbench (CLK_FPGA 400/500 MHz switch):
//   - Power-on safe boot from unknown/wrong Si549 startup frequency (250 MHz) via CFGMCLK
//   - Silent Si549 FCAL gap (mem[17]==0 -> fpga_clk stops while I2C & DRP complete)
//   - Runtime 500 -> 400 -> 500 MHz mode switch (Si549 I2C + MMCM sys/eth DRP + IAS1 retrain)
//   - Non-MMCM dac_clk period measurement (125 MHz @ 500M mode, 100 MHz @ 400M mode)
//   - SGMII +/-50 ppm ADPLL_DELTA_M clamp (ENABLE_ETH=1)
//   - Switch-free HF channel defaults: AD9253 Ch B (0x05) enabled at reset, DAC2 (IF_TX_C) primary + DAC1 mute
//
// Mutation checked via run.ps1 -Mutate:
//   - no_delta_clamp : disables SGMII +/-50 ppm clamp -> overspec delta_M passes -> FAIL

`timescale 1ns/1ps

module tb_clk_mode_switch_i2c_slave #(
    parameter [6:0] SLAVE_ADDR = 7'h55
) (
    input  wire scl,
    inout  wire sda,
    input  wire enable_ack
);
    reg [7:0] mem [0:255];
    reg       sda_drv_low = 1'b0;
    assign sda = sda_drv_low ? 1'b0 : 1'bz;

    reg       prev_scl = 1'b1, prev_sda = 1'b1;
    reg [2:0] state = 3'd0;
    reg [3:0] bit_cnt = 4'd0;
    reg [7:0] shift_reg = 8'd0, reg_ptr = 8'd0;
    reg       have_reg_ptr = 1'b0, rw_bit = 1'b0, addr_match = 1'b0, ack_done = 1'b0;

    integer idx;
    initial begin
        for (idx = 0; idx < 256; idx = idx + 1)
            mem[idx] = 8'h00;
        // Unknown initial startup frequency (neither 400 nor 500 MHz), output initially on
        mem[17] = 8'h01;
        mem[23] = 8'h38; // HSDIV=56 (250 MHz bogus startup)
    end

    always @(scl or sda) begin
        if (scl === 1'b1 && prev_scl === 1'b1 && prev_sda === 1'b1 && sda === 1'b0) begin
            state <= 3'd1; bit_cnt <= 4'd0; ack_done <= 1'b0; sda_drv_low <= 1'b0;
        end else if (scl === 1'b1 && prev_scl === 1'b1 && prev_sda === 1'b0 && sda === 1'b1) begin
            state <= 3'd0; have_reg_ptr <= 1'b0; ack_done <= 1'b0; sda_drv_low <= 1'b0;
        end else if (scl === 1'b1 && prev_scl === 1'b0) begin
            if (state == 3'd1 || state == 3'd2 || state == 3'd3) begin
                if (bit_cnt < 4'd8) begin
                    shift_reg <= {shift_reg[6:0], (sda !== 1'b0)};
                    bit_cnt   <= bit_cnt + 4'd1;
                end else bit_cnt <= 4'd0;
            end else if (state == 3'd4) begin
                if (bit_cnt < 4'd8) bit_cnt <= bit_cnt + 4'd1;
                else begin
                    bit_cnt <= 4'd0;
                    if (sda === 1'b0) reg_ptr <= reg_ptr + 8'd1;
                    else              state   <= 3'd0;
                end
            end
        end else if (scl === 1'b0 && prev_scl === 1'b1) begin
            if (state == 3'd1 && bit_cnt == 4'd8) begin
                addr_match  = (shift_reg[7:1] == SLAVE_ADDR) && enable_ack;
                rw_bit      = shift_reg[0];
                ack_done   <= 1'b1;
                sda_drv_low <= addr_match ? 1'b1 : 1'b0;
            end else if ((state == 3'd1 || state == 3'd2 || state == 3'd3) && ack_done && (bit_cnt == 4'd0)) begin
                ack_done    <= 1'b0;
                sda_drv_low <= 1'b0;
                if (state == 3'd1) begin
                    if (!addr_match) state <= 3'd0;
                    else if (rw_bit) begin
                        state       <= 3'd4;
                        shift_reg   <= mem[reg_ptr];
                        sda_drv_low <= ~mem[reg_ptr][7];
                    end else state <= have_reg_ptr ? 3'd3 : 3'd2;
                end else if (state == 3'd2) begin
                    reg_ptr <= shift_reg; have_reg_ptr <= 1'b1; state <= 3'd3;
                end else if (state == 3'd3) begin
                    mem[reg_ptr] <= shift_reg; reg_ptr <= reg_ptr + 8'd1;
                end
            end else if ((state == 3'd2 || state == 3'd3) && bit_cnt == 4'd8) begin
                ack_done <= 1'b1; sda_drv_low <= 1'b1;
            end else if (state == 3'd4) begin
                if (bit_cnt == 4'd8) sda_drv_low <= 1'b0;
                else if (bit_cnt == 4'd0) begin
                    shift_reg <= mem[reg_ptr]; sda_drv_low <= ~mem[reg_ptr][7];
                end else sda_drv_low <= ~shift_reg[7 - bit_cnt[2:0]];
            end else sda_drv_low <= 1'b0;
        end
        prev_scl <= scl;
        prev_sda <= sda;
    end
endmodule

module tb_clk_mode_switch;

    // -------------------------------------------------------------------------
    // Behavioral Dynamic Si549 Clock Output (unknown 250 MHz startup -> silent during FCAL -> 400/500 MHz)
    // -------------------------------------------------------------------------
    reg fpga_clk_raw = 1'b0;
    real clk_half_ns = 2.000; // Initial unknown 250 MHz clock before safe boot

    wire xo_out_en;
    wire fpga_clk_p = xo_out_en ? fpga_clk_raw : 1'b0;
    wire fpga_clk_n = ~fpga_clk_p;

    initial forever #(clk_half_ns) fpga_clk_raw = ~fpga_clk_raw;

    reg adcs_dco_400m = 1'b0; always #1.250 adcs_dco_400m = ~adcs_dco_400m;
    reg clk_400m_adc  = 1'b0; always #1.250 clk_400m_adc  = ~clk_400m_adc;
    reg dco_true      = 1'b0;
    initial begin dco_true = 1'b0; #1.875; forever #2.500 dco_true = ~dco_true; end
    reg dco_board_del = 1'b0; always @(dco_true) dco_board_del <= #0.250 dco_true;
    reg [7:0] adcr_samp = 8'h55;
    always @(posedge clk_400m_adc) adcr_samp <= (adcr_samp == 8'hAA) ? 8'h55 : 8'hAA;
    reg [7:0] adcr_d_del = 8'h55;
    always @(adcr_samp) adcr_d_del <= #0.250 adcr_samp;

    reg kria_ref_300m = 1'b0; always #1.666 kria_ref_300m = ~kria_ref_300m;
    reg kria_tx_ddr   = 1'b0; always #1.000 kria_tx_ddr   = ~kria_tx_ddr;
    reg [1:0] kria_tx_div = 2'b00;
    reg       kria_tx_clk = 1'b0;
    always @(posedge kria_tx_ddr) begin
        kria_tx_div <= kria_tx_div + 2'd1;
        if (kria_tx_div == 2'd1)      kria_tx_clk <= 1'b1;
        else if (kria_tx_div == 2'd3) kria_tx_clk <= 1'b0;
    end

    // AD9253 dummy wordwise generator (distinct markers on Ch A vs Ch B)
    reg        adcs_dco_quad = 1'b0;
    always @(adcs_dco_400m) adcs_dco_quad <= #0.625 adcs_dco_400m;
    reg [3:0]  ui_idx = 4'd3;
    reg        fco_serial = 1'b0, d0_serial = 1'b0, d1_serial = 1'b0;
    localparam [15:0] FCO_W = 16'hFF00;
    localparam [15:0] WORD_CHA = {14'sd2000, 2'b00};
    localparam [15:0] WORD_CHB = {14'sd3500, 2'b00};
    always @(adcs_dco_400m) begin
        fco_serial <= FCO_W[15 - ui_idx];
        d0_serial  <= WORD_CHA[15 - ui_idx];
        d1_serial  <= WORD_CHB[15 - ui_idx];
        ui_idx     <= ui_idx + 4'd1;
    end

    // External Pins & Behavioral I2C Slaves
    wire       ul_tx_clk_p, ul_tx_clk_n, ul_tx_d0_p, ul_tx_d0_n, ul_tx_d1_p, ul_tx_d1_n;
    wire       dl_rx_clk_p, dl_rx_clk_n, dl_rx_d0_p, dl_rx_d0_n;
    wire       pmod_miso, pmod_spare2, fpga_irq;
    wire       dacr_clk;
    wire [7:0] dacr_d;
    wire [13:0] dacs_d;
    wire       dacs_iqclk, dacs_iqreset, dacs_iqsel, dacs_iqwrt;
    wire [3:0] sw_ctrl;
    tri1       xo_scl, xo_sda, hk_scl, hk_sda;
    wire       clk_sel;
    wire       conv_spi_csb_r, conv_spi_csb_s, conv_spi_sclk;
    tri1       conv_spi_sdio;
    wire       adar_sclk;
    tri1       adar_sdio;
    wire [7:0] adar_csb, adar_rx_load, adar_tx_load, adar_tr;
    wire       eth_sgtx_p, eth_sgtx_n, eth_mdc, eth_rst_n;
    tri1       eth_mdio;

    tb_clk_mode_switch_i2c_slave #(.SLAVE_ADDR(7'h55)) u_si549 (
        .scl(xo_scl), .sda(xo_sda), .enable_ack(1'b1)
    );
    assign xo_out_en = u_si549.mem[17][0];
    always @(u_si549.mem[23]) begin
        if (u_si549.mem[23] == 8'h1C)      clk_half_ns = 1.250; // 400.0 MHz
        else if (u_si549.mem[23] == 8'h16) clk_half_ns = 1.000; // 500.0 MHz
    end

    // Track silent gap & MMCM reset behavior during switches
    integer fcal_gap_seen = 0;
    always @(negedge xo_out_en) begin
        if (!u_artix.u_clk_mode_ctrl.mmcm_rst) begin
            $display("FAIL: tb_clk_mode_switch Si549 output disabled while mmcm_rst==0");
            $finish;
        end
        fcal_gap_seen = fcal_gap_seen + 1;
    end

    // Monitor non-MMCM dac_clk period directly
    real dac_clk_t_prev = 0.0, dac_clk_per_ns = 0.0;
    always @(posedge u_artix.dac_clk) begin
        if (dac_clk_t_prev > 0.0)
            dac_clk_per_ns = $realtime - dac_clk_t_prev;
        dac_clk_t_prev = $realtime;
    end

    // -------------------------------------------------------------------------
    // DUT: artix_top with ENABLE_ETH=1, BOOT_FREQ_500M=1
    // -------------------------------------------------------------------------
    artix_top #(
        .DDC_POST_DECIM      (4),
        .LINK_AM_PERIOD      (64),
        .ADC_AUTO_TRAIN      (1'b1),
        .ENABLE_ETH          (1'b1),
        .ETH_BYPASS_AN       (1'b1),
        .ETH_ALIVE_TIMEOUT   (12500000),
        .ETH_MDIO_RST_CYC    (20),
        .ETH_MDIO_POLL_DIV   (100000),
        .CONV_SPI_AUTO_INIT  (1'b0),
        .ADAR_AUTO_INIT      (1'b0),
        .HK_CLK_DIV          (3),
        .HK_POLL_DIV         (500000),
        .XO_FCAL_WAIT_CYC    (80),
        .BOOT_FREQ_500M      (1'b1),
        .XADC_POLL_DIV_P     (10000),
        .PPS_DEFAULT_NOM_CYC (32'd1250)
    ) u_artix (
        .fpga_clk_p    (fpga_clk_p),
        .fpga_clk_n    (fpga_clk_n),
        .adcr_d_p      (adcr_d_del),
        .adcr_d_n      (~adcr_d_del),
        .adcr_or_p     (1'b0),
        .adcr_or_n     (1'b1),
        .adcr_dco_n    (~dco_board_del),
        .adcr_dco_p    (dco_board_del),
        .adcs_dco_p    (adcs_dco_quad),
        .adcs_dco_n    (~adcs_dco_quad),
        .adcs_fco_p    (fco_serial),
        .adcs_fco_n    (~fco_serial),
        .adcs_d0_p     (d0_serial),
        .adcs_d0_n     (~d0_serial),
        .adcs_d1_p     (d1_serial),
        .adcs_d1_n     (~d1_serial),
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
        .beam_strobe   (1'b0),
        .pps_sync      (1'b0),
        .pmod_spare1   (1'b1),
        .pmod_spare2   (pmod_spare2),
        .dacr_clk      (dacr_clk),
        .dacr_d        (dacr_d),
        .dacs_d        (dacs_d),
        .dacs_iqclk    (dacs_iqclk),
        .dacs_iqreset  (dacs_iqreset),
        .dacs_iqsel    (dacs_iqsel),
        .dacs_iqwrt    (dacs_iqwrt),
        .sw_ctrl       (sw_ctrl),
        .xo_scl        (xo_scl),
        .xo_sda        (xo_sda),
        .clk_sel       (clk_sel),
        .hk_scl        (hk_scl),
        .hk_sda        (hk_sda),
        .hk_alert_n    (1'b1),
        .fpga_irq      (fpga_irq),
        .conv_spi_csb_r(conv_spi_csb_r),
        .conv_spi_csb_s(conv_spi_csb_s),
        .conv_spi_sclk (conv_spi_sclk),
        .conv_spi_sdio (conv_spi_sdio),
        .adar_sclk     (adar_sclk),
        .adar_sdio     (adar_sdio),
        .adar_sdo      (1'b0),
        .adar_csb      (adar_csb),
        .adar_rx_load  (adar_rx_load),
        .adar_tx_load  (adar_tx_load),
        .adar_tr       (adar_tr),
        .eth_sgtx_p    (eth_sgtx_p),
        .eth_sgtx_n    (eth_sgtx_n),
        .eth_sgrx_p    (1'b1),
        .eth_sgrx_n    (1'b0),
        .eth_mdc       (eth_mdc),
        .eth_mdio      (eth_mdio),
        .eth_rst_n     (eth_rst_n)
    );

    // -------------------------------------------------------------------------
    // Kria-side IAS1 Uplink RX & Downlink TX (with realistic PCB/Pkg delays)
    // -------------------------------------------------------------------------
    wire #0.678 ul_adap_clk_p = ul_tx_clk_p, ul_adap_clk_n = ul_tx_clk_n;
    wire #0.773 ul_adap_d0_p  = ul_tx_d0_p,  ul_adap_d0_n  = ul_tx_d0_n;
    wire #0.717 ul_adap_d1_p  = ul_tx_d1_p,  ul_adap_d1_n  = ul_tx_d1_n;

    reg kria_rx_rst = 1'b1, kria_tx_rst = 1'b1;
    wire rx_clk_ibuf, rx_d0_ibuf, rx_d1_ibuf;
    IBUFDS u_kib_clk (.I(ul_adap_clk_p), .IB(ul_adap_clk_n), .O(rx_clk_ibuf));
    IBUFDS u_kib_d0  (.I(ul_adap_d0_p),  .IB(ul_adap_d0_n),  .O(rx_d0_ibuf));
    IBUFDS u_kib_d1  (.I(ul_adap_d1_p),  .IB(ul_adap_d1_n),  .O(rx_d1_ibuf));

    wire #0.527 rx_clk_bufg = rx_clk_ibuf;
    reg [1:0] rx_div_c = 2'b00;
    reg       rx_clkdiv = 1'b0;
    always @(posedge rx_clk_bufg) begin
        rx_div_c <= rx_div_c + 2'd1;
        if (rx_div_c == 2'd1) rx_clkdiv <= 1'b1;
        else if (rx_div_c == 2'd3) rx_clkdiv <= 1'b0;
    end

    wire idelayctrl_rdy;
    IDELAYCTRL #(.SIM_DEVICE("ULTRASCALE")) u_kidc (.RDY(idelayctrl_rdy), .REFCLK(kria_ref_300m), .RST(kria_rx_rst));
    wire en_vtc, load_l0, load_l1; wire [8:0] cntval_l0, cntval_l1;
    wire rx_d0_idly, rx_d1_idly;
    IDELAYE3 #(.DELAY_FORMAT("TIME"),.DELAY_SRC("IDATAIN"),.DELAY_TYPE("VAR_LOAD"),.REFCLK_FREQUENCY(300.0),.SIM_DEVICE("ULTRASCALE_PLUS"),.SIM_VERSION(2.0),.UPDATE_MODE("ASYNC"))
        u_kid_d0 (.CASC_OUT(),.CNTVALUEOUT(),.DATAOUT(rx_d0_idly),.CASC_IN(1'b0),.CASC_RETURN(1'b0),.CE(1'b0),.CLK(rx_clkdiv),.CNTVALUEIN(cntval_l0),.DATAIN(1'b0),.EN_VTC(en_vtc),.IDATAIN(rx_d0_ibuf),.INC(1'b0),.LOAD(load_l0),.RST(kria_rx_rst));
    IDELAYE3 #(.DELAY_FORMAT("TIME"),.DELAY_SRC("IDATAIN"),.DELAY_TYPE("VAR_LOAD"),.REFCLK_FREQUENCY(300.0),.SIM_DEVICE("ULTRASCALE_PLUS"),.SIM_VERSION(2.0),.UPDATE_MODE("ASYNC"))
        u_kid_d1 (.CASC_OUT(),.CNTVALUEOUT(),.DATAOUT(rx_d1_idly),.CASC_IN(1'b0),.CASC_RETURN(1'b0),.CE(1'b0),.CLK(rx_clkdiv),.CNTVALUEIN(cntval_l1),.DATAIN(1'b0),.EN_VTC(en_vtc),.IDATAIN(rx_d1_ibuf),.INC(1'b0),.LOAD(load_l1),.RST(kria_rx_rst));

    wire [7:0] rx_byte_l0, rx_byte_l1;
    ISERDESE3 #(.DATA_WIDTH(8),.DDR_CLK_EDGE("OPPOSITE_EDGE"),.FIFO_ENABLE("FALSE"),.SIM_DEVICE("ULTRASCALE_PLUS"),.SIM_VERSION(2.0))
        u_kis_d0 (.FIFO_EMPTY(),.INTERNAL_DIVCLK(),.Q(rx_byte_l0),.CLK(rx_clk_bufg),.CLKDIV(rx_clkdiv),.CLK_B(~rx_clk_bufg),.D(rx_d0_idly),.FIFO_RD_CLK(1'b0),.FIFO_RD_EN(1'b0),.RST(kria_rx_rst));
    ISERDESE3 #(.DATA_WIDTH(8),.DDR_CLK_EDGE("OPPOSITE_EDGE"),.FIFO_ENABLE("FALSE"),.SIM_DEVICE("ULTRASCALE_PLUS"),.SIM_VERSION(2.0))
        u_kis_d1 (.FIFO_EMPTY(),.INTERNAL_DIVCLK(),.Q(rx_byte_l1),.CLK(rx_clk_bufg),.CLKDIV(rx_clkdiv),.CLK_B(~rx_clk_bufg),.D(rx_d1_idly),.FIFO_RD_CLK(1'b0),.FIFO_RD_EN(1'b0),.RST(kria_rx_rst));

    wire rx_out_v, rx_out_sop, rx_out_eop, rx_done_v, rx_done_ok;
    wire [7:0]  rx_out_sid;
    wire [63:0] rx_out_data;
    wire l0_lock, l1_lock, deskew_lock, ul_link_up, l0_bv, l0_bo, l1_bv, l1_bo;
    wire [31:0] ul_crc_err;

    link_rx_train_fsm #(.SINGLE_LANE(0),.MAX_TAP(511),.TAP_STEP(8),.TAP_DWELL_CYCLES(16'd256),.MIN_EYE_STEPS(9'd18))
        u_ktr (.clk(rx_clkdiv),.rst(kria_rx_rst),.retrain(1'b0),.cfg_tap_override(1'b0),.cfg_tap_l0(9'd0),.cfg_tap_l1(9'd0),.rx_byte_l0(rx_byte_l0),.rx_byte_l1(rx_byte_l1),.l0_block_lock(l0_lock),.l1_block_lock(l1_lock),.deskew_lock(deskew_lock),.l0_rx_blk_valid(l0_bv),.l0_rx_blk_ok(l0_bo),.l1_rx_blk_valid(l1_bv),.l1_rx_blk_ok(l1_bo),.en_vtc(en_vtc),.load_l0(load_l0),.cntval_l0(cntval_l0),.load_l1(load_l1),.cntval_l1(cntval_l1),.train_state(),.link_up(ul_link_up),.eye_left_l0(),.eye_right_l0(),.eye_left_l1(),.eye_right_l1());

    link_pcs_rx #(.SKIP_CRC(0)) u_kul_rx (
        .clk(rx_clkdiv),.rst(kria_rx_rst),.link_ready(ul_link_up),
        .rx_byte_l0(rx_byte_l0),.rx_byte_l1(rx_byte_l1),
        .out_valid(rx_out_v),.out_sop(rx_out_sop),.out_eop(rx_out_eop),
        .out_stream_id(rx_out_sid),.out_len(),.out_seq(),.out_timestamp(),.out_data(rx_out_data),
        .pkt_done_valid(rx_done_v),.pkt_done_ok(rx_done_ok),.pkt_done_err(),
        .l0_block_lock(l0_lock),.l1_block_lock(l1_lock),.deskew_lock(deskew_lock),
        .skew_blocks(),.remote_status(),.remote_dropped_cnt(),
        .sh_err_cnt_l0(),.sh_err_cnt_l1(),.pkt_rx_cnt(),.crc_err_cnt(ul_crc_err),
        .l0_rx_blk_valid(l0_bv),.l0_rx_blk_ok(l0_bo),.l1_rx_blk_valid(l1_bv),.l1_rx_blk_ok(l1_bo)
    );

    reg        dl_tx_valid = 1'b0, dl_tx_sop = 1'b0, dl_tx_eop = 1'b0;
    wire       dl_tx_ready;
    reg [7:0]  dl_tx_sid   = 8'h10;
    reg [15:0] dl_tx_len   = 16'd8;
    reg [31:0] dl_tx_seq   = 32'd0;
    reg [63:0] dl_tx_data  = 64'd0;
    wire [7:0] dl_tx_byte;

    link_pcs_single_tx u_kdl_tx (
        .clk(kria_tx_clk),.rst(kria_tx_rst),.pkt_valid(dl_tx_valid),.pkt_ready(dl_tx_ready),
        .pkt_sop(dl_tx_sop),.pkt_eop(dl_tx_eop),.pkt_stream_id(dl_tx_sid),.pkt_len(dl_tx_len),
        .pkt_seq(dl_tx_seq),.pkt_timestamp(64'd0),.pkt_data(dl_tx_data),.dropped_cnt(24'd0),
        .local_status({15'd0, ul_link_up}),.tx_byte_l0(dl_tx_byte)
    );
    wire ser_dl_clk, ser_dl_d0;
    OSERDESE3 #(.DATA_WIDTH(8),.SIM_DEVICE("ULTRASCALE_PLUS"),.SIM_VERSION(2.0)) u_kos_clk (.OQ(ser_dl_clk),.CLK(kria_tx_ddr),.CLKDIV(kria_tx_clk),.D(8'hAA),.RST(kria_tx_rst),.T(1'b0));
    OSERDESE3 #(.DATA_WIDTH(8),.SIM_DEVICE("ULTRASCALE_PLUS"),.SIM_VERSION(2.0)) u_kos_d0  (.OQ(ser_dl_d0), .CLK(kria_tx_ddr),.CLKDIV(kria_tx_clk),.D(dl_tx_byte),.RST(kria_tx_rst),.T(1'b0));
    assign dl_rx_clk_p = ser_dl_clk; assign dl_rx_clk_n = ~ser_dl_clk;
    assign dl_rx_d0_p  = ser_dl_d0;  assign dl_rx_d0_n  = ~ser_dl_d0;

    integer cnt_04 = 0, cnt_05 = 0;
    reg [7:0]  active_pkt_sid = 8'd0;
    reg        resp_valid_flag = 1'b0;
    reg [15:0] resp_addr_cap   = 16'd0;
    reg [31:0] resp_data_cap   = 32'd0;
    always @(posedge rx_clkdiv) if (!kria_rx_rst) begin
        if (rx_out_v) begin
            if (rx_out_sop) active_pkt_sid <= rx_out_sid;
            if (rx_out_sid == 8'h11 && rx_out_data[63:48] == 16'h0002) begin
                resp_valid_flag <= 1'b1;
                resp_addr_cap   <= rx_out_data[47:32];
                resp_data_cap   <= rx_out_data[31:0];
            end
        end
        if (rx_done_v && rx_done_ok) begin
            if (active_pkt_sid == 8'h04)      cnt_04 <= cnt_04 + 1;
            else if (active_pkt_sid == 8'h05) cnt_05 <= cnt_05 + 1;
        end
    end

    // Monitor AD9767 DAC1 (IQSEL=1) and DAC2 (IQSEL=0) latched words
    reg [13:0] dac1_last_u  = 14'h2000, dac2_last_u  = 14'h2000;
    reg [13:0] dac1_last_nz = 14'h2000, dac2_last_nz = 14'h2000;
    integer    dac1_wrts = 0, dac2_wrts = 0;
    always @(posedge dacs_iqwrt) begin
        if (dacs_iqsel) begin
            dac1_last_u <= dacs_d;
            dac1_wrts   <= dac1_wrts + 1;
            if (dacs_d != 14'h2000) dac1_last_nz <= dacs_d;
        end else begin
            dac2_last_u <= dacs_d;
            dac2_wrts   <= dac2_wrts + 1;
            if (dacs_d != 14'h2000) dac2_last_nz <= dacs_d;
        end
    end

    task automatic dl_send_word(input [7:0] sid, input [15:0] len_b, input [63:0] w);
        begin
            @(posedge kria_tx_clk);
            dl_tx_valid <= 1'b1; dl_tx_sop <= 1'b1; dl_tx_eop <= 1'b1;
            dl_tx_sid   <= sid;  dl_tx_len <= len_b; dl_tx_data <= w;
            @(posedge kria_tx_clk);
            while (!dl_tx_ready) @(posedge kria_tx_clk);
            dl_tx_valid <= 1'b0; dl_tx_sop <= 1'b0; dl_tx_eop <= 1'b0;
            dl_tx_seq   <= dl_tx_seq + 32'd1;
        end
    endtask

    task automatic wr_reg(input [15:0] addr, input [31:0] data);
        begin
            dl_send_word(8'h10, 16'd8, {8'h01, 8'h00, addr, data});
            repeat (12) @(posedge kria_tx_clk);
        end
    endtask

    integer rd_max_tmo = 0;   // longest read-back, rx_clkdiv cycles (reported in the PASS line)
    task automatic rd_reg(input [15:0] addr, output [31:0] data_o);
        integer tmo;
        begin
            @(posedge rx_clkdiv); resp_valid_flag <= 1'b0;
            dl_send_word(8'h10, 16'd8, {8'h02, 8'h00, addr, 32'd0});
            tmo = 0;
            // 1,250 rx_clkdiv cycles (10 us at 125 MHz). While the uplink retrains after a 500 <-> 400 MHz switch,
            // dual_path_mux drops the bulk packets meant for IAS1 (ias_drain) instead of queueing them in its
            // 1024-word FIFO, so the first read-back does not wait behind a backlog (about 40 us before; 3.7 us now,
            // reported as rd_max in the PASS line).
            while ((!resp_valid_flag || (resp_addr_cap != addr)) && tmo < 1250) begin
                @(posedge rx_clkdiv);
                tmo = tmo + 1;
            end
            if (!resp_valid_flag || (resp_addr_cap != addr)) begin
                $display("FAIL: tb_clk_mode_switch rd_reg timeout on 0x%04h", addr);
                $finish;
            end
            if (tmo > rd_max_tmo) rd_max_tmo = tmo;
            data_o = resp_data_cap;
        end
    endtask

    task automatic wait_ias_retrain;
        integer tmo;
        begin
            kria_rx_rst <= 1'b1;
            tmo = 0;
            while ((u_artix.u_clk_mode_ctrl.mmcm_rst || !u_artix.sys_mmcm_locked ||
                    !u_artix.eth_mmcm_locked_w || u_artix.sys_rst) && tmo < 40000) begin
                #50;
                tmo = tmo + 1;
            end
            if (!u_artix.sys_mmcm_locked || !u_artix.eth_mmcm_locked_w || u_artix.sys_rst) begin
                $display("FAIL: tb_clk_mode_switch MMCM relock timeout mmcm_rst=%b sys_lk=%b eth_lk=%b sys_rst=%b",
                         u_artix.u_clk_mode_ctrl.mmcm_rst, u_artix.sys_mmcm_locked,
                         u_artix.eth_mmcm_locked_w, u_artix.sys_rst);
                $finish;
            end
            repeat (32) @(posedge rx_clkdiv);
            kria_rx_rst <= 1'b0;
            tmo = 0;
            while ((!ul_link_up || !deskew_lock || !u_artix.dl_link_up) && tmo < 40000) begin
                #50;
                tmo = tmo + 1;
            end
            if (!ul_link_up || !u_artix.dl_link_up) begin
                $display("FAIL: tb_clk_mode_switch wait_ias_retrain timeout mmcm_rst=%b sys_lk=%b eth_lk=%b ul=%b dl=%b",
                         u_artix.u_clk_mode_ctrl.mmcm_rst, u_artix.sys_mmcm_locked, u_artix.eth_mmcm_locked_w,
                         ul_link_up, u_artix.dl_link_up);
                $finish;
            end
        end
    endtask

    reg [31:0] rval;
    reg [23:0] si_delta_rd;
    integer    wait_c;
    real       dac_per_500_boot, dac_per_400, dac_per_500_back;

    initial begin
        // Verify mmcm_rst stays asserted at startup while Si549 is reprogrammed from wrong 250 MHz
        #300;
        if (u_artix.u_clk_mode_ctrl.mmcm_rst !== 1'b1) begin
            $display("FAIL: tb_clk_mode_switch mmcm_rst not held at boot (got %b)", u_artix.u_clk_mode_ctrl.mmcm_rst);
            $finish;
        end

        @(posedge kria_tx_clk);
        kria_rx_rst <= 1'b0;
        kria_tx_rst <= 1'b0;

        wait_ias_retrain();

        // Check Test 1: Safe boot to 500 MHz
        if (u_si549.mem[23] !== 8'h16 || u_si549.mem[17] !== 8'h01) begin
            $display("FAIL: tb_clk_mode_switch boot Si549 mem[23]=%02x mem[17]=%02x", u_si549.mem[23], u_si549.mem[17]);
            $finish;
        end
        if (fcal_gap_seen < 1) begin
            $display("FAIL: tb_clk_mode_switch expected Si549 silent FCAL gap during boot");
            $finish;
        end
        rd_reg(16'h00A8, rval);
        if (!rval[14] || rval[12] || !rval[10] || !rval[9]) begin
            $display("FAIL: tb_clk_mode_switch boot 0xA8=0x%08h (exp boot_done=1 boot_err=0 active_500m=1 prog_done=1)", rval);
            $finish;
        end
        repeat (8) @(posedge u_artix.dac_clk);
        dac_per_500_boot = dac_clk_per_ns;
        if (dac_per_500_boot < 7.9 || dac_per_500_boot > 8.1) begin
            $display("FAIL: tb_clk_mode_switch boot dac_clk period=%0.3f ns (exp 8.000 ns)", dac_per_500_boot);
            $finish;
        end

        // Check Test 2: HF switch-free defaults (AD9253 Ch B 0x05 + DAC2 IF_TX_C primary)
        rd_reg(16'h0034, rval);
        if (rval !== 32'h0000_0009) begin
            $display("FAIL: tb_clk_mode_switch ADCS_CTRL reset default=0x%08h (exp 0x0000_0009 Ch B)", rval);
            $finish;
        end
        cnt_04 = 0; cnt_05 = 0;
        #20000;
        if (cnt_05 < 1 || cnt_04 != 0) begin
            $display("FAIL: tb_clk_mode_switch HF RX default expected Ch B 0x05 only: c04=%0d c05=%0d", cnt_04, cnt_05);
            $finish;
        end

        // Push IQ sample pair {Q=-4096, I=+8192} -> [31:18]=-1024 (0x1C00), [15:2]=+2048 (0x2800)
        // With hf_dac2_mode=1 default (DACS_CTRL=1), DAC2 (IQSEL=0) must output +2048 (0x2800) and DAC1 (IQSEL=1) -1024 (0x1C00)
        dac1_last_nz = 14'h2000;
        dac2_last_nz = 14'h2000;
        repeat (8) dl_send_word(8'h12, 16'd8, {-16'sd4096, 16'sd8192, -16'sd4096, 16'sd8192});
        #500;
        wr_reg(16'h0070, 32'h0000_0001);
        #1500;
        if (dac2_last_nz !== 14'h2800 || dac1_last_nz !== 14'h1C00) begin
            $display("FAIL: tb_clk_mode_switch HF DAC2 primary mismatch dac2=0x%04h(exp 2800) dac1=0x%04h(exp 1C00)",
                     dac2_last_nz, dac1_last_nz);
            $finish;
        end
        wr_reg(16'h0070, 32'h0000_0000);
        #500;

        // Mute DAC1 (DACS_CTRL=0x5): DAC1 parked at midscale 0x2000, DAC2 keeps driving I
        dac1_last_nz = 14'h2000;
        dac2_last_nz = 14'h2000;
        repeat (8) dl_send_word(8'h12, 16'd8, {-16'sd4096, 16'sd8192, -16'sd4096, 16'sd8192});
        #500;
        wr_reg(16'h0070, 32'h0000_0005);
        #1500;
        if (dac2_last_nz !== 14'h2800 || dac1_last_nz !== 14'h2000) begin
            $display("FAIL: tb_clk_mode_switch HF DAC1 mute mismatch dac2=0x%04h(exp 2800) dac1=0x%04h(exp 2000)",
                     dac2_last_nz, dac1_last_nz);
            $finish;
        end
        wr_reg(16'h0070, 32'h0000_0000);

        // Check Test 3: SGMII +/-50 ppm ADPLL_DELTA_M clamp (ENABLE_ETH=1)
        wr_reg(16'h00AC, 32'd900_000);       // +104.8 ppm -> must clamp to +429553
        wr_reg(16'h00A8, 32'h0000_000A);     // delta_start=1, prog_500m=1
        wait_c = 0; rval = 32'h0000_0100;
        while (rval[8] && wait_c < 30) begin #500; rd_reg(16'h00A8, rval); wait_c = wait_c + 1; end
        si_delta_rd = {u_si549.mem[233], u_si549.mem[232], u_si549.mem[231]};
        if (!rval[13] || ($signed(si_delta_rd) !== 24'sd429553)) begin
            $display("FAIL: tb_clk_mode_switch +delta_M clamp failed rval=0x%08h si_delta=%0d (exp +429553, clamped=1)",
                     rval, $signed(si_delta_rd));
            $finish;
        end

        wr_reg(16'h00AC, 32'hFFF2_4460);     // -900_000 -> must clamp to -429553
        wr_reg(16'h00A8, 32'h0000_000A);
        wait_c = 0; rval = 32'h0000_0100;
        while (rval[8] && wait_c < 30) begin #500; rd_reg(16'h00A8, rval); wait_c = wait_c + 1; end
        si_delta_rd = {u_si549.mem[233], u_si549.mem[232], u_si549.mem[231]};
        if (!rval[13] || ($signed(si_delta_rd) !== -24'sd429553)) begin
            $display("FAIL: tb_clk_mode_switch -delta_M clamp failed rval=0x%08h si_delta=%0d (exp -429553, clamped=1)",
                     rval, $signed(si_delta_rd));
            $finish;
        end

        wr_reg(16'h00AC, 32'd100_000);       // +11.64 ppm -> pass-through unclamped
        wr_reg(16'h00A8, 32'h0000_000A);
        wait_c = 0; rval = 32'h0000_0100;
        while (rval[8] && wait_c < 30) begin #500; rd_reg(16'h00A8, rval); wait_c = wait_c + 1; end
        si_delta_rd = {u_si549.mem[233], u_si549.mem[232], u_si549.mem[231]};
        if (rval[13] || ($signed(si_delta_rd) !== 24'sd100000)) begin
            $display("FAIL: tb_clk_mode_switch in-range delta_M unexpected clamp rval=0x%08h si_delta=%0d",
                     rval, $signed(si_delta_rd));
            $finish;
        end

        // Check Test 4a: Runtime switch 500 MHz -> 400 MHz (must clear radar_path_disabled & train AD9484)
        rd_reg(16'h00E8, rval);
        if (!rval[0] || rval[1] || rval[2]) begin
            $display("FAIL: tb_clk_mode_switch 500M boot A-1 expected 0xE8[0]=1,mmcm=0,tr=0 got 0x%08h", rval);
            $finish;
        end
        wr_reg(16'h00A8, 32'h0000_0004); // prog_start=1, prog_500m=0
        #2000;
        wait_ias_retrain();
        rd_reg(16'h00A8, rval);
        if (u_si549.mem[23] !== 8'h1C || rval[10] !== 1'b0 || !rval[9]) begin
            $display("FAIL: tb_clk_mode_switch 500->400 switch mismatch mem[23]=%02x 0xA8=0x%08h",
                     u_si549.mem[23], rval);
            $finish;
        end
        wait_c = 0;
        rval = 32'd0;
        while ((!rval[2] || rval[0]) && wait_c < 80) begin
            #2000;
            rd_reg(16'h00E8, rval);
            wait_c = wait_c + 1;
        end
        if (rval[0] || !rval[1] || !rval[2]) begin
            $display("FAIL: tb_clk_mode_switch 400M switch did not enable/train AD9484 (0xE8=0x%08h)", rval);
            $finish;
        end
        repeat (8) @(posedge u_artix.dac_clk);
        dac_per_400 = dac_clk_per_ns;
        if (dac_per_400 < 9.9 || dac_per_400 > 10.1) begin
            $display("FAIL: tb_clk_mode_switch 400M dac_clk period=%0.3f ns (exp 10.000 ns)", dac_per_400);
            $finish;
        end

        // Check Test 4b: Runtime switch 400 MHz -> 500 MHz (must re-assert A-1 radar_path_disabled=1)
        wr_reg(16'h00A8, 32'h0000_0006); // prog_start=1, prog_500m=1
        #2000;
        wait_ias_retrain();
        rd_reg(16'h00A8, rval);
        if (u_si549.mem[23] !== 8'h16 || rval[10] !== 1'b1 || !rval[9]) begin
            $display("FAIL: tb_clk_mode_switch 400->500 switch mismatch mem[23]=%02x 0xA8=0x%08h",
                     u_si549.mem[23], rval);
            $finish;
        end
        rd_reg(16'h00E8, rval);
        if (!rval[0] || rval[1] || rval[2]) begin
            $display("FAIL: tb_clk_mode_switch 500M-back did not re-disable AD9484 (0xE8=0x%08h)", rval);
            $finish;
        end
        repeat (8) @(posedge u_artix.dac_clk);
        dac_per_500_back = dac_clk_per_ns;
        if (dac_per_500_back < 7.9 || dac_per_500_back > 8.1) begin
            $display("FAIL: tb_clk_mode_switch 500M-back dac_clk period=%0.3f ns (exp 8.000 ns)", dac_per_500_back);
            $finish;
        end

        $display("PASS: tb_clk_mode_switch boot=500M dac_500=%0.3fns dac_400=%0.3fns dac_back=%0.3fns fcal_gaps=%0d clamp=+/-429553 hf_chb=%0d hf_dac2=0x%04h rd_max=%0d",
                 dac_per_500_boot, dac_per_400, dac_per_500_back, fcal_gap_seen, cnt_05, dac2_last_nz, rd_max_tmo);
        $finish;
    end

    initial begin
        #2_500_000;
        $display("FAIL: tb_clk_mode_switch global simulation timeout");
        $finish;
    end

endmodule
