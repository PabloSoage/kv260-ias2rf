// SPDX-License-Identifier: BSD-2-Clause
// Kria K26 (XCK26-SFVC784-2LV-C) Top-Level Gateware on KV260 Carrier
//
// Pinout verified against fpga/link/PINMAP.md and Vivado xck26-sfvc784-2LV-c:
//   - Bank 66 HP (VCCO = 1.2 V):
//       link_rx_{clk,d0,d1}_{p,n} : DIFF_SSTL12, ODT=RTT_48, EQUALIZATION=EQ_LEVEL0
//       link_tx_{clk,d0}_{p,n}    : DIFF_SSTL12, OUTPUT_IMPEDANCE=RDRV_60_60
//       fpga_irq                  : LVCMOS12 (input from Artix via U72 translator)
//   - Bank 45 HD (VCCO = 3.3 V, LVCMOS33):
//       hk_scl, hk_sda            : PS8 EMIOI2C0 open-drain via IOBUF (carrier TCA9546A ch1)
//       fpga_prog_b               : PS8 EMIOGPIO0 -> SLG7XL46528 reset translator
//       pmod_*                    : KV260 Pmod J2 (PS8 EMIOSPI0 + EMIOGPIO0/I)

`timescale 1ns/1ps

module kria_async_fifo #(
    parameter integer DW = 64,
    parameter integer AW = 4
) (
    input  wire          wr_clk,
    input  wire          wr_rst,
    input  wire          wr_en,
    input  wire [DW-1:0] wr_data,
    output wire          wr_full,

    input  wire          rd_clk,
    input  wire          rd_rst,
    input  wire          rd_en,
    output wire [DW-1:0] rd_data,
    output wire          rd_empty
);
    localparam integer DEPTH = (1 << AW);

    (* ram_style = "distributed" *) reg [DW-1:0] mem [0:DEPTH-1];

    reg [AW:0] wr_bin, wr_gray;
    reg [AW:0] rd_bin, rd_gray;

    (* ASYNC_REG = "TRUE" *) reg [AW:0] rd_gray_meta, rd_gray_sync;
    (* ASYNC_REG = "TRUE" *) reg [AW:0] wr_gray_meta, wr_gray_sync;

    function [AW:0] bin2gray;
        input [AW:0] b;
        begin
            bin2gray = (b >> 1) ^ b;
        end
    endfunction

    wire [AW:0] wr_bin_next  = wr_bin + {{AW{1'b0}}, (wr_en && !wr_full)};
    wire [AW:0] wr_gray_next = bin2gray(wr_bin_next);

    assign wr_full = (wr_gray == {~rd_gray_sync[AW:AW-1], rd_gray_sync[AW-2:0]});

    always @(posedge wr_clk) begin
        if (wr_rst) begin
            wr_bin       <= {(AW+1){1'b0}};
            wr_gray      <= {(AW+1){1'b0}};
            rd_gray_meta <= {(AW+1){1'b0}};
            rd_gray_sync <= {(AW+1){1'b0}};
        end else begin
            rd_gray_meta <= rd_gray;
            rd_gray_sync <= rd_gray_meta;
            if (wr_en && !wr_full)
                mem[wr_bin[AW-1:0]] <= wr_data;
            wr_bin  <= wr_bin_next;
            wr_gray <= wr_gray_next;
        end
    end

    wire [AW:0] rd_bin_next  = rd_bin + {{AW{1'b0}}, (rd_en && !rd_empty)};
    wire [AW:0] rd_gray_next = bin2gray(rd_bin_next);

    assign rd_empty = (rd_gray == wr_gray_sync);
    assign rd_data  = mem[rd_bin[AW-1:0]];

    always @(posedge rd_clk) begin
        if (rd_rst) begin
            rd_bin       <= {(AW+1){1'b0}};
            rd_gray      <= {(AW+1){1'b0}};
            wr_gray_meta <= {(AW+1){1'b0}};
            wr_gray_sync <= {(AW+1){1'b0}};
        end else begin
            wr_gray_meta <= wr_gray;
            wr_gray_sync <= wr_gray_meta;
            rd_bin       <= rd_bin_next;
            rd_gray      <= rd_gray_next;
        end
    end
endmodule

module kria_top (
    // Uplink LVDS/SSTL12 pairs (Artix Bank 34 -> K26 Bank 66 HP)
    input  wire link_rx_clk_p,
    input  wire link_rx_clk_n,
    input  wire link_rx_d0_p,
    input  wire link_rx_d0_n,
    input  wire link_rx_d1_p,
    input  wire link_rx_d1_n,

    // Downlink SSTL12 pairs (K26 Bank 66 HP -> Artix Bank 14 HR)
    output wire link_tx_clk_p,
    output wire link_tx_clk_n,
    output wire link_tx_d0_p,
    output wire link_tx_d0_n,

    // Single-ended IAS1 control/status (Bank 66 LVCMOS12 & Bank 45 LVCMOS33)
    input  wire fpga_irq,
    inout  wire hk_scl,
    inout  wire hk_sda,
    output wire fpga_prog_b,

    // KV260 Carrier Pmod J2 (Bank 45 HD LVCMOS33)
    output wire pmod_cs_n,
    output wire pmod_mosi,
    input  wire pmod_miso,
    output wire pmod_sclk,
    output wire pmod_beam_strobe,
    output wire pmod_pps_sync,
    output wire pmod_spare1,
    input  wire pmod_spare2
);

    // -------------------------------------------------------------------------
    // Zynq UltraScale+ PS8 Hard Block + Clocking
    // -------------------------------------------------------------------------
    wire [3:0]   ps_plclk;
    wire [95:0]  ps_gpio_o;
    wire [95:0]  ps_gpio_tn;
    wire [95:0]  ps_gpio_i;

    wire         ps_i2c0_scl_o, ps_i2c0_scl_t, ps_i2c0_scl_i;
    wire         ps_i2c0_sda_o, ps_i2c0_sda_t, ps_i2c0_sda_i;

    wire         ps_spi0_mo, ps_spi0_motn;
    wire         ps_spi0_sclko, ps_spi0_sclktn;
    wire [2:0]   ps_spi0_sson;
    wire         ps_spi0_ssntn;

    wire [39:0]  m_axi_awaddr, m_axi_araddr;
    wire [15:0]  m_axi_awid,   m_axi_arid;
    wire [7:0]   m_axi_awlen,  m_axi_arlen;
    wire [2:0]   m_axi_awsize, m_axi_arsize;
    wire [1:0]   m_axi_awburst, m_axi_arburst;
    wire         m_axi_awvalid, m_axi_arvalid;
    wire         m_axi_wvalid,  m_axi_wlast;
    wire [127:0] m_axi_wdata;
    wire [15:0]  m_axi_wstrb;
    wire         m_axi_bready,  m_axi_rready;

    reg          m_axi_awready_r, m_axi_wready_r, m_axi_bvalid_r;
    reg  [1:0]   m_axi_bresp_r;
    reg  [15:0]  m_axi_bid_r;
    reg          m_axi_arready_r, m_axi_rvalid_r;
    reg  [127:0] m_axi_rdata_r;
    reg  [1:0]   m_axi_rresp_r;
    reg  [15:0]  m_axi_rid_r;

    // SAXIGP2 (HP0 PL->PS Master AXI port driven in tx_clk_div domain)
    reg  [48:0]  s_axi_hp_awaddr, s_axi_hp_araddr;
    reg          s_axi_hp_awvalid, s_axi_hp_wvalid, s_axi_hp_wlast;
    reg  [127:0] s_axi_hp_wdata;
    reg  [15:0]  s_axi_hp_wstrb;
    reg          s_axi_hp_arvalid;
    wire         s_axi_hp_awready, s_axi_hp_wready, s_axi_hp_bvalid;
    wire [1:0]   s_axi_hp_bresp;
    wire [5:0]   s_axi_hp_bid;
    wire         s_axi_hp_arready, s_axi_hp_rvalid, s_axi_hp_rlast;
    wire [127:0] s_axi_hp_rdata;
    wire [1:0]   s_axi_hp_rresp;
    wire [5:0]   s_axi_hp_rid;

    wire [7:0]   pl_ps_irq0;
    wire         pl_clk_100m;
    wire         rx_clk_ibuf, rx_clk_hs, rx_clkdiv;
    wire         tx_clk_hs, tx_clk_div, refclk_300m;

    PS8 u_ps8 (
        .PLCLK          (ps_plclk),
        .EMIOGPIOO      (ps_gpio_o),
        .EMIOGPIOTN     (ps_gpio_tn),
        .EMIOGPIOI      (ps_gpio_i),

        .EMIOI2C0SCLO   (ps_i2c0_scl_o),
        .EMIOI2C0SCLTN  (ps_i2c0_scl_t),
        .EMIOI2C0SCLI   (ps_i2c0_scl_i),
        .EMIOI2C0SDAO   (ps_i2c0_sda_o),
        .EMIOI2C0SDATN  (ps_i2c0_sda_t),
        .EMIOI2C0SDAI   (ps_i2c0_sda_i),

        .EMIOSPI0MO     (ps_spi0_mo),
        .EMIOSPI0MOTN   (ps_spi0_motn),
        .EMIOSPI0SCLKO  (ps_spi0_sclko),
        .EMIOSPI0SCLKTN (ps_spi0_sclktn),
        .EMIOSPI0SSON   (ps_spi0_sson),
        .EMIOSPI0SSNTN  (ps_spi0_ssntn),
        .EMIOSPI0MI     (pmod_miso),
        .EMIOSPI0SCLKI  (1'b0),
        .EMIOSPI0SI     (1'b0),
        .EMIOSPI0SSIN   (1'b1),

        .PLPSIRQ0       (pl_ps_irq0),

        // M_AXI_HPM0_LPD (AXI4 Master from PS -> link_axis CSRs in rx_clkdiv)
        .MAXIGP2ACLK    (rx_clkdiv),
        .MAXIGP2AWADDR  (m_axi_awaddr),
        .MAXIGP2AWID    (m_axi_awid),
        .MAXIGP2AWLEN   (m_axi_awlen),
        .MAXIGP2AWSIZE  (m_axi_awsize),
        .MAXIGP2AWBURST (m_axi_awburst),
        .MAXIGP2AWVALID (m_axi_awvalid),
        .MAXIGP2AWREADY (m_axi_awready_r),
        .MAXIGP2WDATA   (m_axi_wdata),
        .MAXIGP2WSTRB   (m_axi_wstrb),
        .MAXIGP2WLAST   (m_axi_wlast),
        .MAXIGP2WVALID  (m_axi_wvalid),
        .MAXIGP2WREADY  (m_axi_wready_r),
        .MAXIGP2BID     (m_axi_bid_r),
        .MAXIGP2BRESP   (m_axi_bresp_r),
        .MAXIGP2BVALID  (m_axi_bvalid_r),
        .MAXIGP2BREADY  (m_axi_bready),
        .MAXIGP2ARADDR  (m_axi_araddr),
        .MAXIGP2ARID    (m_axi_arid),
        .MAXIGP2ARLEN   (m_axi_arlen),
        .MAXIGP2ARSIZE  (m_axi_arsize),
        .MAXIGP2ARBURST (m_axi_arburst),
        .MAXIGP2ARVALID (m_axi_arvalid),
        .MAXIGP2ARREADY (m_axi_arready_r),
        .MAXIGP2RID     (m_axi_rid_r),
        .MAXIGP2RDATA   (m_axi_rdata_r),
        .MAXIGP2RRESP   (m_axi_rresp_r),
        .MAXIGP2RLAST   (m_axi_rvalid_r),
        .MAXIGP2RVALID  (m_axi_rvalid_r),
        .MAXIGP2RREADY  (m_axi_rready),

        // S_AXI_HP0_FPD (AXI4 Slave on PS <- DMA engine in tx_clk_div)
        .SAXIGP2WCLK    (tx_clk_div),
        .SAXIGP2RCLK    (tx_clk_div),
        .SAXIGP2AWID    (6'd0),
        .SAXIGP2AWADDR  (s_axi_hp_awaddr),
        .SAXIGP2AWLEN   (8'd0),
        .SAXIGP2AWSIZE  (3'b011), // 8 bytes per beat
        .SAXIGP2AWBURST (2'b01),
        .SAXIGP2AWLOCK  (1'b0),
        .SAXIGP2AWCACHE (4'b0011),
        .SAXIGP2AWPROT  (3'b000),
        .SAXIGP2AWQOS   (4'd0),
        .SAXIGP2AWUSER  (1'b0),
        .SAXIGP2AWVALID (s_axi_hp_awvalid),
        .SAXIGP2AWREADY (s_axi_hp_awready),
        .SAXIGP2WDATA   (s_axi_hp_wdata),
        .SAXIGP2WSTRB   (s_axi_hp_wstrb),
        .SAXIGP2WLAST   (s_axi_hp_wlast),
        .SAXIGP2WVALID  (s_axi_hp_wvalid),
        .SAXIGP2WREADY  (s_axi_hp_wready),
        .SAXIGP2BID     (s_axi_hp_bid),
        .SAXIGP2BRESP   (s_axi_hp_bresp),
        .SAXIGP2BVALID  (s_axi_hp_bvalid),
        .SAXIGP2BREADY  (1'b1),
        .SAXIGP2ARID    (6'd0),
        .SAXIGP2ARADDR  (s_axi_hp_araddr),
        .SAXIGP2ARLEN   (8'd0),
        .SAXIGP2ARSIZE  (3'b011),
        .SAXIGP2ARBURST (2'b01),
        .SAXIGP2ARLOCK  (1'b0),
        .SAXIGP2ARCACHE (4'b0011),
        .SAXIGP2ARPROT  (3'b000),
        .SAXIGP2ARQOS   (4'd0),
        .SAXIGP2ARUSER  (1'b0),
        .SAXIGP2ARVALID (s_axi_hp_arvalid),
        .SAXIGP2ARREADY (s_axi_hp_arready),
        .SAXIGP2RID     (s_axi_hp_rid),
        .SAXIGP2RDATA   (s_axi_hp_rdata),
        .SAXIGP2RRESP   (s_axi_hp_rresp),
        .SAXIGP2RLAST   (s_axi_hp_rlast),
        .SAXIGP2RVALID  (s_axi_hp_rvalid),
        .SAXIGP2RREADY  (1'b1)
    );

    BUFG_PS u_bufg_ps (
        .I (ps_plclk[0]),
        .O (pl_clk_100m)
    );

    // MMCME4_BASE: 100 MHz -> VCO 1500 MHz -> CLKOUT0 500 MHz (HS TX + /4 via BUFGCE_DIV),
    //              CLKOUT1 300 MHz (IDELAYCTRL REFCLK).
    wire mmcm_fb, mmcm_fb_buf;
    wire clk_500_u, clk_300_u, mmcm_locked;

    MMCME4_BASE #(
        .CLKIN1_PERIOD    (10.000),
        .CLKFBOUT_MULT_F  (15.000),
        .DIVCLK_DIVIDE    (1),
        .CLKOUT0_DIVIDE_F (3.000),
        .CLKOUT1_DIVIDE   (5)
    ) u_mmcm (
        .CLKIN1   (pl_clk_100m),
        .CLKFBIN  (mmcm_fb_buf),
        .RST      (1'b0),
        .PWRDWN   (1'b0),
        .CLKFBOUT (mmcm_fb),
        .CLKOUT0  (clk_500_u),
        .CLKOUT1  (clk_300_u),
        .LOCKED   (mmcm_locked)
    );

    BUFG u_bufg_mmcm_fb (
        .I (mmcm_fb),
        .O (mmcm_fb_buf)
    );

    BUFGCE u_bufg_tx_hs (
        .I  (clk_500_u),
        .CE (1'b1),
        .O  (tx_clk_hs)
    );

    BUFGCE_DIV #(
        .BUFGCE_DIVIDE (4)
    ) u_bufg_tx_div (
        .I   (clk_500_u),
        .CE  (1'b1),
        .CLR (1'b0),
        .O   (tx_clk_div)
    );

    BUFGCE u_bufg_ref300 (
        .I  (clk_300_u),
        .CE (1'b1),
        .O  (refclk_300m)
    );

    // Synchronized resets per domain (async assert on !mmcm_locked, sync release)
    (* ASYNC_REG = "TRUE" *) reg [2:0] rst_300_sync = 3'b111;
    always @(posedge refclk_300m or negedge mmcm_locked) begin
        if (!mmcm_locked) rst_300_sync <= 3'b111;
        else              rst_300_sync <= {rst_300_sync[1:0], 1'b0};
    end
    wire rst_300 = rst_300_sync[2];

    (* ASYNC_REG = "TRUE" *) reg [2:0] rst_tx_sync = 3'b111;
    always @(posedge tx_clk_div or negedge mmcm_locked) begin
        if (!mmcm_locked) rst_tx_sync <= 3'b111;
        else              rst_tx_sync <= {rst_tx_sync[1:0], 1'b0};
    end
    wire rst_tx = rst_tx_sync[2];

    (* ASYNC_REG = "TRUE" *) reg [2:0] rst_rx_sync = 3'b111;
    always @(posedge rx_clkdiv or negedge mmcm_locked) begin
        if (!mmcm_locked) rst_rx_sync <= 3'b111;
        else              rst_rx_sync <= {rst_rx_sync[1:0], 1'b0};
    end
    wire rst_rx = rst_rx_sync[2];

    // -------------------------------------------------------------------------
    // Uplink RX (LINK_RX_CLK, LINK_RX_D0, LINK_RX_D1) -> rx_clkdiv (125 MHz)
    // -------------------------------------------------------------------------
    wire rx_d0_ibuf, rx_d1_ibuf;
    IBUFDS u_ibuf_rx_clk (.I(link_rx_clk_p), .IB(link_rx_clk_n), .O(rx_clk_ibuf));
    IBUFDS u_ibuf_rx_d0  (.I(link_rx_d0_p),  .IB(link_rx_d0_n),  .O(rx_d0_ibuf));
    IBUFDS u_ibuf_rx_d1  (.I(link_rx_d1_p),  .IB(link_rx_d1_n),  .O(rx_d1_ibuf));

    BUFGCE u_bufg_rx_hs (
        .I  (rx_clk_ibuf),
        .CE (1'b1),
        .O  (rx_clk_hs)
    );

    BUFGCE_DIV #(
        .BUFGCE_DIVIDE (4)
    ) u_bufg_rx_div (
        .I   (rx_clk_ibuf),
        .CE  (1'b1),
        .CLR (1'b0),
        .O   (rx_clkdiv)
    );

    wire idelayctrl_rdy;
    IDELAYCTRL #(.SIM_DEVICE("ULTRASCALE_PLUS")) u_idelayctrl (
        .RDY    (idelayctrl_rdy),
        .REFCLK (refclk_300m),
        .RST    (rst_300)
    );

    wire       ctrl_soft_rst, ctrl_loopback_en, ctrl_retrain_pulse;
    wire       ctrl_tap_override_en, ctrl_prbs7_tx_en, ctrl_prbs7_rx_chk_en;
    wire [8:0] cfg_tap_l0, cfg_tap_l1;
    wire       cfg_load_l0, cfg_load_l1;

    wire       train_en_vtc, train_load_l0, train_load_l1;
    wire [8:0] train_cnt_l0, train_cnt_l1;
    wire [8:0] active_cnt_l0, active_cnt_l1;
    wire       rx_d0_idelay, rx_d1_idelay;
    reg        pcs_rst_rx;
    wire       kria_link_up;

    reg idly_en_vtc_r;
    always @(posedge rx_clkdiv) begin
        if (pcs_rst_rx || ctrl_tap_override_en || train_load_l0 || train_load_l1 || cfg_load_l0 || cfg_load_l1 || !kria_link_up)
            idly_en_vtc_r <= 1'b0;
        else
            idly_en_vtc_r <= 1'b1;
    end
    wire       idly_en_vtc  = idly_en_vtc_r | train_en_vtc;
    wire       idly_load_l0 = ctrl_tap_override_en ? (train_load_l0 | cfg_load_l0) : train_load_l0;
    wire       idly_load_l1 = ctrl_tap_override_en ? (train_load_l1 | cfg_load_l1) : train_load_l1;
    wire [8:0] idly_cnt_l0  = (ctrl_tap_override_en && cfg_load_l0) ? cfg_tap_l0 : train_cnt_l0;
    wire [8:0] idly_cnt_l1  = (ctrl_tap_override_en && cfg_load_l1) ? cfg_tap_l1 : train_cnt_l1;

    IDELAYE3 #(
        .CASCADE          ("NONE"),
        .DELAY_FORMAT     ("TIME"),
        .DELAY_SRC        ("IDATAIN"),
        .DELAY_TYPE       ("VAR_LOAD"),
        .DELAY_VALUE      (0),
        .REFCLK_FREQUENCY (300.0),
        .SIM_DEVICE       ("ULTRASCALE_PLUS"),
        .UPDATE_MODE      ("ASYNC")
    ) u_idelay_d0 (
        .CASC_OUT    (),
        .CNTVALUEOUT (active_cnt_l0),
        .DATAOUT     (rx_d0_idelay),
        .CASC_IN     (1'b0),
        .CASC_RETURN (1'b0),
        .CE          (1'b0),
        .CLK         (rx_clkdiv),
        .CNTVALUEIN  (idly_cnt_l0),
        .DATAIN      (1'b0),
        .EN_VTC      (idly_en_vtc),
        .IDATAIN     (rx_d0_ibuf),
        .INC         (1'b0),
        .LOAD        (idly_load_l0),
        .RST         (rst_rx)
    );

    IDELAYE3 #(
        .CASCADE          ("NONE"),
        .DELAY_FORMAT     ("TIME"),
        .DELAY_SRC        ("IDATAIN"),
        .DELAY_TYPE       ("VAR_LOAD"),
        .DELAY_VALUE      (0),
        .REFCLK_FREQUENCY (300.0),
        .SIM_DEVICE       ("ULTRASCALE_PLUS"),
        .UPDATE_MODE      ("ASYNC")
    ) u_idelay_d1 (
        .CASC_OUT    (),
        .CNTVALUEOUT (active_cnt_l1),
        .DATAOUT     (rx_d1_idelay),
        .CASC_IN     (1'b0),
        .CASC_RETURN (1'b0),
        .CE          (1'b0),
        .CLK         (rx_clkdiv),
        .CNTVALUEIN  (idly_cnt_l1),
        .DATAIN      (1'b0),
        .EN_VTC      (idly_en_vtc),
        .IDATAIN     (rx_d1_ibuf),
        .INC         (1'b0),
        .LOAD        (idly_load_l1),
        .RST         (rst_rx)
    );

    wire [7:0] rx_byte_l0_raw, rx_byte_l1_raw;
    ISERDESE3 #(
        .DATA_WIDTH     (8),
        .DDR_CLK_EDGE   ("OPPOSITE_EDGE"),
        .FIFO_ENABLE    ("FALSE"),
        .FIFO_SYNC_MODE ("FALSE"),
        .IDDR_MODE      ("FALSE"),
        .SIM_DEVICE     ("ULTRASCALE_PLUS")
    ) u_iserdes_d0 (
        .FIFO_EMPTY      (),
        .INTERNAL_DIVCLK (),
        .Q               (rx_byte_l0_raw),
        .CLK             (rx_clk_hs),
        .CLK_B           (~rx_clk_hs),
        .CLKDIV          (rx_clkdiv),
        .D               (rx_d0_idelay),
        .FIFO_RD_CLK     (1'b0),
        .FIFO_RD_EN      (1'b0),
        .RST             (rst_rx)
    );

    ISERDESE3 #(
        .DATA_WIDTH     (8),
        .DDR_CLK_EDGE   ("OPPOSITE_EDGE"),
        .FIFO_ENABLE    ("FALSE"),
        .FIFO_SYNC_MODE ("FALSE"),
        .IDDR_MODE      ("FALSE"),
        .SIM_DEVICE     ("ULTRASCALE_PLUS")
    ) u_iserdes_d1 (
        .FIFO_EMPTY      (),
        .INTERNAL_DIVCLK (),
        .Q               (rx_byte_l1_raw),
        .CLK             (rx_clk_hs),
        .CLK_B           (~rx_clk_hs),
        .CLKDIV          (rx_clkdiv),
        .D               (rx_d1_idelay),
        .FIFO_RD_CLK     (1'b0),
        .FIFO_RD_EN      (1'b0),
        .RST             (rst_rx)
    );

    reg [7:0] rx_byte_l0, rx_byte_l1;
    always @(posedge rx_clkdiv) begin
        rx_byte_l0 <= rx_byte_l0_raw;
        rx_byte_l1 <= rx_byte_l1_raw;
    end

    // PRBS7 checker on rx_byte_l0 when ctrl_prbs7_rx_chk_en == 1
    reg  [6:0]  prbs_rx_state;
    reg  [31:0] prbs_err_cnt_r;
    reg         idelay_rdy_rx_m, idelay_rdy_rx;
    always @(posedge rx_clkdiv) begin
        idelay_rdy_rx_m <= idelayctrl_rdy;
        idelay_rdy_rx   <= idelay_rdy_rx_m;
        pcs_rst_rx      <= rst_rx || ctrl_soft_rst || !idelay_rdy_rx;
    end

    integer prbs_i;
    reg [6:0] prbs_next_s;
    reg [7:0] prbs_exp_byte;
    reg [3:0] prbs_bit_errs;
    always @* begin
        prbs_next_s = prbs_rx_state;
        for (prbs_i = 0; prbs_i < 8; prbs_i = prbs_i + 1) begin
            prbs_exp_byte[prbs_i] = prbs_next_s[6];
            prbs_next_s = {prbs_next_s[5:0], prbs_next_s[6] ^ prbs_next_s[5]};
        end
    end

    always @(posedge rx_clkdiv) begin
        if (pcs_rst_rx || !ctrl_prbs7_rx_chk_en) begin
            prbs_rx_state  <= 7'h7F;
            prbs_err_cnt_r <= 32'd0;
        end else begin
            prbs_rx_state <= {rx_byte_l0[1]^rx_byte_l0[0], rx_byte_l0[7:2]};
            prbs_bit_errs = 4'd0;
            for (prbs_i = 0; prbs_i < 8; prbs_i = prbs_i + 1)
                prbs_bit_errs = prbs_bit_errs + {3'd0, (rx_byte_l0[prbs_i] ^ prbs_exp_byte[prbs_i])};
            if (prbs_rx_state != 7'd0)
                prbs_err_cnt_r <= prbs_err_cnt_r + {28'd0, prbs_bit_errs};
        end
    end

    wire        l0_lock, l1_lock, d_lock;
    wire        l0_blk_v, l0_blk_ok, l1_blk_v, l1_blk_ok;
    wire [2:0]  train_state;
    wire [8:0]  eye_l0, eye_r0, eye_l1, eye_r1;
    wire        rx_out_v, rx_out_sop, rx_out_eop;
    wire [7:0]  rx_out_sid;
    wire [15:0] rx_out_len;
    wire [31:0] rx_out_seq;
    wire [63:0] rx_out_ts, rx_out_data;
    wire        rx_done_v, rx_done_ok, rx_done_err;
    wire signed [7:0] skew_blk;
    wire [15:0] rem_stat;
    wire [23:0] rem_drop;
    wire [31:0] sh_err0, sh_err1, pkt_rx_cnt, crc_err_cnt;

    link_rx_train_fsm #(
        .DEFAULT_CENTER_TAP (9'd202),
        .MAX_TAP            (9'd511),
        .TAP_STEP           (9'd8),
        .MIN_EYE_STEPS      (9'd16),
        .WAIT_RESET_CYCLES  (16'd16),
        .TAP_SETTLE_CYCLES  (16'd24),
        .TAP_DWELL_CYCLES   (16'd1800),
        .LOCK_TIMEOUT       (16'd8192),
        .SINGLE_LANE        (0)
    ) u_train_fsm (
        .clk              (rx_clkdiv),
        .rst              (pcs_rst_rx),
        .retrain          (ctrl_retrain_pulse),
        .cfg_tap_override (ctrl_tap_override_en),
        .cfg_tap_l0       (cfg_tap_l0),
        .cfg_tap_l1       (cfg_tap_l1),
        .rx_byte_l0       (rx_byte_l0),
        .rx_byte_l1       (rx_byte_l1),
        .l0_block_lock    (l0_lock),
        .l1_block_lock    (l1_lock),
        .deskew_lock      (d_lock),
        .l0_rx_blk_valid  (l0_blk_v),
        .l0_rx_blk_ok     (l0_blk_ok),
        .l1_rx_blk_valid  (l1_blk_v),
        .l1_rx_blk_ok     (l1_blk_ok),
        .en_vtc           (train_en_vtc),
        .load_l0          (train_load_l0),
        .cntval_l0        (train_cnt_l0),
        .load_l1          (train_load_l1),
        .cntval_l1        (train_cnt_l1),
        .train_state      (train_state),
        .link_up          (kria_link_up),
        .eye_left_l0      (eye_l0),
        .eye_right_l0     (eye_r0),
        .eye_left_l1      (eye_l1),
        .eye_right_l1     (eye_r1)
    );

    link_pcs_rx #(
        .DISABLE_DESKEW (0)
    ) u_pcs_rx (
        .clk                (rx_clkdiv),
        .rst                (pcs_rst_rx),
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

    // -------------------------------------------------------------------------
    // PS MAXIGP2 -> AXI4-Lite Bridge (rx_clkdiv) -> link_axis CSRs
    // -------------------------------------------------------------------------
    reg         csr_awvalid_r, csr_wvalid_r, csr_arvalid_r;
    reg  [7:0]  csr_awaddr_r, csr_araddr_r;
    reg  [31:0] csr_wdata_r;
    reg  [3:0]  csr_wstrb_r;
    reg         aw_seen, w_seen, wr_inflight, rd_inflight;

    wire        csr_awready, csr_wready, csr_bvalid, csr_arready, csr_rvalid;
    wire [1:0]  csr_bresp, csr_rresp;
    wire [31:0] csr_rdata;

    always @(posedge rx_clkdiv) begin
        if (rst_rx) begin
            m_axi_awready_r <= 1'b0;
            m_axi_wready_r  <= 1'b0;
            m_axi_bvalid_r  <= 1'b0;
            m_axi_bresp_r   <= 2'b00;
            m_axi_bid_r     <= 16'd0;
            m_axi_arready_r <= 1'b0;
            m_axi_rvalid_r  <= 1'b0;
            m_axi_rdata_r   <= 128'd0;
            m_axi_rresp_r   <= 2'b00;
            m_axi_rid_r     <= 16'd0;
            csr_awvalid_r   <= 1'b0;
            csr_wvalid_r    <= 1'b0;
            csr_arvalid_r   <= 1'b0;
            csr_awaddr_r    <= 8'd0;
            csr_araddr_r    <= 8'd0;
            csr_wdata_r     <= 32'd0;
            csr_wstrb_r     <= 4'd0;
            aw_seen         <= 1'b0;
            w_seen          <= 1'b0;
            wr_inflight     <= 1'b0;
            rd_inflight     <= 1'b0;
        end else begin
            m_axi_awready_r <= !wr_inflight && !aw_seen && !m_axi_bvalid_r;
            m_axi_wready_r  <= !wr_inflight && !w_seen  && !m_axi_bvalid_r;
            m_axi_arready_r <= !rd_inflight && !m_axi_rvalid_r;

            if (m_axi_awvalid && m_axi_awready_r) begin
                aw_seen       <= 1'b1;
                csr_awaddr_r  <= m_axi_awaddr[7:0];
                m_axi_bid_r   <= m_axi_awid;
                csr_awvalid_r <= 1'b1;
                m_axi_awready_r <= 1'b0;
            end
            if (csr_awvalid_r && csr_awready)
                csr_awvalid_r <= 1'b0;

            if (m_axi_wvalid && m_axi_wready_r) begin
                w_seen       <= m_axi_wlast;
                csr_wdata_r  <= m_axi_wdata[31:0];
                csr_wstrb_r  <= m_axi_wstrb[3:0];
                csr_wvalid_r <= 1'b1;
                m_axi_wready_r <= 1'b0;
            end
            if (csr_wvalid_r && csr_wready)
                csr_wvalid_r <= 1'b0;

            if (aw_seen && w_seen && !wr_inflight && !m_axi_bvalid_r) begin
                aw_seen     <= 1'b0;
                w_seen      <= 1'b0;
                wr_inflight <= 1'b1;
            end

            if (wr_inflight && csr_bvalid) begin
                wr_inflight    <= 1'b0;
                m_axi_bvalid_r <= 1'b1;
                m_axi_bresp_r  <= csr_bresp;
            end else if (m_axi_bvalid_r && m_axi_bready) begin
                m_axi_bvalid_r <= 1'b0;
            end

            if (m_axi_arvalid && m_axi_arready_r) begin
                rd_inflight   <= 1'b1;
                csr_araddr_r  <= m_axi_araddr[7:0];
                m_axi_rid_r   <= m_axi_arid;
                csr_arvalid_r <= 1'b1;
                m_axi_arready_r <= 1'b0;
            end
            if (csr_arvalid_r && csr_arready)
                csr_arvalid_r <= 1'b0;

            if (rd_inflight && csr_rvalid) begin
                rd_inflight    <= 1'b0;
                m_axi_rvalid_r <= 1'b1;
                m_axi_rdata_r  <= {4{csr_rdata}};
                m_axi_rresp_r  <= csr_rresp;
            end else if (m_axi_rvalid_r && m_axi_rready) begin
                m_axi_rvalid_r <= 1'b0;
            end
        end
    end

    // -------------------------------------------------------------------------
    // link_axis + Cross-Clock Async FIFOs (rx_clkdiv <-> tx_clk_div)
    // -------------------------------------------------------------------------
    wire [63:0] m_axis_rx_tdata;
    wire        m_axis_rx_tvalid, m_axis_rx_tlast;
    wire [7:0]  m_axis_rx_tid;
    wire [0:0]  m_axis_rx_tuser;
    wire        rx2tx_full, rx2tx_empty, rx2tx_rd_en;
    wire [73:0] rx2tx_rd_data;

    wire [63:0] s_axis_tx_tdata;
    wire        s_axis_tx_tvalid, s_axis_tx_tready, s_axis_tx_tlast;
    wire [7:0]  s_axis_tx_tid;
    wire        tx2rx_full, tx2rx_empty;
    wire [72:0] tx2rx_rd_data;
    reg         tx2rx_wr_en;
    reg  [72:0] tx2rx_wr_data;

    wire        dl_pkt_valid, dl_pkt_sop, dl_pkt_eop;
    wire [7:0]  dl_pkt_sid;
    wire [15:0] dl_pkt_len;
    wire [31:0] dl_pkt_seq;
    wire [63:0] dl_pkt_data;
    wire        dl_fifo_full, dl_fifo_empty, dl_pkt_ready_tx;
    wire [129:0] dl_fifo_rd_data;

    wire [31:0] last_rx_seq;
    wire [63:0] last_rx_ts;
    wire [15:0] last_rx_len;

    // 64-bit timestamp counter clocked in rx_clkdiv, PPS synced via Pmod J2.4
    (* ASYNC_REG = "TRUE" *) reg [1:0] pps_rx_sync;
    reg        pps_rx_prev;
    reg [63:0] ts_cnt_rx;
    always @(posedge rx_clkdiv) begin
        if (rst_rx) begin
            pps_rx_sync <= 2'b00;
            pps_rx_prev <= 1'b0;
            ts_cnt_rx   <= 64'd0;
        end else begin
            pps_rx_sync <= {pps_rx_sync[0], pmod_pps_sync};
            pps_rx_prev <= pps_rx_sync[1];
            if (pps_rx_sync[1] && !pps_rx_prev)
                ts_cnt_rx <= {ts_cnt_rx[63:32] + 32'd1, 32'd0};
            else
                ts_cnt_rx <= ts_cnt_rx + 64'd1;
        end
    end

    link_axis #(
        .RX_FIFO_DEPTH (256),
        .TX_FIFO_DEPTH (128)
    ) u_link_axis (
        .clk                  (rx_clkdiv),
        .rst                  (pcs_rst_rx),
        .m_axis_rx_tdata      (m_axis_rx_tdata),
        .m_axis_rx_tvalid     (m_axis_rx_tvalid),
        .m_axis_rx_tready     (!rx2tx_full),
        .m_axis_rx_tlast      (m_axis_rx_tlast),
        .m_axis_rx_tid        (m_axis_rx_tid),
        .m_axis_rx_tuser      (m_axis_rx_tuser),
        .s_axis_tx_tdata      (tx2rx_rd_data[63:0]),
        .s_axis_tx_tvalid     (!tx2rx_empty),
        .s_axis_tx_tready     (s_axis_tx_tready),
        .s_axis_tx_tlast      (tx2rx_rd_data[72]),
        .s_axis_tx_tid        (tx2rx_rd_data[71:64]),
        .s_axis_tx_tuser      (16'd0),
        .s_axi_awaddr         (csr_awaddr_r),
        .s_axi_awvalid        (csr_awvalid_r),
        .s_axi_awready        (csr_awready),
        .s_axi_wdata          (csr_wdata_r),
        .s_axi_wstrb          (csr_wstrb_r),
        .s_axi_wvalid         (csr_wvalid_r),
        .s_axi_wready         (csr_wready),
        .s_axi_bresp          (csr_bresp),
        .s_axi_bvalid         (csr_bvalid),
        .s_axi_bready         (1'b1),
        .s_axi_araddr         (csr_araddr_r),
        .s_axi_arvalid        (csr_arvalid_r),
        .s_axi_arready        (csr_arready),
        .s_axi_rdata          (csr_rdata),
        .s_axi_rresp          (csr_rresp),
        .s_axi_rvalid         (csr_rvalid),
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
        .tx_pkt_valid         (dl_pkt_valid),
        .tx_pkt_ready         (!dl_fifo_full),
        .tx_pkt_sop           (dl_pkt_sop),
        .tx_pkt_eop           (dl_pkt_eop),
        .tx_pkt_stream_id     (dl_pkt_sid),
        .tx_pkt_len           (dl_pkt_len),
        .tx_pkt_seq           (dl_pkt_seq),
        .tx_pkt_timestamp     (),
        .tx_pkt_data          (dl_pkt_data),
        .timestamp_cnt        (ts_cnt_rx),
        .ctrl_soft_rst        (ctrl_soft_rst),
        .ctrl_loopback_en     (ctrl_loopback_en),
        .ctrl_retrain_pulse   (ctrl_retrain_pulse),
        .ctrl_tap_override_en (ctrl_tap_override_en),
        .ctrl_prbs7_tx_en     (ctrl_prbs7_tx_en),
        .ctrl_prbs7_rx_chk_en (ctrl_prbs7_rx_chk_en),
        .cfg_tap_l0           (cfg_tap_l0),
        .cfg_load_l0          (cfg_load_l0),
        .cfg_tap_l1           (cfg_tap_l1),
        .cfg_load_l1          (cfg_load_l1),
        .st_train_state       (train_state),
        .st_l0_block_lock     (l0_lock),
        .st_l1_block_lock     (l1_lock),
        .st_deskew_lock       (d_lock),
        .st_link_up           (kria_link_up),
        .st_idelayctrl_rdy    (idelay_rdy_rx),
        .st_remote_status     (rem_stat[7:0]),
        .active_tap_l0        (active_cnt_l0),
        .active_tap_l1        (active_cnt_l1),
        .pcs_sh_err_cnt_l0    (sh_err0),
        .pcs_sh_err_cnt_l1    (sh_err1),
        .tx_dropped_cnt       (rem_drop),
        .skew_blocks          (skew_blk),
        .am_seq               (16'd0),
        .pcs_prbs_err_cnt     (prbs_err_cnt_r),
        .eye_left_l0          (eye_l0),
        .eye_right_l0         (eye_r0),
        .eye_left_l1          (eye_l1),
        .eye_right_l1         (eye_r1),
        .last_rx_seq          (last_rx_seq),
        .last_rx_timestamp    (last_rx_ts),
        .last_rx_len          (last_rx_len)
    );

    kria_async_fifo #(.DW(74), .AW(4)) u_fifo_rx2tx (
        .wr_clk   (rx_clkdiv),
        .wr_rst   (rst_rx),
        .wr_en    (m_axis_rx_tvalid && !rx2tx_full),
        .wr_data  ({m_axis_rx_tlast, m_axis_rx_tuser[0], m_axis_rx_tid, m_axis_rx_tdata}),
        .wr_full  (rx2tx_full),
        .rd_clk   (tx_clk_div),
        .rd_rst   (rst_tx),
        .rd_en    (rx2tx_rd_en),
        .rd_data  (rx2tx_rd_data),
        .rd_empty (rx2tx_empty)
    );

    kria_async_fifo #(.DW(73), .AW(4)) u_fifo_tx2rx (
        .wr_clk   (tx_clk_div),
        .wr_rst   (rst_tx),
        .wr_en    (tx2rx_wr_en),
        .wr_data  (tx2rx_wr_data),
        .wr_full  (tx2rx_full),
        .rd_clk   (rx_clkdiv),
        .rd_rst   (rst_rx),
        .rd_en    (!tx2rx_empty && s_axis_tx_tready),
        .rd_data  (tx2rx_rd_data),
        .rd_empty (tx2rx_empty)
    );

    kria_async_fifo #(.DW(130), .AW(4)) u_fifo_dl (
        .wr_clk   (rx_clkdiv),
        .wr_rst   (rst_rx),
        .wr_en    (dl_pkt_valid && !dl_fifo_full),
        .wr_data  ({dl_pkt_sop, dl_pkt_eop, dl_pkt_sid, dl_pkt_len, dl_pkt_seq, dl_pkt_data}),
        .wr_full  (dl_fifo_full),
        .rd_clk   (tx_clk_div),
        .rd_rst   (rst_tx),
        .rd_en    (!dl_fifo_empty && dl_pkt_ready_tx),
        .rd_data  (dl_fifo_rd_data),
        .rd_empty (dl_fifo_empty)
    );

    // -------------------------------------------------------------------------
    // SAXIGP2 DMA Engine + Downlink Loopback in tx_clk_div (125 MHz)
    // -------------------------------------------------------------------------
    (* ASYNC_REG = "TRUE" *) reg [1:0] link_up_tx_sync, lb_tx_sync, prbs_tx_sync;
    reg [15:0] dma_wr_ofs, dma_rd_ofs;
    reg        wr_aw_done, wr_w_done, wr_busy;
    reg        rd_ar_done, rd_busy;
    reg [63:0] ts_cnt_tx;
    reg        pps_tx_prev;

    assign rx2tx_rd_en = !rx2tx_empty && (!wr_busy || lb_tx_sync[1]);

    always @(posedge tx_clk_div) begin
        if (rst_tx) begin
            link_up_tx_sync  <= 2'b00;
            lb_tx_sync       <= 2'b00;
            prbs_tx_sync     <= 2'b00;
            dma_wr_ofs       <= 16'd0;
            dma_rd_ofs       <= 16'd0;
            s_axi_hp_awvalid <= 1'b0;
            s_axi_hp_wvalid  <= 1'b0;
            s_axi_hp_wlast   <= 1'b1;
            s_axi_hp_awaddr  <= 49'h0000_1000_0000;
            s_axi_hp_wdata   <= 128'd0;
            s_axi_hp_wstrb   <= 16'h00FF;
            wr_aw_done       <= 1'b0;
            wr_w_done        <= 1'b0;
            wr_busy          <= 1'b0;
            s_axi_hp_arvalid <= 1'b0;
            s_axi_hp_araddr  <= 49'h0000_1010_0000;
            rd_ar_done       <= 1'b0;
            rd_busy          <= 1'b0;
            tx2rx_wr_en      <= 1'b0;
            tx2rx_wr_data    <= 73'd0;
            ts_cnt_tx        <= 64'd0;
            pps_tx_prev      <= 1'b0;
        end else begin
            link_up_tx_sync <= {link_up_tx_sync[0], kria_link_up};
            lb_tx_sync      <= {lb_tx_sync[0],      ctrl_loopback_en};
            prbs_tx_sync    <= {prbs_tx_sync[0],    ctrl_prbs7_tx_en};
            pps_tx_prev     <= ps_gpio_o[2];

            if (ps_gpio_o[2] && !pps_tx_prev)
                ts_cnt_tx <= {ts_cnt_tx[63:32] + 32'd1, 32'd0};
            else
                ts_cnt_tx <= ts_cnt_tx + 64'd1;

            tx2rx_wr_en <= 1'b0;

            // RX -> SAXIGP2 DDR write DMA (or TX loopback when lb_tx_sync[1] == 1)
            if (!wr_busy && !rx2tx_empty) begin
                if (lb_tx_sync[1]) begin
                    if (!tx2rx_full) begin
                        tx2rx_wr_en   <= 1'b1;
                        tx2rx_wr_data <= {rx2tx_rd_data[73], rx2tx_rd_data[71:0]};
                    end
                end else begin
                    wr_busy          <= 1'b1;
                    wr_aw_done       <= 1'b0;
                    wr_w_done        <= 1'b0;
                    s_axi_hp_awvalid <= 1'b1;
                    s_axi_hp_wvalid  <= 1'b1;
                    s_axi_hp_wlast   <= 1'b1;
                    s_axi_hp_awaddr  <= {30'h0000_0400, dma_wr_ofs, 3'b000};
                    s_axi_hp_wdata   <= {rx2tx_rd_data[63:0], rx2tx_rd_data[63:0]};
                    s_axi_hp_wstrb   <= dma_wr_ofs[0] ? 16'hFF00 : 16'h00FF;
                    dma_wr_ofs       <= dma_wr_ofs + 16'd1;
                end
            end

            if (s_axi_hp_awvalid && s_axi_hp_awready) begin
                s_axi_hp_awvalid <= 1'b0;
                wr_aw_done       <= 1'b1;
            end
            if (s_axi_hp_wvalid && s_axi_hp_wready) begin
                s_axi_hp_wvalid <= 1'b0;
                wr_w_done       <= 1'b1;
            end
            if (wr_busy && wr_aw_done && wr_w_done && s_axi_hp_bvalid) begin
                wr_busy <= 1'b0;
            end

            // SAXIGP2 DDR read DMA -> Downlink AXIS TX when ps_gpio_o[16] is asserted
            if (!rd_busy && ps_gpio_o[16] && !tx2rx_full && !lb_tx_sync[1]) begin
                rd_busy          <= 1'b1;
                rd_ar_done       <= 1'b0;
                s_axi_hp_arvalid <= 1'b1;
                s_axi_hp_araddr  <= {30'h0000_0401, dma_rd_ofs, 3'b000};
            end
            if (s_axi_hp_arvalid && s_axi_hp_arready) begin
                s_axi_hp_arvalid <= 1'b0;
                rd_ar_done       <= 1'b1;
            end
            if (rd_busy && rd_ar_done && s_axi_hp_rvalid) begin
                rd_busy <= 1'b0;
                if (!tx2rx_full) begin
                    tx2rx_wr_en   <= 1'b1;
                    tx2rx_wr_data <= {1'b1, ps_gpio_o[15:8],
                                      dma_rd_ofs[0] ? s_axi_hp_rdata[127:64] : s_axi_hp_rdata[63:0]};
                end
                dma_rd_ofs <= dma_rd_ofs + 16'd1;
            end
        end
    end

    // -------------------------------------------------------------------------
    // Downlink TX (link_pcs_single_tx + PRBS7 + OSERDESE3 -> LINK_TX_*)
    // -------------------------------------------------------------------------
    wire [7:0] dl_tx_byte;
    link_pcs_single_tx u_pcs_dl_tx (
        .clk           (tx_clk_div),
        .rst           (rst_tx),
        .pkt_valid     (!dl_fifo_empty),
        .pkt_ready     (dl_pkt_ready_tx),
        .pkt_sop       (dl_fifo_rd_data[129]),
        .pkt_eop       (dl_fifo_rd_data[128]),
        .pkt_stream_id (dl_fifo_rd_data[127:120]),
        .pkt_len       (dl_fifo_rd_data[119:104]),
        .pkt_seq       (dl_fifo_rd_data[103:72]),
        .pkt_timestamp (ts_cnt_tx),
        .pkt_data      (dl_fifo_rd_data[63:0]),
        .dropped_cnt   (24'd0),
        .local_status  ({15'd0, link_up_tx_sync[1]}),
        .tx_byte_l0    (dl_tx_byte)
    );

    reg [6:0] prbs_tx_lfsr;
    reg [7:0] dl_tx_byte_r, prbs_tx_byte;
    reg [6:0] prbs_tx_next;
    integer   ptx_i;
    always @* begin
        prbs_tx_next = prbs_tx_lfsr;
        for (ptx_i = 0; ptx_i < 8; ptx_i = ptx_i + 1) begin
            prbs_tx_byte[ptx_i] = prbs_tx_next[6];
            prbs_tx_next = {prbs_tx_next[5:0], prbs_tx_next[6] ^ prbs_tx_next[5]};
        end
    end

    always @(posedge tx_clk_div) begin
        if (rst_tx) begin
            prbs_tx_lfsr <= 7'h7F;
            dl_tx_byte_r <= 8'd0;
        end else begin
            prbs_tx_lfsr <= prbs_tx_sync[1] ? prbs_tx_next : 7'h7F;
            dl_tx_byte_r <= prbs_tx_sync[1] ? prbs_tx_byte : dl_tx_byte;
        end
    end

    wire dl_ser_clk, dl_ser_d0;
    OSERDESE3 #(
        .DATA_WIDTH       (8),
        .INIT             (1'b0),
        .ODDR_MODE        ("FALSE"),
        .OSERDES_D_BYPASS ("FALSE"),
        .OSERDES_T_BYPASS ("FALSE"),
        .SIM_DEVICE       ("ULTRASCALE_PLUS")
    ) u_oserdes_tx_clk (
        .OQ     (dl_ser_clk),
        .T_OUT  (),
        .CLK    (tx_clk_hs),
        .CLKDIV (tx_clk_div),
        .D      (8'b10101010),
        .RST    (rst_tx),
        .T      (1'b0)
    );

    OSERDESE3 #(
        .DATA_WIDTH       (8),
        .INIT             (1'b0),
        .ODDR_MODE        ("FALSE"),
        .OSERDES_D_BYPASS ("FALSE"),
        .OSERDES_T_BYPASS ("FALSE"),
        .SIM_DEVICE       ("ULTRASCALE_PLUS")
    ) u_oserdes_tx_d0 (
        .OQ     (dl_ser_d0),
        .T_OUT  (),
        .CLK    (tx_clk_hs),
        .CLKDIV (tx_clk_div),
        .D      (dl_tx_byte_r),
        .RST    (rst_tx),
        .T      (1'b0)
    );

    OBUFDS u_obuf_tx_clk (.I(dl_ser_clk), .O(link_tx_clk_p), .OB(link_tx_clk_n));
    OBUFDS u_obuf_tx_d0  (.I(dl_ser_d0),  .O(link_tx_d0_p),  .OB(link_tx_d0_n));

    // -------------------------------------------------------------------------
    // Single-Ended Control, Pmod J2 & I2C Housekeeping
    // -------------------------------------------------------------------------
    IOBUF u_iobuf_scl (
        .I  (ps_i2c0_scl_o),
        .O  (ps_i2c0_scl_i),
        .T  (ps_i2c0_scl_t),
        .IO (hk_scl)
    );

    IOBUF u_iobuf_sda (
        .I  (ps_i2c0_sda_o),
        .O  (ps_i2c0_sda_i),
        .T  (ps_i2c0_sda_t),
        .IO (hk_sda)
    );

    reg pmod_cs_r, pmod_mosi_r, pmod_sclk_r, pmod_strobe_r, pmod_pps_r, pmod_sp1_r, prog_b_r;
    always @(posedge tx_clk_div) begin
        if (rst_tx) begin
            pmod_cs_r     <= 1'b1;
            pmod_mosi_r   <= 1'b0;
            pmod_sclk_r   <= 1'b0;
            pmod_strobe_r <= 1'b0;
            pmod_pps_r    <= 1'b0;
            pmod_sp1_r    <= 1'b0;
            prog_b_r      <= 1'b1;
        end else begin
            pmod_cs_r     <= ps_gpio_o[4] ? ~ps_gpio_tn[4] : ps_spi0_sson[0];
            pmod_mosi_r   <= ps_spi0_mo;
            pmod_sclk_r   <= ps_spi0_sclko;
            pmod_strobe_r <= ps_gpio_o[1];
            pmod_pps_r    <= ps_gpio_o[2];
            pmod_sp1_r    <= ps_gpio_o[3];
            prog_b_r      <= ps_gpio_o[0];
        end
    end

    assign fpga_prog_b      = prog_b_r;
    assign pmod_cs_n        = pmod_cs_r;
    assign pmod_mosi        = pmod_mosi_r;
    assign pmod_sclk        = pmod_sclk_r;
    assign pmod_beam_strobe = pmod_strobe_r;
    assign pmod_pps_sync    = pmod_pps_r;
    assign pmod_spare1      = pmod_sp1_r;

    (* ASYNC_REG = "TRUE" *) reg [1:0] irq_sync, spare2_sync;
    reg [63:0] rx_meta_snap_tx;
    always @(posedge tx_clk_div) begin
        irq_sync        <= {irq_sync[0], fpga_irq};
        spare2_sync     <= {spare2_sync[0], pmod_spare2};
        rx_meta_snap_tx <= {last_rx_len, last_rx_seq[15:0], last_rx_ts[31:0]};
    end

    assign ps_gpio_i  = {rx_meta_snap_tx, 27'd0,
                         rx_err_or_flags(s_axi_hp_bresp, s_axi_hp_rresp),
                         link_up_tx_sync[1], spare2_sync[1], irq_sync[1]};
    assign pl_ps_irq0 = {6'd0, kria_link_up, irq_sync[1]};

    function [1:0] rx_err_or_flags;
        input [1:0] bresp, rresp;
        begin
            rx_err_or_flags = bresp | rresp;
        end
    endfunction

endmodule
