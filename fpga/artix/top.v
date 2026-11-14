// SPDX-License-Identifier: BSD-2-Clause
// Artix-7 Front-End Top-Level Module for XC7A50T-FTG256-2 (U1101)
//
// Integrates:
//   - CLK_FPGA (N11/N12, 100 MHz LVDS_25) MMCM -> 125 MHz link_clk, 500 MHz DDR TX, 200 MHz IDELAYCTRL refclk
//   - AD9484 400 MSPS DDR LVDS ADC capture (adc_capture, inverted DCO N14/P14)
//   - AERIS 400->100 MSPS DDC + post-decimation + async packetizer (ddc_wrapper)
//   - 2-Lane 64b/66b TX PCS (link_pcs_tx) -> 8:1 DDR OSERDESE2 -> Bank 34 LINK_RX_*
//   - 1-Lane Downlink RX (Bank 14 LINK_TX_* -> IBUFDS -> BUFIO/BUFR -> IDELAYE2 -> ISERDESE2 -> train FSM + PCS)
//   - Pmod J1102 SPI slave & fallback DDC FIFO (pmod_spi, Bank 15 LVCMOS33)
//   - Housekeeping I2C/IRQ pins (Bank 35 LVCMOS18)

`timescale 1ns/1ps

module artix_top #(
    parameter integer DDC_POST_DECIM     = 4,           // 4 => 25 MSPS I/Q (0.8 Gb/s on 1.6 Gb/s link)
    parameter integer LINK_AM_PERIOD     = 16384,       // Alignment marker period (override to 64 in sim)
    parameter [0:0]   ADC_AUTO_TRAIN     = 1'b1,        // Trigger AD9484 IDELAY scan automatically after lock
    parameter [0:0]   ENABLE_ETH         = 1'b1,        // Rev06: 1 = enable SGMII-over-LVDS Ethernet + dual-path mux
    parameter [0:0]   ETH_BYPASS_AN      = 1'b0,        // 0 = full Clause 37 SGMII AN handshake
    parameter integer ETH_ALIVE_TIMEOUT  = 125_000_000, // Keepalive timeout @ 125 MHz (override in sim)
    parameter integer ETH_MDIO_RST_CYC   = 1_250_000,   // PHY hardware reset pulse width (10 ms @ 125 MHz)
    parameter integer ETH_MDIO_POLL_DIV  = 125_000,     // BMSR poll period (1 ms @ 125 MHz)
    parameter integer ETH_SDR_PKT_BYTES  = 1024,        // Stream 1 SDR telemetry UDP packet size
    parameter integer ETH_SDR_GAP_CYC    = 64,          // Stream 1 inter-packet gap
    parameter [1:0]   ETH_DEFAULT_POLICY = 2'd0,        // 0=STREAM_SPLIT, 1=MIRROR_1P1, 2=IAS_ONLY, 3=ETH_ONLY
    parameter integer CONV_SPI_CLK_DIV   = 8,           // Half-SCLK in 125 MHz cycles (7.81 MHz SCLK)
    parameter integer CONV_SPI_RST_CYC   = 7_500_000,   // 60 ms @ 125 MHz for AD9253 post-reset wake
    parameter [0:0]   CONV_SPI_AUTO_INIT = 1'b1,        // Auto-init AD9253 + read AD9484/AD9253 IDs at boot
    parameter integer ADAR_CLK_DIV       = 8,           // Half-SCLK in 125 MHz cycles
    parameter [0:0]   ADAR_AUTO_INIT     = 1'b1,        // Auto-init all 8 ADAR1000 chips at boot
    parameter integer HK_CLK_DIV         = 312,         // ~100 kHz I2C @ 125 MHz (4*312 = 1248)
    parameter integer HK_POLL_DIV        = 12_500_000,  // 100 ms TMP1075 background poll interval
    parameter integer XO_FCAL_WAIT_CYC   = 1_250_000,   // 10 ms Si549 FCAL settle wait @ 125 MHz
    parameter integer XADC_POLL_DIV_P    = 125_000,     // 1 ms XADC poll @ 125 MHz
    parameter [31:0]  PPS_DEFAULT_NOM_CYC= 32'd125_000_000
) (
    // System clock: 100 MHz LVDS via attenuator on Bank 14 MRCC (DIFF_TERM=FALSE)
    input  wire       fpga_clk_p,
    input  wire       fpga_clk_n,

    // AD9484 8-bit 400 MSPS DDR LVDS ADC on Bank 14 (DIFF_TERM=FALSE, ext 100 ohm)
    input  wire [7:0] adcr_d_p,
    input  wire [7:0] adcr_d_n,
    input  wire       adcr_or_p,
    input  wire       adcr_or_n,
    input  wire       adcr_dco_n,   // Ball N14 (MRCC_P wired to ADCR_DCO_N on PCB)
    input  wire       adcr_dco_p,   // Ball P14 (MRCC_N wired to ADCR_DCO_P on PCB)

    // AD9253 Dual 14-bit SDR ADC on Bank 14 (LVDS_25, DIFF_TERM=FALSE, ext 100 ohm)
    input  wire       adcs_dco_p,
    input  wire       adcs_dco_n,
    input  wire       adcs_fco_p,
    input  wire       adcs_fco_n,
    input  wire       adcs_d0_p,
    input  wire       adcs_d0_n,
    input  wire       adcs_d1_p,
    input  wire       adcs_d1_n,

    // IAS1 Uplink TX (Artix -> Kria) on Bank 34 (VCCO = 2.5V, LVDS_25 outputs)
    output wire       link_rx_clk_p,
    output wire       link_rx_clk_n,
    output wire       link_rx_d0_p,
    output wire       link_rx_d0_n,
    output wire       link_rx_d1_p,
    output wire       link_rx_d1_n,

    // IAS1 Downlink RX (Kria -> Artix) on Bank 14 (VCCO = 3.3V, LVDS_25 DIFF_TERM=FALSE)
    input  wire       link_tx_clk_p,
    input  wire       link_tx_clk_n,
    input  wire       link_tx_d0_p,
    input  wire       link_tx_d0_n,

    // Adapter Pmod J1102 on Bank 15 (VCCO = 3.3V, LVCMOS33)
    input  wire       pmod_cs_n,
    input  wire       pmod_mosi,
    output wire       pmod_miso,
    input  wire       pmod_sclk,
    input  wire       beam_strobe,
    input  wire       pps_sync,
    input  wire       pmod_spare1,
    output wire       pmod_spare2,

    // AD9708 8-bit Radar DAC on Bank 15 (LVCMOS33)
    output wire       dacr_clk,
    output wire [7:0] dacr_d,

    // AD9767 Dual 14-bit Interleaved SDR DAC on Bank 15 (LVCMOS33)
    output wire [13:0] dacs_d,
    output wire        dacs_iqclk,
    output wire        dacs_iqreset,
    output wire        dacs_iqsel,
    output wire        dacs_iqwrt,

    // RF Switches & Si549 Clock Mux/I2C on Bank 15 (LVCMOS33)
    output wire [3:0] sw_ctrl,
    inout  wire       xo_scl,
    inout  wire       xo_sda,
    output wire       clk_sel,

    // Housekeeping, Shared Converter SPI & 8x ADAR1000 Ribbon on Bank 35 (VCCO = 1.8V, LVCMOS18)
    inout  wire       hk_scl,
    inout  wire       hk_sda,
    input  wire       hk_alert_n,
    output wire       fpga_irq,
    output wire       conv_spi_csb_r,
    output wire       conv_spi_csb_s,
    output wire       conv_spi_sclk,
    inout  wire       conv_spi_sdio,
    output wire       adar_sclk,
    inout  wire       adar_sdio,
    input  wire       adar_sdo,
    output wire [7:0] adar_csb,
    output wire [7:0] adar_rx_load,
    output wire [7:0] adar_tx_load,
    output wire [7:0] adar_tr,

    // Rev06 Dedicated Ethernet SGMII PHY (U1201 RTL8211FSI-CG, Final Pins)
    //   Bank 34 (2.5V): ETH_SGTX (R2/R1), ETH_SGRX (R3/T2, DIFF_TERM=TRUE + DC bias),
    //                   ETH_MDC (P1 LVCMOS25), INTB unrouted (polled via MDIO)
    //   Bank 14 (3.3V): ETH_MDIO (M15 LVCMOS33 open-drain only, 1.5k to 2.5V DVDDRG; EMCCLK disabled),
    //                   ETH_RST_N (K13 LVCMOS33)
    output wire       eth_sgtx_p,
    output wire       eth_sgtx_n,
    input  wire       eth_sgrx_p,
    input  wire       eth_sgrx_n,
    output wire       eth_mdc,
    inout  wire       eth_mdio,
    output wire       eth_rst_n
);

    // -------------------------------------------------------------------------
    // 1. Primary 100 MHz Clock & MMCM (125 MHz link_clk, 500 MHz DDR, 200 MHz refclk)
    // -------------------------------------------------------------------------
    wire fpga_clk_ibuf;
    wire fpga_clk_bufg;

    IBUFDS #(
        .DIFF_TERM  ("FALSE"),
        .IOSTANDARD ("LVDS_25")
    ) u_ibuf_fpga_clk (
        .I  (fpga_clk_p),
        .IB (fpga_clk_n),
        .O  (fpga_clk_ibuf)
    );

    // Route via BUFG so u_mmcm_sys can occupy a CMT outside Bank 14 (u_mmcm_adc uses Bank 14)
    BUFG u_bufg_fpga_clk (
        .I (fpga_clk_ibuf),
        .O (fpga_clk_bufg)
    );

    wire sys_fb;
    wire link_clk_unbuf, tx_clk_ddr_unbuf, refclk_200m_unbuf, adcs_ddc_clk_unbuf;
    wire link_clk, tx_clk_ddr, refclk_200m, adcs_ddc_clk;
    wire sys_mmcm_locked;

    MMCME2_ADV #(
        .BANDWIDTH          ("OPTIMIZED"),
        .CLKFBOUT_MULT_F    (10.000),   // 100 MHz * 10 = 1000 MHz VCO
        .CLKFBOUT_PHASE     (0.0),
        .CLKIN1_PERIOD      (10.000),
        .CLKOUT0_DIVIDE_F   (8.000),    // 125 MHz link_clk / parallel fabric
        .CLKOUT0_PHASE      (0.0),
        .CLKOUT1_DIVIDE     (2),        // 500 MHz DDR serial clock (1.0 Gb/s)
        .CLKOUT1_PHASE      (0.0),
        .CLKOUT2_DIVIDE     (5),        // 200 MHz IDELAYCTRL REFCLK
        .CLKOUT2_PHASE      (0.0),
        .CLKOUT3_DIVIDE     (12),       // 83.333 MHz AD9253 SDR DDC fabric clock
        .CLKOUT3_PHASE      (0.0),
        .DIVCLK_DIVIDE      (1),
        .COMPENSATION       ("INTERNAL"),
        .STARTUP_WAIT       ("FALSE")
    ) u_mmcm_sys (
        .CLKIN1       (fpga_clk_bufg),
        .CLKIN2       (1'b0),
        .CLKINSEL     (1'b1),
        .CLKFBIN      (sys_fb),
        .CLKFBOUT     (sys_fb),
        .CLKFBOUTB    (),
        .CLKOUT0      (link_clk_unbuf),
        .CLKOUT0B     (),
        .CLKOUT1      (tx_clk_ddr_unbuf),
        .CLKOUT1B     (),
        .CLKOUT2      (refclk_200m_unbuf),
        .CLKOUT2B     (),
        .CLKOUT3      (adcs_ddc_clk_unbuf),
        .CLKOUT3B     (),
        .CLKOUT4      (),
        .CLKOUT5      (),
        .CLKOUT6      (),
        .LOCKED       (sys_mmcm_locked),
        .PWRDWN       (1'b0),
        .RST          (1'b0),
        .DADDR        (7'd0),
        .DCLK         (1'b0),
        .DEN          (1'b0),
        .DI           (16'd0),
        .DWE          (1'b0),
        .DO           (),
        .DRDY         (),
        .PSCLK        (1'b0),
        .PSEN         (1'b0),
        .PSINCDEC     (1'b0),
        .PSDONE       (),
        .CLKFBSTOPPED (),
        .CLKINSTOPPED ()
    );

    BUFG u_bufg_link_clk   (.I(link_clk_unbuf),     .O(link_clk));
    BUFG u_bufg_tx_ddr     (.I(tx_clk_ddr_unbuf),   .O(tx_clk_ddr));
    BUFG u_bufg_refclk_200 (.I(refclk_200m_unbuf),  .O(refclk_200m));
    BUFG u_bufg_adcs_ddc   (.I(adcs_ddc_clk_unbuf), .O(adcs_ddc_clk));

    // Power-on reset held until MMCM locks plus 64 link_clk cycles
    reg [5:0] por_cnt = 6'd0;
    reg       sys_rst = 1'b1;
    always @(posedge link_clk or negedge sys_mmcm_locked) begin
        if (!sys_mmcm_locked) begin
            por_cnt <= 6'd0;
            sys_rst <= 1'b1;
        end else if (por_cnt != 6'h3F) begin
            por_cnt <= por_cnt + 6'd1;
            sys_rst <= 1'b1;
        end else begin
            sys_rst <= 1'b0;
        end
    end

    // Synchronize system reset into refclk_200m domain for adc_capture IDELAYCTRL
    (* ASYNC_REG = "TRUE" *) reg [1:0] ref_rst_sync = 2'b11;
    always @(posedge refclk_200m or posedge sys_rst) begin
        if (sys_rst)
            ref_rst_sync <= 2'b11;
        else
            ref_rst_sync <= {ref_rst_sync[0], 1'b0};
    end
    wire ref_rst = ref_rst_sync[1];

    // Control signals from SPI & Downlink
    wire       spi_ctrl_soft_rst;
    wire       spi_ctrl_loopback_en;
    wire       spi_ctrl_retrain_pulse;
    wire       spi_ctrl_tap_override_en;
    wire       spi_ctrl_prbs7_tx_en;
    wire       spi_ctrl_prbs7_rx_chk_en;
    wire       spi_ctrl_clr_err_pulse;
    wire       spi_ctrl_fallback_en;
    wire [8:0] spi_cfg_tap_l0, spi_cfg_tap_l1;
    wire       spi_cfg_load_l0, spi_cfg_load_l1;

    wire       link_rst = sys_rst | spi_ctrl_soft_rst;

    // -------------------------------------------------------------------------
    // 2. PPS-Disciplined 64-bit Timestamp & Pmod Misc Synchronizers (link_clk)
    // -------------------------------------------------------------------------
    (* ASYNC_REG = "TRUE" *) reg [2:0] pps_sync_r;
    (* ASYNC_REG = "TRUE" *) reg [1:0] beam_sync_r, spare1_sync_r, alert_sync_r;
    reg [63:0] timestamp_cnt;
    reg [15:0] pps_pulse_cnt;

    always @(posedge link_clk) begin
        if (link_rst) begin
            pps_sync_r    <= 3'b000;
            beam_sync_r   <= 2'b00;
            spare1_sync_r <= 2'b00;
            alert_sync_r  <= 2'b11;
            timestamp_cnt <= 64'd0;
            pps_pulse_cnt <= 16'd0;
        end else begin
            pps_sync_r    <= {pps_sync_r[1:0], pps_sync};
            beam_sync_r   <= {beam_sync_r[0], beam_strobe};
            spare1_sync_r <= {spare1_sync_r[0], pmod_spare1};
            alert_sync_r  <= {alert_sync_r[0], hk_alert_n};

            // Increment in 8 ns steps at 125 MHz link_clk; align upper bits on PPS edge
            if (!pps_sync_r[2] && pps_sync_r[1]) begin
                pps_pulse_cnt <= pps_pulse_cnt + 16'd1;
                timestamp_cnt <= {pps_pulse_cnt + 16'd1, 48'd0};
            end else begin
                timestamp_cnt <= timestamp_cnt + 64'd8;
            end
        end
    end

    // -------------------------------------------------------------------------
    // 3. AD9484 Capture + AERIS DDC Wrapper (ADCR_DCO MMCM -> clk_400m / clk_100m)
    // -------------------------------------------------------------------------
    wire        adc_clk_400m, adc_clk_100m, adc_mmcm_locked;
    wire [7:0]  adc_data;
    wire        adc_or;
    wire        adc_valid;
    wire        adc_trained, adc_dco_phase_err;
    wire [39:0] adc_tap_flat;
    wire [5:0]  adc_eye_width_min;

    // Retrain pulse toggle-CDC from link_clk -> adc_clk_100m + optional boot trigger
    reg        retrain_tog_link;
    always @(posedge link_clk) begin
        if (link_rst)
            retrain_tog_link <= 1'b0;
        else if (spi_ctrl_retrain_pulse)
            retrain_tog_link <= ~retrain_tog_link;
    end

    (* ASYNC_REG = "TRUE" *) reg [2:0] adc_retrain_sync;
    (* ASYNC_REG = "TRUE" *) reg [1:0] adc_rst_sync_100 = 2'b11;
    wire adc_rst_src = ref_rst | ~adc_mmcm_locked;
    always @(posedge adc_clk_100m or posedge adc_rst_src) begin
        if (adc_rst_src)
            adc_rst_sync_100 <= 2'b11;
        else
            adc_rst_sync_100 <= {adc_rst_sync_100[0], 1'b0};
    end
    wire adc_rst_100m = adc_rst_sync_100[1];

    reg [3:0] adc_boot_cnt;
    reg       adc_train_start_100;
    always @(posedge adc_clk_100m) begin
        if (adc_rst_100m) begin
            adc_retrain_sync    <= 3'd0;
            adc_boot_cnt        <= 4'd0;
            adc_train_start_100 <= 1'b0;
        end else begin
            adc_retrain_sync <= {adc_retrain_sync[1:0], retrain_tog_link};
            if (ADC_AUTO_TRAIN && adc_boot_cnt != 4'hF) begin
                adc_boot_cnt        <= adc_boot_cnt + 4'd1;
                adc_train_start_100 <= 1'b1;
            end else begin
                adc_train_start_100 <= (adc_retrain_sync[2] ^ adc_retrain_sync[1]);
            end
        end
    end

    adc_capture #(
        .DCO_INVERT      (1'b1),
        .DCO_PERIOD_NS   (5.000),
        .REFCLK_FREQ_MHZ (200.0),
        .INST_IDELAYCTRL (1'b1)
    ) u_adc_cap (
        .rst              (ref_rst),
        .refclk_200m      (refclk_200m),
        .adcr_d_p         (adcr_d_p),
        .adcr_d_n         (adcr_d_n),
        .adcr_or_p        (adcr_or_p),
        .adcr_or_n        (adcr_or_n),
        .adcr_dco_n_pin   (adcr_dco_n),
        .adcr_dco_p_pin   (adcr_dco_p),
        .train_start      (adc_train_start_100),
        .train_pattern_en (1'b1),
        .clk_400m         (adc_clk_400m),
        .clk_100m         (adc_clk_100m),
        .mmcm_locked      (adc_mmcm_locked),
        .adc_data         (adc_data),
        .adc_or           (adc_or),
        .adc_valid        (adc_valid),
        .adc_trained      (adc_trained),
        .dco_phase_err    (adc_dco_phase_err),
        .tap_flat         (adc_tap_flat),
        .eye_width_min    (adc_eye_width_min)
    );

    wire signed [15:0] bb_i, bb_q;
    wire               bb_valid;
    wire [1:0]         ddc_status;
    wire               mixer_saturation, filter_overflow, sync_error;

    wire               tx_pkt_valid, tx_pkt_ready, tx_pkt_sop, tx_pkt_eop;
    wire [7:0]         tx_pkt_stream_id;
    wire [15:0]        tx_pkt_len;
    wire [31:0]        tx_pkt_seq;
    wire [63:0]        tx_pkt_timestamp, tx_pkt_data;
    wire [23:0]        tx_dropped_cnt;

    (* ASYNC_REG = "TRUE" *) reg [1:0] adc_tr_100_sync, spare1_100_sync;
    always @(posedge adc_clk_100m) begin
        if (adc_rst_100m) begin
            adc_tr_100_sync <= 2'b00;
            spare1_100_sync <= 2'b00;
        end else begin
            adc_tr_100_sync <= {adc_tr_100_sync[0], adc_trained};
            spare1_100_sync <= {spare1_100_sync[0], pmod_spare1};
        end
    end

    ddc_wrapper #(
        .POST_DECIM (DDC_POST_DECIM),
        .PKT_WORDS  (8),
        .STREAM_ID  (8'h01)
    ) u_ddc (
        .clk_400m         (adc_clk_400m),
        .clk_100m         (adc_clk_100m),
        .rst              (adc_rst_100m),
        .ddc_en           (adc_tr_100_sync[1] & ~spare1_100_sync[1]),
        .reset_monitors   (spi_ctrl_clr_err_pulse),
        .adc_data         (adc_data),
        .adc_valid        (adc_valid),
        .bb_i             (bb_i),
        .bb_q             (bb_q),
        .bb_valid         (bb_valid),
        .ddc_status       (ddc_status),
        .mixer_saturation (mixer_saturation),
        .filter_overflow  (filter_overflow),
        .sync_error       (sync_error),
        .link_clk         (link_clk),
        .link_rst         (link_rst),
        .timestamp_cnt    (timestamp_cnt),
        .pkt_valid        (tx_pkt_valid),
        .pkt_ready        (tx_pkt_ready),
        .pkt_sop          (tx_pkt_sop),
        .pkt_eop          (tx_pkt_eop),
        .pkt_stream_id    (tx_pkt_stream_id),
        .pkt_len          (tx_pkt_len),
        .pkt_seq          (tx_pkt_seq),
        .pkt_timestamp    (tx_pkt_timestamp),
        .pkt_data         (tx_pkt_data),
        .dropped_cnt      (tx_dropped_cnt)
    );

    // CDC fallback DDC baseband sample + sticky status from clk_100m/clk_200m -> link_clk
    reg [15:0] fb_i_hold_100, fb_q_hold_100;
    reg        fb_tog_100;
    always @(posedge adc_clk_100m) begin
        if (adc_rst_100m) begin
            fb_i_hold_100 <= 16'd0;
            fb_q_hold_100 <= 16'd0;
            fb_tog_100    <= 1'b0;
        end else if (bb_valid) begin
            fb_i_hold_100 <= bb_i;
            fb_q_hold_100 <= bb_q;
            fb_tog_100    <= ~fb_tog_100;
        end
    end

    (* ASYNC_REG = "TRUE" *) reg [2:0] fb_tog_sync;
    (* ASYNC_REG = "TRUE" *) reg [1:0] adc_tr_sync, adc_err_sync, sat_sync, ovf_sync;
    reg [15:0] fb_ddc_i_link, fb_ddc_q_link;
    reg        fb_ddc_valid_link;

    always @(posedge link_clk) begin
        if (link_rst) begin
            fb_tog_sync       <= 3'd0;
            fb_ddc_i_link     <= 16'd0;
            fb_ddc_q_link     <= 16'd0;
            fb_ddc_valid_link <= 1'b0;
            adc_tr_sync       <= 2'b00;
            adc_err_sync      <= 2'b00;
            sat_sync          <= 2'b00;
            ovf_sync          <= 2'b00;
        end else begin
            fb_tog_sync       <= {fb_tog_sync[1:0], fb_tog_100};
            fb_ddc_valid_link <= (fb_tog_sync[2] ^ fb_tog_sync[1]);
            if (fb_tog_sync[2] ^ fb_tog_sync[1]) begin
                fb_ddc_i_link <= fb_i_hold_100;
                fb_ddc_q_link <= fb_q_hold_100;
            end
            adc_tr_sync  <= {adc_tr_sync[0], adc_trained};
            adc_err_sync <= {adc_err_sync[0], adc_dco_phase_err};
            sat_sync     <= {sat_sync[0], mixer_saturation};
            ovf_sync     <= {ovf_sync[0], filter_overflow};
        end
    end

    // -------------------------------------------------------------------------
    // 4. Downlink 1-Lane RX (Bank 14 LINK_TX_CLK/D0 -> BUFIO/BUFR -> IDELAYE2 -> ISERDESE2)
    // -------------------------------------------------------------------------
    wire dl_clk_ibuf, dl_d0_ibuf;
    wire dl_clk_bufio, dl_rx_clk;

    IBUFDS #(.DIFF_TERM("FALSE"), .IOSTANDARD("LVDS_25")) u_ibuf_dl_clk (
        .I(link_tx_clk_p), .IB(link_tx_clk_n), .O(dl_clk_ibuf)
    );
    IBUFDS #(.DIFF_TERM("FALSE"), .IOSTANDARD("LVDS_25")) u_ibuf_dl_d0 (
        .I(link_tx_d0_p), .IB(link_tx_d0_n), .O(dl_d0_ibuf)
    );

    // Per UG472 Fig 2-18: SRCC/MRCC IBUFDS drives BUFIO and BUFR(DIV4) in parallel
    BUFIO u_dl_bufio (.I(dl_clk_ibuf), .O(dl_clk_bufio));
    BUFR #(.BUFR_DIVIDE("4"), .SIM_DEVICE("7SERIES")) u_dl_bufr (
        .O(dl_rx_clk), .CE(1'b1), .CLR(1'b0), .I(dl_clk_ibuf)
    );

    // Synchronize reset & SPI controls into dl_rx_clk domain
    (* ASYNC_REG = "TRUE" *) reg [1:0] dl_rst_sync = 2'b11;
    always @(posedge dl_rx_clk or posedge link_rst) begin
        if (link_rst)
            dl_rst_sync <= 2'b11;
        else
            dl_rst_sync <= {dl_rst_sync[0], 1'b0};
    end
    wire dl_rx_rst = dl_rst_sync[1];

    // Toggle-CDC pulses & quasi-static config link_clk -> dl_rx_clk
    reg       dl_load_tog, dl_clr_tog;
    reg [8:0] dl_cfg_tap_hold;
    always @(posedge link_clk) begin
        if (link_rst) begin
            dl_load_tog     <= 1'b0;
            dl_clr_tog      <= 1'b0;
            dl_cfg_tap_hold <= 9'd0;
        end else begin
            if (spi_cfg_load_l0) begin
                dl_load_tog     <= ~dl_load_tog;
                dl_cfg_tap_hold <= spi_cfg_tap_l0;
            end
            if (spi_ctrl_clr_err_pulse)
                dl_clr_tog <= ~dl_clr_tog;
        end
    end

    (* ASYNC_REG = "TRUE" *) reg [1:0] dl_ov_sync, dl_prbs_en_sync;
    (* ASYNC_REG = "TRUE" *) reg [2:0] dl_retrain_sync, dl_load_sync, dl_clr_sync;
    always @(posedge dl_rx_clk) begin
        if (dl_rx_rst) begin
            dl_ov_sync      <= 2'd0;
            dl_prbs_en_sync <= 2'd0;
            dl_retrain_sync <= 3'd0;
            dl_load_sync    <= 3'd0;
            dl_clr_sync     <= 3'd0;
        end else begin
            dl_ov_sync      <= {dl_ov_sync[0], spi_ctrl_tap_override_en};
            dl_prbs_en_sync <= {dl_prbs_en_sync[0], spi_ctrl_prbs7_rx_chk_en};
            dl_retrain_sync <= {dl_retrain_sync[1:0], retrain_tog_link};
            dl_load_sync    <= {dl_load_sync[1:0], dl_load_tog};
            dl_clr_sync     <= {dl_clr_sync[1:0], dl_clr_tog};
        end
    end

    wire       dl_fsm_load_l0, dl_en_vtc_unused;
    wire [8:0] dl_fsm_cntval_l0, dl_eye_l0, dl_eye_r0;
    wire       dl_d0_idelay;
    wire [4:0] dl_tap_active = dl_ov_sync[1] ? dl_cfg_tap_hold[4:0] : dl_fsm_cntval_l0[4:0];
    wire       dl_tap_load   = dl_ov_sync[1] ? (dl_load_sync[2] ^ dl_load_sync[1]) : dl_fsm_load_l0;

    (* IODELAY_GROUP = "bank14_idelay_grp" *)
    IDELAYE2 #(
        .CINVCTRL_SEL          ("FALSE"),
        .DELAY_SRC             ("IDATAIN"),
        .HIGH_PERFORMANCE_MODE ("TRUE"),
        .IDELAY_TYPE           ("VAR_LOAD"),
        .IDELAY_VALUE          (0),
        .PIPE_SEL              ("FALSE"),
        .REFCLK_FREQUENCY      (200.0),
        .SIGNAL_PATTERN        ("DATA")
    ) u_dl_idelay_d0 (
        .CNTVALUEOUT (),
        .DATAOUT     (dl_d0_idelay),
        .C           (dl_rx_clk),
        .CE          (1'b0),
        .CINVCTRL    (1'b0),
        .CNTVALUEIN  (dl_tap_active),
        .DATAIN      (1'b0),
        .IDATAIN     (dl_d0_ibuf),
        .INC         (1'b0),
        .LD          (dl_tap_load),
        .LDPIPEEN    (1'b0),
        .REGRST      (dl_rx_rst)
    );

    wire dl_q1, dl_q2, dl_q3, dl_q4, dl_q5, dl_q6, dl_q7, dl_q8;
    ISERDESE2 #(
        .DATA_RATE          ("DDR"),
        .DATA_WIDTH         (8),
        .DYN_CLKDIV_INV_EN  ("FALSE"),
        .DYN_CLK_INV_EN     ("FALSE"),
        .INIT_Q1            (1'b0),
        .INIT_Q2            (1'b0),
        .INIT_Q3            (1'b0),
        .INIT_Q4            (1'b0),
        .INTERFACE_TYPE     ("NETWORKING"),
        .IOBDELAY           ("IFD"),
        .IS_CLKB_INVERTED   (1'b1),
        .IS_CLKDIVP_INVERTED(1'b0),
        .IS_CLKDIV_INVERTED (1'b0),
        .IS_CLK_INVERTED    (1'b0),
        .IS_D_INVERTED      (1'b0),
        .IS_OCLKB_INVERTED  (1'b0),
        .IS_OCLK_INVERTED   (1'b0),
        .NUM_CE             (1),
        .OFB_USED           ("FALSE"),
        .SERDES_MODE        ("MASTER"),
        .SRVAL_Q1           (1'b0),
        .SRVAL_Q2           (1'b0),
        .SRVAL_Q3           (1'b0),
        .SRVAL_Q4           (1'b0)
    ) u_dl_iserdes_d0 (
        .O            (),
        .Q1           (dl_q1),
        .Q2           (dl_q2),
        .Q3           (dl_q3),
        .Q4           (dl_q4),
        .Q5           (dl_q5),
        .Q6           (dl_q6),
        .Q7           (dl_q7),
        .Q8           (dl_q8),
        .SHIFTOUT1    (),
        .SHIFTOUT2    (),
        .BITSLIP      (1'b0),
        .CE1          (1'b1),
        .CE2          (1'b1),
        .CLK          (dl_clk_bufio),
        .CLKB         (dl_clk_bufio),
        .CLKDIV       (dl_rx_clk),
        .CLKDIVP      (1'b0),
        .D            (1'b0),
        .DDLY         (dl_d0_idelay),
        .DYNCLKDIVSEL (1'b0),
        .DYNCLKSEL    (1'b0),
        .OCLK         (1'b0),
        .OCLKB        (1'b0),
        .OFB          (1'b0),
        .RST          (dl_rx_rst),
        .SHIFTIN1     (1'b0),
        .SHIFTIN2     (1'b0)
    );

    wire [7:0] dl_rx_byte = {dl_q1, dl_q2, dl_q3, dl_q4, dl_q5, dl_q6, dl_q7, dl_q8};

    wire        dl_out_valid, dl_out_sop, dl_out_eop;
    wire [7:0]  dl_out_sid;
    wire [63:0] dl_out_data;
    wire        dl_done_valid, dl_done_ok, dl_done_err;
    wire        dl_l0_lock, dl_link_up;
    wire [2:0]  dl_train_state;
    wire [15:0] dl_remote_status;
    wire [31:0] dl_sh_err_cnt, dl_pkt_rx_cnt, dl_crc_err_cnt;
    wire        dl_blk_valid, dl_blk_ok;

    link_rx_train_fsm #(
        .DEFAULT_CENTER_TAP (9'd9),
        .MAX_TAP            (9'd31),
        .TAP_STEP           (9'd1),
        .MIN_EYE_STEPS      (9'd7),
        .BAD_TAP            (9'd3),
        .SINGLE_LANE        (1)
    ) u_dl_train_fsm (
        .clk              (dl_rx_clk),
        .rst              (dl_rx_rst),
        .retrain          (dl_retrain_sync[2] ^ dl_retrain_sync[1]),
        .cfg_tap_override (dl_ov_sync[1]),
        .cfg_tap_l0       (dl_cfg_tap_hold),
        .cfg_tap_l1       (9'd0),
        .rx_byte_l0       (dl_rx_byte),
        .rx_byte_l1       (8'd0),
        .l0_block_lock    (dl_l0_lock),
        .l1_block_lock    (1'b1),
        .deskew_lock      (dl_l0_lock),
        .l0_rx_blk_valid  (dl_blk_valid),
        .l0_rx_blk_ok     (dl_blk_ok),
        .l1_rx_blk_valid  (1'b1),
        .l1_rx_blk_ok     (1'b1),
        .en_vtc           (dl_en_vtc_unused),
        .load_l0          (dl_fsm_load_l0),
        .cntval_l0        (dl_fsm_cntval_l0),
        .load_l1          (),
        .cntval_l1        (),
        .train_state      (dl_train_state),
        .link_up          (dl_link_up),
        .eye_left_l0      (dl_eye_l0),
        .eye_right_l0     (dl_eye_r0),
        .eye_left_l1      (),
        .eye_right_l1     ()
    );

    wire [15:0] dl_out_len;

    link_pcs_single_rx #(
        .SKIP_CRC (0)
    ) u_dl_pcs_rx (
        .clk                (dl_rx_clk),
        .rst                (dl_rx_rst),
        .link_ready         (dl_link_up),
        .rx_byte_l0         (dl_rx_byte),
        .out_valid          (dl_out_valid),
        .out_sop            (dl_out_sop),
        .out_eop            (dl_out_eop),
        .out_stream_id      (dl_out_sid),
        .out_len            (dl_out_len),
        .out_seq            (),
        .out_timestamp      (),
        .out_data           (dl_out_data),
        .pkt_done_valid     (dl_done_valid),
        .pkt_done_ok        (dl_done_ok),
        .pkt_done_err       (dl_done_err),
        .l0_block_lock      (dl_l0_lock),
        .remote_status      (dl_remote_status),
        .remote_dropped_cnt (),
        .sh_err_cnt_l0      (dl_sh_err_cnt),
        .pkt_rx_cnt         (dl_pkt_rx_cnt),
        .crc_err_cnt        (dl_crc_err_cnt),
        .l0_rx_blk_valid    (dl_blk_valid),
        .l0_rx_blk_ok       (dl_blk_ok)
    );

    // Optional PRBS7 RX checker + control word capture in dl_rx_clk
    reg [6:0]  dl_prbs_lfsr;
    reg [31:0] dl_prbs_err_cnt;
    reg [31:0] dl_ctrl_shadow;
    reg [7:0]  dl_rx_drop_cnt;

    function [7:0] prbs7_expect8(input [6:0] st, input [7:0] rx_b);
        reg [6:0] s;
        reg       fb;
        integer   k;
        begin
            s = st;
            for (k = 0; k < 8; k = k + 1) begin
                fb = s[6] ^ s[5];
                prbs7_expect8[k] = fb;
                s = {s[5:0], rx_b[k]};
            end
        end
    endfunction

    always @(posedge dl_rx_clk) begin
        if (dl_rx_rst || (dl_clr_sync[2] ^ dl_clr_sync[1])) begin
            dl_prbs_lfsr    <= 7'h7F;
            dl_prbs_err_cnt <= 32'd0;
            dl_ctrl_shadow  <= 32'd0;
            dl_rx_drop_cnt  <= 8'd0;
        end else begin
            if (dl_prbs_en_sync[1]) begin
                if (dl_rx_byte != prbs7_expect8(dl_prbs_lfsr, dl_rx_byte))
                    dl_prbs_err_cnt <= dl_prbs_err_cnt + 32'd1;
                dl_prbs_lfsr <= dl_rx_byte[7:1];
            end
            if (dl_out_valid && dl_out_sop && (dl_out_sid == 8'h10))
                dl_ctrl_shadow <= dl_out_data[31:0];
            if (dl_done_valid && dl_done_err && (dl_rx_drop_cnt != 8'hFF))
                dl_rx_drop_cnt <= dl_rx_drop_cnt + 8'd1;
        end
    end

    // Synchronize downlink health to link_clk (quasi-static telemetry)
    (* ASYNC_REG = "TRUE" *) reg [1:0]  dl_up_sync, dl_lock_sync;
    (* ASYNC_REG = "TRUE" *) reg [2:0]  dl_st_sync1, dl_st_sync2;
    (* ASYNC_REG = "TRUE" *) reg [7:0]  dl_rem_sync1, dl_rem_sync2, dl_drop_sync1, dl_drop_sync2;
    (* ASYNC_REG = "TRUE" *) reg [8:0]  dl_el_sync1, dl_el_sync2, dl_er_sync1, dl_er_sync2, dl_tap_sync1, dl_tap_sync2;
    (* ASYNC_REG = "TRUE" *) reg [31:0] dl_sh_sync1, dl_sh_sync2, dl_crc_sync1, dl_crc_sync2, dl_pkt_sync1, dl_pkt_sync2, dl_prbs_sync1, dl_prbs_sync2;

    always @(posedge link_clk) begin
        if (link_rst) begin
            dl_up_sync   <= 2'd0; dl_lock_sync <= 2'd0;
            dl_st_sync1  <= 3'd0; dl_st_sync2  <= 3'd0;
            dl_rem_sync1 <= 8'd0; dl_rem_sync2 <= 8'd0;
            dl_drop_sync1<= 8'd0; dl_drop_sync2<= 8'd0;
            dl_el_sync1  <= 9'd0; dl_el_sync2  <= 9'd0;
            dl_er_sync1  <= 9'd0; dl_er_sync2  <= 9'd0;
            dl_tap_sync1 <= 9'd0; dl_tap_sync2 <= 9'd0;
            dl_sh_sync1  <= 32'd0; dl_sh_sync2 <= 32'd0;
            dl_crc_sync1 <= 32'd0; dl_crc_sync2<= 32'd0;
            dl_pkt_sync1 <= 32'd0; dl_pkt_sync2<= 32'd0;
            dl_prbs_sync1<= 32'd0; dl_prbs_sync2<= 32'd0;
        end else begin
            dl_up_sync    <= {dl_up_sync[0], dl_link_up};
            dl_lock_sync  <= {dl_lock_sync[0], dl_l0_lock};
            dl_st_sync1   <= dl_train_state;    dl_st_sync2   <= dl_st_sync1;
            dl_rem_sync1  <= dl_remote_status[7:0]; dl_rem_sync2 <= dl_rem_sync1;
            dl_drop_sync1 <= dl_rx_drop_cnt;    dl_drop_sync2 <= dl_drop_sync1;
            dl_el_sync1   <= dl_eye_l0;         dl_el_sync2   <= dl_el_sync1;
            dl_er_sync1   <= dl_eye_r0;         dl_er_sync2   <= dl_er_sync1;
            dl_tap_sync1  <= {4'd0, dl_tap_active}; dl_tap_sync2 <= dl_tap_sync1;
            dl_sh_sync1   <= dl_sh_err_cnt;     dl_sh_sync2   <= dl_sh_sync1;
            dl_crc_sync1  <= dl_crc_err_cnt;    dl_crc_sync2  <= dl_crc_sync1;
            dl_pkt_sync1  <= dl_pkt_rx_cnt;     dl_pkt_sync2  <= dl_pkt_sync1;
            dl_prbs_sync1 <= dl_prbs_err_cnt;   dl_prbs_sync2 <= dl_prbs_sync1;
        end
    end

    // -------------------------------------------------------------------------
    // 5. Uplink 2-Lane TX (link_pcs_tx -> OSERDESE2 -> Bank 34 LVDS_25 OBUFDS)
    // -------------------------------------------------------------------------
    wire hk_scl_in, hk_sda_in;
    (* ASYNC_REG = "TRUE" *) reg [1:0] hk_scl_sync_r, hk_sda_sync_r;
    always @(posedge link_clk) begin
        if (link_rst) begin
            hk_scl_sync_r <= 2'b11;
            hk_sda_sync_r <= 2'b11;
        end else begin
            hk_scl_sync_r <= {hk_scl_sync_r[0], hk_scl_in};
            hk_sda_sync_r <= {hk_sda_sync_r[0], hk_sda_in};
        end
    end

    wire [7:0] pcs_tx_byte_l0, pcs_tx_byte_l1;
    wire       eth_link_up_stat;
    wire       eth_remote_alive_stat;
    wire       eth_copper_up_stat;
    wire [15:0] local_status_word = {
        eth_remote_alive_stat,
        eth_link_up_stat,
        hk_sda_sync_r[1],
        hk_scl_sync_r[1],
        spi_ctrl_loopback_en,
        sat_sync[1] | ovf_sync[1],
        ~alert_sync_r[1],
        dl_up_sync[1],
        beam_sync_r[1],
        adc_err_sync[1],
        adc_tr_sync[1],
        adc_mmcm_locked,
        ddc_status,
        dl_st_sync2[1:0]
    };

    // -------------------------------------------------------------------------
    // 5b. Rev06 SGMII-over-LVDS Ethernet + Dual-Path Mux (ENABLE_ETH)
    // -------------------------------------------------------------------------
    wire        s0_arb_valid, s0_arb_ready, s0_arb_sop, s0_arb_eop;
    wire [7:0]  s0_arb_sid;
    wire [15:0] s0_arb_len;
    wire [31:0] s0_arb_seq;
    wire [63:0] s0_arb_ts, s0_arb_data;

    wire        eth_ctrl_wr;
    wire [15:0] eth_ctrl_addr;
    wire [31:0] eth_ctrl_wdata;

    wire        ias_mux_valid, ias_mux_ready, ias_mux_sop, ias_mux_eop;
    wire [7:0]  ias_mux_sid;
    wire [15:0] ias_mux_len;
    wire [31:0] ias_mux_seq;
    wire [63:0] ias_mux_ts, ias_mux_data;

    generate
        if (ENABLE_ETH) begin : gen_rev06_eth
            // Second MMCM (1250 MHz VCO) -> 625 MHz (0/90) & 312.5 MHz (0/45)
            wire eth_mmcm_fb, eth_mmcm_locked;
            wire clk_625_0_u, clk_625_90_u, clk_312p5_u, clk_312p5_45_u;
            wire clk_625_0,   clk_625_90,   clk_312p5,   clk_312p5_45;

            MMCME2_ADV #(
                .BANDWIDTH         ("OPTIMIZED"),
                .CLKIN1_PERIOD     (10.000),
                .DIVCLK_DIVIDE     (1),
                .CLKFBOUT_MULT_F   (12.500),
                .CLKFBOUT_PHASE    (0.0),
                .CLKOUT0_DIVIDE_F  (2.000),   // 625.0 MHz 0 deg
                .CLKOUT0_PHASE     (0.0),
                .CLKOUT1_DIVIDE    (2),       // 625.0 MHz 90 deg
                .CLKOUT1_PHASE     (90.0),
                .CLKOUT2_DIVIDE    (4),       // 312.5 MHz 0 deg
                .CLKOUT2_PHASE     (0.0),
                .CLKOUT3_DIVIDE    (4),       // 312.5 MHz 45 deg
                .CLKOUT3_PHASE     (45.0),
                .COMPENSATION      ("INTERNAL"),
                .STARTUP_WAIT      ("FALSE")
            ) u_mmcm_eth (
                .CLKIN1       (fpga_clk_bufg),
                .CLKIN2       (1'b0),
                .CLKINSEL     (1'b1),
                .CLKFBIN      (eth_mmcm_fb),
                .CLKFBOUT     (eth_mmcm_fb),
                .CLKFBOUTB    (),
                .CLKOUT0      (clk_625_0_u),
                .CLKOUT0B     (),
                .CLKOUT1      (clk_625_90_u),
                .CLKOUT1B     (),
                .CLKOUT2      (clk_312p5_u),
                .CLKOUT2B     (),
                .CLKOUT3      (clk_312p5_45_u),
                .CLKOUT3B     (),
                .CLKOUT4      (),
                .CLKOUT5      (),
                .CLKOUT6      (),
                .LOCKED       (eth_mmcm_locked),
                .PWRDWN       (1'b0),
                .RST          (1'b0),
                .DADDR        (7'd0), .DCLK(1'b0), .DEN(1'b0), .DI(16'd0), .DWE(1'b0),
                .DO           (), .DRDY(), .PSCLK(1'b0), .PSEN(1'b0), .PSINCDEC(1'b0), .PSDONE(),
                .CLKFBSTOPPED (), .CLKINSTOPPED()
            );

            BUFG u_bufg_eth_625_0  (.I(clk_625_0_u),    .O(clk_625_0));
            BUFG u_bufg_eth_625_90 (.I(clk_625_90_u),   .O(clk_625_90));
            BUFG u_bufg_eth_312_0  (.I(clk_312p5_u),    .O(clk_312p5));
            BUFG u_bufg_eth_312_45 (.I(clk_312p5_45_u), .O(clk_312p5_45));

            // Bank 34 IDELAYCTRL (shares refclk_200m BUFG)
            wire b34_idc_rdy;
            (* IODELAY_GROUP = "bank34_idelay_grp" *)
            IDELAYCTRL u_idelayctrl_b34 (
                .RDY    (b34_idc_rdy),
                .REFCLK (refclk_200m),
                .RST    (ref_rst)
            );

            wire eth_rst_src = link_rst | ~eth_mmcm_locked | ~b34_idc_rdy;
            (* ASYNC_REG = "TRUE" *) reg [2:0] eth_rst_312_s = 3'b111;
            (* ASYNC_REG = "TRUE" *) reg [2:0] eth_rst_125_s = 3'b111;
            always @(posedge clk_312p5 or posedge eth_rst_src) begin
                if (eth_rst_src) eth_rst_312_s <= 3'b111;
                else             eth_rst_312_s <= {eth_rst_312_s[1:0], 1'b0};
            end
            always @(posedge link_clk or posedge eth_rst_src) begin
                if (eth_rst_src) eth_rst_125_s <= 3'b111;
                else             eth_rst_125_s <= {eth_rst_125_s[1:0], 1'b0};
            end
            wire eth_rst_312 = eth_rst_312_s[2];
            wire eth_rst_125 = eth_rst_125_s[2];

            // SGMII PHY + Clause 36/37 PCS
            wire       gmii_tx_en, gmii_tx_er, gmii_rx_dv, gmii_rx_er;
            wire [7:0] gmii_txd, gmii_rxd;
            wire       phy_an_complete, phy_comma_aligned;
            reg        ctrl_an_restart;

            eth_sgmii_phy #(
                .DIFF_TERM_EN       (1'b1),
                .IODELAY_GROUP_NAME ("bank34_idelay_grp"),
                .BYPASS_AN          (ETH_BYPASS_AN)
            ) u_eth_phy (
                .sgmii_rx_p       (eth_sgrx_p),
                .sgmii_rx_n       (eth_sgrx_n),
                .sgmii_tx_p       (eth_sgtx_p),
                .sgmii_tx_n       (eth_sgtx_n),
                .clk_625_0        (clk_625_0),
                .clk_625_90       (clk_625_90),
                .clk_312p5        (clk_312p5),
                .clk_312p5_45     (clk_312p5_45),
                .clk_125          (link_clk),
                .rst_312p5        (eth_rst_312),
                .rst_125          (eth_rst_125),
                .gmii_tx_en       (gmii_tx_en),
                .gmii_tx_er       (gmii_tx_er),
                .gmii_txd         (gmii_txd),
                .gmii_rx_dv       (gmii_rx_dv),
                .gmii_rx_er       (gmii_rx_er),
                .gmii_rxd         (gmii_rxd),
                .an_restart       (ctrl_an_restart),
                .rx_comma_aligned (phy_comma_aligned),
                .an_complete      (phy_an_complete),
                .link_up          (eth_link_up_stat),
                .an_lp_ability    (),
                .phase_sel_mon    (),
                .phase_switch_cnt (),
                .code_err_cnt     (),
                .disp_err_cnt     ()
            );

            // 1G MAC + UDP/IPv4 Framing + Control RX
            wire        eth_mux_valid, eth_mux_ready, eth_mux_sop, eth_mux_eop;
            wire [7:0]  eth_mux_sid;
            wire [15:0] eth_mux_len;
            wire [31:0] eth_mux_seq;
            wire [63:0] eth_mux_ts, eth_mux_data;

            wire        udp_ctrl_wr;
            wire [15:0] udp_ctrl_addr;
            wire [31:0] udp_ctrl_wdata;

            eth_mac_udp #(
                .ALIVE_TIMEOUT (ETH_ALIVE_TIMEOUT)
            ) u_eth_mac (
                .clk              (link_clk),
                .rst              (eth_rst_125),
                .link_up          (eth_link_up_stat),
                .pkt_valid        (eth_mux_valid),
                .pkt_ready        (eth_mux_ready),
                .pkt_sop          (eth_mux_sop),
                .pkt_eop          (eth_mux_eop),
                .pkt_stream_id    (eth_mux_sid),
                .pkt_len          (eth_mux_len),
                .pkt_seq          (eth_mux_seq),
                .pkt_timestamp    (eth_mux_ts),
                .pkt_data         (eth_mux_data),
                .gmii_tx_en       (gmii_tx_en),
                .gmii_tx_er       (gmii_tx_er),
                .gmii_txd         (gmii_txd),
                .gmii_rx_dv       (gmii_rx_dv),
                .gmii_rx_er       (gmii_rx_er),
                .gmii_rxd         (gmii_rxd),
                .ctrl_wr_en       (udp_ctrl_wr),
                .ctrl_addr        (udp_ctrl_addr),
                .ctrl_wdata       (udp_ctrl_wdata),
                .ctrl_seq         (),
                .eth_remote_alive (eth_remote_alive_stat),
                .tx_pkt_cnt       (),
                .rx_pkt_cnt       (),
                .fcs_err_cnt      ()
            );

            // Clause 22 MDIO Management + PHY Reset
            reg        mdio_req_vld;
            reg        mdio_req_wr;
            reg [4:0]  mdio_req_reg;
            reg [15:0] mdio_req_wdata;
            wire       mdio_req_ready;

            eth_mdio #(
                .PHY_ADDR (5'd1),
                .MDC_DIV  (64),
                .RST_CYC  (ETH_MDIO_RST_CYC),
                .POLL_DIV (ETH_MDIO_POLL_DIV)
            ) u_eth_mdio (
                .clk            (link_clk),
                .rst            (link_rst),
                .req_valid      (mdio_req_vld),
                .req_write      (mdio_req_wr),
                .req_reg        (mdio_req_reg),
                .req_wdata      (mdio_req_wdata),
                .req_ready      (mdio_req_ready),
                .resp_valid     (),
                .resp_rdata     (),
                .phy_rst_done   (),
                .copper_link_up (eth_copper_up_stat),
                .bmsr_val       (),
                .int_pending    (),
                .eth_mdc        (eth_mdc),
                .eth_mdio       (eth_mdio),
                .eth_rst_n      (eth_rst_n),
                .eth_int_n      (1'b1)
            );

            // Runtime Redundancy Policy & Fault Injection Registers (written via UDP Control)
            reg [1:0] eth_policy;
            reg       eth_sdr_en;
            reg       ctrl_force_ias_fault;
            reg       ctrl_force_eth_fault;
            reg       ias_seen_dl_up;

            always @(posedge link_clk) begin
                if (eth_rst_125) begin
                    eth_policy           <= ETH_DEFAULT_POLICY;
                    eth_sdr_en           <= 1'b1;
                    ctrl_force_ias_fault <= 1'b0;
                    ctrl_force_eth_fault <= 1'b0;
                    ctrl_an_restart      <= 1'b0;
                    mdio_req_vld         <= 1'b0;
                    mdio_req_wr          <= 1'b0;
                    mdio_req_reg         <= 5'd0;
                    mdio_req_wdata       <= 16'd0;
                    ias_seen_dl_up       <= 1'b0;
                end else begin
                    ctrl_an_restart <= 1'b0;
                    if (mdio_req_vld && mdio_req_ready)
                        mdio_req_vld <= 1'b0;
                    if (dl_up_sync[1])
                        ias_seen_dl_up <= 1'b1;

                    if (udp_ctrl_wr) begin
                        case (udp_ctrl_addr)
                            16'h0000: begin
                                eth_policy           <= udp_ctrl_wdata[1:0];
                                eth_sdr_en           <= udp_ctrl_wdata[2];
                                ctrl_force_ias_fault <= udp_ctrl_wdata[3];
                                ctrl_force_eth_fault <= udp_ctrl_wdata[4];
                                ctrl_an_restart      <= udp_ctrl_wdata[5];
                            end
                            16'h0004: begin
                                mdio_req_vld   <= 1'b1;
                                mdio_req_wr    <= udp_ctrl_wdata[21];
                                mdio_req_reg   <= udp_ctrl_wdata[20:16];
                                mdio_req_wdata <= udp_ctrl_wdata[15:0];
                            end
                            default: ;
                        endcase
                    end
                end
            end

            // Stream 1 (SDR / Telemetry, stream_id=8'h02)
            wire        sdr_pkt_valid, sdr_pkt_ready, sdr_pkt_sop, sdr_pkt_eop;
            wire [7:0]  sdr_pkt_sid;
            wire [15:0] sdr_pkt_len;
            wire [31:0] sdr_pkt_seq;
            wire [63:0] sdr_pkt_ts, sdr_pkt_data;

            eth_sdr_pkt_gen #(
                .STREAM_ID (8'h02),
                .PKT_BYTES (ETH_SDR_PKT_BYTES),
                .GAP_CYC   (ETH_SDR_GAP_CYC)
            ) u_sdr_gen (
                .clk           (link_clk),
                .rst           (eth_rst_125),
                .en            (eth_sdr_en & eth_link_up_stat),
                .timestamp_cnt (timestamp_cnt),
                .pkt_valid     (sdr_pkt_valid),
                .pkt_ready     (sdr_pkt_ready),
                .pkt_sop       (sdr_pkt_sop),
                .pkt_eop       (sdr_pkt_eop),
                .pkt_stream_id (sdr_pkt_sid),
                .pkt_len       (sdr_pkt_len),
                .pkt_seq       (sdr_pkt_seq),
                .pkt_timestamp (sdr_pkt_ts),
                .pkt_data      (sdr_pkt_data)
            );

            assign eth_ctrl_wr    = udp_ctrl_wr;
            assign eth_ctrl_addr  = udp_ctrl_addr;
            assign eth_ctrl_wdata = udp_ctrl_wdata;

            wire ias_path_ok = ~ctrl_force_ias_fault & (dl_up_sync[1] | ~ias_seen_dl_up);
            wire eth_path_ok = eth_link_up_stat & ~ctrl_force_eth_fault;

            dual_path_mux u_dual_mux (
                .clk           (link_clk),
                .rst           (eth_rst_125),
                .policy        (eth_policy),
                .ias_healthy   (ias_path_ok),
                .eth_healthy   (eth_path_ok),
                .s0_valid      (s0_arb_valid),
                .s0_ready      (s0_arb_ready),
                .s0_sop        (s0_arb_sop),
                .s0_eop        (s0_arb_eop),
                .s0_stream_id  (s0_arb_sid),
                .s0_len        (s0_arb_len),
                .s0_seq        (s0_arb_seq),
                .s0_timestamp  (s0_arb_ts),
                .s0_data       (s0_arb_data),
                .s1_valid      (sdr_pkt_valid),
                .s1_ready      (sdr_pkt_ready),
                .s1_sop        (sdr_pkt_sop),
                .s1_eop        (sdr_pkt_eop),
                .s1_stream_id  (sdr_pkt_sid),
                .s1_len        (sdr_pkt_len),
                .s1_seq        (sdr_pkt_seq),
                .s1_timestamp  (sdr_pkt_ts),
                .s1_data       (sdr_pkt_data),
                .ias_valid     (ias_mux_valid),
                .ias_ready     (ias_mux_ready),
                .ias_sop       (ias_mux_sop),
                .ias_eop       (ias_mux_eop),
                .ias_stream_id (ias_mux_sid),
                .ias_len       (ias_mux_len),
                .ias_seq       (ias_mux_seq),
                .ias_timestamp (ias_mux_ts),
                .ias_data      (ias_mux_data),
                .eth_valid     (eth_mux_valid),
                .eth_ready     (eth_mux_ready),
                .eth_sop       (eth_mux_sop),
                .eth_eop       (eth_mux_eop),
                .eth_stream_id (eth_mux_sid),
                .eth_len       (eth_mux_len),
                .eth_seq       (eth_mux_seq),
                .eth_timestamp (eth_mux_ts),
                .eth_data      (eth_mux_data),
                .failover_cnt  ()
            );
        end else begin : gen_no_eth
            assign eth_ctrl_wr           = 1'b0;
            assign eth_ctrl_addr         = 16'd0;
            assign eth_ctrl_wdata        = 32'd0;
            assign eth_link_up_stat      = 1'b0;
            assign eth_remote_alive_stat = 1'b0;
            assign eth_copper_up_stat    = 1'b0;
            assign ias_mux_valid         = s0_arb_valid;
            assign s0_arb_ready          = ias_mux_ready;
            assign ias_mux_sop           = s0_arb_sop;
            assign ias_mux_eop           = s0_arb_eop;
            assign ias_mux_sid           = s0_arb_sid;
            assign ias_mux_len           = s0_arb_len;
            assign ias_mux_seq           = s0_arb_seq;
            assign ias_mux_ts            = s0_arb_ts;
            assign ias_mux_data          = s0_arb_data;

            wire eth_sgrx_unused;
            IBUFDS #(.DIFF_TERM("TRUE"), .IOSTANDARD("LVDS_25")) u_ibuf_eth_unused (.I(eth_sgrx_p), .IB(eth_sgrx_n), .O(eth_sgrx_unused));
            OBUFDS #(.IOSTANDARD("LVDS_25")) u_obuf_eth_unused (.I(1'b0), .O(eth_sgtx_p), .OB(eth_sgtx_n));
            assign eth_mdc   = 1'b0;
            assign eth_mdio  = 1'bz;
            assign eth_rst_n = 1'b0;
        end
    endgenerate

    link_pcs_tx #(
        .AM_PERIOD (LINK_AM_PERIOD)
    ) u_ul_pcs_tx (
        .clk           (link_clk),
        .rst           (link_rst),
        .pkt_valid     (ias_mux_valid),
        .pkt_ready     (ias_mux_ready),
        .pkt_sop       (ias_mux_sop),
        .pkt_eop       (ias_mux_eop),
        .pkt_stream_id (ias_mux_sid),
        .pkt_len       (ias_mux_len),
        .pkt_seq       (ias_mux_seq),
        .pkt_timestamp (ias_mux_ts),
        .pkt_data      (ias_mux_data),
        .dropped_cnt   (tx_dropped_cnt),
        .local_status  (local_status_word),
        .tx_byte_l0    (pcs_tx_byte_l0),
        .tx_byte_l1    (pcs_tx_byte_l1)
    );

    // Optional PRBS7 TX override for link bring-up bathtub testing
    reg [6:0] tx_prbs_lfsr;
    reg [7:0] tx_prbs_byte;
    integer   pk;
    always @(posedge link_clk) begin
        if (link_rst) begin
            tx_prbs_lfsr <= 7'h7F;
            tx_prbs_byte <= 8'd0;
        end else if (spi_ctrl_prbs7_tx_en) begin
            for (pk = 0; pk < 8; pk = pk + 1) begin
                tx_prbs_byte[pk] <= tx_prbs_lfsr[6] ^ tx_prbs_lfsr[5];
                tx_prbs_lfsr     <= {tx_prbs_lfsr[5:0], tx_prbs_lfsr[6] ^ tx_prbs_lfsr[5]};
            end
        end
    end

    wire [7:0] ul_byte_l0 = spi_ctrl_prbs7_tx_en ? tx_prbs_byte : pcs_tx_byte_l0;
    wire [7:0] ul_byte_l1 = spi_ctrl_prbs7_tx_en ? ~tx_prbs_byte : pcs_tx_byte_l1;

    wire ser_ul_clk, ser_ul_d0, ser_ul_d1;

    OSERDESE2 #(
        .DATA_RATE_OQ("DDR"), .DATA_RATE_TQ("BUF"), .DATA_WIDTH(8),
        .SERDES_MODE("MASTER"), .TRISTATE_WIDTH(1)
    ) u_oserdes_ul_clk (
        .OFB(), .OQ(ser_ul_clk), .SHIFTOUT1(), .SHIFTOUT2(), .TBYTEOUT(), .TFB(), .TQ(),
        .CLK(tx_clk_ddr), .CLKDIV(link_clk),
        .D1(1'b0), .D2(1'b1), .D3(1'b0), .D4(1'b1),
        .D5(1'b0), .D6(1'b1), .D7(1'b0), .D8(1'b1),
        .OCE(1'b1), .RST(link_rst), .SHIFTIN1(1'b0), .SHIFTIN2(1'b0),
        .T1(1'b0), .T2(1'b0), .T3(1'b0), .T4(1'b0), .TBYTEIN(1'b0), .TCE(1'b0)
    );

    OSERDESE2 #(
        .DATA_RATE_OQ("DDR"), .DATA_RATE_TQ("BUF"), .DATA_WIDTH(8),
        .SERDES_MODE("MASTER"), .TRISTATE_WIDTH(1)
    ) u_oserdes_ul_d0 (
        .OFB(), .OQ(ser_ul_d0), .SHIFTOUT1(), .SHIFTOUT2(), .TBYTEOUT(), .TFB(), .TQ(),
        .CLK(tx_clk_ddr), .CLKDIV(link_clk),
        .D1(ul_byte_l0[0]), .D2(ul_byte_l0[1]), .D3(ul_byte_l0[2]), .D4(ul_byte_l0[3]),
        .D5(ul_byte_l0[4]), .D6(ul_byte_l0[5]), .D7(ul_byte_l0[6]), .D8(ul_byte_l0[7]),
        .OCE(1'b1), .RST(link_rst), .SHIFTIN1(1'b0), .SHIFTIN2(1'b0),
        .T1(1'b0), .T2(1'b0), .T3(1'b0), .T4(1'b0), .TBYTEIN(1'b0), .TCE(1'b0)
    );

    OSERDESE2 #(
        .DATA_RATE_OQ("DDR"), .DATA_RATE_TQ("BUF"), .DATA_WIDTH(8),
        .SERDES_MODE("MASTER"), .TRISTATE_WIDTH(1)
    ) u_oserdes_ul_d1 (
        .OFB(), .OQ(ser_ul_d1), .SHIFTOUT1(), .SHIFTOUT2(), .TBYTEOUT(), .TFB(), .TQ(),
        .CLK(tx_clk_ddr), .CLKDIV(link_clk),
        .D1(ul_byte_l1[0]), .D2(ul_byte_l1[1]), .D3(ul_byte_l1[2]), .D4(ul_byte_l1[3]),
        .D5(ul_byte_l1[4]), .D6(ul_byte_l1[5]), .D7(ul_byte_l1[6]), .D8(ul_byte_l1[7]),
        .OCE(1'b1), .RST(link_rst), .SHIFTIN1(1'b0), .SHIFTIN2(1'b0),
        .T1(1'b0), .T2(1'b0), .T3(1'b0), .T4(1'b0), .TBYTEIN(1'b0), .TCE(1'b0)
    );

    OBUFDS #(.IOSTANDARD("LVDS_25")) u_obuf_ul_clk (.I(ser_ul_clk), .O(link_rx_clk_p), .OB(link_rx_clk_n));
    OBUFDS #(.IOSTANDARD("LVDS_25")) u_obuf_ul_d0  (.I(ser_ul_d0),  .O(link_rx_d0_p),  .OB(link_rx_d0_n));
    OBUFDS #(.IOSTANDARD("LVDS_25")) u_obuf_ul_d1  (.I(ser_ul_d1),  .O(link_rx_d1_p),  .OB(link_rx_d1_n));

    // -------------------------------------------------------------------------
    // 6. Pmod J1102 SPI Slave & Housekeeping (Bank 15 & Bank 35)
    // -------------------------------------------------------------------------
    wire pmod_miso_int, pmod_miso_oe;

    pmod_spi #(
        .FB_FIFO_DEPTH (64)
    ) u_pmod_spi (
        .clk                  (link_clk),
        .rst                  (sys_rst),
        .pmod_cs_n            (pmod_cs_n),
        .pmod_sclk            (pmod_sclk),
        .pmod_mosi            (pmod_mosi),
        .pmod_miso            (pmod_miso_int),
        .pmod_miso_oe         (pmod_miso_oe),
        .ctrl_soft_rst        (spi_ctrl_soft_rst),
        .ctrl_loopback_en     (spi_ctrl_loopback_en),
        .ctrl_retrain_pulse   (spi_ctrl_retrain_pulse),
        .ctrl_tap_override_en (spi_ctrl_tap_override_en),
        .ctrl_prbs7_tx_en     (spi_ctrl_prbs7_tx_en),
        .ctrl_prbs7_rx_chk_en (spi_ctrl_prbs7_rx_chk_en),
        .ctrl_clr_err_pulse   (spi_ctrl_clr_err_pulse),
        .ctrl_fallback_en     (spi_ctrl_fallback_en),
        .cfg_tap_l0           (spi_cfg_tap_l0),
        .cfg_load_l0          (spi_cfg_load_l0),
        .cfg_tap_l1           (spi_cfg_tap_l1),
        .cfg_load_l1          (spi_cfg_load_l1),
        .st_train_state       (dl_st_sync2),
        .st_l0_block_lock     (dl_lock_sync[1]),
        .st_l1_block_lock     (1'b1),
        .st_deskew_lock       (dl_lock_sync[1]),
        .st_link_up           (dl_up_sync[1]),
        .st_idelayctrl_rdy    (1'b1),
        .st_remote_status     (dl_rem_sync2),
        .active_tap_l0        (dl_tap_sync2),
        .active_tap_l1        ({4'd0, adc_tap_flat[4:0]}),
        .err_cnt_sh_l0        (dl_sh_sync2),
        .err_cnt_sh_l1        ({26'd0, adc_eye_width_min}),
        .err_cnt_crc          (dl_crc_sync2),
        .pkt_cnt_rx           (dl_pkt_sync2),
        .tx_dropped_cnt       (tx_dropped_cnt),
        .rx_drop_cnt          (dl_drop_sync2),
        .skew_blocks          (8'd0),
        .am_seq               ({15'd0, eth_copper_up_stat}),
        .prbs_err_cnt         (dl_prbs_sync2),
        .eye_left_l0          (dl_el_sync2),
        .eye_right_l0         (dl_er_sync2),
        .eye_left_l1          (9'd0),
        .eye_right_l1         (9'd0),
        .fb_ddc_i             (fb_ddc_i_link),
        .fb_ddc_q             (fb_ddc_q_link),
        .fb_ddc_valid         (fb_ddc_valid_link)
    );

    assign pmod_miso   = pmod_miso_oe ? pmod_miso_int : 1'bz;
    assign pmod_spare2 = dl_up_sync[1] & adc_tr_sync[1];

    // -------------------------------------------------------------------------
    // 7. Tasks 13-16: AD9253 + SDR DDC, DACs, 8x ADAR1000 + RF SW, HK + XO + XADC + PPS
    //    Register map 0x34..0xE0 (LINK_PROTOCOL.md Section 7.2) via Downlink 0x10 or UDP 0x10
    // -------------------------------------------------------------------------
    reg  [31:0] reg_adcs_ctrl;
    reg  [31:0] reg_conv_spi_cmd;
    reg         reg_conv_spi_start_p;
    reg         reg_adcs_init_p;
    reg         conv_resp_valid_sticky;
    reg  [7:0]  conv_resp_rdata_hold;

    reg  [31:0] reg_sdr_nco_a;
    reg  [31:0] reg_sdr_nco_b;
    reg  [15:0] reg_sdr_decim;
    reg  [9:0]  reg_sdr_words_per_pkt;
    reg         sdr_cfg_tog_link;

    reg  [31:0] reg_dacr_ctrl;
    reg         reg_dacr_trig_p;
    reg  [31:0] reg_dacr_f0;
    reg  [31:0] reg_dacr_df;
    reg  [31:0] reg_dacr_plen;
    reg  [31:0] reg_dacr_pri;
    reg  [31:0] reg_dacs_ctrl;

    reg  [31:0] reg_adar_ctrl;
    reg         reg_adar_load_p;
    reg         reg_adar_init_p;
    reg         reg_adar_sw_p;
    reg  [31:0] reg_adar_guard;
    reg  [15:0] reg_adar_sw_settle;
    reg  [31:0] reg_adar_tbl_wr;
    reg         reg_adar_tbl_p;
    reg  [31:0] reg_adar_spi_cmd;
    reg         reg_adar_spi_p;

    reg  [31:0] reg_hk_i2c_ctrl;
    reg  [31:0] reg_hk_i2c_cmd;
    reg         reg_hk_i2c_p;
    reg  [31:0] reg_hk_i2c_wdata;

    reg  [31:0] reg_xo_ctrl;
    reg         reg_xo_prog_p;
    reg         reg_xo_delta_p;
    reg  [23:0] reg_xo_delta_m;
    reg  [31:0] reg_xo_raw_cmd;
    reg         reg_xo_raw_p;
    reg         xo_raw_valid_sticky;
    reg  [7:0]  xo_raw_rdata_hold;
    reg         xo_raw_err_hold;

    reg  [15:0] reg_pps_step_q8;
    reg         reg_pps_disc_en;
    reg         reg_pps_clear_p;
    reg  [31:0] reg_pps_nom_cyc;

    // Cross DACS_CTRL[0] cleanly into dl_rx_clk to gate long 0x10 vs command 0x10
    (* ASYNC_REG = "TRUE" *) reg [1:0] reg_dacs_ctrl_dl;
    always @(posedge dl_rx_clk or posedge dl_rx_rst) begin
        if (dl_rx_rst) reg_dacs_ctrl_dl <= 2'b00;
        else           reg_dacs_ctrl_dl <= {reg_dacs_ctrl_dl[0], reg_dacs_ctrl[0]};
    end

    wire dl_is_iq_pkt = dl_out_valid &&
                        ((dl_out_sid == 8'h12) ||
                         ((dl_out_sid == 8'h10) && reg_dacs_ctrl_dl[1] && (dl_out_len >= 16'd24)));
    wire dl_cmd_push  = dl_out_valid && (dl_out_sid == 8'h10) && dl_out_sop && !dl_is_iq_pkt;

    // Gray-coded 16-entry async FIFO: downlink 8'h10 commands (dl_rx_clk -> link_clk)
    (* ram_style = "distributed" *) reg [63:0] dl_cmd_mem [0:15];
    reg  [4:0] dl_cmd_wbin, dl_cmd_wgray;
    reg  [4:0] dl_cmd_rbin, dl_cmd_rgray;
    (* ASYNC_REG = "TRUE" *) reg [4:0] dl_cmd_wgray_s1, dl_cmd_wgray_s2;
    (* ASYNC_REG = "TRUE" *) reg [4:0] dl_cmd_rgray_s1, dl_cmd_rgray_s2;

    function [4:0] gray5(input [4:0] b);
        begin
            gray5 = (b >> 1) ^ b;
        end
    endfunction

    wire dl_cmd_full  = (dl_cmd_wgray == {~dl_cmd_rgray_s2[4:3], dl_cmd_rgray_s2[2:0]});
    wire dl_cmd_empty = (dl_cmd_rgray == dl_cmd_wgray_s2);

    always @(posedge dl_rx_clk or posedge dl_rx_rst) begin
        if (dl_rx_rst) begin
            dl_cmd_wbin     <= 5'd0;
            dl_cmd_wgray    <= 5'd0;
            dl_cmd_rgray_s1 <= 5'd0;
            dl_cmd_rgray_s2 <= 5'd0;
        end else begin
            dl_cmd_rgray_s1 <= dl_cmd_rgray;
            dl_cmd_rgray_s2 <= dl_cmd_rgray_s1;
            if (dl_cmd_push && !dl_cmd_full) begin
                dl_cmd_mem[dl_cmd_wbin[3:0]] <= dl_out_data;
                dl_cmd_wbin  <= dl_cmd_wbin + 5'd1;
                dl_cmd_wgray <= gray5(dl_cmd_wbin + 5'd1);
            end
        end
    end

    reg  [63:0] dl_cmd_word;
    reg         dl_cmd_pop_r;
    always @(posedge link_clk) begin
        if (link_rst) begin
            dl_cmd_rbin     <= 5'd0;
            dl_cmd_rgray    <= 5'd0;
            dl_cmd_wgray_s1 <= 5'd0;
            dl_cmd_wgray_s2 <= 5'd0;
            dl_cmd_pop_r    <= 1'b0;
            dl_cmd_word     <= 64'd0;
        end else begin
            dl_cmd_wgray_s1 <= dl_cmd_wgray;
            dl_cmd_wgray_s2 <= dl_cmd_wgray_s1;
            dl_cmd_pop_r    <= 1'b0;
            if (!dl_cmd_empty && !dl_cmd_pop_r) begin
                dl_cmd_word  <= dl_cmd_mem[dl_cmd_rbin[3:0]];
                dl_cmd_rbin  <= dl_cmd_rbin + 5'd1;
                dl_cmd_rgray <= gray5(dl_cmd_rbin + 5'd1);
                dl_cmd_pop_r <= 1'b1;
            end
        end
    end

    // AD9253 Capture (shares Bank 14 IDELAYCTRL with u_adc_cap -> INST_IDELAYCTRL = 0)
    wire        adcs_clk_div;
    wire        adcs_sample_valid;
    wire signed [13:0] adcs_sample_a, adcs_sample_b;
    wire        adcs_aligned, adcs_idelay_done, adcs_idelay_err, adcs_bitslip_err;
    wire [4:0]  adcs_best_tap;

    adcs_capture #(
        .INST_IDELAYCTRL (1'b0)
    ) u_adcs_cap (
        .rst          (ref_rst),
        .refclk_200m  (refclk_200m),
        .enable       (reg_adcs_ctrl[0]),
        .adcs_dco_p   (adcs_dco_p),
        .adcs_dco_n   (adcs_dco_n),
        .adcs_fco_p   (adcs_fco_p),
        .adcs_fco_n   (adcs_fco_n),
        .adcs_d0_p    (adcs_d0_p),
        .adcs_d0_n    (adcs_d0_n),
        .adcs_d1_p    (adcs_d1_p),
        .adcs_d1_n    (adcs_d1_n),
        .clk_div      (adcs_clk_div),
        .sample_valid (adcs_sample_valid),
        .sample_a     (adcs_sample_a),
        .sample_b     (adcs_sample_b),
        .aligned      (adcs_aligned),
        .idelay_done  (adcs_idelay_done),
        .idelay_err   (adcs_idelay_err),
        .bitslip_err  (adcs_bitslip_err),
        .best_tap     (adcs_best_tap),
        .bitslip_cnt  (),
        .idelay_rdy   ()
    );

    // Sync adcs_capture status into link_clk + reset & 16-entry Gray-coded async
    // sample FIFO from u_adcs_cap BUFR (adcs_clk_div) into global BUFG adcs_ddc_clk
    // so SDR DDC DSP48 slices can span all clock regions of XC7A50T.
    (* ASYNC_REG = "TRUE" *) reg [1:0] adcs_rst_sync = 2'b11;
    wire adcs_rst_src = link_rst;
    always @(posedge adcs_clk_div or posedge adcs_rst_src) begin
        if (adcs_rst_src) adcs_rst_sync <= 2'b11;
        else              adcs_rst_sync <= {adcs_rst_sync[0], 1'b0};
    end
    wire adcs_rst_div = adcs_rst_sync[1];

    (* ASYNC_REG = "TRUE" *) reg [1:0] adcs_ddc_rst_sync = 2'b11;
    always @(posedge adcs_ddc_clk or posedge adcs_rst_src) begin
        if (adcs_rst_src) adcs_ddc_rst_sync <= 2'b11;
        else              adcs_ddc_rst_sync <= {adcs_ddc_rst_sync[0], 1'b0};
    end
    wire adcs_ddc_rst = adcs_ddc_rst_sync[1];

    function automatic [4:0] adcs_gray5;
        input [4:0] b;
        begin
            adcs_gray5 = b ^ (b >> 1);
        end
    endfunction

    (* ram_style = "distributed" *)
    reg [27:0] adcs_samp_mem [0:15];
    reg [4:0]  adcs_samp_wbin, adcs_samp_wgray;
    (* ASYNC_REG = "TRUE" *) reg [4:0] adcs_samp_rgray_s1, adcs_samp_rgray_s2;
    reg [4:0]  adcs_samp_rbin, adcs_samp_rgray;
    (* ASYNC_REG = "TRUE" *) reg [4:0] adcs_samp_wgray_s1, adcs_samp_wgray_s2;

    wire adcs_samp_full  = (adcs_samp_wgray == {~adcs_samp_rgray_s2[4:3], adcs_samp_rgray_s2[2:0]});
    wire adcs_samp_empty = (adcs_samp_rgray == adcs_samp_wgray_s2);

    always @(posedge adcs_clk_div) begin
        if (adcs_rst_div) begin
            adcs_samp_wbin     <= 5'd0;
            adcs_samp_wgray    <= 5'd0;
            adcs_samp_rgray_s1 <= 5'd0;
            adcs_samp_rgray_s2 <= 5'd0;
        end else begin
            adcs_samp_rgray_s1 <= adcs_samp_rgray;
            adcs_samp_rgray_s2 <= adcs_samp_rgray_s1;
            if (adcs_sample_valid && !adcs_samp_full) begin
                adcs_samp_mem[adcs_samp_wbin[3:0]] <= {adcs_sample_b, adcs_sample_a};
                adcs_samp_wbin                     <= adcs_samp_wbin + 5'd1;
                adcs_samp_wgray                    <= adcs_gray5(adcs_samp_wbin + 5'd1);
            end
        end
    end

    reg        sdr_in_valid;
    reg signed [13:0] sdr_in_a, sdr_in_b;
    always @(posedge adcs_ddc_clk) begin
        if (adcs_ddc_rst) begin
            adcs_samp_rbin     <= 5'd0;
            adcs_samp_rgray    <= 5'd0;
            adcs_samp_wgray_s1 <= 5'd0;
            adcs_samp_wgray_s2 <= 5'd0;
            sdr_in_valid       <= 1'b0;
            sdr_in_a           <= 14'sd0;
            sdr_in_b           <= 14'sd0;
        end else begin
            adcs_samp_wgray_s1 <= adcs_samp_wgray;
            adcs_samp_wgray_s2 <= adcs_samp_wgray_s1;
            sdr_in_valid       <= 1'b0;
            if (!adcs_samp_empty) begin
                {sdr_in_b, sdr_in_a} <= adcs_samp_mem[adcs_samp_rbin[3:0]];
                sdr_in_valid         <= 1'b1;
                adcs_samp_rbin       <= adcs_samp_rbin + 5'd1;
                adcs_samp_rgray      <= adcs_gray5(adcs_samp_rbin + 5'd1);
            end
        end
    end

    (* ASYNC_REG = "TRUE" *) reg [1:0] adcs_ch_en_s1, adcs_ch_en_s2;
    (* ASYNC_REG = "TRUE" *) reg [2:0] sdr_cfg_tog_sync;
    reg [31:0] sdr_nco_a_adcs, sdr_nco_b_adcs;
    reg [15:0] sdr_decim_adcs;
    always @(posedge adcs_ddc_clk) begin
        if (adcs_ddc_rst) begin
            adcs_ch_en_s1    <= 2'b00;
            adcs_ch_en_s2    <= 2'b00;
            sdr_cfg_tog_sync <= 3'd0;
            sdr_nco_a_adcs   <= 32'd0;
            sdr_nco_b_adcs   <= 32'd0;
            sdr_decim_adcs   <= 16'd4;
        end else begin
            adcs_ch_en_s1    <= reg_adcs_ctrl[3:2];
            adcs_ch_en_s2    <= adcs_ch_en_s1;
            sdr_cfg_tog_sync <= {sdr_cfg_tog_sync[1:0], sdr_cfg_tog_link};
            if (sdr_cfg_tog_sync[2] ^ sdr_cfg_tog_sync[1]) begin
                sdr_nco_a_adcs <= reg_sdr_nco_a;
                sdr_nco_b_adcs <= reg_sdr_nco_b;
                sdr_decim_adcs <= reg_sdr_decim;
            end
        end
    end

    (* ASYNC_REG = "TRUE" *) reg [1:0] adcs_al_s, adcs_id_s, adcs_ie_s, adcs_be_s;
    (* ASYNC_REG = "TRUE" *) reg [4:0] adcs_tap_s1, adcs_tap_s2;
    always @(posedge link_clk) begin
        if (link_rst) begin
            adcs_al_s   <= 2'b00; adcs_id_s <= 2'b00;
            adcs_ie_s   <= 2'b00; adcs_be_s <= 2'b00;
            adcs_tap_s1 <= 5'd0;  adcs_tap_s2 <= 5'd0;
        end else begin
            adcs_al_s   <= {adcs_al_s[0], adcs_aligned};
            adcs_id_s   <= {adcs_id_s[0], adcs_idelay_done};
            adcs_ie_s   <= {adcs_ie_s[0], adcs_idelay_err};
            adcs_be_s   <= {adcs_be_s[0], adcs_bitslip_err};
            adcs_tap_s1 <= adcs_best_tap;
            adcs_tap_s2 <= adcs_tap_s1;
        end
    end

    // Converter Shared 3-wire SPI (AD9484 + AD9253, Bank 35 LVCMOS18)
    wire       conv_req_ready, conv_resp_valid;
    wire [7:0] conv_resp_rdata, ad9253_chip_id;
    wire       conv_init_done, conv_init_err;
    wire       conv_sdio_o, conv_sdio_t, conv_sdio_i;

    conv_spi #(
        .CLK_DIV           (CONV_SPI_CLK_DIV),
        .RESET_WAIT_CYCLES (CONV_SPI_RST_CYC),
        .AUTO_INIT         (CONV_SPI_AUTO_INIT),
        .CHECK_AD9484      (1'b1)
    ) u_conv_spi (
        .clk        (link_clk),
        .rst        (link_rst),
        .start_init (reg_adcs_init_p),
        .req_valid  (reg_conv_spi_start_p),
        .req_ready  (conv_req_ready),
        .req_target (reg_conv_spi_cmd[22]),
        .req_rw     (reg_conv_spi_cmd[21]),
        .req_addr   (reg_conv_spi_cmd[20:8]),
        .req_wdata  (reg_conv_spi_cmd[7:0]),
        .resp_valid (conv_resp_valid),
        .resp_rdata (conv_resp_rdata),
        .init_done  (conv_init_done),
        .init_err   (conv_init_err),
        .ad9253_id  (ad9253_chip_id),
        .ad9484_id  (),
        .spi_sclk   (conv_spi_sclk),
        .spi_csb_r  (conv_spi_csb_r),
        .spi_csb_s  (conv_spi_csb_s),
        .spi_sdio_o (conv_sdio_o),
        .spi_sdio_t (conv_sdio_t),
        .spi_sdio_i (conv_sdio_i)
    );
    IOBUF #(.IOSTANDARD("LVCMOS18")) u_iobuf_conv_sdio (
        .I(conv_sdio_o), .T(conv_sdio_t), .O(conv_sdio_i), .IO(conv_spi_sdio)
    );

    // XADC + PPS Discipline (also feeds monotonic timestamp_ns_sys to SDR DDC & 0xC0..0xE0)
    wire [11:0] xadc_temp_raw, xadc_vccint_raw, xadc_vccaux_raw;
    wire        xadc_valid, xadc_overtemp;
    wire [63:0] xadc_ts_sys, pps_latch_ts;
    wire [31:0] pps_period_cyc, pps_meas_cnt;
    wire signed [31:0] pps_ppm_err;
    wire        pps_locked;

    hk_xadc_pps #(
        .DEFAULT_NOM_CYC (PPS_DEFAULT_NOM_CYC),
        .DEFAULT_STEP_Q8 (16'h0800),
        .XADC_POLL_DIV   (XADC_POLL_DIV_P)
    ) u_xadc_pps (
        .sys_clk            (link_clk),
        .sys_rst            (link_rst),
        .adc_clk            (link_clk),
        .adc_rst            (link_rst),
        .pps_sync           (pps_sync),
        .cfg_nom_period_cyc (reg_pps_nom_cyc),
        .cfg_ts_step_q8     (reg_pps_step_q8),
        .cfg_pps_disc_en    (reg_pps_disc_en),
        .cfg_ts_clear       (reg_pps_clear_p),
        .xadc_temp_raw      (xadc_temp_raw),
        .xadc_vccint_raw    (xadc_vccint_raw),
        .xadc_vccaux_raw    (xadc_vccaux_raw),
        .xadc_valid         (xadc_valid),
        .xadc_overtemp      (xadc_overtemp),
        .timestamp_ns_adc   (),
        .timestamp_ns_sys   (xadc_ts_sys),
        .pps_latch_ts       (pps_latch_ts),
        .pps_period_cyc     (pps_period_cyc),
        .pps_ppm_err        (pps_ppm_err),
        .pps_cnt            (pps_meas_cnt),
        .pps_locked         (pps_locked)
    );

    // AD9253 Dual-Channel SDR DDC (Streams 8'h04 Ch A, 8'h05 Ch B)
    wire        sdr_adc_pkt_valid, sdr_adc_pkt_ready, sdr_adc_pkt_sop, sdr_adc_pkt_eop;
    wire [7:0]  sdr_adc_pkt_sid;
    wire [15:0] sdr_adc_pkt_len;
    wire [31:0] sdr_adc_pkt_seq;
    wire [63:0] sdr_adc_pkt_ts, sdr_adc_pkt_data;
    wire [23:0] sdr_adc_dropped_cnt;

    sdr_ddc #(
        .STREAM_ID_A (8'h04),
        .STREAM_ID_B (8'h05),
        .FIFO_AW     (9)
    ) u_sdr_ddc (
        .adc_clk       (adcs_ddc_clk),
        .adc_rst       (adcs_ddc_rst),
        .sample_valid  (sdr_in_valid),
        .sample_a      (sdr_in_a),
        .sample_b      (sdr_in_b),
        .ch_enable     (adcs_ch_en_s2),
        .nco_ftw_a     (sdr_nco_a_adcs),
        .nco_ftw_b     (sdr_nco_b_adcs),
        .decim_ratio   (sdr_decim_adcs),
        .words_per_pkt (reg_sdr_words_per_pkt),
        .link_clk      (link_clk),
        .link_rst      (link_rst),
        .timestamp_cnt (xadc_ts_sys),
        .pkt_valid     (sdr_adc_pkt_valid),
        .pkt_ready     (sdr_adc_pkt_ready),
        .pkt_sop       (sdr_adc_pkt_sop),
        .pkt_eop       (sdr_adc_pkt_eop),
        .pkt_stream_id (sdr_adc_pkt_sid),
        .pkt_len       (sdr_adc_pkt_len),
        .pkt_seq       (sdr_adc_pkt_seq),
        .pkt_timestamp (sdr_adc_pkt_ts),
        .pkt_data      (sdr_adc_pkt_data),
        .dropped_cnt   (sdr_adc_dropped_cnt)
    );

    // AD9708 Radar Chirp DAC + AD9767 Interleaved SDR DAC
    wire        dacr_chirp_active;
    wire [31:0] dacr_pulse_cnt;
    dac_radar u_dac_radar (
        .dac_clk      (link_clk),
        .dac_rst      (link_rst),
        .chirp_enable (reg_dacr_ctrl[0]),
        .chirp_trig   (reg_dacr_trig_p),
        .f0_ftw       (reg_dacr_f0),
        .df_ftw       (reg_dacr_df),
        .pulse_len    (reg_dacr_plen),
        .pri_len      (reg_dacr_pri),
        .amp_scale    (reg_dacr_ctrl[23:16]),
        .chirp_active (dacr_chirp_active),
        .pulse_cnt    (dacr_pulse_cnt),
        .dacr_clk     (dacr_clk),
        .dacr_d       (dacr_d)
    );

    wire [31:0] dacs_underflow_cnt;
    wire [9:0]  dacs_fifo_lvl_dl;
    dac_sdr #(
        .FIFO_AW (9)
    ) u_dac_sdr (
        .link_clk        (dl_rx_clk),
        .link_rst        (dl_rx_rst),
        .s_valid         (dl_is_iq_pkt),
        .s_ready         (),
        .s_data          (dl_out_data),
        .dac_clk         (link_clk),
        .dac_rst         (link_rst),
        .tx_enable       (reg_dacs_ctrl[0]),
        .underflow_cnt   (dacs_underflow_cnt),
        .fifo_level_link (dacs_fifo_lvl_dl),
        .dacs_d          (dacs_d),
        .dacs_iqclk      (dacs_iqclk),
        .dacs_iqwrt      (dacs_iqwrt),
        .dacs_iqsel      (dacs_iqsel),
        .dacs_iqreset    (dacs_iqreset)
    );

    // Toggle-sampled CDC for dacs_fifo_lvl_dl (dl_rx_clk -> link_clk)
    reg [9:0] dacs_lvl_hold_dl;
    reg       dacs_lvl_tog_dl;
    (* ASYNC_REG = "TRUE" *) reg [2:0] dacs_lvl_tog_s;
    (* ASYNC_REG = "TRUE" *) reg       dacs_lvl_ack_s1, dacs_lvl_ack_s2;
    reg       dacs_lvl_ack_link;
    reg [9:0] dacs_fifo_lvl_link;

    always @(posedge dl_rx_clk or posedge dl_rx_rst) begin
        if (dl_rx_rst) begin
            dacs_lvl_hold_dl <= 10'd0;
            dacs_lvl_tog_dl  <= 1'b0;
            dacs_lvl_ack_s1  <= 1'b0;
            dacs_lvl_ack_s2  <= 1'b0;
        end else begin
            dacs_lvl_ack_s1 <= dacs_lvl_ack_link;
            dacs_lvl_ack_s2 <= dacs_lvl_ack_s1;
            if (dacs_lvl_tog_dl == dacs_lvl_ack_s2) begin
                dacs_lvl_hold_dl <= dacs_fifo_lvl_dl;
                dacs_lvl_tog_dl  <= ~dacs_lvl_tog_dl;
            end
        end
    end

    always @(posedge link_clk) begin
        if (link_rst) begin
            dacs_lvl_tog_s     <= 3'd0;
            dacs_lvl_ack_link  <= 1'b0;
            dacs_fifo_lvl_link <= 10'd0;
        end else begin
            dacs_lvl_tog_s <= {dacs_lvl_tog_s[1:0], dacs_lvl_tog_dl};
            if (dacs_lvl_tog_s[2] ^ dacs_lvl_tog_s[1]) begin
                dacs_fifo_lvl_link <= dacs_lvl_hold_dl;
                dacs_lvl_ack_link  <= dacs_lvl_tog_s[1];
            end
        end
    end

    // 8x ADAR1000 Beamformer Ribbon Controller & RF Switch Matrix
    wire       adar_spi_req_ready, adar_spi_resp_valid;
    wire [7:0] adar_spi_resp_rdata;
    wire       adar_init_done, adar_init_err, adar_load_busy, adar_tr_ready;
    wire [4:0] adar_cur_beam_id;
    wire       adar_sdio_o, adar_sdio_t, adar_sdio_i;
    wire       adar_tr_eff = reg_adar_ctrl[12] ? dacr_chirp_active : reg_adar_ctrl[5];

    adar_ctrl #(
        .CLK_DIV   (ADAR_CLK_DIV),
        .NUM_CHIPS (8),
        .NUM_BEAMS (32),
        .AUTO_INIT (ADAR_AUTO_INIT)
    ) u_adar_ctrl (
        .clk             (link_clk),
        .rst             (link_rst),
        .tbl_wr_en       (reg_adar_tbl_p),
        .tbl_beam_id     (reg_adar_tbl_wr[20:16]),
        .tbl_chip_id     (reg_adar_tbl_wr[15:13]),
        .tbl_byte_idx    (reg_adar_tbl_wr[12:8]),
        .tbl_wdata       (reg_adar_tbl_wr[7:0]),
        .start_init      (reg_adar_init_p),
        .beam_strobe     (beam_strobe),
        .soft_load       (reg_adar_load_p),
        .active_beam_id  (reg_adar_ctrl[4:0]),
        .tr_req          (adar_tr_eff),
        .guard_pre       (reg_adar_guard[15:0]),
        .guard_post      (reg_adar_guard[31:16]),
        .spi_req_valid   (reg_adar_spi_p),
        .spi_req_ready   (adar_spi_req_ready),
        .spi_req_chip    (reg_adar_spi_cmd[26:24]),
        .spi_req_rw      (reg_adar_spi_cmd[23]),
        .spi_req_addr    (reg_adar_spi_cmd[22:8]),
        .spi_req_wdata   (reg_adar_spi_cmd[7:0]),
        .spi_resp_valid  (adar_spi_resp_valid),
        .spi_resp_rdata  (adar_spi_resp_rdata),
        .init_done       (adar_init_done),
        .init_err        (adar_init_err),
        .load_busy       (adar_load_busy),
        .tr_ready        (adar_tr_ready),
        .current_beam_id (adar_cur_beam_id),
        .adar_sclk       (adar_sclk),
        .adar_sdio_o     (adar_sdio_o),
        .adar_sdio_t     (adar_sdio_t),
        .adar_sdo        (adar_sdo),
        .adar_csb        (adar_csb),
        .adar_tx_load    (adar_tx_load),
        .adar_rx_load    (adar_rx_load),
        .adar_tr         (adar_tr)
    );
    IOBUF #(.IOSTANDARD("LVCMOS18")) u_iobuf_adar_sdio (
        .I(adar_sdio_o), .T(adar_sdio_t), .O(adar_sdio_i), .IO(adar_sdio)
    );

    reg [7:0] adar_spi_rdata_hold;
    always @(posedge link_clk) begin
        if (link_rst)               adar_spi_rdata_hold <= 8'd0;
        else if (adar_spi_resp_valid) adar_spi_rdata_hold <= adar_spi_resp_rdata;
    end

    wire rf_sw_ready;
    rf_switch #(
        .DEFAULT_SETTLE (16'd125)
    ) u_rf_switch (
        .clk           (link_clk),
        .rst           (link_rst),
        .sw_req        (reg_adar_ctrl[11:8]),
        .settle_cycles (reg_adar_sw_settle),
        .sw_ready      (rf_sw_ready),
        .sw_ctrl       (sw_ctrl)
    );

    // Housekeeping I2C Master (TMP1075 0x48 + M24C02 0x50, Bank 35 LVCMOS18 open-drain)
    wire        hk_req_ready, hk_req_done, hk_req_ack_err;
    wire [15:0] hk_req_rdata, hk_tmp_raw, hk_ack_err_cnt;
    wire        hk_tmp_valid, hk_alert_active, hk_last_ack_err, hk_busy;
    wire        hk_scl_t, hk_sda_t;

    hk_i2c_master #(
        .CLK_DIV  (HK_CLK_DIV),
        .POLL_DIV (HK_POLL_DIV)
    ) u_hk_i2c (
        .clk          (link_clk),
        .rst          (link_rst),
        .poll_en      (reg_hk_i2c_ctrl[0]),
        .req_valid    (reg_hk_i2c_p),
        .req_ready    (hk_req_ready),
        .req_dev_addr (reg_hk_i2c_cmd[6:0]),
        .req_wr_len   (reg_hk_i2c_cmd[9:7]),
        .req_wdata    (reg_hk_i2c_wdata),
        .req_rd_len   (reg_hk_i2c_cmd[11:10]),
        .req_done     (hk_req_done),
        .req_ack_err  (hk_req_ack_err),
        .req_rdata    (hk_req_rdata),
        .tmp_raw      (hk_tmp_raw),
        .tmp_valid    (hk_tmp_valid),
        .alert_active (hk_alert_active),
        .last_ack_err (hk_last_ack_err),
        .ack_err_cnt  (hk_ack_err_cnt),
        .busy         (hk_busy),
        .hk_scl_t     (hk_scl_t),
        .hk_scl_in    (hk_scl_in),
        .hk_sda_t     (hk_sda_t),
        .hk_sda_in    (hk_sda_in),
        .hk_alert_n   (hk_alert_n)
    );
    IOBUF #(.IOSTANDARD("LVCMOS18")) u_iobuf_hk_scl (.I(1'b0), .T(hk_scl_t), .O(hk_scl_in), .IO(hk_scl));
    IOBUF #(.IOSTANDARD("LVCMOS18")) u_iobuf_hk_sda (.I(1'b0), .T(hk_sda_t), .O(hk_sda_in), .IO(hk_sda));

    // Si549 XO I2C + CLK_SEL Mux (Bank 15 LVCMOS33)
    wire        xo_raw_req_ready, xo_raw_resp_valid, xo_raw_resp_err;
    wire [7:0]  xo_raw_resp_rdata;
    wire        xo_busy, xo_prog_done, xo_active_500m, xo_ack_err;
    wire [15:0] xo_ack_err_cnt;
    wire        clk_sel_t, xo_scl_t, xo_scl_in, xo_sda_t, xo_sda_in;

    hk_xo_ctrl #(
        .SI549_ADDR    (7'h55),
        .CLK_DIV       (HK_CLK_DIV),
        .FCAL_WAIT_CYC (XO_FCAL_WAIT_CYC)
    ) u_hk_xo (
        .clk              (link_clk),
        .rst              (link_rst),
        .use_ext_clk      (reg_xo_ctrl[0]),
        .clk_sel_t        (clk_sel_t),
        .prog_start       (reg_xo_prog_p),
        .prog_freq_500m   (reg_xo_ctrl[1]),
        .delta_start      (reg_xo_delta_p),
        .delta_m          (reg_xo_delta_m),
        .raw_req_valid    (reg_xo_raw_p),
        .raw_req_ready    (xo_raw_req_ready),
        .raw_req_rw       (reg_xo_raw_cmd[16]),
        .raw_req_reg      (reg_xo_raw_cmd[7:0]),
        .raw_req_wdata    (reg_xo_raw_cmd[15:8]),
        .raw_resp_valid   (xo_raw_resp_valid),
        .raw_resp_rdata   (xo_raw_resp_rdata),
        .raw_resp_err     (xo_raw_resp_err),
        .busy             (xo_busy),
        .prog_done        (xo_prog_done),
        .active_freq_500m (xo_active_500m),
        .ack_err          (xo_ack_err),
        .ack_err_cnt      (xo_ack_err_cnt),
        .xo_scl_t         (xo_scl_t),
        .xo_scl_in        (xo_scl_in),
        .xo_sda_t         (xo_sda_t),
        .xo_sda_in        (xo_sda_in)
    );
    OBUFT #(.IOSTANDARD("LVCMOS33")) u_obuft_clk_sel (.I(1'b0), .T(clk_sel_t), .O(clk_sel));
    IOBUF #(.IOSTANDARD("LVCMOS33")) u_iobuf_xo_scl  (.I(1'b0), .T(xo_scl_t),  .O(xo_scl_in), .IO(xo_scl));
    IOBUF #(.IOSTANDARD("LVCMOS33")) u_iobuf_xo_sda  (.I(1'b0), .T(xo_sda_t),  .O(xo_sda_in), .IO(xo_sda));

    // Register File 0x34..0xE0 Read Mux
    function [31:0] reg_rd_word;
        input [15:0] addr;
        begin
            case (addr[7:2])
                6'h0D: reg_rd_word = {28'd0, reg_adcs_ctrl[3:2], 1'b0, reg_adcs_ctrl[0]}; // 0x34
                6'h0E: reg_rd_word = {ad9253_chip_id, 6'd0, conv_init_err, conv_init_done,
                                      7'd0, adcs_tap_s2, adcs_be_s[1], adcs_ie_s[1], adcs_id_s[1], adcs_al_s[1]}; // 0x38
                6'h0F: reg_rd_word = reg_conv_spi_cmd;                                      // 0x3C
                6'h10: reg_rd_word = {22'd0, conv_req_ready, conv_resp_valid_sticky, conv_resp_rdata_hold}; // 0x40
                6'h11: reg_rd_word = reg_sdr_nco_a;                                         // 0x44
                6'h12: reg_rd_word = reg_sdr_nco_b;                                         // 0x48
                6'h13: reg_rd_word = {6'd0, reg_sdr_words_per_pkt, reg_sdr_decim};          // 0x4C
                6'h14: reg_rd_word = {8'd0, sdr_adc_dropped_cnt};                           // 0x50
                6'h15: reg_rd_word = {8'd0, reg_dacr_ctrl[23:16], 15'd0, reg_dacr_ctrl[0]}; // 0x54
                6'h16: reg_rd_word = reg_dacr_f0;                                           // 0x58
                6'h17: reg_rd_word = reg_dacr_df;                                           // 0x5C
                6'h18: reg_rd_word = reg_dacr_plen;                                         // 0x60
                6'h19: reg_rd_word = reg_dacr_pri;                                          // 0x64
                6'h1A: reg_rd_word = {31'd0, dacr_chirp_active};                            // 0x68
                6'h1B: reg_rd_word = dacr_pulse_cnt;                                        // 0x6C
                6'h1C: reg_rd_word = {31'd0, reg_dacs_ctrl[0]};                             // 0x70
                6'h1D: reg_rd_word = dacs_underflow_cnt;                                    // 0x74
                6'h1E: reg_rd_word = {22'd0, dacs_fifo_lvl_link};                           // 0x78
                6'h1F: reg_rd_word = {19'd0, reg_adar_ctrl[12:8], 2'd0, reg_adar_ctrl[5:0]}; // 0x7C
                6'h20: reg_rd_word = reg_adar_guard;                                        // 0x80
                6'h21: reg_rd_word = {16'd0, reg_adar_sw_settle};                           // 0x84
                6'h22: reg_rd_word = 32'd0;                                                 // 0x88 WO
                6'h23: reg_rd_word = reg_adar_spi_cmd;                                      // 0x8C
                6'h24: reg_rd_word = {9'd0, sw_ctrl, adar_spi_req_ready, adar_spi_rdata_hold,
                                      adar_cur_beam_id, rf_sw_ready, adar_tr_ready,
                                      adar_load_busy, adar_init_err, adar_init_done};       // 0x90
                6'h25: reg_rd_word = {31'd0, reg_hk_i2c_ctrl[0]};                           // 0x94
                6'h26: reg_rd_word = reg_hk_i2c_cmd;                                        // 0x98
                6'h27: reg_rd_word = reg_hk_i2c_wdata;                                      // 0x9C
                6'h28: reg_rd_word = {11'd0, hk_tmp_valid, hk_alert_active, hk_busy,
                                      hk_last_ack_err, hk_req_ready, hk_req_rdata};         // 0xA0
                6'h29: reg_rd_word = {hk_ack_err_cnt, hk_tmp_raw};                          // 0xA4
                6'h2A: reg_rd_word = {xo_ack_err_cnt, 4'd0, xo_ack_err, xo_active_500m,
                                      xo_prog_done, xo_busy, 6'd0, reg_xo_ctrl[1:0]};       // 0xA8
                6'h2B: reg_rd_word = {8'd0, reg_xo_delta_m};                                // 0xAC
                6'h2C: reg_rd_word = reg_xo_raw_cmd;                                        // 0xB0
                6'h2D: reg_rd_word = {21'd0, xo_raw_err_hold, xo_raw_req_ready,
                                      xo_raw_valid_sticky, xo_raw_rdata_hold};              // 0xB4
                6'h2E: reg_rd_word = {6'd0, xadc_overtemp, xadc_valid, xadc_vccint_raw, xadc_temp_raw}; // 0xB8
                6'h2F: reg_rd_word = {20'd0, xadc_vccaux_raw};                              // 0xBC
                6'h30: reg_rd_word = {7'd0, pps_locked, 7'd0, reg_pps_disc_en, reg_pps_step_q8}; // 0xC0
                6'h31: reg_rd_word = reg_pps_nom_cyc;                                       // 0xC4
                6'h32: reg_rd_word = pps_period_cyc;                                        // 0xC8
                6'h33: reg_rd_word = pps_ppm_err;                                           // 0xCC
                6'h34: reg_rd_word = pps_meas_cnt;                                          // 0xD0
                6'h35: reg_rd_word = xadc_ts_sys[31:0];                                     // 0xD4
                6'h36: reg_rd_word = xadc_ts_sys[63:32];                                    // 0xD8
                6'h37: reg_rd_word = pps_latch_ts[31:0];                                    // 0xDC
                6'h38: reg_rd_word = pps_latch_ts[63:32];                                   // 0xE0
                default: reg_rd_word = 32'hDEAD_BEEF;
            endcase
        end
    endfunction

    // Write & Downlink 8'h11 Readback Response Engine (link_clk)
    reg         resp_pkt_pend;
    reg  [31:0] resp_pkt_seq;
    reg  [63:0] resp_pkt_data;
    wire        resp_pkt_ready;

    wire        reg_wr_en    = (dl_cmd_pop_r && (dl_cmd_word[63:56] == 8'h01)) ||
                               (eth_ctrl_wr && (eth_ctrl_addr >= 16'h0034));
    wire [15:0] reg_wr_addr  = dl_cmd_pop_r ? dl_cmd_word[47:32] : eth_ctrl_addr;
    wire [31:0] reg_wr_wdata = dl_cmd_pop_r ? dl_cmd_word[31:0]  : eth_ctrl_wdata;
`ifdef MUTATE_NO_REG_RESP
    wire        reg_rd_req   = 1'b0;
