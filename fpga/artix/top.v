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
    parameter [1:0]   ETH_DEFAULT_POLICY = 2'd0         // 0=STREAM_SPLIT, 1=MIRROR_1P1, 2=IAS_ONLY, 3=ETH_ONLY
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

    // Housekeeping & Interrupt on Bank 35 (VCCO = 1.8V, LVCMOS18)
    inout  wire       hk_scl,
    inout  wire       hk_sda,
    input  wire       hk_alert_n,
    output wire       fpga_irq,

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
    wire link_clk_unbuf, tx_clk_ddr_unbuf, refclk_200m_unbuf;
    wire link_clk, tx_clk_ddr, refclk_200m;
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
        .CLKOUT3      (),
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

    BUFG u_bufg_link_clk   (.I(link_clk_unbuf),    .O(link_clk));
    BUFG u_bufg_tx_ddr     (.I(tx_clk_ddr_unbuf),  .O(tx_clk_ddr));
    BUFG u_bufg_refclk_200 (.I(refclk_200m_unbuf), .O(refclk_200m));

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
        .out_len            (),
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

            wire ias_path_ok = ~ctrl_force_ias_fault & (dl_up_sync[1] | ~ias_seen_dl_up);
            wire eth_path_ok = eth_link_up_stat & ~ctrl_force_eth_fault;

            dual_path_mux u_dual_mux (
                .clk           (link_clk),
                .rst           (eth_rst_125),
                .policy        (eth_policy),
                .ias_healthy   (ias_path_ok),
                .eth_healthy   (eth_path_ok),
                .s0_valid      (tx_pkt_valid),
                .s0_ready      (tx_pkt_ready),
                .s0_sop        (tx_pkt_sop),
                .s0_eop        (tx_pkt_eop),
                .s0_stream_id  (tx_pkt_stream_id),
                .s0_len        (tx_pkt_len),
                .s0_seq        (tx_pkt_seq),
                .s0_timestamp  (tx_pkt_timestamp),
                .s0_data       (tx_pkt_data),
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
            assign eth_link_up_stat      = 1'b0;
            assign eth_remote_alive_stat = 1'b0;
            assign eth_copper_up_stat    = 1'b0;
            assign ias_mux_valid         = tx_pkt_valid;
            assign tx_pkt_ready          = ias_mux_ready;
            assign ias_mux_sop           = tx_pkt_sop;
            assign ias_mux_eop           = tx_pkt_eop;
            assign ias_mux_sid           = tx_pkt_stream_id;
            assign ias_mux_len           = tx_pkt_len;
            assign ias_mux_seq           = tx_pkt_seq;
            assign ias_mux_ts            = tx_pkt_timestamp;
            assign ias_mux_data          = tx_pkt_data;

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

    // Active-high interrupt to KV260 carrier (Bank 35, LVCMOS18)
    assign fpga_irq = ~alert_sync_r[1] | adc_err_sync[1] | (dl_crc_sync2 != 32'd0);

    // Passive open-drain observation on HK I2C (KV260 PS I2C master talks to TMP1075/M24C02 directly)
    IOBUF #(.IOSTANDARD("LVCMOS18")) u_iobuf_hk_scl (.I(1'b0), .T(1'b1), .O(hk_scl_in), .IO(hk_scl));
    IOBUF #(.IOSTANDARD("LVCMOS18")) u_iobuf_hk_sda (.I(1'b0), .T(1'b1), .O(hk_sda_in), .IO(hk_sda));

endmodule
