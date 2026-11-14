// SPDX-License-Identifier: BSD-2-Clause
// Full-System Co-Simulation Testbench (Task 22 Part A):
//   Real artix_top (ENABLE_ETH=1) <-> Real kria_pl_link (K26 PL wrapper)
//   Connected through Rev05 PCB/package/SOM LVDS channel models with exact
//   lvds_skew.py delays, SIGNAL_INTEGRITY.md jitter budgets, +/-100 ppm clock
//   skews, behavioral AD9484/AD9253/AD9708/AD9767/8xADAR1000/TMP1075/CAT24C02/
//   Si549/PPS peripherals, and behavioral RTL8211FSI + PS GEM3 SGMII/UDP peer.
//
// Simulation speed scaling:
//   - TAP_DWELL_CYCLES overridden to 768 (vs 1800 hw) on both train FSMs
//   - ETH_ALIVE_TIMEOUT = 25000 (200 us vs 1 s hw), HK_POLL_DIV = 16000
//   - XO_FCAL_WAIT_CYC = 150, ETH_MDIO_POLL_DIV = 1200

`timescale 1ps/10fs

module tb_system;
    localparam real PI = 3.14159265358979323846;

    // -------------------------------------------------------------------------
    // 1. Clocks (+/-100 ppm skew between Artix 100.000 MHz and Kria/PHY peer)
    // -------------------------------------------------------------------------
    reg fpga_clk_p   = 1'b0; // Artix 100.000 MHz nominal (T = 10.000 ns)
    always #5000.000 fpga_clk_p = ~fpga_clk_p;
    wire fpga_clk_n = ~fpga_clk_p;

    reg clk_400m_adc = 1'b0; // AD9484 400 MSPS clock (200 MHz DDR DCO)
    always #1250.000 clk_400m_adc = ~clk_400m_adc;
    reg dco_true = 1'b0;
    always @(posedge clk_400m_adc) dco_true <= ~dco_true;

    // Configurable Kria pl_clk_100m half-period (+100 ppm = 4999.500, -100 ppm = 5000.500)
    real pl_half_ps = 4999.500;
    reg  pl_clk_100m = 1'b0;
    always #(pl_half_ps) pl_clk_100m = ~pl_clk_100m;

    reg pl_resetn = 1'b0;

    // -------------------------------------------------------------------------
    // 2. Kria PL Wrapper Interfaces (AXI4-Lite CSR, AXI4-Stream TX/RX, EMIO)
    // -------------------------------------------------------------------------
    reg  [7:0]  s_axi_awaddr  = 8'd0;
    reg  [2:0]  s_axi_awprot  = 3'd0;
    reg         s_axi_awvalid = 1'b0;
    wire        s_axi_awready;
    reg  [31:0] s_axi_wdata   = 32'd0;
    reg  [3:0]  s_axi_wstrb   = 4'h0;
    reg         s_axi_wvalid  = 1'b0;
    wire        s_axi_wready;
    wire [1:0]  s_axi_bresp;
    wire        s_axi_bvalid;
    reg         s_axi_bready  = 1'b1;

    reg  [7:0]  s_axi_araddr  = 8'd0;
    reg  [2:0]  s_axi_arprot  = 3'd0;
    reg         s_axi_arvalid = 1'b0;
    wire        s_axi_arready;
    wire [31:0] s_axi_rdata;
    wire [1:0]  s_axi_rresp;
    wire        s_axi_rvalid;
    reg         s_axi_rready  = 1'b1;

    wire [63:0] m_axis_rx_tdata;
    wire [7:0]  m_axis_rx_tkeep;
    wire        m_axis_rx_tvalid;
    reg         m_axis_rx_tready = 1'b1;
    wire        m_axis_rx_tlast;
    wire [7:0]  m_axis_rx_tid;
    wire [0:0]  m_axis_rx_tuser;

    reg  [63:0] s_axis_tx_tdata  = 64'd0;
    reg  [7:0]  s_axis_tx_tkeep  = 8'hFF;
    reg         s_axis_tx_tvalid = 1'b0;
    wire        s_axis_tx_tready;
    reg         s_axis_tx_tlast  = 1'b0;
    reg  [7:0]  s_axis_tx_tid    = 8'd0;
    reg  [15:0] s_axis_tx_tuser  = 16'd0;

    wire        emio_i2c_scl_i, emio_i2c_sda_i;
    wire        emio_spi_mi;
    reg  [7:0]  emio_gpio_o = 8'h08; // Bit 3 (pmod_spare1)=1 pauses DDC during link eye training
    reg  [7:0]  emio_gpio_t = 8'h00;
    wire [7:0]  emio_gpio_i;

    wire        irq_fpga, irq_link_up;

    // -------------------------------------------------------------------------
    // 3. Board Nets Between Artix-7, Kria K26, Peripherals & PHY
    // -------------------------------------------------------------------------
    // Raw FPGA pads (TX -> Channel Model -> RX)
    wire a_ul_clk_p, a_ul_clk_n, a_ul_d0_p, a_ul_d0_n, a_ul_d1_p, a_ul_d1_n;
    wire k_ul_clk_p, k_ul_clk_n, k_ul_d0_p, k_ul_d0_n, k_ul_d1_p, k_ul_d1_n;

    wire k_dl_clk_p, k_dl_clk_n, k_dl_d0_p, k_dl_d0_n;
    wire a_dl_clk_p, a_dl_clk_n, a_dl_d0_p, a_dl_d0_n;

    wire a_sgtx_p, a_sgtx_n, p_sgtx_p, p_sgtx_n;
    wire p_sgrx_p, p_sgrx_n, a_sgrx_p, a_sgrx_n;

    reg  cut_ias_ul_d0 = 1'b0, cut_ias_ul_d1 = 1'b0;
    reg  glitch_ul_d0  = 1'b0;
    reg  cut_eth_sgtx  = 1'b0, cut_eth_sgrx  = 1'b0;

    // Uplink IAS1 channels (Artix -> Kria): lvds_skew.py + SOM(413/405 ps) + carrier(180 ps)
    sim_board_lvds_channel #(
        .DLY_P_PS(1271.0), .DLY_N_PS(1270.0), .JITTER_SPREAD_PS(14.0), .SEED(32'h1100_0001)
    ) u_ch_ul_clk (
        .tx_p(a_ul_clk_p), .tx_n(a_ul_clk_n), .cut_fault(1'b0), .glitch_inj(1'b0),
        .rx_p(k_ul_clk_p), .rx_n(k_ul_clk_n)
    );

`ifdef MUTATE_BAD_CHANNEL_SKEW
    localparam real UL_D0_JITTER_PS = 1250.0; // Exceeds 1 UI (1000 ps) -> destroys eye
