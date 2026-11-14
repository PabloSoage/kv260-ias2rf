// SPDX-License-Identifier: BSD-2-Clause
// Kria K26 (XCK26-SFVC784-2LV-C) Block-Design PL Link Wrapper
//
// Exposes standard AXI4-Lite CSR (s_axi_*), AXI4-Stream RX (m_axis_rx_* -> axi_dma S2MM),
// AXI4-Stream TX (s_axis_tx_* <- axi_dma MM2S), and PS EMIO control/I2C/SPI on pl_clk_100m,
// while bridging to the source-synchronous 125 MHz rx_clkdiv / tx_clk_div PCS domains.

`timescale 1ns/1ps

module kria_pl_async_fifo #(
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

module kria_pl_link (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 pl_clk_100m CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axi:m_axis_rx:s_axis_tx, ASSOCIATED_RESET pl_resetn" *)
    input  wire        pl_clk_100m,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 pl_resetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire        pl_resetn,

    // AXI4-Lite Slave CSR (0x00 .. 0x30 in pl_clk_100m domain)
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWADDR" *)
    (* X_INTERFACE_PARAMETER = "PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 8" *)
    input  wire [7:0]  s_axi_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWPROT" *)
    input  wire [2:0]  s_axi_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWVALID" *)
    input  wire        s_axi_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWREADY" *)
    output reg         s_axi_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WDATA" *)
    input  wire [31:0] s_axi_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WSTRB" *)
    input  wire [3:0]  s_axi_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WVALID" *)
    input  wire        s_axi_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WREADY" *)
    output reg         s_axi_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi BRESP" *)
    output reg  [1:0]  s_axi_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi BVALID" *)
    output reg         s_axi_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi BREADY" *)
    input  wire        s_axi_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi ARADDR" *)
    input  wire [7:0]  s_axi_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi ARPROT" *)
    input  wire [2:0]  s_axi_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi ARVALID" *)
    input  wire        s_axi_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi ARREADY" *)
    output reg         s_axi_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RDATA" *)
    output reg  [31:0] s_axi_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RRESP" *)
    output reg  [1:0]  s_axi_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RVALID" *)
    output reg         s_axi_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RREADY" *)
    input  wire        s_axi_rready,

    // AXI4-Stream Master RX (toward axi_dma S2MM in pl_clk_100m domain)
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis_rx TDATA" *)
    output wire [63:0] m_axis_rx_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis_rx TKEEP" *)
    output wire [7:0]  m_axis_rx_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis_rx TVALID" *)
    output wire        m_axis_rx_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis_rx TREADY" *)
    input  wire        m_axis_rx_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis_rx TLAST" *)
    output wire        m_axis_rx_tlast,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis_rx TID" *)
    output wire [7:0]  m_axis_rx_tid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis_rx TUSER" *)
    output wire [0:0]  m_axis_rx_tuser,

    // AXI4-Stream Slave TX (from axi_dma MM2S in pl_clk_100m domain)
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_tx TDATA" *)
    input  wire [63:0] s_axis_tx_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_tx TKEEP" *)
    input  wire [7:0]  s_axis_tx_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_tx TVALID" *)
    input  wire        s_axis_tx_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_tx TREADY" *)
    output wire        s_axis_tx_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_tx TLAST" *)
    input  wire        s_axis_tx_tlast,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_tx TID" *)
    input  wire [7:0]  s_axis_tx_tid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_tx TUSER" *)
    input  wire [15:0] s_axis_tx_tuser,

    // Zynq PS EMIO Sideband
    output wire        emio_i2c_scl_i,
    input  wire        emio_i2c_scl_o,
    input  wire        emio_i2c_scl_t,
    output wire        emio_i2c_sda_i,
    input  wire        emio_i2c_sda_o,
    input  wire        emio_i2c_sda_t,

    input  wire        emio_spi_mo,
    input  wire        emio_spi_sclk,
    input  wire        emio_spi_ssn,
    output wire        emio_spi_mi,

    input  wire [7:0]  emio_gpio_o,
    input  wire [7:0]  emio_gpio_t,
    output wire [7:0]  emio_gpio_i,

    // Interrupts to PS pl_ps_irq0
    output wire        irq_fpga,
    output wire        irq_link_up,

    // Physical Board Pins (Bank 66 HP + Bank 45 HD)
    input  wire        link_rx_clk_p,
    input  wire        link_rx_clk_n,
    input  wire        link_rx_d0_p,
    input  wire        link_rx_d0_n,
    input  wire        link_rx_d1_p,
    input  wire        link_rx_d1_n,

    output wire        link_tx_clk_p,
    output wire        link_tx_clk_n,
    output wire        link_tx_d0_p,
    output wire        link_tx_d0_n,

    input  wire        fpga_irq,
    inout  wire        hk_scl,
    inout  wire        hk_sda,
    output wire        fpga_prog_b,

    output wire        pmod_cs_n,
    output wire        pmod_mosi,
    input  wire        pmod_miso,
    output wire        pmod_sclk,
    output wire        pmod_beam_strobe,
    output wire        pmod_pps_sync,
    output wire        pmod_spare1,
    input  wire        pmod_spare2
);

    // -------------------------------------------------------------------------
    // 1. MMCM (100 MHz PL -> 500 MHz TX HS/125 MHz TX DIV + 300 MHz IDELAYCTRL)
    // -------------------------------------------------------------------------
    wire mmcm_fb, mmcm_fb_buf;
    wire clk_500_u, clk_300_u, mmcm_locked;
    wire tx_clk_hs, tx_clk_div, refclk_300m;

    MMCME4_BASE #(
        .CLKIN1_PERIOD    (10.000),
        .CLKFBOUT_MULT_F  (15.000),
        .DIVCLK_DIVIDE    (1),
        .CLKOUT0_DIVIDE_F (3.000),
        .CLKOUT1_DIVIDE   (5)
    ) u_mmcm (
        .CLKIN1   (pl_clk_100m),
        .CLKFBIN  (mmcm_fb_buf),
        .RST      (!pl_resetn),
        .PWRDWN   (1'b0),
        .CLKFBOUT (mmcm_fb),
        .CLKOUT0  (clk_500_u),
        .CLKOUT1  (clk_300_u),
        .LOCKED   (mmcm_locked)
    );

    BUFG u_bufg_mmcm_fb (.I(mmcm_fb), .O(mmcm_fb_buf));
    BUFGCE u_bufg_tx_hs (.I(clk_500_u), .CE(1'b1), .O(tx_clk_hs));
    BUFGCE_DIV #(.BUFGCE_DIVIDE(4)) u_bufg_tx_div (.I(clk_500_u), .CE(1'b1), .CLR(1'b0), .O(tx_clk_div));
    BUFGCE u_bufg_ref300 (.I(clk_300_u), .CE(1'b1), .O(refclk_300m));

    wire sys_rst_n = pl_resetn & mmcm_locked;

    (* ASYNC_REG = "TRUE" *) reg [2:0] rst_300_sync = 3'b111;
    always @(posedge refclk_300m or negedge sys_rst_n) begin
        if (!sys_rst_n) rst_300_sync <= 3'b111;
        else            rst_300_sync <= {rst_300_sync[1:0], 1'b0};
    end
    wire rst_300 = rst_300_sync[2];

    (* ASYNC_REG = "TRUE" *) reg [2:0] rst_tx_sync = 3'b111;
    always @(posedge tx_clk_div or negedge sys_rst_n) begin
        if (!sys_rst_n) rst_tx_sync <= 3'b111;
        else            rst_tx_sync <= {rst_tx_sync[1:0], 1'b0};
    end
    wire rst_tx = rst_tx_sync[2];

    // -------------------------------------------------------------------------
    // 2. Uplink LVDS RX (Bank 66 HP) -> rx_clkdiv (125 MHz)
    // -------------------------------------------------------------------------
    wire rx_clk_ibuf, rx_d0_ibuf, rx_d1_ibuf;
    wire rx_clk_hs, rx_clkdiv;

    IBUFDS u_ibuf_rx_clk (.I(link_rx_clk_p), .IB(link_rx_clk_n), .O(rx_clk_ibuf));
    IBUFDS u_ibuf_rx_d0  (.I(link_rx_d0_p),  .IB(link_rx_d0_n),  .O(rx_d0_ibuf));
    IBUFDS u_ibuf_rx_d1  (.I(link_rx_d1_p),  .IB(link_rx_d1_n),  .O(rx_d1_ibuf));

    BUFGCE u_bufg_rx_hs (.I(rx_clk_ibuf), .CE(1'b1), .O(rx_clk_hs));
    BUFGCE_DIV #(.BUFGCE_DIVIDE(4)) u_bufg_rx_div (.I(rx_clk_ibuf), .CE(1'b1), .CLR(1'b0), .O(rx_clkdiv));

    (* ASYNC_REG = "TRUE" *) reg [2:0] rst_rx_sync = 3'b111;
    always @(posedge rx_clkdiv or negedge sys_rst_n) begin
        if (!sys_rst_n) rst_rx_sync <= 3'b111;
        else            rst_rx_sync <= {rst_rx_sync[1:0], 1'b0};
    end
    wire rst_rx = rst_rx_sync[2];

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
        .CASCADE("NONE"), .DELAY_FORMAT("TIME"), .DELAY_SRC("IDATAIN"),
        .DELAY_TYPE("VAR_LOAD"), .DELAY_VALUE(0), .REFCLK_FREQUENCY(300.0),
        .SIM_DEVICE("ULTRASCALE_PLUS"), .UPDATE_MODE("ASYNC")
    ) u_idelay_d0 (
        .CASC_OUT(), .CNTVALUEOUT(active_cnt_l0), .DATAOUT(rx_d0_idelay),
        .CASC_IN(1'b0), .CASC_RETURN(1'b0), .CE(1'b0), .CLK(rx_clkdiv),
        .CNTVALUEIN(idly_cnt_l0), .DATAIN(1'b0), .EN_VTC(idly_en_vtc),
        .IDATAIN(rx_d0_ibuf), .INC(1'b0), .LOAD(idly_load_l0), .RST(rst_rx)
    );

    IDELAYE3 #(
        .CASCADE("NONE"), .DELAY_FORMAT("TIME"), .DELAY_SRC("IDATAIN"),
        .DELAY_TYPE("VAR_LOAD"), .DELAY_VALUE(0), .REFCLK_FREQUENCY(300.0),
        .SIM_DEVICE("ULTRASCALE_PLUS"), .UPDATE_MODE("ASYNC")
    ) u_idelay_d1 (
        .CASC_OUT(), .CNTVALUEOUT(active_cnt_l1), .DATAOUT(rx_d1_idelay),
        .CASC_IN(1'b0), .CASC_RETURN(1'b0), .CE(1'b0), .CLK(rx_clkdiv),
        .CNTVALUEIN(idly_cnt_l1), .DATAIN(1'b0), .EN_VTC(idly_en_vtc),
        .IDATAIN(rx_d1_ibuf), .INC(1'b0), .LOAD(idly_load_l1), .RST(rst_rx)
    );

    wire [7:0] rx_byte_l0_raw, rx_byte_l1_raw;
    ISERDESE3 #(
        .DATA_WIDTH(8), .DDR_CLK_EDGE("OPPOSITE_EDGE"), .FIFO_ENABLE("FALSE"),
        .FIFO_SYNC_MODE("FALSE"), .IDDR_MODE("FALSE"), .SIM_DEVICE("ULTRASCALE_PLUS")
    ) u_iserdes_d0 (
        .FIFO_EMPTY(), .INTERNAL_DIVCLK(), .Q(rx_byte_l0_raw),
        .CLK(rx_clk_hs), .CLK_B(~rx_clk_hs), .CLKDIV(rx_clkdiv),
        .D(rx_d0_idelay), .FIFO_RD_CLK(1'b0), .FIFO_RD_EN(1'b0), .RST(rst_rx)
    );

    ISERDESE3 #(
        .DATA_WIDTH(8), .DDR_CLK_EDGE("OPPOSITE_EDGE"), .FIFO_ENABLE("FALSE"),
        .FIFO_SYNC_MODE("FALSE"), .IDDR_MODE("FALSE"), .SIM_DEVICE("ULTRASCALE_PLUS")
    ) u_iserdes_d1 (
        .FIFO_EMPTY(), .INTERNAL_DIVCLK(), .Q(rx_byte_l1_raw),
        .CLK(rx_clk_hs), .CLK_B(~rx_clk_hs), .CLKDIV(rx_clkdiv),
        .D(rx_d1_idelay), .FIFO_RD_CLK(1'b0), .FIFO_RD_EN(1'b0), .RST(rst_rx)
    );

    reg [7:0] rx_byte_l0, rx_byte_l1;
    always @(posedge rx_clkdiv) begin
        rx_byte_l0 <= rx_byte_l0_raw;
        rx_byte_l1 <= rx_byte_l1_raw;
    end

    reg [6:0]  prbs_rx_state;
    reg [31:0] prbs_err_cnt_r;
    reg        idelay_rdy_rx_m, idelay_rdy_rx;
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
        .DEFAULT_CENTER_TAP (9'd202), .MAX_TAP(9'd511), .TAP_STEP(9'd8),
        .MIN_EYE_STEPS(9'd16), .WAIT_RESET_CYCLES(16'd16), .TAP_SETTLE_CYCLES(16'd24),
        .TAP_DWELL_CYCLES(16'd1800), .LOCK_TIMEOUT(16'd8192), .SINGLE_LANE(0)
    ) u_train_fsm (
        .clk(rx_clkdiv), .rst(pcs_rst_rx), .retrain(ctrl_retrain_pulse),
        .cfg_tap_override(ctrl_tap_override_en), .cfg_tap_l0(cfg_tap_l0), .cfg_tap_l1(cfg_tap_l1),
        .rx_byte_l0(rx_byte_l0), .rx_byte_l1(rx_byte_l1),
        .l0_block_lock(l0_lock), .l1_block_lock(l1_lock), .deskew_lock(d_lock),
        .l0_rx_blk_valid(l0_blk_v), .l0_rx_blk_ok(l0_blk_ok),
        .l1_rx_blk_valid(l1_blk_v), .l1_rx_blk_ok(l1_blk_ok),
        .en_vtc(train_en_vtc), .load_l0(train_load_l0), .cntval_l0(train_cnt_l0),
        .load_l1(train_load_l1), .cntval_l1(train_cnt_l1), .train_state(train_state),
        .link_up(kria_link_up), .eye_left_l0(eye_l0), .eye_right_l0(eye_r0),
        .eye_left_l1(eye_l1), .eye_right_l1(eye_r1)
    );

    link_pcs_rx #(.DISABLE_DESKEW(0)) u_pcs_rx (
        .clk(rx_clkdiv), .rst(pcs_rst_rx), .link_ready(kria_link_up),
        .rx_byte_l0(rx_byte_l0), .rx_byte_l1(rx_byte_l1),
        .out_valid(rx_out_v), .out_sop(rx_out_sop), .out_eop(rx_out_eop),
        .out_stream_id(rx_out_sid), .out_len(rx_out_len), .out_seq(rx_out_seq),
        .out_timestamp(rx_out_ts), .out_data(rx_out_data),
        .pkt_done_valid(rx_done_v), .pkt_done_ok(rx_done_ok), .pkt_done_err(rx_done_err),
        .l0_block_lock(l0_lock), .l1_block_lock(l1_lock), .deskew_lock(d_lock),
        .skew_blocks(skew_blk), .remote_status(rem_stat), .remote_dropped_cnt(rem_drop),
        .sh_err_cnt_l0(sh_err0), .sh_err_cnt_l1(sh_err1),
        .pkt_rx_cnt(pkt_rx_cnt), .crc_err_cnt(crc_err_cnt),
        .l0_rx_blk_valid(l0_blk_v), .l0_rx_blk_ok(l0_blk_ok),
        .l1_rx_blk_valid(l1_blk_v), .l1_rx_blk_ok(l1_blk_ok)
    );

    // -------------------------------------------------------------------------
    // 3. AXI4-Lite Clock-Crossing Bridge (pl_clk_100m <-> rx_clkdiv) with Watchdog
    // -------------------------------------------------------------------------
    reg        csr_req_tog_pl = 1'b0;
    reg        csr_req_wr_pl  = 1'b0;
    reg  [7:0] csr_req_addr_pl = 8'd0;
    reg [31:0] csr_req_wdata_pl = 32'd0;
    reg  [3:0] csr_req_wstrb_pl = 4'd0;

    (* ASYNC_REG = "TRUE" *) reg [2:0] csr_req_sync_rx = 3'b000;
    reg        csr_ack_tog_rx = 1'b0;
    reg [31:0] csr_rsp_rdata_rx = 32'd0;
    reg  [1:0] csr_rsp_resp_rx  = 2'b00;

    (* ASYNC_REG = "TRUE" *) reg [2:0] csr_ack_sync_pl = 3'b000;
    reg [1:0]  axil_state = 2'd0;
    reg [10:0] axil_tmo   = 11'd0;
    reg        aw_seen = 1'b0, w_seen = 1'b0;
    reg  [7:0] awaddr_lat = 8'd0;
    reg [31:0] wdata_lat  = 32'd0;
    reg  [3:0] wstrb_lat  = 4'd0;
    reg  [7:0] tx_default_sid_r = 8'h10;

    // rx_clkdiv side AXI-Lite master toward u_link_axis
    reg  [7:0] link_awaddr, link_araddr;
    reg [31:0] link_wdata;
    reg  [3:0] link_wstrb;
    reg        link_awvalid, link_wvalid, link_arvalid;
    wire       link_awready, link_wready, link_bvalid, link_arready, link_rvalid;
    wire [1:0] link_bresp, link_rresp;
    wire [31:0] link_rdata;

    reg        rx_csr_busy, rx_csr_is_wr;
    always @(posedge rx_clkdiv) begin
        if (rst_rx) begin
            csr_req_sync_rx  <= 3'b000;
            csr_ack_tog_rx   <= 1'b0;
            csr_rsp_rdata_rx <= 32'd0;
            csr_rsp_resp_rx  <= 2'b00;
            link_awvalid     <= 1'b0;
            link_wvalid      <= 1'b0;
            link_arvalid     <= 1'b0;
            link_awaddr      <= 8'd0;
            link_araddr      <= 8'd0;
            link_wdata       <= 32'd0;
            link_wstrb       <= 4'd0;
            rx_csr_busy      <= 1'b0;
            rx_csr_is_wr     <= 1'b0;
        end else begin
            csr_req_sync_rx <= {csr_req_sync_rx[1:0], csr_req_tog_pl};
            if (!rx_csr_busy) begin
                if (csr_req_sync_rx[2] ^ csr_req_sync_rx[1]) begin
                    rx_csr_busy  <= 1'b1;
                    rx_csr_is_wr <= csr_req_wr_pl;
                    if (csr_req_wr_pl) begin
                        link_awaddr  <= csr_req_addr_pl;
                        link_wdata   <= csr_req_wdata_pl;
                        link_wstrb   <= csr_req_wstrb_pl;
                        link_awvalid <= 1'b1;
                        link_wvalid  <= 1'b1;
                    end else begin
                        link_araddr  <= csr_req_addr_pl;
                        link_arvalid <= 1'b1;
                    end
                end
            end else begin
                if (link_awvalid && link_awready) link_awvalid <= 1'b0;
                if (link_wvalid  && link_wready)  link_wvalid  <= 1'b0;
                if (link_arvalid && link_arready) link_arvalid <= 1'b0;
                if (rx_csr_is_wr && link_bvalid) begin
                    csr_rsp_resp_rx <= link_bresp;
                    csr_ack_tog_rx  <= ~csr_ack_tog_rx;
                    rx_csr_busy     <= 1'b0;
                end else if (!rx_csr_is_wr && link_rvalid) begin
                    csr_rsp_rdata_rx <= link_rdata;
                    csr_rsp_resp_rx  <= link_rresp;
                    csr_ack_tog_rx   <= ~csr_ack_tog_rx;
                    rx_csr_busy      <= 1'b0;
                end
            end
        end
    end

    // pl_clk_100m side AXI4-Lite slave
    always @(posedge pl_clk_100m) begin
        if (!pl_resetn) begin
            s_axi_awready    <= 1'b0;
            s_axi_wready     <= 1'b0;
            s_axi_bvalid     <= 1'b0;
            s_axi_bresp      <= 2'b00;
            s_axi_arready    <= 1'b0;
            s_axi_rvalid     <= 1'b0;
            s_axi_rdata      <= 32'd0;
            s_axi_rresp      <= 2'b00;
            csr_ack_sync_pl  <= 3'b000;
            csr_req_tog_pl   <= 1'b0;
            csr_req_wr_pl    <= 1'b0;
            csr_req_addr_pl  <= 8'd0;
            csr_req_wdata_pl <= 32'd0;
            csr_req_wstrb_pl <= 4'd0;
            axil_state       <= 2'd0;
            axil_tmo         <= 11'd0;
            aw_seen          <= 1'b0;
            w_seen           <= 1'b0;
            tx_default_sid_r <= 8'h10;
        end else begin
            csr_ack_sync_pl <= {csr_ack_sync_pl[1:0], csr_ack_tog_rx};
            s_axi_awready   <= 1'b0;
            s_axi_wready    <= 1'b0;
            s_axi_arready   <= 1'b0;
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 1'b0;
            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 1'b0;

            case (axil_state)
                2'd0: begin
                    if (s_axi_awvalid && !aw_seen) begin
                        aw_seen       <= 1'b1;
                        awaddr_lat    <= s_axi_awaddr;
                        s_axi_awready <= 1'b1;
                    end
                    if (s_axi_wvalid && !w_seen) begin
                        w_seen       <= 1'b1;
                        wdata_lat    <= s_axi_wdata;
                        wstrb_lat    <= s_axi_wstrb;
                        s_axi_wready <= 1'b1;
                    end
                    if (((aw_seen || s_axi_awvalid) && (w_seen || s_axi_wvalid)) && !s_axi_bvalid) begin
                        if ((aw_seen ? awaddr_lat : s_axi_awaddr) == 8'h34) begin
                            if ((w_seen ? wstrb_lat[0] : s_axi_wstrb[0]))
                                tx_default_sid_r <= w_seen ? wdata_lat[7:0] : s_axi_wdata[7:0];
                            s_axi_bresp  <= 2'b00;
                            s_axi_bvalid <= 1'b1;
                            aw_seen      <= 1'b0;
                            w_seen       <= 1'b0;
                        end else begin
                            csr_req_wr_pl    <= 1'b1;
                            csr_req_addr_pl  <= aw_seen ? awaddr_lat : s_axi_awaddr;
                            csr_req_wdata_pl <= w_seen  ? wdata_lat  : s_axi_wdata;
                            csr_req_wstrb_pl <= w_seen  ? wstrb_lat  : s_axi_wstrb;
                            csr_req_tog_pl   <= ~csr_req_tog_pl;
                            aw_seen          <= 1'b0;
                            w_seen           <= 1'b0;
                            axil_tmo         <= 11'd0;
                            axil_state       <= 2'd1;
                        end
                    end else if (s_axi_arvalid && !aw_seen && !w_seen && !s_axi_rvalid) begin
                        s_axi_arready <= 1'b1;
                        if (s_axi_araddr == 8'h34) begin
                            s_axi_rdata  <= {24'd0, tx_default_sid_r};
                            s_axi_rresp  <= 2'b00;
                            s_axi_rvalid <= 1'b1;
                        end else begin
                            csr_req_wr_pl   <= 1'b0;
                            csr_req_addr_pl <= s_axi_araddr;
                            csr_req_tog_pl  <= ~csr_req_tog_pl;
                            axil_tmo        <= 11'd0;
                            axil_state      <= 2'd2;
                        end
                    end
                end
                2'd1: begin // Wait write ack or watchdog timeout (if rx_clkdiv stopped)
                    if (csr_ack_sync_pl[2] ^ csr_ack_sync_pl[1]) begin
                        s_axi_bresp  <= csr_rsp_resp_rx;
                        s_axi_bvalid <= 1'b1;
                        axil_state   <= 2'd0;
                    end else if (axil_tmo == 11'd1023) begin
                        s_axi_bresp  <= 2'b10;
                        s_axi_bvalid <= 1'b1;
                        axil_state   <= 2'd0;
                    end else begin
                        axil_tmo <= axil_tmo + 11'd1;
                    end
                end
                2'd2: begin // Wait read ack or watchdog timeout
                    if (csr_ack_sync_pl[2] ^ csr_ack_sync_pl[1]) begin
                        s_axi_rdata  <= csr_rsp_rdata_rx;
                        s_axi_rresp  <= csr_rsp_resp_rx;
                        s_axi_rvalid <= 1'b1;
                        axil_state   <= 2'd0;
                    end else if (axil_tmo == 11'd1023) begin
                        s_axi_rdata  <= 32'hDEAD_C10C;
                        s_axi_rresp  <= 2'b10;
                        s_axi_rvalid <= 1'b1;
                        axil_state   <= 2'd0;
                    end else begin
                        axil_tmo <= axil_tmo + 11'd1;
                    end
                end
                default: axil_state <= 2'd0;
            endcase
        end
    end

    // -------------------------------------------------------------------------
    // 4. link_axis + Dual-Clock Stream Async FIFOs (rx_clkdiv <-> pl_clk_100m)
    // -------------------------------------------------------------------------
    (* ASYNC_REG = "TRUE" *) reg [1:0] pps_rx_sync;
    reg        pps_rx_prev;
    reg [63:0] ts_cnt_rx;
    always @(posedge rx_clkdiv) begin
        if (rst_rx) begin
            pps_rx_sync <= 2'b00;
            pps_rx_prev <= 1'b0;
            ts_cnt_rx   <= 64'd0;
        end else begin
            pps_rx_sync <= {pps_rx_sync[0], emio_gpio_o[2]};
            pps_rx_prev <= pps_rx_sync[1];
            if (pps_rx_sync[1] && !pps_rx_prev)
                ts_cnt_rx <= {ts_cnt_rx[63:32] + 32'd1, 32'd0};
            else
                ts_cnt_rx <= ts_cnt_rx + 64'd1;
        end
    end

    wire [63:0] la_rx_tdata;
    wire        la_rx_tvalid, la_rx_tlast;
    wire [7:0]  la_rx_tid;
    wire [0:0]  la_rx_tuser;
    wire        rx_afifo_full, rx_afifo_empty;
    wire [73:0] rx_afifo_rd;

    wire [88:0] tx_afifo_rd;
    wire        tx_afifo_full, tx_afifo_empty, la_tx_tready;

    wire        dl_pkt_valid, dl_pkt_sop, dl_pkt_eop;
    wire [7:0]  dl_pkt_sid;
    wire [15:0] dl_pkt_len;
    wire [31:0] dl_pkt_seq;
    wire [63:0] dl_pkt_data;
    wire        dl_fifo_full, dl_fifo_empty, dl_pkt_ready_tx;
    wire [129:0] dl_fifo_rd_data;

    wire [31:0] last_rx_seq, last_rx_len_unused;
    wire [63:0] last_rx_ts;

    link_axis #(.RX_FIFO_DEPTH(256), .TX_FIFO_DEPTH(128)) u_link_axis (
        .clk                  (rx_clkdiv),
        .rst                  (pcs_rst_rx),
        .m_axis_rx_tdata      (la_rx_tdata),
        .m_axis_rx_tvalid     (la_rx_tvalid),
        .m_axis_rx_tready     (!rx_afifo_full),
        .m_axis_rx_tlast      (la_rx_tlast),
        .m_axis_rx_tid        (la_rx_tid),
        .m_axis_rx_tuser      (la_rx_tuser),
        .s_axis_tx_tdata      (tx_afifo_rd[63:0]),
        .s_axis_tx_tvalid     (!tx_afifo_empty),
        .s_axis_tx_tready     (la_tx_tready),
        .s_axis_tx_tlast      (tx_afifo_rd[88]),
        .s_axis_tx_tid        (tx_afifo_rd[71:64]),
        .s_axis_tx_tuser      (tx_afifo_rd[87:72]),
        .s_axi_awaddr         (link_awaddr),
        .s_axi_awvalid        (link_awvalid),
        .s_axi_awready        (link_awready),
        .s_axi_wdata          (link_wdata),
        .s_axi_wstrb          (link_wstrb),
        .s_axi_wvalid         (link_wvalid),
        .s_axi_wready         (link_wready),
        .s_axi_bresp          (link_bresp),
        .s_axi_bvalid         (link_bvalid),
        .s_axi_bready         (1'b1),
        .s_axi_araddr         (link_araddr),
        .s_axi_arvalid        (link_arvalid),
        .s_axi_arready        (link_arready),
        .s_axi_rdata          (link_rdata),
        .s_axi_rresp          (link_rresp),
        .s_axi_rvalid         (link_rvalid),
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
        .last_rx_len          ()
    );

    kria_pl_async_fifo #(.DW(74), .AW(5)) u_fifo_rx2pl (
        .wr_clk   (rx_clkdiv),
        .wr_rst   (pcs_rst_rx),
        .wr_en    (la_rx_tvalid && !rx_afifo_full),
        .wr_data  ({la_rx_tlast, la_rx_tuser[0], la_rx_tid, la_rx_tdata}),
        .wr_full  (rx_afifo_full),
        .rd_clk   (pl_clk_100m),
        .rd_rst   (!pl_resetn),
        .rd_en    (m_axis_rx_tvalid && m_axis_rx_tready),
        .rd_data  (rx_afifo_rd),
        .rd_empty (rx_afifo_empty)
    );
    assign m_axis_rx_tvalid = !rx_afifo_empty;
    assign m_axis_rx_tlast  = rx_afifo_rd[73];
    assign m_axis_rx_tuser  = rx_afifo_rd[72:72];
    assign m_axis_rx_tid    = rx_afifo_rd[71:64];
    assign m_axis_rx_tdata  = rx_afifo_rd[63:0];
    assign m_axis_rx_tkeep  = 8'hFF;

    wire [7:0] tx_eff_sid = (s_axis_tx_tid != 8'd0) ? s_axis_tx_tid : tx_default_sid_r;
    kria_pl_async_fifo #(.DW(89), .AW(4)) u_fifo_pl2tx (
        .wr_clk   (pl_clk_100m),
        .wr_rst   (!pl_resetn),
        .wr_en    (s_axis_tx_tvalid && s_axis_tx_tready),
        .wr_data  ({s_axis_tx_tlast, s_axis_tx_tuser, tx_eff_sid, s_axis_tx_tdata}),
        .wr_full  (tx_afifo_full),
        .rd_clk   (rx_clkdiv),
        .rd_rst   (pcs_rst_rx),
        .rd_en    (!tx_afifo_empty && la_tx_tready),
        .rd_data  (tx_afifo_rd),
        .rd_empty (tx_afifo_empty)
    );
    assign s_axis_tx_tready = !tx_afifo_full;

    kria_pl_async_fifo #(.DW(130), .AW(4)) u_fifo_dl (
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
    // 5. Downlink LVDS TX (link_pcs_single_tx + PRBS7 + OSERDESE3 -> LINK_TX_*)
    // -------------------------------------------------------------------------
    (* ASYNC_REG = "TRUE" *) reg [1:0] prbs_tx_sync, link_up_tx_sync;
    reg [63:0] ts_cnt_tx;
    always @(posedge tx_clk_div) begin
        if (rst_tx) begin
            prbs_tx_sync    <= 2'b00;
            link_up_tx_sync <= 2'b00;
            ts_cnt_tx       <= 64'd0;
        end else begin
            prbs_tx_sync    <= {prbs_tx_sync[0], ctrl_prbs7_tx_en};
            link_up_tx_sync <= {link_up_tx_sync[0], kria_link_up};
            ts_cnt_tx       <= ts_cnt_tx + 64'd1;
        end
    end

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
        .DATA_WIDTH(8), .INIT(1'b0), .ODDR_MODE("FALSE"),
        .OSERDES_D_BYPASS("FALSE"), .OSERDES_T_BYPASS("FALSE"), .SIM_DEVICE("ULTRASCALE_PLUS")
    ) u_oserdes_tx_clk (
        .OQ(dl_ser_clk), .T_OUT(), .CLK(tx_clk_hs), .CLKDIV(tx_clk_div),
        .D(8'b10101010), .RST(rst_tx), .T(1'b0)
    );
    OSERDESE3 #(
        .DATA_WIDTH(8), .INIT(1'b0), .ODDR_MODE("FALSE"),
        .OSERDES_D_BYPASS("FALSE"), .OSERDES_T_BYPASS("FALSE"), .SIM_DEVICE("ULTRASCALE_PLUS")
    ) u_oserdes_tx_d0 (
        .OQ(dl_ser_d0), .T_OUT(), .CLK(tx_clk_hs), .CLKDIV(tx_clk_div),
        .D(dl_tx_byte_r), .RST(rst_tx), .T(1'b0)
    );

    OBUFDS u_obuf_tx_clk (.I(dl_ser_clk), .O(link_tx_clk_p), .OB(link_tx_clk_n));
    OBUFDS u_obuf_tx_d0  (.I(dl_ser_d0),  .O(link_tx_d0_p),  .OB(link_tx_d0_n));

    // -------------------------------------------------------------------------
    // 6. Bank 45 / Bank 66 Single-Ended IOs & EMIO Connections
    // -------------------------------------------------------------------------
    IOBUF u_iobuf_scl (.I(emio_i2c_scl_o), .O(emio_i2c_scl_i), .T(emio_i2c_scl_t), .IO(hk_scl));
    IOBUF u_iobuf_sda (.I(emio_i2c_sda_o), .O(emio_i2c_sda_i), .T(emio_i2c_sda_t), .IO(hk_sda));

    assign fpga_prog_b      = emio_gpio_t[0] ? 1'b1 : emio_gpio_o[0];
    assign pmod_cs_n        = emio_gpio_o[4] ? ~emio_gpio_t[4] : emio_spi_ssn;
    assign pmod_mosi        = emio_spi_mo;
    assign pmod_sclk        = emio_spi_sclk;
    assign emio_spi_mi      = pmod_miso;
    assign pmod_beam_strobe = emio_gpio_o[1];
    assign pmod_pps_sync    = emio_gpio_o[2];
    assign pmod_spare1      = emio_gpio_o[3];

    (* ASYNC_REG = "TRUE" *) reg [1:0] irq_sync, spare2_sync, linkup_pl_sync;
    always @(posedge pl_clk_100m) begin
        irq_sync       <= {irq_sync[0], fpga_irq};
        spare2_sync    <= {spare2_sync[0], pmod_spare2};
        linkup_pl_sync <= {linkup_pl_sync[0], kria_link_up};
    end

    assign irq_fpga    = irq_sync[1];
    assign irq_link_up = linkup_pl_sync[1];
    assign emio_gpio_i = {1'b0, linkup_pl_sync[1], spare2_sync[1], irq_sync[1], emio_gpio_o[3:0]};

endmodule