`else
    wire        reg_rd_req   = dl_cmd_pop_r && (dl_cmd_word[63:56] == 8'h02);
`endif

    always @(posedge link_clk) begin
        if (link_rst) begin
            reg_adcs_ctrl          <= 32'h0000_0001;
            reg_conv_spi_cmd       <= 32'd0;
            reg_conv_spi_start_p   <= 1'b0;
            reg_adcs_init_p        <= 1'b0;
            conv_resp_valid_sticky <= 1'b0;
            conv_resp_rdata_hold   <= 8'd0;
            reg_sdr_nco_a          <= 32'd0;
            reg_sdr_nco_b          <= 32'd0;
            reg_sdr_decim          <= 16'd4;
            reg_sdr_words_per_pkt  <= 10'd64;
            sdr_cfg_tog_link       <= 1'b0;
            reg_dacr_ctrl          <= 32'h00FF_0000;
            reg_dacr_trig_p        <= 1'b0;
            reg_dacr_f0            <= 32'd0;
            reg_dacr_df            <= 32'd0;
            reg_dacr_plen          <= 32'h0000_0400;
            reg_dacr_pri           <= 32'h0000_2000;
            reg_dacs_ctrl          <= 32'd0;
            reg_adar_ctrl          <= 32'd0;
            reg_adar_load_p        <= 1'b0;
            reg_adar_init_p        <= 1'b0;
            reg_adar_sw_p          <= 1'b0;
            reg_adar_guard         <= 32'h000C_000A;
            reg_adar_sw_settle     <= 16'd125;
            reg_adar_tbl_wr        <= 32'd0;
            reg_adar_tbl_p         <= 1'b0;
            reg_adar_spi_cmd       <= 32'd0;
            reg_adar_spi_p         <= 1'b0;
            reg_hk_i2c_ctrl        <= 32'h0000_0001;
            reg_hk_i2c_cmd         <= 32'd0;
            reg_hk_i2c_p           <= 1'b0;
            reg_hk_i2c_wdata       <= 32'd0;
            reg_xo_ctrl            <= 32'd0;
            reg_xo_prog_p          <= 1'b0;
            reg_xo_delta_p         <= 1'b0;
            reg_xo_delta_m         <= 24'd0;
            reg_xo_raw_cmd         <= 32'd0;
            reg_xo_raw_p           <= 1'b0;
            xo_raw_valid_sticky    <= 1'b0;
            xo_raw_rdata_hold      <= 8'd0;
            xo_raw_err_hold        <= 1'b0;
            reg_pps_step_q8        <= 16'h0800;
            reg_pps_disc_en        <= 1'b0;
            reg_pps_clear_p        <= 1'b0;
            reg_pps_nom_cyc        <= PPS_DEFAULT_NOM_CYC;
            resp_pkt_pend          <= 1'b0;
            resp_pkt_seq           <= 32'd0;
            resp_pkt_data          <= 64'd0;
        end else begin
            // 1-cycle W1P pulse clears
            reg_adcs_init_p      <= 1'b0;
            reg_conv_spi_start_p <= 1'b0;
            reg_dacr_trig_p      <= 1'b0;
            reg_adar_load_p      <= 1'b0;
            reg_adar_init_p      <= 1'b0;
            reg_adar_sw_p        <= 1'b0;
            reg_adar_tbl_p       <= 1'b0;
            reg_adar_spi_p       <= 1'b0;
            reg_hk_i2c_p         <= 1'b0;
            reg_xo_prog_p        <= 1'b0;
            reg_xo_delta_p       <= 1'b0;
            reg_xo_raw_p         <= 1'b0;
            reg_pps_clear_p      <= 1'b0;

            if (conv_resp_valid) begin
                conv_resp_valid_sticky <= 1'b1;
                conv_resp_rdata_hold   <= conv_resp_rdata;
            end
            if (xo_raw_resp_valid) begin
                xo_raw_valid_sticky <= 1'b1;
                xo_raw_rdata_hold   <= xo_raw_resp_rdata;
                xo_raw_err_hold     <= xo_raw_resp_err;
            end
            if (resp_pkt_pend && resp_pkt_ready) begin
                resp_pkt_pend <= 1'b0;
                resp_pkt_seq  <= resp_pkt_seq + 32'd1;
            end

            if (reg_wr_en) begin
                case (reg_wr_addr[7:2])
                    6'h0D: begin // 0x34 ADCS_CTRL
                        reg_adcs_ctrl   <= reg_wr_wdata;
                        reg_adcs_init_p <= reg_wr_wdata[1];
                    end
                    6'h0F: begin // 0x3C CONV_SPI_CMD
                        reg_conv_spi_cmd     <= reg_wr_wdata;
                        reg_conv_spi_start_p <= reg_wr_wdata[31];
                        if (reg_wr_wdata[31]) conv_resp_valid_sticky <= 1'b0;
                    end
                    6'h11: begin // 0x44 SDR_DDC_NCO_A
                        reg_sdr_nco_a    <= reg_wr_wdata;
                        sdr_cfg_tog_link <= ~sdr_cfg_tog_link;
                    end
                    6'h12: begin // 0x48 SDR_DDC_NCO_B
                        reg_sdr_nco_b    <= reg_wr_wdata;
                        sdr_cfg_tog_link <= ~sdr_cfg_tog_link;
                    end
                    6'h13: begin // 0x4C SDR_DDC_DECIM
                        reg_sdr_decim         <= (reg_wr_wdata[15:0] < 16'd2) ? 16'd2 : reg_wr_wdata[15:0];
                        reg_sdr_words_per_pkt <= (reg_wr_wdata[25:16] == 10'd0) ? 10'd64 : reg_wr_wdata[25:16];
                        sdr_cfg_tog_link      <= ~sdr_cfg_tog_link;
                    end
                    6'h15: begin // 0x54 DACR_CTRL
                        reg_dacr_ctrl   <= reg_wr_wdata;
                        reg_dacr_trig_p <= reg_wr_wdata[1];
                    end
                    6'h16: reg_dacr_f0   <= reg_wr_wdata; // 0x58
                    6'h17: reg_dacr_df   <= reg_wr_wdata; // 0x5C
                    6'h18: reg_dacr_plen <= reg_wr_wdata; // 0x60
                    6'h19: reg_dacr_pri  <= reg_wr_wdata; // 0x64
                    6'h1C: reg_dacs_ctrl <= reg_wr_wdata; // 0x70
                    6'h1F: begin // 0x7C ADAR_CTRL
                        reg_adar_ctrl   <= reg_wr_wdata;
                        reg_adar_load_p <= reg_wr_wdata[6];
                        reg_adar_init_p <= reg_wr_wdata[7];
                        reg_adar_sw_p   <= 1'b1;
                    end
                    6'h20: reg_adar_guard     <= reg_wr_wdata;       // 0x80
                    6'h21: reg_adar_sw_settle <= reg_wr_wdata[15:0]; // 0x84
                    6'h22: begin // 0x88 ADAR_TBL_WR
                        reg_adar_tbl_wr <= reg_wr_wdata;
                        reg_adar_tbl_p  <= reg_wr_wdata[31];
                    end
                    6'h23: begin // 0x8C ADAR_SPI_CMD
                        reg_adar_spi_cmd <= reg_wr_wdata;
                        reg_adar_spi_p   <= reg_wr_wdata[31];
                    end
                    6'h25: reg_hk_i2c_ctrl <= reg_wr_wdata; // 0x94
                    6'h26: begin // 0x98 HK_I2C_CMD
                        reg_hk_i2c_cmd <= reg_wr_wdata;
                        reg_hk_i2c_p   <= reg_wr_wdata[31];
                    end
                    6'h27: reg_hk_i2c_wdata <= reg_wr_wdata; // 0x9C
                    6'h2A: begin // 0xA8 XO_CTRL
                        reg_xo_ctrl    <= reg_wr_wdata;
                        reg_xo_prog_p  <= reg_wr_wdata[2];
                        reg_xo_delta_p <= reg_wr_wdata[3];
                    end
                    6'h2B: reg_xo_delta_m <= reg_wr_wdata[23:0]; // 0xAC
                    6'h2C: begin // 0xB0 XO_RAW_CMD
                        reg_xo_raw_cmd <= reg_wr_wdata;
                        reg_xo_raw_p   <= reg_wr_wdata[31];
                        if (reg_wr_wdata[31]) xo_raw_valid_sticky <= 1'b0;
                    end
                    6'h30: begin // 0xC0 PPS_CTRL
                        reg_pps_step_q8 <= reg_wr_wdata[15:0];
                        reg_pps_disc_en <= reg_wr_wdata[16];
                        reg_pps_clear_p <= reg_wr_wdata[17];
                    end
                    6'h31: reg_pps_nom_cyc <= reg_wr_wdata; // 0xC4
                    default: ;
                endcase
            end else if (reg_rd_req) begin
                resp_pkt_pend <= 1'b1;
                resp_pkt_data <= {16'h0002, dl_cmd_word[47:32], reg_rd_word(dl_cmd_word[47:32])};
            end
        end
    end

    // Packet-atomic 3-way Arbiter into s0_arb_* (0x11 Reg Readback > 0x01 Radar DDC <-> 0x04/05 SDR DDC)
    reg [1:0] arb_owner; // 0=IDLE, 1=RESP, 2=RAD, 3=SDR
    reg       arb_rr_sdr;
    always @(posedge link_clk) begin
        if (link_rst) begin
            arb_owner  <= 2'd0;
            arb_rr_sdr <= 1'b0;
        end else begin
            if (arb_owner == 2'd0) begin
                if (resp_pkt_pend) begin
                    arb_owner <= 2'd1;
                end else if (tx_pkt_valid && sdr_adc_pkt_valid) begin
                    arb_owner  <= arb_rr_sdr ? 2'd3 : 2'd2;
                    arb_rr_sdr <= ~arb_rr_sdr;
                end else if (tx_pkt_valid) begin
                    arb_owner  <= 2'd2;
                    arb_rr_sdr <= 1'b1;
                end else if (sdr_adc_pkt_valid) begin
                    arb_owner  <= 2'd3;
                    arb_rr_sdr <= 1'b0;
                end
            end else if (s0_arb_valid && s0_arb_ready && s0_arb_eop) begin
                arb_owner <= 2'd0;
            end
        end
    end

    assign s0_arb_valid    = (arb_owner == 2'd1) ? resp_pkt_pend :
                             (arb_owner == 2'd2) ? tx_pkt_valid  :
                             (arb_owner == 2'd3) ? sdr_adc_pkt_valid : 1'b0;
    assign s0_arb_sop      = (arb_owner == 2'd1) ? 1'b1 :
                             (arb_owner == 2'd2) ? tx_pkt_sop :
                             (arb_owner == 2'd3) ? sdr_adc_pkt_sop : 1'b0;
    assign s0_arb_eop      = (arb_owner == 2'd1) ? 1'b1 :
                             (arb_owner == 2'd2) ? tx_pkt_eop :
                             (arb_owner == 2'd3) ? sdr_adc_pkt_eop : 1'b0;
    assign s0_arb_sid      = (arb_owner == 2'd1) ? 8'h11 :
                             (arb_owner == 2'd2) ? tx_pkt_stream_id :
                             (arb_owner == 2'd3) ? sdr_adc_pkt_sid : 8'd0;
    assign s0_arb_len      = (arb_owner == 2'd1) ? 16'd8 :
                             (arb_owner == 2'd2) ? tx_pkt_len :
                             (arb_owner == 2'd3) ? sdr_adc_pkt_len : 16'd0;
    assign s0_arb_seq      = (arb_owner == 2'd1) ? resp_pkt_seq :
                             (arb_owner == 2'd2) ? tx_pkt_seq :
                             (arb_owner == 2'd3) ? sdr_adc_pkt_seq : 32'd0;
    assign s0_arb_ts       = (arb_owner == 2'd1) ? xadc_ts_sys :
                             (arb_owner == 2'd2) ? tx_pkt_timestamp :
                             (arb_owner == 2'd3) ? sdr_adc_pkt_ts : 64'd0;
    assign s0_arb_data     = (arb_owner == 2'd1) ? resp_pkt_data :
                             (arb_owner == 2'd2) ? tx_pkt_data :
                             (arb_owner == 2'd3) ? sdr_adc_pkt_data : 64'd0;

    assign resp_pkt_ready    = (arb_owner == 2'd1) && s0_arb_ready;
    assign tx_pkt_ready      = (arb_owner == 2'd2) && s0_arb_ready;
    assign sdr_adc_pkt_ready = (arb_owner == 2'd3) && s0_arb_ready;

    // Active-high interrupt to KV260 carrier (Bank 35, LVCMOS18)
    assign fpga_irq = ~alert_sync_r[1] | hk_alert_active | xadc_overtemp |
                      adc_err_sync[1] | adcs_ie_s[1] | adcs_be_s[1] |
                      (dl_crc_sync2 != 32'd0);

endmodule
