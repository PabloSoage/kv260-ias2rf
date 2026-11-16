// SPDX-License-Identifier: Apache-2.0
// Rev08 G-8 End-to-End Realistic Signal Testbench (Full Artix + Board Channel + Kria PL)
//
// Parameterized completely via +plusargs so all 8 Rev08 bands/cases run through the real
// Artix-7 + LVDS PCB channel + Kria PL RTL (with concurrent SGMII peer) without recompiling:
//   +CASE=HF_AM|HF_SSB|FM_BCAST|AIRBAND|VHF_UHF|ADSB|TX_ALL|RADAR
//   +ADCS_SIG_FILE=<hex> +ADCR_SIG_FILE=<hex> +SIG_WAIT_ARM
//   +OUT_DDC=<txt> +OUT_DEMOD=<txt> +OUT_ADSB=<txt> +OUT_TX=<txt> +OUT_RADAR=<txt>
//   +RUN_US=<us>

`timescale 1ps/10fs

module tb_system_signals;

`ifdef FPGA_CLK_400M
    localparam [0:0] TB_BOOT_500M = 1'b0;
    real sys_half_ps = 1250.000;
`else
    localparam [0:0] TB_BOOT_500M = 1'b1;
    real sys_half_ps = 1000.000;
`endif

    reg sys_clk_p = 1'b0;
    always #(sys_half_ps) sys_clk_p = ~sys_clk_p;
    wire sys_clk_n = ~sys_clk_p;

    reg kria_pl_clk_100m = 1'b0;
    always #5000.000 kria_pl_clk_100m = ~kria_pl_clk_100m;
    reg kria_pl_resetn = 1'b0;

    // IAS1 LVDS + SGMII Differential Wires & PCB Channels
    wire k_dl_clk_p, k_dl_clk_n, k_dl_d0_p, k_dl_d0_n;
    wire a_dl_clk_p, a_dl_clk_n, a_dl_d0_p, a_dl_d0_n;
    wire a_ul_clk_p, a_ul_clk_n, a_ul_d0_p, a_ul_d0_n, a_ul_d1_p, a_ul_d1_n;
    wire k_ul_clk_p, k_ul_clk_n, k_ul_d0_p, k_ul_d0_n, k_ul_d1_p, k_ul_d1_n;
    wire a_sgtx_p, a_sgtx_n, p_sgtx_p, p_sgtx_n;
    wire p_sgrx_p, p_sgrx_n, a_sgrx_p, a_sgrx_n;

    sim_board_lvds_channel #(.DLY_P_PS(965.0), .DLY_N_PS(975.0), .JITTER_SPREAD_PS(20.0), .SEED(32'h1100_0001))
        u_ch_ul_clk (.tx_p(a_ul_clk_p), .tx_n(a_ul_clk_n), .cut_fault(1'b0), .glitch_inj(1'b0), .rx_p(k_ul_clk_p), .rx_n(k_ul_clk_n));
    sim_board_lvds_channel #(.DLY_P_PS(951.0), .DLY_N_PS(959.0), .JITTER_SPREAD_PS(20.0), .SEED(32'h1100_0002))
        u_ch_ul_d0  (.tx_p(a_ul_d0_p),  .tx_n(a_ul_d0_n),  .cut_fault(1'b0), .glitch_inj(1'b0), .rx_p(k_ul_d0_p),  .rx_n(k_ul_d0_n));
    sim_board_lvds_channel #(.DLY_P_PS(957.0), .DLY_N_PS(965.0), .JITTER_SPREAD_PS(20.0), .SEED(32'h1100_0003))
        u_ch_ul_d1  (.tx_p(a_ul_d1_p),  .tx_n(a_ul_d1_n),  .cut_fault(1'b0), .glitch_inj(1'b0), .rx_p(k_ul_d1_p),  .rx_n(k_ul_d1_n));

    sim_board_lvds_channel #(.DLY_P_PS(1010.0), .DLY_N_PS(1006.0), .JITTER_SPREAD_PS(20.0), .SEED(32'h2200_0001))
        u_ch_dl_clk (.tx_p(k_dl_clk_p), .tx_n(k_dl_clk_n), .cut_fault(1'b0), .glitch_inj(1'b0), .rx_p(a_dl_clk_p), .rx_n(a_dl_clk_n));
    sim_board_lvds_channel #(.DLY_P_PS(1001.0), .DLY_N_PS(999.0),  .JITTER_SPREAD_PS(20.0), .SEED(32'h2200_0002))
        u_ch_dl_d0  (.tx_p(k_dl_d0_p),  .tx_n(k_dl_d0_n),  .cut_fault(1'b0), .glitch_inj(1'b0), .rx_p(a_dl_d0_p),  .rx_n(a_dl_d0_n));

    sim_board_lvds_channel #(.DLY_P_PS(404.0), .DLY_N_PS(402.0), .JITTER_SPREAD_PS(35.0), .SEED(32'h3300_0001))
        u_ch_eth_sgtx (.tx_p(a_sgtx_p), .tx_n(a_sgtx_n), .cut_fault(1'b0), .glitch_inj(1'b0), .rx_p(p_sgtx_p), .rx_n(p_sgtx_n));
    sim_board_lvds_channel #(.DLY_P_PS(464.0), .DLY_N_PS(468.0), .JITTER_SPREAD_PS(35.0), .SEED(32'h3300_0002))
        u_ch_eth_sgrx (.tx_p(p_sgrx_p), .tx_n(p_sgrx_n), .cut_fault(1'b0), .glitch_inj(1'b0), .rx_p(a_sgrx_p), .rx_n(a_sgrx_n));

    // Converter & Peripheral Wires
    wire [7:0]  adcr_d_p, adcr_d_n;
    wire        adcr_or_p, adcr_or_n, adcr_dco_p, adcr_dco_n;
    wire        adcs_dco_p, adcs_dco_n, adcs_fco_p, adcs_fco_n;
    wire        adcs_d0_p, adcs_d0_n, adcs_d1_p, adcs_d1_n;
    wire        dacr_clk;
    wire [7:0]  dacr_d;
    wire [13:0] dacs_d;
    wire        dacs_iqclk, dacs_iqwrt, dacs_iqsel, dacs_iqreset;
    wire        conv_spi_sclk, conv_spi_csb_r, conv_spi_csb_s;
    tri1        conv_spi_sdio;
    wire        adar_sclk, adar_sdo;
    tri1        adar_sdio;
    wire [7:0]  adar_csb, adar_rx_load, adar_tx_load, adar_tr;
    wire [3:0]  sw_ctrl;
    tri1        hk_scl, hk_sda;
    tri1        hk_alert_n = 1'b1;
    wire        fpga_irq_pad, fpga_prog_b_pad;
    tri1        xo_scl, xo_sda;
    tri1        clk_sel;
    wire        pmod_cs_n, pmod_sclk, pmod_mosi, pmod_miso;
    wire        kria_beam_strobe, kria_pps_sync, kria_spare1, kria_spare2;
    wire        eth_mdc, eth_rst_n;
    tri1        eth_mdio;

    artix_top #(
        .DDC_POST_DECIM    (4),
        .LINK_AM_PERIOD    (64),
        .ADC_AUTO_TRAIN    (1'b1),
        .ENABLE_ETH        (1'b1),
        .ETH_BYPASS_AN     (1'b1),
        .ETH_ALIVE_TIMEOUT (25000),
        .ETH_MDIO_RST_CYC  (128),
        .ETH_MDIO_POLL_DIV (1200),
        .ETH_SDR_PKT_BYTES (512),
        .ETH_SDR_GAP_CYC   (256),
        .ETH_DEFAULT_POLICY(2'd0),
        .CONV_SPI_CLK_DIV  (2),
        .CONV_SPI_RST_CYC  (16),
        .CONV_SPI_AUTO_INIT(1'b1),
        .ADAR_CLK_DIV      (2),
        .ADAR_AUTO_INIT    (1'b1),
        .HK_CLK_DIV        (3),
        .HK_POLL_DIV       (16000),
        .XO_FCAL_WAIT_CYC  (150),
        .BOOT_FREQ_500M    (TB_BOOT_500M),
        .XADC_POLL_DIV_P   (500)
    ) dut_artix (
        .fpga_clk_p     (sys_clk_p),
        .fpga_clk_n     (sys_clk_n),
        .adcr_d_p       (adcr_d_p),
        .adcr_d_n       (adcr_d_n),
        .adcr_or_p      (adcr_or_p),
        .adcr_or_n      (adcr_or_n),
        .adcr_dco_n     (adcr_dco_n),
        .adcr_dco_p     (adcr_dco_p),
        .adcs_dco_p     (adcs_dco_p),
        .adcs_dco_n     (adcs_dco_n),
        .adcs_fco_p     (adcs_fco_p),
        .adcs_fco_n     (adcs_fco_n),
        .adcs_d0_p      (adcs_d0_p),
        .adcs_d0_n      (adcs_d0_n),
        .adcs_d1_p      (adcs_d1_p),
        .adcs_d1_n      (adcs_d1_n),
        .link_rx_clk_p  (a_ul_clk_p),
        .link_rx_clk_n  (a_ul_clk_n),
        .link_rx_d0_p   (a_ul_d0_p),
        .link_rx_d0_n   (a_ul_d0_n),
        .link_rx_d1_p   (a_ul_d1_p),
        .link_rx_d1_n   (a_ul_d1_n),
        .link_tx_clk_p  (a_dl_clk_p),
        .link_tx_clk_n  (a_dl_clk_n),
        .link_tx_d0_p   (a_dl_d0_p),
        .link_tx_d0_n   (a_dl_d0_n),
        .pmod_cs_n      (pmod_cs_n),
        .pmod_mosi      (pmod_mosi),
        .pmod_miso      (pmod_miso),
        .pmod_sclk      (pmod_sclk),
        .beam_strobe    (kria_beam_strobe),
        .pps_sync       (kria_pps_sync),
        .pmod_spare1    (kria_spare1),
        .pmod_spare2    (kria_spare2),
        .dacr_clk       (dacr_clk),
        .dacr_d         (dacr_d),
        .dacs_d         (dacs_d),
        .dacs_iqclk     (dacs_iqclk),
        .dacs_iqreset   (dacs_iqreset),
        .dacs_iqsel     (dacs_iqsel),
        .dacs_iqwrt     (dacs_iqwrt),
        .sw_ctrl        (sw_ctrl),
        .xo_scl         (xo_scl),
        .xo_sda         (xo_sda),
        .clk_sel        (clk_sel),
        .hk_scl         (hk_scl),
        .hk_sda         (hk_sda),
        .hk_alert_n     (hk_alert_n),
        .fpga_irq       (fpga_irq_pad),
        .conv_spi_csb_r (conv_spi_csb_r),
        .conv_spi_csb_s (conv_spi_csb_s),
        .conv_spi_sclk  (conv_spi_sclk),
        .conv_spi_sdio  (conv_spi_sdio),
        .adar_sclk      (adar_sclk),
        .adar_sdio      (adar_sdio),
        .adar_sdo       (adar_sdo),
        .adar_csb       (adar_csb),
        .adar_rx_load   (adar_rx_load),
        .adar_tx_load   (adar_tx_load),
        .adar_tr        (adar_tr),
        .eth_sgtx_p     (a_sgtx_p),
        .eth_sgtx_n     (a_sgtx_n),
        .eth_sgrx_p     (a_sgrx_p),
        .eth_sgrx_n     (a_sgrx_n),
        .eth_mdc        (eth_mdc),
        .eth_mdio       (eth_mdio),
        .eth_rst_n      (eth_rst_n)
    );

    reg  [7:0]  s_axi_awaddr = 8'd0, s_axi_araddr = 8'd0;
    reg  [2:0]  s_axi_awprot = 3'd0, s_axi_arprot = 3'd0;
    reg         s_axi_awvalid = 1'b0, s_axi_wvalid = 1'b0, s_axi_bready = 1'b0;
    reg         s_axi_arvalid = 1'b0, s_axi_rready = 1'b0;
    reg  [31:0] s_axi_wdata = 32'd0;
    reg  [3:0]  s_axi_wstrb = 4'd0;
    wire        s_axi_awready, s_axi_wready, s_axi_bvalid, s_axi_arready, s_axi_rvalid;
    wire [1:0]  s_axi_bresp, s_axi_rresp;
    wire [31:0] s_axi_rdata;

    wire [63:0] m_axis_rx_tdata;
    wire [7:0]  m_axis_rx_tkeep, m_axis_rx_tid;
    wire        m_axis_rx_tvalid, m_axis_rx_tlast;
    wire [0:0]  m_axis_rx_tuser;
    reg         m_axis_rx_tready = 1'b1;

    reg  [63:0] s_axis_tx_tdata = 64'd0;
    reg  [7:0]  s_axis_tx_tkeep = 8'hFF, s_axis_tx_tid = 8'd0;
    reg         s_axis_tx_tvalid = 1'b0, s_axis_tx_tlast = 1'b0;
    reg  [15:0] s_axis_tx_tuser = 16'd0;
    wire        s_axis_tx_tready;

    reg  [7:0]  emio_gpio_o = 8'd0, emio_gpio_t = 8'hFF;
    wire [7:0]  emio_gpio_i;
    wire        irq_fpga, irq_link_up;

    kria_pl_link dut_kria (
        .pl_clk_100m      (kria_pl_clk_100m),
        .pl_resetn        (kria_pl_resetn),
        .s_axi_awaddr     (s_axi_awaddr),
        .s_axi_awprot     (s_axi_awprot),
        .s_axi_awvalid    (s_axi_awvalid),
        .s_axi_awready    (s_axi_awready),
        .s_axi_wdata      (s_axi_wdata),
        .s_axi_wstrb      (s_axi_wstrb),
        .s_axi_wvalid     (s_axi_wvalid),
        .s_axi_wready     (s_axi_wready),
        .s_axi_bresp      (s_axi_bresp),
        .s_axi_bvalid     (s_axi_bvalid),
        .s_axi_bready     (s_axi_bready),
        .s_axi_araddr     (s_axi_araddr),
        .s_axi_arprot     (s_axi_arprot),
        .s_axi_arvalid    (s_axi_arvalid),
        .s_axi_arready    (s_axi_arready),
        .s_axi_rdata      (s_axi_rdata),
        .s_axi_rresp      (s_axi_rresp),
        .s_axi_rvalid     (s_axi_rvalid),
        .s_axi_rready     (s_axi_rready),
        .m_axis_rx_tdata  (m_axis_rx_tdata),
        .m_axis_rx_tkeep  (m_axis_rx_tkeep),
        .m_axis_rx_tvalid (m_axis_rx_tvalid),
        .m_axis_rx_tready (m_axis_rx_tready),
        .m_axis_rx_tlast  (m_axis_rx_tlast),
        .m_axis_rx_tid    (m_axis_rx_tid),
        .m_axis_rx_tuser  (m_axis_rx_tuser),
        .s_axis_tx_tdata  (s_axis_tx_tdata),
        .s_axis_tx_tkeep  (s_axis_tx_tkeep),
        .s_axis_tx_tvalid (s_axis_tx_tvalid),
        .s_axis_tx_tready (s_axis_tx_tready),
        .s_axis_tx_tlast  (s_axis_tx_tlast),
        .s_axis_tx_tid    (s_axis_tx_tid),
        .s_axis_tx_tuser  (s_axis_tx_tuser),
        .emio_i2c_scl_i   (),
        .emio_i2c_scl_o   (1'b1),
        .emio_i2c_scl_t   (1'b1),
        .emio_i2c_sda_i   (),
        .emio_i2c_sda_o   (1'b1),
        .emio_i2c_sda_t   (1'b1),
        .emio_spi_mo      (1'b0),
        .emio_spi_sclk    (1'b0),
        .emio_spi_ssn     (1'b1),
        .emio_spi_mi      (),
        .emio_gpio_o      (emio_gpio_o),
        .emio_gpio_t      (emio_gpio_t),
        .emio_gpio_i      (emio_gpio_i),
        .emio_uart1_txd   (1'b1),
        .emio_uart1_rxd   (),
        .irq_fpga         (irq_fpga),
        .irq_link_up      (irq_link_up),
        .link_rx_clk_p    (k_ul_clk_p),
        .link_rx_clk_n    (k_ul_clk_n),
        .link_rx_d0_p     (k_ul_d0_p),
        .link_rx_d0_n     (k_ul_d0_n),
        .link_rx_d1_p     (k_ul_d1_p),
        .link_rx_d1_n     (k_ul_d1_n),
        .link_tx_clk_p    (k_dl_clk_p),
        .link_tx_clk_n    (k_dl_clk_n),
        .link_tx_d0_p     (k_dl_d0_p),
        .link_tx_d0_n     (k_dl_d0_n),
        .fpga_irq         (fpga_irq_pad),
        .hk_scl           (hk_scl),
        .hk_sda           (hk_sda),
        .fpga_prog_b      (fpga_prog_b_pad),
        .pmod_cs_n        (pmod_cs_n),
        .pmod_mosi        (pmod_mosi),
        .pmod_miso        (pmod_miso),
        .pmod_sclk        (pmod_sclk),
        .pmod_beam_strobe (kria_beam_strobe),
        .pmod_pps_sync    (kria_pps_sync),
        .pmod_spare1      (kria_spare1),
        .pmod_spare2      (kria_spare2)
    );

    // Peripheral & ADC/DAC Board Models
    reg clk_400m_adcr = 1'b0;
    always #1250.000 clk_400m_adcr = ~clk_400m_adcr;
    reg dco_true_adcr = 1'b0;
    always @(posedge clk_400m_adcr) dco_true_adcr <= ~dco_true_adcr;
    reg [1:0] adcr_mode = 2'd0;
    sim_ad9484_model dut_adcr (
        .clk_400m_adc(clk_400m_adcr), .dco_true(dco_true_adcr),
        .mode(adcr_mode), .no_echo_mut(1'b0),
        .spi_csb(conv_spi_csb_r), .spi_sclk(conv_spi_sclk), .spi_sdio(conv_spi_sdio),
        .dacr_clk(dacr_clk), .dacr_d(dacr_d),
        .adcr_d_p(adcr_d_p), .adcr_d_n(adcr_d_n),
        .adcr_or_p(adcr_or_p), .adcr_or_n(adcr_or_n),
        .adcr_dco_n(adcr_dco_n), .adcr_dco_p(adcr_dco_p)
    );

    sim_ad9253_model dut_adcs (
        .spi_csb(conv_spi_csb_s), .spi_sclk(conv_spi_sclk), .spi_sdio(conv_spi_sdio),
        .adcs_dco_p(adcs_dco_p), .adcs_dco_n(adcs_dco_n),
        .adcs_fco_p(adcs_fco_p), .adcs_fco_n(adcs_fco_n),
        .adcs_d0_p(adcs_d0_p), .adcs_d0_n(adcs_d0_n),
        .adcs_d1_p(adcs_d1_p), .adcs_d1_n(adcs_d1_n)
    );

    wire [31:0] tr_viol, tx_load_cnt;
    sim_adar1000_array u_adar (
        .chk_clk(kria_pl_clk_100m), .chk_rst(!kria_pl_resetn),
        .adar_sclk(adar_sclk), .adar_sdio(adar_sdio), .adar_sdo(adar_sdo),
        .adar_csb(adar_csb), .adar_rx_load(adar_rx_load),
        .adar_tx_load(adar_tx_load), .adar_tr(adar_tr),
        .tr_viol(tr_viol), .tx_load_cnt(tx_load_cnt)
    );

    wire [31:0] dacr_edges, dacr_terrs, dacr_act, dacr_zc1, dacr_zc2;
    wire signed [7:0] dacr_max;
    sim_dac_radar_mon u_dacr_mon (
        .dacr_clk(dacr_clk), .dacr_d(dacr_d),
        .clk_edges(dacr_edges), .timing_errs(dacr_terrs), .active_samples(dacr_act),
        .zc_first_half(dacr_zc1), .zc_second_half(dacr_zc2), .max_amp(dacr_max)
    );

    wire [31:0] dacs_cedges, dacs_wedges, dacs_icnt, dacs_qcnt;
    wire signed [13:0] dacs_last_i, dacs_last_q;
    sim_dac_sdr_mon u_dacs_mon (
        .dacs_iqclk(dacs_iqclk), .dacs_iqwrt(dacs_iqwrt), .dacs_iqsel(dacs_iqsel), .dacs_d(dacs_d),
        .clk_edges(dacs_cedges), .wrt_edges(dacs_wedges), .i_samples(dacs_icnt), .q_samples(dacs_qcnt),
        .last_i(dacs_last_i), .last_q(dacs_last_q)
    );

    sim_hk_i2c_slave #(.SLAVE_ADDR(7'h55)) u_si549 (.scl(xo_scl), .sda(xo_sda), .enable_ack(1'b1));
    sim_hk_i2c_slave #(.SLAVE_ADDR(7'h48)) u_tmp1075 (.scl(hk_scl), .sda(hk_sda), .enable_ack(1'b1));

    wire [31:0] mdio_r, mdio_w, eth_fcs_fail, eth_s1, eth_s2, eth_max1, eth_max2;
    wire [1023:0] seen1, seen2;
    sim_sgmii_phy_peer u_eth_peer (
        .eth_rst_n(eth_rst_n), .eth_mdc(eth_mdc), .eth_mdio(eth_mdio),
        .eth_sgtx_p(p_sgtx_p), .eth_sgtx_n(p_sgtx_n), .eth_sgrx_p(p_sgrx_p), .eth_sgrx_n(p_sgrx_n),
        .peer_half_ui_fs(32'd400000), .peer_rst_n(kria_pl_resetn), .link_rx_cut(1'b0),
        .mdio_poll_reads(mdio_r), .mdio_custom_wrs(mdio_w), .eth_fcs_fail(eth_fcs_fail),
        .eth_s1_cnt(eth_s1), .eth_s2_cnt(eth_s2), .seen_eth_s1(seen1), .seen_eth_s2(seen2),
        .eth_max_s1(eth_max1), .eth_max_s2(eth_max2)
    );

    // -------------------------------------------------------------------------
    // AXI-Lite & Downlink Config Helpers
    // -------------------------------------------------------------------------
    task kria_wr(input [7:0] addr, input [31:0] data);
        reg aw_ok, w_ok, b_ok;
        begin
            aw_ok = 1'b0; w_ok = 1'b0; b_ok = 1'b0;
            @(negedge kria_pl_clk_100m);
            s_axi_awaddr  = addr; s_axi_awvalid = 1'b1;
            s_axi_wdata   = data; s_axi_wstrb = 4'hF; s_axi_wvalid = 1'b1;
            s_axi_bready  = 1'b1;
            while (!aw_ok || !w_ok || !b_ok) begin
                @(posedge kria_pl_clk_100m);
                if (s_axi_awvalid && s_axi_awready) aw_ok = 1'b1;
                if (s_axi_wvalid  && s_axi_wready)  w_ok  = 1'b1;
                if (s_axi_bvalid  && s_axi_bready)  b_ok  = 1'b1;
                @(negedge kria_pl_clk_100m);
                if (aw_ok) s_axi_awvalid = 1'b0;
                if (w_ok)  s_axi_wvalid  = 1'b0;
            end
            s_axi_bready = 1'b0;
        end
    endtask

    task kria_rd(input [7:0] addr, output [31:0] data);
        reg ar_ok, r_ok;
        begin
            ar_ok = 1'b0; r_ok = 1'b0; data = 32'd0;
            @(negedge kria_pl_clk_100m);
            s_axi_araddr = addr; s_axi_arvalid = 1'b1; s_axi_rready = 1'b1;
            while (!ar_ok || !r_ok) begin
                @(posedge kria_pl_clk_100m);
                if (s_axi_arvalid && s_axi_arready) ar_ok = 1'b1;
                if (s_axi_rvalid  && s_axi_rready) begin
                    data = s_axi_rdata;
                    r_ok = 1'b1;
                end
                @(negedge kria_pl_clk_100m);
                if (ar_ok) s_axi_arvalid = 1'b0;
            end
            s_axi_rready = 1'b0;
        end
    endtask

    task dl_artix_wr(input [15:0] addr, input [31:0] val);
        begin
            @(negedge kria_pl_clk_100m);
            s_axis_tx_tid    = 8'h10;
            s_axis_tx_tuser  = 16'd8;
            s_axis_tx_tlast  = 1'b1;
            s_axis_tx_tdata  = {8'h01, 8'h00, addr, val};
            s_axis_tx_tvalid = 1'b1;
            @(posedge kria_pl_clk_100m);
            while (!s_axis_tx_tready) @(posedge kria_pl_clk_100m);
            @(negedge kria_pl_clk_100m);
            s_axis_tx_tvalid = 1'b0;
            repeat (40) @(posedge kria_pl_clk_100m);
        end
    endtask

    // -------------------------------------------------------------------------
    // Real-Time Output Recorders (when +SIG_WAIT_ARM is released)
    // -------------------------------------------------------------------------
    integer fd_ddc = 0, fd_demod = 0, fd_adsb = 0, fd_tx = 0, fd_radar = 0;
    reg     cap_en = 1'b0;
    integer cnt_ddc = 0, cnt_demod = 0, cnt_adsb = 0, cnt_tx_sdr = 0, cnt_tx_rad = 0, cnt_radar = 0;
    reg [7:0] target_ddc_sid = 8'h05;

    always @(posedge kria_pl_clk_100m) begin
        if (cap_en) begin
            if (fd_ddc != 0 && m_axis_rx_tvalid && m_axis_rx_tready && (m_axis_rx_tid == target_ddc_sid)) begin
                $fwrite(fd_ddc, "%d %d\n%d %d\n",
                        $signed(m_axis_rx_tdata[15:0]),  $signed(m_axis_rx_tdata[31:16]),
                        $signed(m_axis_rx_tdata[47:32]), $signed(m_axis_rx_tdata[63:48]));
                cnt_ddc = cnt_ddc + 2;
            end
            if (fd_demod != 0 && dut_kria.u_dsp_suite.mon_audio_valid) begin
                $fwrite(fd_demod, "%d %d %d %0d %0d\n",
                        $signed(dut_kria.u_dsp_suite.mon_audio_l),
                        $signed(dut_kria.u_dsp_suite.mon_audio_r),
                        $signed(dut_kria.u_dsp_suite.mon_audio_mono),
                        dut_kria.u_dsp_suite.mon_pilot_locked,
                        dut_kria.u_dsp_suite.mon_ctcss_det);
                cnt_demod = cnt_demod + 1;
            end
            if (fd_adsb != 0 && dut_kria.u_dsp_suite.mon_adsb_valid) begin
                $fwrite(fd_adsb, "%0d %028h %0d\n",
                        dut_kria.u_dsp_suite.mon_adsb_crc_ok,
                        dut_kria.u_dsp_suite.mon_adsb_data,
                        dut_kria.u_dsp_suite.mon_adsb_snr);
                cnt_adsb = cnt_adsb + 1;
            end
            if (fd_radar != 0 && dut_kria.u_dsp_suite.mon_rd_valid) begin
                $fwrite(fd_radar, "%0d %0d %0d %0d\n",
                        dut_kria.u_dsp_suite.mon_rd_rbin,
                        dut_kria.u_dsp_suite.mon_rd_dbin,
                        dut_kria.u_dsp_suite.mon_rd_pwr,
                        dut_kria.u_dsp_suite.mon_rd_det);
                cnt_radar = cnt_radar + 1;
            end
        end
    end

    // Record real physical DAC output words (AD9767 I/Q + AD9708 radar)
    reg signed [13:0] tx_hold_i = 14'sd0;
    reg               tx_have_i = 1'b0;
    always @(posedge dacs_iqwrt) begin
        if (cap_en && fd_tx != 0) begin
            if (dacs_iqsel) begin
                tx_hold_i <= $signed({~dacs_d[13], dacs_d[12:0]}); // offset bin -> signed
                tx_have_i <= 1'b1;
            end else if (tx_have_i) begin
                $fwrite(fd_tx, "S %d %d\n", tx_hold_i, $signed({~dacs_d[13], dacs_d[12:0]}));
                cnt_tx_sdr = cnt_tx_sdr + 1;
            end
        end
    end
    always @(posedge dacr_clk) begin
        if (cap_en && fd_tx != 0 && dacr_d != 8'h80) begin
            $fwrite(fd_tx, "R %d\n", $signed(dacr_d) - 8'sd128);
            cnt_tx_rad = cnt_tx_rad + 1;
        end
    end

    // Main Control Sequence
    reg [2047:0] case_str, fpath;
    reg [31:0]   artix_nco_b, artix_decim, artix_rad_ctrl;
    reg [31:0]   k_ctrl, k_nco, k_decim, k_demod, k_pilot, k_ctcss, k_thr, k_adsb;
    reg [31:0]   tx_car, tx_tone, tx_cfg, rad_alpha;
    integer      run_us = 1000;
    reg [31:0]   rdv, stat1, stat2;
    integer      tout;

    initial begin
        if (!$value$plusargs("CASE=%s", case_str)) case_str = "HF_AM";
        if (!$value$plusargs("RUN_US=%d", run_us)) run_us = 1000;
        if ($value$plusargs("OUT_DDC=%s", fpath))   fd_ddc   = $fopen(fpath, "w");
        if ($value$plusargs("OUT_DEMOD=%s", fpath)) fd_demod = $fopen(fpath, "w");
        if ($value$plusargs("OUT_ADSB=%s", fpath))  fd_adsb  = $fopen(fpath, "w");
        if ($value$plusargs("OUT_TX=%s", fpath))    fd_tx    = $fopen(fpath, "w");
        if ($value$plusargs("OUT_RADAR=%s", fpath)) fd_radar = $fopen(fpath, "w");

        artix_nco_b    = 32'd0;
        artix_decim    = 32'h0040_0004;
        artix_rad_ctrl = 32'h0000_0001;
        k_ctrl   = 32'd0; k_nco = 32'd0; k_decim = 32'h0001_0001; k_demod = 32'h7FE7_3000;
        k_pilot  = 32'd0; k_ctcss = 32'h00CA_0140; k_thr = 32'd2000; k_adsb = 32'h000800_8C;
        tx_car   = 32'd0; tx_tone = 32'd0; tx_cfg = 32'h6000_4000; rad_alpha = 32'd1536;

        if ($value$plusargs("ARTIX_NCO_B=%h", rdv))    artix_nco_b = rdv;
        if ($value$plusargs("ARTIX_DECIM=%h", rdv))    artix_decim = rdv;
        if ($value$plusargs("ARTIX_RAD_CTRL=%h", rdv)) artix_rad_ctrl = rdv;
        if ($value$plusargs("KRIA_CTRL=%h", rdv))      k_ctrl = rdv;
        if ($value$plusargs("KRIA_NCO=%h", rdv))       k_nco = rdv;
        if ($value$plusargs("KRIA_DECIM=%h", rdv))     k_decim = rdv;
        if ($value$plusargs("KRIA_DEMOD=%h", rdv))     k_demod = rdv;
        if ($value$plusargs("KRIA_PILOT=%h", rdv))     k_pilot = rdv;
        if ($value$plusargs("KRIA_CTCSS=%h", rdv))     k_ctcss = rdv;
        if ($value$plusargs("KRIA_THR=%h", rdv))       k_thr = rdv;
        if ($value$plusargs("KRIA_ADSB=%h", rdv))      k_adsb = rdv;
        if ($value$plusargs("TX_CAR=%h", rdv))         tx_car = rdv;
        if ($value$plusargs("TX_TONE=%h", rdv))        tx_tone = rdv;
        if ($value$plusargs("TX_CFG=%h", rdv))         tx_cfg = rdv;
        if ($value$plusargs("RAD_ALPHA=%h", rdv))      rad_alpha = rdv;

        target_ddc_sid = (k_ctrl[3:2] == 2'd0) ? 8'h01 : ((k_ctrl[3:2] == 2'd1) ? 8'h05 : 8'h04);

        #200_000;
        kria_pl_resetn = 1'b1;

        // Wait for Kria+Artix link up & ADC alignment (bounded)
        tout = 0;
        rdv  = 32'd0;
        while (!rdv[6] && tout < 3000) begin
            #200_000;
            kria_rd(8'h04, rdv);
            tout = tout + 1;
        end
        if (!rdv[6]) begin
            $display("FAIL: link did not train (status=%08x)", rdv);
            $finish;
        end
        // Also wait for Artix ADCS & (when 400M) ADCR eye training
        tout = 0;
        while ((!dut_artix.adcs_aligned || (!TB_BOOT_500M && !dut_artix.adc_trained)) && tout < 2000) begin
            #200_000;
            tout = tout + 1;
        end
        #2_000_000;

        // Configure Artix over real IAS1 downlink BEFORE arming DSP RX/TX
        dl_artix_wr(16'h0048, artix_nco_b);
        dl_artix_wr(16'h004C, artix_decim);
        dl_artix_wr(16'h00E4, artix_rad_ctrl);
        if (k_ctrl[1]) begin
            // TX_ALL mode: enable Artix dac_sdr (0x70) and dac_radar (0x54..0x64)
            dl_artix_wr(16'h0070, 32'h0000_0003); // tx_enable + dual IQ
            dl_artix_wr(16'h0058, 32'h0400_0000); // dacr start f0
            dl_artix_wr(16'h005C, 32'h0002_0000); // dacr chirp df
            dl_artix_wr(16'h0060, 32'h0000_0200); // 512 clk chirp
            dl_artix_wr(16'h0064, 32'h0000_0400); // 1024 clk PRI
            dl_artix_wr(16'h0054, 32'h00FF_0003); // enable + trig
        end
        if (k_ctrl[8]) begin
            // RADAR mode: also step ADAR1000 beam table (write + load beam 1) to verify array model
            dl_artix_wr(16'h0088, 32'h8001_003A); // chip 0, byte 0, beam 1 -> 0x3A
            dl_artix_wr(16'h007C, 32'h0000_0041); // active_beam=1, soft_load=1
        end
        #2_000_000;

        // Configure Kria PL DSP suite
        kria_wr(8'h44, k_nco);
        kria_wr(8'h48, k_decim);
        kria_wr(8'h4C, k_demod);
        kria_wr(8'h50, k_pilot);
        kria_wr(8'h54, k_ctcss);
        kria_wr(8'h58, k_thr);
        kria_wr(8'h64, k_adsb);
        kria_wr(8'h70, tx_car);
        kria_wr(8'h74, tx_tone);
        kria_wr(8'h78, tx_cfg);
        kria_wr(8'h7C, rad_alpha);

        // Switch AD9484 out of 0xAA/0x55 training pattern into idle (0 LSB) and flush Artix DDC/IAS1 FIFOs
        adcr_mode = 2'd1;
        #3_000_000;

        // Arm signal files + DSP suite
        dut_adcs.sig_armed = 1'b1;
        dut_adcr.sig_armed = 1'b1;
        cap_en             = 1'b1;
        if (k_ctrl[8]) begin
            // Align radar CPI capture to first non-zero DDC sample (within 1 sample of CPI start)
            while (!(m_axis_rx_tvalid && m_axis_rx_tready && (m_axis_rx_tid == 8'h01) &&
                     (($signed(m_axis_rx_tdata[15:0]) > 16'sd500) || ($signed(m_axis_rx_tdata[15:0]) < -16'sd500) ||
                      ($signed(m_axis_rx_tdata[31:16]) > 16'sd500) || ($signed(m_axis_rx_tdata[31:16]) < -16'sd500)))) begin
                @(posedge kria_pl_clk_100m);
            end
        end
        kria_wr(8'h40, k_ctrl);

        repeat (run_us) #1_000_000;
        cap_en = 1'b0;

        kria_rd(8'h60, stat1);
        kria_rd(8'h7C, stat2);
        kria_rd(8'h68, rdv);

        if (fd_ddc   != 0) $fclose(fd_ddc);
        if (fd_demod != 0) $fclose(fd_demod);
        if (fd_adsb  != 0) $fclose(fd_adsb);
        if (fd_tx    != 0) $fclose(fd_tx);
        if (fd_radar != 0) $fclose(fd_radar);

        $display("[SYS_SIG %0s] ddc=%0d demod=%0d adsb=%0d(ok=%0d) tx_s=%0d tx_r=%0d radar=%0d pk=(%0d,%0d) dacr_err=%0d tr_viol=%0d",
                 case_str, cnt_ddc, cnt_demod, cnt_adsb, rdv[15:0], cnt_tx_sdr, cnt_tx_rad,
                 cnt_radar, stat2[5:0], stat2[9:6], dacr_terrs, tr_viol);
        if (dacr_terrs != 0 || tr_viol != 0) begin
            $display("FAIL: tb_system_signals hardware timing/TR violation");
            $finish;
        end
        $display("PASS: tb_system_signals (%0s)", case_str);
        $finish;
    end
endmodule