`else
    localparam real UL_D0_JITTER_PS = 109.0;  // SI §8 C1220/C1221 stub spread
`endif

    sim_board_lvds_channel #(
        .DLY_P_PS(1359.0), .DLY_N_PS(1358.0), .JITTER_SPREAD_PS(UL_D0_JITTER_PS), .SEED(32'h1100_0002)
    ) u_ch_ul_d0 (
        .tx_p(a_ul_d0_p), .tx_n(a_ul_d0_n), .cut_fault(cut_ias_ul_d0), .glitch_inj(glitch_ul_d0),
        .rx_p(k_ul_d0_p), .rx_n(k_ul_d0_n)
    );

    sim_board_lvds_channel #(
        .DLY_P_PS(1302.0), .DLY_N_PS(1302.0), .JITTER_SPREAD_PS(77.0), .SEED(32'h1100_0003)
    ) u_ch_ul_d1 (
        .tx_p(a_ul_d1_p), .tx_n(a_ul_d1_n), .cut_fault(cut_ias_ul_d1), .glitch_inj(1'b0),
        .rx_p(k_ul_d1_p), .rx_n(k_ul_d1_n)
    );

    // Downlink IAS1 channels (Kria -> Artix)
    sim_board_lvds_channel #(
        .DLY_P_PS(1210.0), .DLY_N_PS(1212.0), .JITTER_SPREAD_PS(63.0), .SEED(32'h2200_0001)
    ) u_ch_dl_clk (
        .tx_p(k_dl_clk_p), .tx_n(k_dl_clk_n), .cut_fault(1'b0), .glitch_inj(1'b0),
        .rx_p(a_dl_clk_p), .rx_n(a_dl_clk_n)
    );

    sim_board_lvds_channel #(
        .DLY_P_PS(1175.0), .DLY_N_PS(1174.0), .JITTER_SPREAD_PS(62.0), .SEED(32'h2200_0002)
    ) u_ch_dl_d0 (
        .tx_p(k_dl_d0_p), .tx_n(k_dl_d0_n), .cut_fault(1'b0), .glitch_inj(1'b0),
        .rx_p(a_dl_d0_p), .rx_n(a_dl_d0_n)
    );

    // Rev06 SGMII differential channels (SI §9.7: 50 ps TX / 53 ps RX spread, 1.25 Gbps = 800 ps UI)
    sim_board_lvds_channel #(
        .DLY_P_PS(360.0), .DLY_N_PS(360.0), .JITTER_SPREAD_PS(50.0), .SEED(32'h3300_0001)
    ) u_ch_eth_sgtx (
        .tx_p(a_sgtx_p), .tx_n(a_sgtx_n), .cut_fault(cut_eth_sgtx), .glitch_inj(1'b0),
        .rx_p(p_sgtx_p), .rx_n(p_sgtx_n)
    );

    sim_board_lvds_channel #(
        .DLY_P_PS(380.0), .DLY_N_PS(380.0), .JITTER_SPREAD_PS(53.0), .SEED(32'h3300_0002)
    ) u_ch_eth_sgrx (
        .tx_p(p_sgrx_p), .tx_n(p_sgrx_n), .cut_fault(cut_eth_sgrx), .glitch_inj(1'b0),
        .rx_p(a_sgrx_p), .rx_n(a_sgrx_n)
    );

    // Converter & Peripheral Board Nets
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

    // -------------------------------------------------------------------------
    // 4. Real DUTs: artix_top (Rev06 ENABLE_ETH=1) & kria_pl_link (K26 PL BD IP)
    // -------------------------------------------------------------------------
    artix_top #(
        .DDC_POST_DECIM    (4),
        .LINK_AM_PERIOD    (64),
        .ADC_AUTO_TRAIN    (1'b1),
        .ENABLE_ETH        (1'b1),
        .ETH_BYPASS_AN     (1'b0),
        .ETH_ALIVE_TIMEOUT (25000),
        .ETH_MDIO_RST_CYC  (256),
        .ETH_MDIO_POLL_DIV (1200),
        .ETH_SDR_PKT_BYTES (1024),
        .ETH_SDR_GAP_CYC   (64),
        .ETH_DEFAULT_POLICY(2'd0),
        .CONV_SPI_CLK_DIV  (2),
        .CONV_SPI_RST_CYC  (16),
        .CONV_SPI_AUTO_INIT(1'b1),
        .ADAR_CLK_DIV      (2),
        .ADAR_AUTO_INIT    (1'b1),
        .HK_CLK_DIV        (3),
        .HK_POLL_DIV       (16000),
        .XO_FCAL_WAIT_CYC  (150),
        .XADC_POLL_DIV_P   (500),
        .PPS_DEFAULT_NOM_CYC(32'd1250)
    ) u_artix (
        .fpga_clk_p     (fpga_clk_p),
        .fpga_clk_n     (fpga_clk_n),
        .adcr_d_p       (adcr_d_p),
        .adcr_d_n       (adcr_d_n),
        .adcr_or_p      (adcr_or_p),
        .adcr_or_n      (adcr_or_n),
        .adcr_dco_p     (adcr_dco_p),
        .adcr_dco_n     (adcr_dco_n),
        .adcs_dco_p     (adcs_dco_p),
        .adcs_dco_n     (adcs_dco_n),
        .adcs_fco_p     (adcs_fco_p),
        .adcs_fco_n     (adcs_fco_n),
        .adcs_d0_p      (adcs_d0_p),
        .adcs_d0_n      (adcs_d0_n),
        .adcs_d1_p      (adcs_d1_p),
        .adcs_d1_n      (adcs_d1_n),
        .dacr_clk       (dacr_clk),
        .dacr_d         (dacr_d),
        .dacs_d         (dacs_d),
        .dacs_iqclk     (dacs_iqclk),
        .dacs_iqwrt     (dacs_iqwrt),
        .dacs_iqsel     (dacs_iqsel),
        .dacs_iqreset   (dacs_iqreset),
        .conv_spi_sclk  (conv_spi_sclk),
        .conv_spi_csb_r (conv_spi_csb_r),
        .conv_spi_csb_s (conv_spi_csb_s),
        .conv_spi_sdio  (conv_spi_sdio),
        .adar_sclk      (adar_sclk),
        .adar_sdio      (adar_sdio),
        .adar_sdo       (adar_sdo),
        .adar_csb       (adar_csb),
        .adar_rx_load   (adar_rx_load),
        .adar_tx_load   (adar_tx_load),
        .adar_tr        (adar_tr),
        .sw_ctrl        (sw_ctrl),
        .xo_scl         (xo_scl),
        .xo_sda         (xo_sda),
        .clk_sel        (clk_sel),
        .link_tx_clk_p  (a_dl_clk_p),
        .link_tx_clk_n  (a_dl_clk_n),
        .link_tx_d0_p   (a_dl_d0_p),
        .link_tx_d0_n   (a_dl_d0_n),
        .link_rx_clk_p  (a_ul_clk_p),
        .link_rx_clk_n  (a_ul_clk_n),
        .link_rx_d0_p   (a_ul_d0_p),
        .link_rx_d0_n   (a_ul_d0_n),
        .link_rx_d1_p   (a_ul_d1_p),
        .link_rx_d1_n   (a_ul_d1_n),
        .eth_sgtx_p     (a_sgtx_p),
        .eth_sgtx_n     (a_sgtx_n),
        .eth_sgrx_p     (a_sgrx_p),
        .eth_sgrx_n     (a_sgrx_n),
        .eth_mdc        (eth_mdc),
        .eth_mdio       (eth_mdio),
        .eth_rst_n      (eth_rst_n),
        .pmod_cs_n      (pmod_cs_n),
        .pmod_sclk      (pmod_sclk),
        .pmod_mosi      (pmod_mosi),
        .pmod_miso      (pmod_miso),
        .beam_strobe    (kria_beam_strobe),
        .pps_sync       (kria_pps_sync),
        .pmod_spare1    (kria_spare1),
        .pmod_spare2    (kria_spare2),
        .hk_scl         (hk_scl),
        .hk_sda         (hk_sda),
        .hk_alert_n     (hk_alert_n),
        .fpga_irq       (fpga_irq_pad)
    );

    kria_pl_link u_kria (
        .pl_clk_100m      (pl_clk_100m),
        .pl_resetn        (pl_resetn),
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
        .emio_i2c_scl_i   (emio_i2c_scl_i),
        .emio_i2c_scl_o   (1'b0),
        .emio_i2c_scl_t   (1'b1), // Hi-Z on Kria side so Artix owns HK_SCL
        .emio_i2c_sda_i   (emio_i2c_sda_i),
        .emio_i2c_sda_o   (1'b0),
        .emio_i2c_sda_t   (1'b1),
        .emio_spi_mo      (1'b0),
        .emio_spi_sclk    (1'b0),
        .emio_spi_ssn     (1'b1),
        .emio_spi_mi      (emio_spi_mi),
        .emio_gpio_o      (emio_gpio_o),
        .emio_gpio_t      (emio_gpio_t),
        .emio_gpio_i      (emio_gpio_i),
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

    // Simulation speed-up for both real eye-scan FSMs (768 cyc covers 64-block Clause 49 lock)
    defparam u_kria.u_train_fsm.TAP_DWELL_CYCLES   = 16'd768;
    defparam u_artix.u_dl_train_fsm.TAP_DWELL_CYCLES = 16'd768;

    // -------------------------------------------------------------------------
    // 5. Peripheral, Converter, RF & SGMII PHY Behavioral Models
    // -------------------------------------------------------------------------
    reg [1:0] adcr_mode   = 2'd0;
`ifdef MUTATE_NO_ECHO_RETURN
    reg       no_echo_mut = 1'b1;
`else
    reg       no_echo_mut = 1'b0;
`endif

    sim_ad9484_model #(
        .ECHO_DELAY_DAC_CYC (250),
        .SEED               (32'hA484_1001)
    ) u_ad9484 (
        .clk_400m_adc (clk_400m_adc),
        .dco_true     (dco_true),
        .mode         (adcr_mode),
        .no_echo_mut  (no_echo_mut),
        .dacr_clk     (dacr_clk),
        .dacr_d       (dacr_d),
        .spi_csb      (conv_spi_csb_r),
        .spi_sclk     (conv_spi_sclk),
        .spi_sdio     (conv_spi_sdio),
        .adcr_d_p     (adcr_d_p),
        .adcr_d_n     (adcr_d_n),
        .adcr_or_p    (adcr_or_p),
        .adcr_or_n    (adcr_or_n),
        .adcr_dco_p   (adcr_dco_p),
        .adcr_dco_n   (adcr_dco_n)
    );

    sim_ad9253_model u_ad9253 (
        .spi_csb    (conv_spi_csb_s),
        .spi_sclk   (conv_spi_sclk),
        .spi_sdio   (conv_spi_sdio),
        .adcs_dco_p (adcs_dco_p),
        .adcs_dco_n (adcs_dco_n),
        .adcs_fco_p (adcs_fco_p),
        .adcs_fco_n (adcs_fco_n),
        .adcs_d0_p  (adcs_d0_p),
        .adcs_d0_n  (adcs_d0_n),
        .adcs_d1_p  (adcs_d1_p),
        .adcs_d1_n  (adcs_d1_n)
    );

    wire [31:0] dacr_clk_edges, dacr_timing_errs, dacr_active_samps, dacr_zc1, dacr_zc2;
    wire [7:0]  dacr_max_amp;
    sim_dac_radar_mon u_dac_radar_mon (
        .dacr_clk       (dacr_clk),
        .dacr_d         (dacr_d),
        .clk_edges      (dacr_clk_edges),
        .timing_errs    (dacr_timing_errs),
        .active_samples (dacr_active_samps),
        .zc_first_half  (dacr_zc1),
        .zc_second_half (dacr_zc2),
        .max_amp        (dacr_max_amp)
    );

    wire [31:0] dacs_clk_edges, dacs_wrt_edges, dacs_i_cnt, dacs_q_cnt;
    wire signed [13:0] dacs_last_i, dacs_last_q;
    sim_dac_sdr_mon u_dac_sdr_mon (
        .dacs_iqclk (dacs_iqclk),
        .dacs_iqwrt (dacs_iqwrt),
        .dacs_iqsel (dacs_iqsel),
        .dacs_d     (dacs_d),
        .clk_edges  (dacs_clk_edges),
        .wrt_edges  (dacs_wrt_edges),
        .i_samples  (dacs_i_cnt),
        .q_samples  (dacs_q_cnt),
        .last_i     (dacs_last_i),
        .last_q     (dacs_last_q)
    );

    wire [31:0] adar_tr_viol;
    wire [31:0] adar_tx_load_cnt;
    sim_adar1000_array u_adar (
        .chk_clk     (fpga_clk_p),
        .chk_rst     (~pl_resetn),
        .adar_sclk   (adar_sclk),
        .adar_sdio   (adar_sdio),
        .adar_sdo    (adar_sdo),
        .adar_csb    (adar_csb),
        .adar_rx_load(adar_rx_load),
        .adar_tx_load(adar_tx_load),
        .adar_tr     (adar_tr),
        .tr_viol     (adar_tr_viol),
        .tx_load_cnt (adar_tx_load_cnt)
    );

    sim_hk_i2c_slave #(.SLAVE_ADDR(7'h48), .NUM_REGS(16)) u_tmp1075 (
        .scl(hk_scl), .sda(hk_sda), .enable_ack(1'b1)
    );
    sim_hk_i2c_slave #(.SLAVE_ADDR(7'h50), .NUM_REGS(16)) u_m24c02 (
        .scl(hk_scl), .sda(hk_sda), .enable_ack(1'b1)
    );
    sim_hk_i2c_slave #(.SLAVE_ADDR(7'h55), .NUM_REGS(256)) u_si549 (
        .scl(xo_scl), .sda(xo_sda), .enable_ack(1'b1)
    );

    reg [31:0]  peer_half_ui_fs  = 32'd399960; // +100 ppm relative to 400.000 ps nominal UI/2
    reg         peer_link_rx_cut = 1'b0;
    wire [31:0] mdio_poll_reads, mdio_custom_wrs, eth_fcs_fail;
    wire [31:0] eth_s1_cnt, eth_s2_cnt, eth_max_s1, eth_max_s2;
    wire [1023:0] seen_eth_s1, seen_eth_s2;

    sim_sgmii_phy_peer u_phy_peer (
        .eth_rst_n       (eth_rst_n),
        .eth_mdc         (eth_mdc),
        .eth_mdio        (eth_mdio),
        .eth_sgtx_p      (p_sgtx_p),
        .eth_sgtx_n      (p_sgtx_n),
        .eth_sgrx_p      (p_sgrx_p),
        .eth_sgrx_n      (p_sgrx_n),
        .peer_half_ui_fs (peer_half_ui_fs),
        .peer_rst_n      (pl_resetn),
        .link_rx_cut     (peer_link_rx_cut),
        .mdio_poll_reads (mdio_poll_reads),
        .mdio_custom_wrs (mdio_custom_wrs),
        .eth_fcs_fail    (eth_fcs_fail),
        .eth_s1_cnt      (eth_s1_cnt),
        .eth_s2_cnt      (eth_s2_cnt),
        .seen_eth_s1     (seen_eth_s1),
        .seen_eth_s2     (seen_eth_s2),
        .eth_max_s1      (eth_max_s1),
        .eth_max_s2      (eth_max_s2)
    );

    // -------------------------------------------------------------------------
    // 6. Kria m_axis_rx Drain, Backpressure PRNG & Concurrent Scoreboard
    // -------------------------------------------------------------------------
    reg [31:0] rx_bp_prng = 32'hCAFE_BABE;
    always @(posedge pl_clk_100m) begin
        if (!pl_resetn) begin
            m_axis_rx_tready <= 1'b1;
        end else begin
            rx_bp_prng       <= {rx_bp_prng[30:0], rx_bp_prng[31] ^ rx_bp_prng[21] ^ rx_bp_prng[1] ^ rx_bp_prng[0]};
            m_axis_rx_tready <= rx_bp_prng[0]; // ~50% randomized AXI4-Stream backpressure
        end
    end

    // Register readback (TID=8'h11) capture + Sensor packet counters on Kria m_axis_rx
    integer        rx11_cnt     = 0;
    reg [15:0]     rx11_last_addr = 16'd0;
    reg [31:0]     rx11_last_data = 32'd0;
    reg            rx11_last_err  = 1'b0;

    integer        rx01_pkts    = 0;
    integer        rx02_pkts    = 0;
    integer        rx04_pkts    = 0;
    integer        rx05_pkts    = 0;
    integer        rx_crc_err_pkts = 0;

    reg            sdr_cap_en   = 1'b0;
    reg signed [15:0] sdr_a_max = 16'sd0;
    reg signed [15:0] sdr_b_max = 16'sd0;

    // Radar sample capture buffer (up to 1024 complex baseband samples)
    reg            rad_cap_en   = 1'b0;
    integer        rad_cap_wr   = 0;
    localparam integer RAD_BUF_N = 1024;
    reg signed [15:0] rad_buf_i [0:RAD_BUF_N-1];
    reg signed [15:0] rad_buf_q [0:RAD_BUF_N-1];

    always @(posedge pl_clk_100m) begin
        if (pl_resetn && m_axis_rx_tvalid && m_axis_rx_tready) begin
            if (m_axis_rx_tlast && m_axis_rx_tuser[0])
                rx_crc_err_pkts <= rx_crc_err_pkts + 1;

            if (m_axis_rx_tid == 8'h11 && m_axis_rx_tlast) begin
                rx11_last_addr <= m_axis_rx_tdata[47:32];
                rx11_last_data <= m_axis_rx_tdata[31:0];
                rx11_last_err  <= m_axis_rx_tuser[0];
                rx11_cnt       <= rx11_cnt + 1;
            end else if (m_axis_rx_tid == 8'h01) begin
                if (rad_cap_en && rad_cap_wr < RAD_BUF_N - 1) begin
                    rad_buf_i[rad_cap_wr]     <= $signed(m_axis_rx_tdata[15:0]);
                    rad_buf_q[rad_cap_wr]     <= $signed(m_axis_rx_tdata[31:16]);
                    rad_buf_i[rad_cap_wr + 1] <= $signed(m_axis_rx_tdata[47:32]);
                    rad_buf_q[rad_cap_wr + 1] <= $signed(m_axis_rx_tdata[63:48]);
                    rad_cap_wr                <= rad_cap_wr + 2;
                end
                if (m_axis_rx_tlast && !m_axis_rx_tuser[0])
                    rx01_pkts <= rx01_pkts + 1;
            end else if (m_axis_rx_tid == 8'h02) begin
                if (m_axis_rx_tlast && !m_axis_rx_tuser[0])
                    rx02_pkts <= rx02_pkts + 1;
            end else if (m_axis_rx_tid == 8'h04) begin
                if (sdr_cap_en) begin
                    if ($signed(m_axis_rx_tdata[15:0])  > sdr_a_max) sdr_a_max <= $signed(m_axis_rx_tdata[15:0]);
                    if (-$signed(m_axis_rx_tdata[15:0]) > sdr_a_max) sdr_a_max <= -$signed(m_axis_rx_tdata[15:0]);
                    if ($signed(m_axis_rx_tdata[31:16]) > sdr_a_max) sdr_a_max <= $signed(m_axis_rx_tdata[31:16]);
                    if (-$signed(m_axis_rx_tdata[31:16]) > sdr_a_max) sdr_a_max <= -$signed(m_axis_rx_tdata[31:16]);
                    if ($signed(m_axis_rx_tdata[47:32]) > sdr_a_max) sdr_a_max <= $signed(m_axis_rx_tdata[47:32]);
                    if (-$signed(m_axis_rx_tdata[47:32]) > sdr_a_max) sdr_a_max <= -$signed(m_axis_rx_tdata[47:32]);
                    if ($signed(m_axis_rx_tdata[63:48]) > sdr_a_max) sdr_a_max <= $signed(m_axis_rx_tdata[63:48]);
                    if (-$signed(m_axis_rx_tdata[63:48]) > sdr_a_max) sdr_a_max <= -$signed(m_axis_rx_tdata[63:48]);
                end
                if (m_axis_rx_tlast && !m_axis_rx_tuser[0])
                    rx04_pkts <= rx04_pkts + 1;
            end else if (m_axis_rx_tid == 8'h05) begin
                if (sdr_cap_en) begin
                    if ($signed(m_axis_rx_tdata[15:0])  > sdr_b_max) sdr_b_max <= $signed(m_axis_rx_tdata[15:0]);
                    if (-$signed(m_axis_rx_tdata[15:0]) > sdr_b_max) sdr_b_max <= -$signed(m_axis_rx_tdata[15:0]);
                    if ($signed(m_axis_rx_tdata[31:16]) > sdr_b_max) sdr_b_max <= $signed(m_axis_rx_tdata[31:16]);
                    if (-$signed(m_axis_rx_tdata[31:16]) > sdr_b_max) sdr_b_max <= -$signed(m_axis_rx_tdata[31:16]);
                    if ($signed(m_axis_rx_tdata[47:32]) > sdr_b_max) sdr_b_max <= $signed(m_axis_rx_tdata[47:32]);
                    if (-$signed(m_axis_rx_tdata[47:32]) > sdr_b_max) sdr_b_max <= -$signed(m_axis_rx_tdata[47:32]);
                    if ($signed(m_axis_rx_tdata[63:48]) > sdr_b_max) sdr_b_max <= $signed(m_axis_rx_tdata[63:48]);
                    if (-$signed(m_axis_rx_tdata[63:48]) > sdr_b_max) sdr_b_max <= -$signed(m_axis_rx_tdata[63:48]);
                end
                if (m_axis_rx_tlast && !m_axis_rx_tuser[0])
                    rx05_pkts <= rx05_pkts + 1;
            end
        end
    end

    // IAS1 PCS RX sequence bitmap in MIRROR window (for 0-loss ETH+IAS1 merge check)
    reg           ias_sb_clr = 1'b0;
    reg [1023:0]  seen_ias_s1 = 1024'd0;
    reg [1023:0]  seen_ias_s2 = 1024'd0;
    reg [31:0]    ias_min_s1  = 32'hFFFF_FFFF, ias_max_s1 = 32'd0;
    reg [31:0]    ias_min_s2  = 32'hFFFF_FFFF, ias_max_s2 = 32'd0;
    integer       ias_s1_cnt  = 0, ias_s2_cnt = 0;

    always @(posedge u_kria.rx_clkdiv) begin
        if (ias_sb_clr) begin
            seen_ias_s1 <= 1024'd0;
            seen_ias_s2 <= 1024'd0;
            ias_min_s1  <= 32'hFFFF_FFFF;
            ias_max_s1  <= 32'd0;
            ias_min_s2  <= 32'hFFFF_FFFF;
            ias_max_s2  <= 32'd0;
            ias_s1_cnt  <= 0;
            ias_s2_cnt  <= 0;
        end else if (u_kria.u_link_axis.rx_pkt_done_valid && u_kria.u_link_axis.rx_pkt_done_ok) begin
            if (u_kria.u_link_axis.active_sid == 8'h01) begin
                seen_ias_s1[u_kria.u_link_axis.last_rx_seq[9:0]] <= 1'b1;
                if (u_kria.u_link_axis.last_rx_seq < ias_min_s1) ias_min_s1 <= u_kria.u_link_axis.last_rx_seq;
                if (u_kria.u_link_axis.last_rx_seq > ias_max_s1) ias_max_s1 <= u_kria.u_link_axis.last_rx_seq;
                ias_s1_cnt <= ias_s1_cnt + 1;
            end else if (u_kria.u_link_axis.active_sid == 8'h02) begin
                seen_ias_s2[u_kria.u_link_axis.last_rx_seq[9:0]] <= 1'b1;
                if (u_kria.u_link_axis.last_rx_seq < ias_min_s2) ias_min_s2 <= u_kria.u_link_axis.last_rx_seq;
                if (u_kria.u_link_axis.last_rx_seq > ias_max_s2) ias_max_s2 <= u_kria.u_link_axis.last_rx_seq;
                ias_s2_cnt <= ias_s2_cnt + 1;
            end
        end
    end

    // -------------------------------------------------------------------------
    // 7. AXI4-Lite & AXI4-Stream BFM Helper Tasks
    // -------------------------------------------------------------------------
    integer fails = 0;

    task fail_msg;
        input [8*96-1:0] msg;
        begin
            $display("FAIL @ %0t ps: %0s", $time, msg);
            fails = fails + 1;
        end
    endtask

    task axil_wr;
        input [7:0]  addr;
        input [31:0] data;
        begin
            @(posedge pl_clk_100m);
            s_axi_awaddr  <= addr;
            s_axi_awvalid <= 1'b1;
            s_axi_wdata   <= data;
            s_axi_wstrb   <= 4'hF;
            s_axi_wvalid  <= 1'b1;
            s_axi_bready  <= 1'b1;
            begin : wait_aw_w
                reg aw_done, w_done;
                aw_done = 1'b0;
                w_done  = 1'b0;
                while (!(aw_done && w_done)) begin
                    @(posedge pl_clk_100m);
                    if (s_axi_awvalid && s_axi_awready) begin
                        s_axi_awvalid <= 1'b0;
                        aw_done = 1'b1;
                    end
                    if (s_axi_wvalid && s_axi_wready) begin
                        s_axi_wvalid <= 1'b0;
                        w_done = 1'b1;
                    end
                end
            end
            while (!s_axi_bvalid) @(posedge pl_clk_100m);
            @(posedge pl_clk_100m);
        end
    endtask

    task axil_rd;
        input  [7:0]  addr;
        output [31:0] data;
        begin
            @(posedge pl_clk_100m);
            s_axi_araddr  <= addr;
            s_axi_arvalid <= 1'b1;
            s_axi_rready  <= 1'b1;
            while (!s_axi_arready) @(posedge pl_clk_100m);
            @(posedge pl_clk_100m);
            s_axi_arvalid <= 1'b0;
            while (!s_axi_rvalid) @(posedge pl_clk_100m);
            data = s_axi_rdata;
            @(posedge pl_clk_100m);
        end
    endtask

    task kria_axis_tx_word;
        input [7:0]  tid;
        input [63:0] data;
        input        tlast;
        input [15:0] tuser_len;
        begin
            @(posedge pl_clk_100m);
            s_axis_tx_tdata  <= data;
            s_axis_tx_tkeep  <= 8'hFF;
            s_axis_tx_tid    <= tid;
            s_axis_tx_tuser  <= tuser_len;
            s_axis_tx_tlast  <= tlast;
            s_axis_tx_tvalid <= 1'b1;
            @(posedge pl_clk_100m);
            while (!s_axis_tx_tready) @(posedge pl_clk_100m);
            s_axis_tx_tvalid <= 1'b0;
            s_axis_tx_tlast  <= 1'b0;
        end
    endtask

    task kria_reg_wr;
        input [15:0] addr;
        input [31:0] wdata;
        begin
            kria_axis_tx_word(8'h10, {8'h01, 8'h00, addr, wdata}, 1'b1, 16'd8);
            #1_200_000; // Allow downlink PCS serialization + CDC across 125 MHz domain
        end
    endtask

    task kria_reg_rd;
        input  [15:0] addr;
        output [31:0] rdata;
        integer seq0, tmo;
        begin
            seq0 = rx11_cnt;
            kria_axis_tx_word(8'h10, {8'h02, 8'h00, addr, 32'd0}, 1'b1, 16'd8);
            tmo = 0;
            while ((rx11_cnt == seq0 || rx11_last_addr != addr) && tmo < 4000) begin
                @(posedge pl_clk_100m);
                tmo = tmo + 1;
            end
            if (rx11_cnt == seq0 || rx11_last_addr != addr) begin
                $display("FAIL @ %0t ps: kria_reg_rd timeout on addr 0x%04h [la_pkt=%0d la_wr=%0d la_rd=%0d rx2pl_w=%0d rx2pl_r=%0d d_sid=%h d_len=%0d mv=%b ml=%b mtid=%h md=%h]",
                         $time, addr,
                         u_kria.u_link_axis.pkt_cnt_rx_reg,
                         u_kria.u_link_axis.rx_wr_ptr, u_kria.u_link_axis.rx_rd_ptr,
                         u_kria.u_fifo_rx2pl.wr_bin, u_kria.u_fifo_rx2pl.rd_bin,
                         u_kria.u_pcs_rx.out_stream_id, u_kria.u_pcs_rx.out_len,
                         m_axis_rx_tvalid, m_axis_rx_tlast, m_axis_rx_tid, m_axis_rx_tdata);
                fails = fails + 1;
                rdata = 32'hDEAD_C0DE;
            end else begin
                rdata = rx11_last_data;
            end
        end
    endtask

    task kria_send_sdr_pkt;
        input integer base_val;
        integer wi;
        reg signed [15:0] i0, q0, i1, q1;
        begin
            for (wi = 0; wi < 4; wi = wi + 1) begin
                i0 = base_val + wi * 64 + 16;
                q0 = -(base_val + wi * 32 + 8);
                i1 = base_val + wi * 64 + 48;
                q1 = -(base_val + wi * 32 + 24);
                kria_axis_tx_word(8'h12, {q1, i1, q0, i0}, (wi == 3), (wi == 0) ? 16'd32 : 16'd0);
            end
        end
    endtask

    // -------------------------------------------------------------------------
    // 8. Whole-System Execution Across Scenarios 1 .. 6
    // -------------------------------------------------------------------------
    reg [31:0] csr_r, art_r, pre_fcs;
    integer    tmo_cnt, k, wi;
    real       noise_sum, noise_rms, echo_peak, echo_snr;
    real       dft_re, dft_im, pwr_pos, pwr_img, img_rej_db;
    integer    lost_s1, lost_s2, uniq_s1, uniq_s2;
    reg [1023:0] merged_s1, merged_s2;
    reg [31:0] chk_min_s1, chk_max_s1, chk_min_s2, chk_max_s2;
    integer    s0_rx01, s0_eth_s2;
    reg        retrain_saw_drop;
    integer    post_crc_errs;

    initial begin
        // Pre-seed housekeeping I2C peripherals
        u_tmp1075.mem[0] = 8'h2A;
        u_tmp1075.mem[1] = 8'h80;
        u_m24c02.mem[0]  = 8'hC3;

        pl_resetn = 1'b0;
        #250_000; // 250 ns global reset
        pl_resetn = 1'b1;

        // =====================================================================
        // SCENARIO 1: Power-Up & Dual Link Training (+100 ppm Clock Skew)
        // =====================================================================
        $display("[S1] Waiting for Kria uplink eye training, Artix dl_link_up, AD9484 train & SGMII AN...");
        // Track Artix Clause 37 AN state machine on behavioral RTL8211FSI peer
        begin : an_handshake
            integer an_tmo;
            an_tmo = 0;
            while ((u_artix.gen_rev06_eth.u_eth_phy.an_state == 2'd0) && (an_tmo < 300)) begin
                #200_000;
                an_tmo = an_tmo + 1;
            end
            u_phy_peer.set_an_mode(2'd1); // Acknowledge /C/ Ack=1
            an_tmo = 0;
            while ((u_artix.gen_rev06_eth.u_eth_phy.an_state != 2'd2) && (an_tmo < 200)) begin
                #200_000;
                an_tmo = an_tmo + 1;
            end
            u_phy_peer.set_an_mode(2'd2); // Enter normal 8b/10b IDLE / Data
        end

        tmo_cnt = 0;
        csr_r   = 32'd0;
        while (((!csr_r[6]) || (!csr_r[21]) || (!u_artix.dl_up_sync[1]) ||
                (!u_artix.eth_link_up_stat) || (mdio_poll_reads == 32'd0)) && (tmo_cnt < 1500)) begin
            #1_000_000; // 1 us polling interval -> up to 1.5 ms timeout
            axil_rd(8'h04, csr_r);
            tmo_cnt = tmo_cnt + 1;
        end
        if (!csr_r[6] || !csr_r[21])
            fail_msg("S1: Kria REG_LINK_STATUS did not report link_up & adc_trained");
        if (!u_artix.dl_up_sync[1])
            fail_msg("S1: Artix dl_link_up did not lock");
        if (!u_artix.eth_link_up_stat || mdio_poll_reads == 32'd0)
            fail_msg("S1: SGMII AN or MDIO poll did not complete");
        if (!irq_link_up)
            fail_msg("S1: irq_link_up not asserted");
        $display("[S1] PASS REG_LINK_STATUS=0x%08h mdio_polls=%0d dl_up=%b eth_up=%b",
                 csr_r, mdio_poll_reads, u_artix.dl_up_sync[1], u_artix.eth_link_up_stat);
        if (fails > 0) begin
            $display("FAIL: tb_system aborting early after S1 failure");
            $fatal(1, "tb_system S1 failed");
        end

        // =====================================================================
        // SCENARIO 2: Housekeeping, Clocks & Safety (s_axis_tx 0x10 -> 0x11)
        // =====================================================================
        // 2a. Wait for conv_init_done & adar_init_done over real IAS1 0x10->0x11
        tmo_cnt = 0;
        art_r   = 32'd0;
        while ((!art_r[16]) && (tmo_cnt < 100)) begin
            kria_reg_rd(16'h0038, art_r);
            tmo_cnt = tmo_cnt + 1;
        end
        if (art_r[31:24] !== 8'h8F || !art_r[16] || art_r[17])
            fail_msg("S2: AD9253 conv_init / Chip ID 0x8F mismatch");

        // Read AD9484 Chip ID (0x6C) over shared 3-wire SPI
        kria_reg_wr(16'h003C, 32'h8020_0100);
        tmo_cnt = 0;
        art_r   = 32'd0;
        while (!art_r[8] && tmo_cnt < 50) begin
            kria_reg_rd(16'h0040, art_r);
            tmo_cnt = tmo_cnt + 1;
        end
        if (art_r[7:0] !== 8'h6C)
            fail_msg("S2: AD9484 SPI ID readback != 0x6C");

        // 2b. ADAR1000 init + Beam #3 write/load + RF switch sw_ctrl=4'b1010 + TR safety
        tmo_cnt = 0;
        art_r   = 32'd0;
        while (!art_r[0] && tmo_cnt < 120) begin
            kria_reg_rd(16'h0090, art_r);
            tmo_cnt = tmo_cnt + 1;
        end
        if (!art_r[0] || art_r[1])
            fail_msg("S2: ADAR1000 auto-init failed");
        kria_reg_wr(16'h0088, 32'h8003_005A); // Write custom Beam #3 Chip 0 Byte 0
        kria_reg_wr(16'h007C, 32'h0000_0A43); // sw_ctrl=1010, soft_load=1, active_beam=3
        tmo_cnt = 0;
        art_r   = 32'd0;
        while ((art_r[2] || !art_r[4]) && tmo_cnt < 80) begin
            kria_reg_rd(16'h0090, art_r);
            tmo_cnt = tmo_cnt + 1;
        end
        if (art_r[22:19] !== 4'b1010 || art_r[9:5] !== 5'd3 || adar_tx_load_cnt == 32'd0 || adar_tr_viol)
            fail_msg("S2: ADAR Beam #3 / sw_ctrl=1010 / tr_viol check failed");

        // 2c. TMP1075 (0x48 = 0x2A80 raw, 0x00A0 req_rdata={LSB,MSB}=0x802A) & NACK trap (0x7D)
        kria_reg_wr(16'h009C, 32'd0);
        kria_reg_wr(16'h0098, 32'h8000_08C8); // 7'h48 wr=1 rd=2
        tmo_cnt = 0;
        art_r   = 32'hFFFF_FFFF;
        while (art_r[18] && tmo_cnt < 250) begin
            kria_reg_rd(16'h00A0, art_r);
            tmo_cnt = tmo_cnt + 1;
        end
        if (art_r[15:0] !== 16'h802A || art_r[17])
            fail_msg("S2: TMP1075 0x48 read != 0x802A (0x2A80)");

        kria_reg_wr(16'h0098, 32'h8000_04FD); // Missing slave 7'h7D
        tmo_cnt = 0;
        art_r   = 32'hFFFF_FFFF;
        while (art_r[18] && tmo_cnt < 150) begin
            kria_reg_rd(16'h00A0, art_r);
            tmo_cnt = tmo_cnt + 1;
        end
        kria_reg_rd(16'h00A4, csr_r);
        if (!art_r[17] || csr_r[31:16] == 16'd0)
            fail_msg("S2: Missing-ACK slave 0x7D did not set ack_err_cnt");

        // 2d. Si549 500 MHz XO programming & CLK_SEL pin check
        kria_reg_wr(16'h00A8, 32'h0000_0006); // use_ext_clk=0 (Si549), prog_freq_500m=1, prog_start=1
        tmo_cnt = 0;
        art_r   = 32'd0;
        while (!art_r[9] && tmo_cnt < 300) begin
            kria_reg_rd(16'h00A8, art_r);
            tmo_cnt = tmo_cnt + 1;
        end
        if (!art_r[9] || !art_r[10] || art_r[11] || (clk_sel !== 1'b1))
            fail_msg("S2: Si549 500 MHz XO / clk_sel Hi-Z failed");
        kria_reg_wr(16'h00A8, 32'h0000_0003); // Verify external SMA clk_sel drives 0
        if (clk_sel !== 1'b0)
            fail_msg("S2: clk_sel external override did not drive 0");
        kria_reg_wr(16'h00A8, 32'h0000_0002); // Restore internal Si549 (Hi-Z -> 1)

        // 2e. XADC valid + PPS 1251-cycle -> +800 ppm measurement
        kria_reg_rd(16'h00B8, art_r);
        if (!art_r[24] || art_r[11:0] == 12'd0)
            fail_msg("S2: XADC telemetry invalid");

        // Send 2 rising edges on pmod_pps_sync spaced by exact 1251 Artix link_clk (8 ns) cycles
        kria_reg_wr(16'h00C4, 32'd1250);
        @(posedge u_artix.link_clk);
        emio_gpio_o[2] <= 1'b1;
        repeat (4) @(posedge u_artix.link_clk);
        emio_gpio_o[2] <= 1'b0;
        repeat (1247) @(posedge u_artix.link_clk); // Total period = 4 + 1247 = 1251 cycles
        emio_gpio_o[2] <= 1'b1;
        repeat (4) @(posedge u_artix.link_clk);
        emio_gpio_o[2] <= 1'b0;
        #200_000;
        kria_reg_rd(16'h00C8, art_r);
        kria_reg_rd(16'h00CC, csr_r);
        if (art_r !== 32'd1251 || $signed(csr_r) !== 32'sd800) begin
            $display("[S2] PPS meas=%0d ppm=%0d", art_r, $signed(csr_r));
            fail_msg("S2: PPS 1251-cycle +800 ppm measurement mismatch");
        end
        $display("[S2] PASS AD9253=0x8F AD9484=0x6C TMP1075=0x2A80 PPS=%0d(+%0d ppm)",
                 art_r, $signed(csr_r));

        // =====================================================================
        // SCENARIO 3: Radar Chirp Out (AD9708) -> RF Echo & CW Image Rejection
        // =====================================================================
        emio_gpio_o[3] <= 1'b0; // Release pmod_spare1 to enable Artix DDC uplink stream
        adcr_mode  = 2'd2; // Closed-loop RF echo mode
        rad_cap_wr = 0;
        rad_cap_en = 1'b1;
        #2_500_000; // Wait 2.5 us pre-chirp noise floor samples (~62 samples @ 25 MSPS)

        kria_reg_wr(16'h0058, 32'h0500_0000); // f0
        kria_reg_wr(16'h005C, 32'h0008_0000); // df positive sweep
        kria_reg_wr(16'h0060, 32'h0000_0200); // 512 DAC clocks (4.096 us pulse = 256+256 halves)
        kria_reg_wr(16'h0064, 32'h0000_0800); // PRI 2048 clocks (16.4 us)
        kria_reg_wr(16'h0054, 32'h00FF_0003); // amp=255, trig=1, enable=1

        #10_500_000; // Wait 10.5 us covering 4.1 us chirp + 2.0 us target echo + DDC/IAS1 latency
        rad_cap_en = 1'b0;

        if (dacr_timing_errs != 32'd0 || dacr_zc2 <= dacr_zc1 || dacr_max_amp < 8'd80)
            fail_msg("S3: AD9708 chirp timing/slope/amplitude check failed");

        noise_sum = 0.0;
        echo_peak = 0.0;
        for (k = 0; k < rad_cap_wr; k = k + 1) begin
            if (k < 48) begin
                noise_sum = noise_sum + $sqrt($itor(rad_buf_i[k])*$itor(rad_buf_i[k]) +
                                              $itor(rad_buf_q[k])*$itor(rad_buf_q[k]));
            end else begin
                if ($sqrt($itor(rad_buf_i[k])*$itor(rad_buf_i[k]) +
                          $itor(rad_buf_q[k])*$itor(rad_buf_q[k])) > echo_peak)
                    echo_peak = $sqrt($itor(rad_buf_i[k])*$itor(rad_buf_i[k]) +
                                      $itor(rad_buf_q[k])*$itor(rad_buf_q[k]));
            end
        end
        noise_rms = (noise_sum / 48.0);
        if (noise_rms < 1.0) noise_rms = 1.0;
        echo_snr = echo_peak / noise_rms;
        if (rad_cap_wr < 120 || echo_snr < 4.0) begin
            $display("[S3a] rad_cap=%0d noise_avg=%0f echo_peak=%0f snr=%0fx",
                     rad_cap_wr, noise_rms, echo_peak, echo_snr);
            fail_msg("S3: Closed-loop target echo peak not detected above noise floor");
        end

        // 3b. 121.5625 MHz CW IF -> +1.5625 MHz @ 25 MSPS -> bin +4 in 64-pt DFT (>= 50 dB image rej)
        adcr_mode = 2'd1;
        #3_000_000; // Flush DDC FIR pipeline for CW steady-state
        rad_cap_wr = 0;
        rad_cap_en = 1'b1;
        tmo_cnt = 0;
        while (rad_cap_wr < 128 && tmo_cnt < 500) begin
            #100_000;
            tmo_cnt = tmo_cnt + 1;
        end
        rad_cap_en = 1'b0;

        // Evaluate 64-pt complex DFT at bin 60 (-1.5625 MHz signal per tb_e2e) & bin 4 (+1.5625 MHz image)
        dft_re = 0.0; dft_im = 0.0;
        for (k = 0; k < 64; k = k + 1) begin
            dft_re = dft_re + $itor(rad_buf_i[16+k])*$cos(2.0*PI*60.0*k/64.0) +
                              $itor(rad_buf_q[16+k])*$sin(2.0*PI*60.0*k/64.0);
            dft_im = dft_im + $itor(rad_buf_q[16+k])*$cos(2.0*PI*60.0*k/64.0) -
                              $itor(rad_buf_i[16+k])*$sin(2.0*PI*60.0*k/64.0);
        end
        pwr_pos = dft_re*dft_re + dft_im*dft_im;

        dft_re = 0.0; dft_im = 0.0;
        for (k = 0; k < 64; k = k + 1) begin
            dft_re = dft_re + $itor(rad_buf_i[16+k])*$cos(2.0*PI*4.0*k/64.0) +
                              $itor(rad_buf_q[16+k])*$sin(2.0*PI*4.0*k/64.0);
            dft_im = dft_im + $itor(rad_buf_q[16+k])*$cos(2.0*PI*4.0*k/64.0) -
                              $itor(rad_buf_i[16+k])*$sin(2.0*PI*4.0*k/64.0);
        end
        pwr_img = dft_re*dft_re + dft_im*dft_im;
        if (pwr_img < 1.0) pwr_img = 1.0;
        img_rej_db = 10.0 * $log10(pwr_pos / pwr_img);
        if (img_rej_db < 50.0) begin
            $display("[S3b] img_rej_db=%0f dB (pwr_pos=%0e pwr_img=%0e)", img_rej_db, pwr_pos, pwr_img);
            fail_msg("S3: CW DDC image rejection < 50 dB");
        end
        kria_reg_wr(16'h0054, 32'h0000_0000); // Disable chirp generator
        $display("[S3] PASS chirp zc1=%0d->zc2=%0d echo_snr=%0.1fx cw_img_rej=%0.1f dB",
                 dacr_zc1, dacr_zc2, echo_snr, img_rej_db);

        // =====================================================================
        // SCENARIO 4: SDR RX (AD9253 0x04/0x05) & SDR TX (0x12 -> AD9767)
        // =====================================================================
        kria_reg_wr(16'h0044, 32'h2000_0000); // Ch A NCO = 6.25 MHz @ 50 MSPS
        kria_reg_wr(16'h0048, 32'h4000_0000); // Ch B NCO = 12.5 MHz @ 50 MSPS
        kria_reg_wr(16'h004C, 32'h0008_0004); // 8 words/pkt, decim=4
        sdr_cap_en = 1'b1;
        kria_reg_wr(16'h0034, 32'h0000_000D); // Enable ADCS capture + Ch A/B

        tmo_cnt = 0;
        while ((rx04_pkts < 2 || rx05_pkts < 2) && tmo_cnt < 200) begin
            #200_000;
            tmo_cnt = tmo_cnt + 1;
        end
        sdr_cap_en = 1'b0;
        kria_reg_wr(16'h0034, 32'h0000_0000); // Pause SDR RX before Scenario 5
        if (rx04_pkts < 2 || rx05_pkts < 2 || sdr_a_max < 16'sd50 || sdr_b_max < 16'sd50)
            fail_msg("S4: AD9253 SDR RX TID=0x04/0x05 missing or zero-amplitude");

        // Pre-fill DAC SDR FIFO via s_axis_tx TID=8'h12 before enabling TX
        kria_send_sdr_pkt(1024);
        kria_send_sdr_pkt(1536);
        kria_send_sdr_pkt(2048);
        kria_send_sdr_pkt(2560);
        #500_000;
        kria_reg_wr(16'h0070, 32'h0000_0001); // Enable AD9767 TX
        tmo_cnt = 0;
        while ((dacs_i_cnt < 32'd16 || dacs_q_cnt < 32'd16) && tmo_cnt < 100) begin
            #100_000;
            tmo_cnt = tmo_cnt + 1;
        end
        kria_reg_wr(16'h0070, 32'h0000_0000);
        if (dacs_i_cnt < 32'd16 || dacs_q_cnt < 32'd16 || dacs_last_i == 14'sd0)
            fail_msg("S4: AD9767 s_axis_tx TID=0x12 IQ capture failed");
        $display("[S4] PASS rx04=%0d(max=%0d) rx05=%0d(max=%0d) dacs_i=%0d dacs_q=%0d",
                 rx04_pkts, sdr_a_max, rx05_pkts, sdr_b_max, dacs_i_cnt, dacs_q_cnt);

        // =====================================================================
        // SCENARIO 5: Concurrent IAS1 + Ethernet, Poisoned FCS, Cuts -> lost==0
        // =====================================================================
        // 5a. Clean SPLIT (policy=0): 0x01 -> IAS1 m_axis_rx, 0x02 -> SGMII eth_s2_cnt
        u_phy_peer.send_udp_frame(16'hA55B, 16'h0000, 32'd0, 32'd0, 1'b0); // Arm ETH keepalive
        #5_000_000;
        s0_rx01   = rx01_pkts;
        s0_eth_s2 = eth_s2_cnt;
        #25_000_000; // 25 us concurrent traffic
        if (rx01_pkts <= s0_rx01 || eth_s2_cnt <= s0_eth_s2)
            fail_msg("S5: Concurrent SPLIT missing 0x01 IAS1 or 0x02 ETH traffic");

        // 5b. Poisoned FCS rejection + ETH cut failover (ETH_ALIVE_TIMEOUT = 200 us)
        pre_fcs = u_artix.gen_rev06_eth.u_eth_mac.fcs_err_cnt;
        u_phy_peer.send_udp_frame(16'hA55A, 16'h0000, 32'h0000_0005, 32'd1, 1'b1);
        #5_000_000;
        if (u_artix.gen_rev06_eth.u_eth_mac.fcs_err_cnt == pre_fcs ||
            u_artix.gen_rev06_eth.eth_policy !== 2'd0)
            fail_msg("S5: Poisoned FCS UDP frame was not rejected");

        peer_link_rx_cut = 1'b1; // Stop keepalives + ETH RX -> expire ETH_ALIVE_TIMEOUT
        #215_000_000; // > 200 us ETH_ALIVE_TIMEOUT
        s0_rx01 = rx02_pkts;
        #20_000_000;
        if (rx02_pkts <= s0_rx01) begin
            $display("[DBG5b] rx02=%0d(was %0d) rx01=%0d k_up=%b dl_up=%b ias_ok=%b eth_ok=%b rem=%b seen=%b pol=%0d fov=%0d ias_v=%b ias_r=%b",
                     rx02_pkts, s0_rx01, rx01_pkts, u_kria.kria_link_up, u_artix.dl_up_sync[1],
                     u_artix.gen_rev06_eth.ias_path_ok, u_artix.gen_rev06_eth.eth_path_ok,
                     u_artix.eth_remote_alive_stat, u_artix.gen_rev06_eth.eth_seen_remote_alive,
                     u_artix.gen_rev06_eth.eth_policy, u_artix.gen_rev06_eth.u_dual_mux.failover_cnt,
                     u_artix.ias_mux_valid, u_artix.ias_mux_ready);
            fail_msg("S5: ETH cut did not fail stream 0x02 over to IAS1");
        end
        peer_link_rx_cut = 1'b0;
        u_phy_peer.send_udp_frame(16'hA55B, 16'h0000, 32'd0, 32'd2, 1'b0); // Restore keepalive
        #5_000_000;

        // 5c. Switch PL & SGMII peer to -100 ppm skew, MIRROR_1P1, UDP MDIO write, mid-run cuts
        pl_half_ps      = 5000.500;
        peer_half_ui_fs = 32'd400040;
        u_phy_peer.send_udp_frame(16'hA55A, 16'h0000, 32'h0000_0005, 32'd3, 1'b0); // MIRROR_1P1
        u_phy_peer.send_udp_frame(16'hA55A, 16'h0004, {10'd0, 1'b1, 5'd16, 16'h1234}, 32'd4, 1'b0);
        #65_000_000; // Wait for MDIO write completion
        if (mdio_custom_wrs == 32'd0 || u_phy_peer.phy_regs[16] !== 16'h1234)
            fail_msg("S5: UDP MDIO write to PHY reg 16 failed");

        // Clear IAS1 MIRROR bitmap and run synchronized MIRROR + cut sequence
        @(posedge u_kria.rx_clkdiv);
        ias_sb_clr <= 1'b1;
        @(posedge u_kria.rx_clkdiv);
        ias_sb_clr <= 1'b0;
        #20_000_000; // 20 us healthy MIRROR

        // Cut ETH TX+RX for 25 us (IAS1 delivers 100%)
        cut_eth_sgtx     = 1'b1;
        peer_link_rx_cut = 1'b1;
        #25_000_000;
        cut_eth_sgtx     = 1'b0;
        peer_link_rx_cut = 1'b0;
        u_phy_peer.send_udp_frame(16'hA55B, 16'h0000, 32'd0, 32'd5, 1'b0);
        #20_000_000; // Re-overlap before IAS1 cut

        // Cut IAS1 data lanes for 25 us (ETH delivers 100%)
        cut_ias_ul_d0 = 1'b1;
        cut_ias_ul_d1 = 1'b1;
        #25_000_000;
        cut_ias_ul_d0 = 1'b0;
        cut_ias_ul_d1 = 1'b0;
        tmo_cnt = 0;
        csr_r   = 32'd0;
        while (!csr_r[6] && tmo_cnt < 100) begin
            #2_000_000;
            axil_rd(8'h04, csr_r);
            tmo_cnt = tmo_cnt + 1;
        end
        #10_000_000;

        // Snapshot target sequence window once IAS1 recovers, then wait for
        // u_fifo_eth (1024-word @ 1 Gbps backlog) to drain queued packets up to chk_max.
        chk_min_s1 = ias_min_s1;
        chk_max_s1 = ias_max_s1;
        chk_min_s2 = ias_min_s2;
        chk_max_s2 = ias_max_s2;
        tmo_cnt = 0;
        while ((($signed(eth_max_s1) < $signed(chk_max_s1)) ||
                ($signed(eth_max_s2) < $signed(chk_max_s2))) &&
               (tmo_cnt < 120)) begin
            #1_000_000;
            tmo_cnt = tmo_cnt + 1;
        end

        // Evaluate contiguous merged unique sequence coverage across IAS1 + ETH
        merged_s1 = seen_ias_s1 | seen_eth_s1;
        merged_s2 = seen_ias_s2 | seen_eth_s2;
        uniq_s1 = 0;
        uniq_s2 = 0;
        if (($signed(chk_max_s1) >= $signed(chk_min_s1)) && (ias_s1_cnt > 0)) begin
            for (k = chk_min_s1; k <= chk_max_s1; k = k + 1)
                if (merged_s1[k[9:0]]) uniq_s1 = uniq_s1 + 1;
            lost_s1 = (chk_max_s1 - chk_min_s1 + 1) - uniq_s1;
        end else begin
            lost_s1 = 999;
        end
        if (($signed(chk_max_s2) >= $signed(chk_min_s2)) && (ias_s2_cnt > 0)) begin
            for (k = chk_min_s2; k <= chk_max_s2; k = k + 1)
                if (merged_s2[k[9:0]]) uniq_s2 = uniq_s2 + 1;
            lost_s2 = (chk_max_s2 - chk_min_s2 + 1) - uniq_s2;
        end else begin
            lost_s2 = 999;
        end
        if (lost_s1 != 0 || lost_s2 != 0) begin
            $display("[S5] lost_s1=%0d (%0d..%0d) lost_s2=%0d (%0d..%0d) ias_c=(%0d,%0d) eth_c=(%0d,%0d) eth_max=(%0d,%0d) fcs_fail=%0d k_up=%b pkts=%0d",
                     lost_s1, chk_min_s1, chk_max_s1, lost_s2, chk_min_s2, chk_max_s2,
                     ias_s1_cnt, ias_s2_cnt, eth_s1_cnt, eth_s2_cnt,
                     eth_max_s1, eth_max_s2, eth_fcs_fail,
                     u_kria.kria_link_up, u_kria.pkt_rx_cnt);
            for (k = chk_min_s1; k <= chk_max_s1; k = k + 1)
                if (!merged_s1[k[9:0]]) $display("  missing s1 seq=%0d (ias=%b eth=%b)", k, seen_ias_s1[k[9:0]], seen_eth_s1[k[9:0]]);
            for (k = chk_min_s2; k <= chk_max_s2; k = k + 1)
                if (!merged_s2[k[9:0]]) $display("  missing s2 seq=%0d (ias=%b eth=%b)", k, seen_ias_s2[k[9:0]], seen_eth_s2[k[9:0]]);
            fail_msg("S5: Mid-run cuts caused lost merged packets in MIRROR_1P1");
        end
        u_phy_peer.send_udp_frame(16'hA55A, 16'h0000, 32'h0000_0004, 32'd6, 1'b0); // Restore SPLIT
        $display("[S5] PASS -100ppm MIRROR_1P1 + mid-run ETH/IAS1 cuts lost_s1=0 lost_s2=0 mdio_wrs=%0d",
                 mdio_custom_wrs);

        // =====================================================================
        // SCENARIO 6: Physical Glitch Injection -> CRC Error -> W1C -> Retrain
        // =====================================================================
        axil_wr(8'h00, 32'h0000_0040); // Clear link error counters
        #1_000_000;
        axil_rd(8'h18, csr_r);
        if (csr_r !== 32'd0)
            fail_msg("S6: REG_ERR_CRC did not clear to 0 before glitch");

        rx_crc_err_pkts = 0;
        repeat (3) begin
            wait (u_artix.u_ul_pcs_tx.u_framer.state == 2'd2); // Sync to active ST_DATA payload
            #60_000;
            glitch_ul_d0 = 1'b1;
            #100_000; // 100 ns mid-frame inversion glitch inside payload/CRC window
            glitch_ul_d0 = 1'b0;
            #1_000_000;
        end
        #2_000_000;
        axil_rd(8'h18, csr_r);
        if (csr_r == 32'd0 || rx_crc_err_pkts == 0)
            fail_msg("S6: Glitch injection did not flag m_axis_rx_tuser[0] & REG_ERR_CRC > 0");

        // Clear via AXI-Lite control clear pulse (0x00 bit 6)
        axil_wr(8'h00, 32'h0000_0040);
        axil_rd(8'h18, csr_r);
        if (csr_r !== 32'd0)
            fail_msg("S6: REG_ERR_CRC did not clear to 0");

        // Trigger AXI-Lite LINK_CTRL[2] retrain pulse and confirm full unlock -> lock recovery
        // Pause DDC during manual retrain so Artix sends clean /I/+/A/ idle blocks
        emio_gpio_o[3] <= 1'b1;
        #2_000_000;
`ifdef MUTATE_NO_RETRAIN
        force u_kria.u_link_axis.ctrl_retrain_pulse = 1'b0;
`endif
        retrain_saw_drop = 1'b0;
        axil_wr(8'h00, 32'h0000_0004);
        tmo_cnt = 0;
        while (!retrain_saw_drop && tmo_cnt < 100) begin
            #20_000;
            axil_rd(8'h04, csr_r);
            if (!csr_r[6]) retrain_saw_drop = 1'b1;
            tmo_cnt = tmo_cnt + 1;
        end
        tmo_cnt = 0;
        csr_r   = 32'd0;
        while (!csr_r[6] && tmo_cnt < 2500) begin
            #100_000;
            axil_rd(8'h04, csr_r);
            tmo_cnt = tmo_cnt + 1;
        end
        if (!retrain_saw_drop || !csr_r[6])
            fail_msg("S6: LINK_CTRL[2] retrain did not execute and recover link_up");

        axil_wr(8'h00, 32'h0000_0040);
        emio_gpio_o[3] <= 1'b0;
        #2_000_000;
        s0_rx01 = rx01_pkts;
        #15_000_000; // 15 us post-retrain clean verification
        axil_rd(8'h18, post_crc_errs);
        if (post_crc_errs != 0 || rx01_pkts <= s0_rx01)
            fail_msg("S6: Post-retrain traffic had CRC errors or stopped");

        $display("[S6] PASS glitch->crc_err->clear->retrain(drop=%b,up=%b,post_crc=%0d)",
                 retrain_saw_drop, csr_r[6], post_crc_errs);

        // =====================================================================
        // Final Summary
        // =====================================================================
        if (fails == 0) begin
            $display("PASS: tb_system full-system verification (S1..S6, +/-100 ppm, Rev05 SI, ETH+IAS1) passed");
            $finish;
        end else begin
            $display("FAIL: tb_system finished with %0d error(s)", fails);
            $fatal(1, "tb_system failed");
        end
    end
endmodule
