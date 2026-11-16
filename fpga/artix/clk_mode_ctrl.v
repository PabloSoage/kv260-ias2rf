// SPDX-License-Identifier: Apache-2.0
// Clock Mode & Safe-Boot Sequencer (STARTUPE2 CFGMCLK domain) + Non-MMCM DAC Clock Divider
//
// Responsibilities:
//   1. Generates always-on internal CFGMCLK (~65 MHz +/-50% via STARTUPE2 + BUFG) and local POR,
//      independent of Y401 (Si549) and external clock (CLK_FPGA_P/N), so MMCMs can be held in
//      reset while Si549 is silent during its ~30 ms FCAL window.
//   2. On power-on reset (unknown Si549 startup frequency), holds both u_mmcm_sys and u_mmcm_eth in
//      reset, programs Si549 (0x55) to BOOT_FREQ_500M (default 500 MHz SDR; 0 = 400 MHz radar),
//      performs MMCME2_ADV DRP RMW on DADDR=7'h16 (DIVCLK_DIVIDE=5 for 500 MHz, 4 for 400 MHz)
//      while mmcm_rst=1 (XAPP888), then releases mmcm_rst and waits for MMCM LOCKED.
//   3. Supports runtime 400 <-> 500 MHz switching via CSR 0xA8 (XO_CTRL prog_start=1):
//      asserts mmcm_rst=1 -> reprograms Si549 -> updates DRP DIVCLK_DIVIDE -> releases mmcm_rst ->
//      waits LOCKED -> link_rst / sys_rst automatically restarts IAS1 link training.
//   4. Drives non-MMCM DAC clock (dac_clk = CLK_FPGA / 4 = 100 MHz @ 400M, 125 MHz @ 500M)
//      via a glitch-free 2-bit Johnson divider on fpga_clk_bufg -> BUFG (zero MMCM/PLL jitter).

`timescale 1ns/1ps

module clk_mode_ctrl #(
    parameter         BOOT_FREQ_500M     = 1'b1,       // 1 = 500 MHz (SDR), 0 = 400 MHz (Radar)
    parameter         ENABLE_ETH         = 1'b1,       // 1 = DRP-config u_mmcm_eth & clamp +/-50 ppm
    parameter [6:0]   SI549_ADDR         = 7'h55,
    parameter integer HK_CLK_DIV         = 250,        // ~65..97.5 kHz I2C @ CFGMCLK
    parameter integer XO_FCAL_WAIT_CYC   = 3_000_000   // >= 30.7 ms even at +50% CFGMCLK (97.5 MHz)
) (
    // Primary RF/FPGA clock (400 MHz radar or 500 MHz SDR) from IBUFDS -> BUFG
    input  wire        fpga_clk_bufg,

    // Always-on configuration clock + synchronous POR in cfgmclk domain
    output wire        cfgmclk,
    output reg         cfg_por_rst = 1'b1,

    // Non-MMCM DAC clock (100 MHz @ 400 MHz mode, 125 MHz @ 500 MHz mode) & reset
    output wire        dac_clk,
    output wire        dac_rst,

    // MMCM reset, lock status, and DRP interfaces (driven from cfgmclk while mmcm_rst=1)
    input  wire        sys_mmcm_locked,
    input  wire        eth_mmcm_locked,
    output reg         mmcm_rst = 1'b1,

    output reg  [6:0]  sys_daddr = 7'd0,
    output reg         sys_den   = 1'b0,
    output reg         sys_dwe   = 1'b0,
    output reg  [15:0] sys_di    = 16'd0,
    input  wire [15:0] sys_do,
    input  wire        sys_drdy,

    output reg  [6:0]  eth_daddr = 7'd0,
    output reg         eth_den   = 1'b0,
    output reg         eth_dwe   = 1'b0,
    output reg  [15:0] eth_di    = 16'd0,
    input  wire [15:0] eth_do,
    input  wire        eth_drdy,

    // link_clk domain CSR interface (CDC handled internally)
    input  wire        link_clk,
    input  wire        link_rst,
    input  wire        wr_xo_ctrl_p,     // 1-cycle pulse on 0xA8 write (prog_start=0 updates use_ext_clk)
    input  wire        wr_xo_prog_p,     // 1-cycle pulse on 0xA8 write with prog_start=1
    input  wire [1:0]  wr_xo_ctrl_bits,  // {prog_freq_500m, use_ext_clk}
    input  wire        delta_start_p,    // 1-cycle pulse on 0xA8 write with delta_start=1
    input  wire [23:0] delta_m_in,       // 0xAC ADPLL_DELTA_M
    input  wire        raw_req_p,        // 1-cycle pulse on 0xB0 write with trigger=1
    input  wire        raw_req_rw,
    input  wire [7:0]  raw_req_reg,
    input  wire [7:0]  raw_req_wdata,
    input  wire [6:0]  raw_req_dev,      // 0 = Si549; else another device on the XO bus (Rev08 G-2)

    output reg         raw_req_ready_link  = 1'b1,
    output reg         raw_resp_valid_link = 1'b0,
    output reg  [7:0]  raw_resp_rdata_link = 8'd0,
    output reg         raw_resp_err_link   = 1'b0,

    output wire        xo_busy_link,
    output wire        xo_prog_done_link,
    output wire        xo_active_500m_link,
    output wire        radar_dis_cfg,
    output wire        xo_ack_err_link,
    output wire        xo_boot_done_link,
    output wire        xo_boot_err_link,
    output wire        xo_delta_clamped_link,
    output wire        xo_use_ext_clk_link,
    output wire        xo_req_500m_link,
    output reg  [15:0] xo_ack_err_cnt_link = 16'd0,

    // Rev08 front-end control (fe_ctrl): FE_CMD write and status, link clock side
    input  wire        fe_cmd_p,
    input  wire [31:0] fe_cmd_word,
    output wire        fe_busy_link,
    output wire [31:0] fe_stat_link,
    output wire [15:0] fe_rffc_link,

    // External Si549 + CLK_SEL open-drain pins
    output wire        clk_sel_t,
    output wire        xo_scl_t,
    input  wire        xo_scl_in,
    output wire        xo_sda_t,
    input  wire        xo_sda_in
);

    // MMCME2_ADV DRP DivReg (DADDR = 7'h16):
    //   [15:14] = reserved (preserve from read)
    //   [13]    = EDGE
    //   [12]    = NOCOUNT
    //   [11:6]  = HIGH TIME
    //   [5:0]   = LOW TIME
    // DIVCLK_DIVIDE = 4 (400 MHz / 4 = 100 MHz PFD): EDGE=0, NOCOUNT=0, HT=2, LT=2 -> 14'h0082
    // DIVCLK_DIVIDE = 5 (500 MHz / 5 = 100 MHz PFD): EDGE=1, NOCOUNT=0, HT=2, LT=3 -> 14'h2083
    localparam [13:0] DRP_DIVCLK_4 = 14'h0082;
    localparam [13:0] DRP_DIVCLK_5 = 14'h2083;
    localparam [31:0] BOOT_TMO_CYC = (XO_FCAL_WAIT_CYC * 2) + (HK_CLK_DIV * 16384);

    // -------------------------------------------------------------------------
    // 1. Always-On CFGMCLK via STARTUPE2 + BUFG & Local Power-On Reset
    // -------------------------------------------------------------------------
    wire cfgmclk_raw;
    STARTUPE2 #(
        .PROG_USR      ("FALSE"),
        .SIM_CCLK_FREQ (0.0)
    ) u_startupe2 (
        .CFGCLK    (),
        .CFGMCLK   (cfgmclk_raw),
        .EOS       (),
        .PREQ      (),
        .CLK       (1'b0),
        .GSR       (1'b0),
        .GTS       (1'b0),
        .KEYCLEARB (1'b1),
        .PACK      (1'b0),
        .USRCCLKO  (1'b0),
        .USRCCLKTS (1'b1),
        .USRDONEO  (1'b1),
        .USRDONETS (1'b1)
    );
    BUFG u_bufg_cfgmclk (.I(cfgmclk_raw), .O(cfgmclk));

    reg [3:0] cfg_por_cnt = 4'd0;
    always @(posedge cfgmclk) begin
        if (cfg_por_cnt != 4'hF) begin
            cfg_por_cnt <= cfg_por_cnt + 4'd1;
            cfg_por_rst <= 1'b1;
        end else begin
            cfg_por_rst <= 1'b0;
        end
    end

    // -------------------------------------------------------------------------
    // 2. Non-MMCM DAC Clock Divider (CLK_FPGA / 4 -> 100 or 125 MHz via BUFG)
    //    Glitch-free 2-bit Gray/Johnson ring -> 50% duty cycle, zero MMCM jitter
    // -------------------------------------------------------------------------
    reg [1:0] dac_div_q = 2'b00;
    always @(posedge fpga_clk_bufg)
        dac_div_q <= {dac_div_q[0], ~dac_div_q[1]};

    BUFG u_bufg_dac_clk (.I(dac_div_q[1]), .O(dac_clk));

    wire dac_rst_src = mmcm_rst | ~sys_mmcm_locked;
    (* ASYNC_REG = "TRUE" *) reg [3:0] dac_rst_sync = 4'b1111;
    always @(posedge dac_clk or posedge dac_rst_src) begin
        if (dac_rst_src)
            dac_rst_sync <= 4'b1111;
        else
            dac_rst_sync <= {dac_rst_sync[2:0], 1'b0};
    end
    assign dac_rst = dac_rst_sync[3];

    // -------------------------------------------------------------------------
    // 3. link_clk -> cfgmclk Request Bridges (reset-safe toggle handshakes)
    // -------------------------------------------------------------------------
    reg        req_cfg_tog_link   = 1'b0;
    reg [1:0]  req_ctrl_lat_link  = {BOOT_FREQ_500M, 1'b0};
    reg        req_prog_tog_link  = 1'b0;
    reg [1:0]  req_prog_lat_link  = {BOOT_FREQ_500M, 1'b0};
    reg        req_delta_tog_link = 1'b0;
    reg [23:0] req_delta_lat_link = 24'd0;
    reg        req_raw_tog_link   = 1'b0;
    reg        req_raw_rw_link    = 1'b0;
    reg [7:0]  req_raw_reg_link   = 8'd0;
    reg [7:0]  req_raw_wdata_link = 8'd0;
    reg [6:0]  req_raw_dev_link   = 7'd0;

    always @(posedge link_clk) begin
        if (link_rst) begin
            req_cfg_tog_link   <= 1'b0;
            req_prog_tog_link  <= 1'b0;
            req_delta_tog_link <= 1'b0;
            req_raw_tog_link   <= 1'b0;
        end else begin
            if (wr_xo_ctrl_p && !wr_xo_prog_p) begin
                req_ctrl_lat_link <= wr_xo_ctrl_bits;
                req_cfg_tog_link  <= ~req_cfg_tog_link;
            end
            if (wr_xo_prog_p) begin
                req_prog_lat_link <= wr_xo_ctrl_bits;
                req_prog_tog_link <= ~req_prog_tog_link;
            end
            if (delta_start_p) begin
                req_delta_lat_link <= delta_m_in;
                req_delta_tog_link <= ~req_delta_tog_link;
            end
            if (raw_req_p) begin
                req_raw_rw_link    <= raw_req_rw;
                req_raw_reg_link   <= raw_req_reg;
                req_raw_wdata_link <= raw_req_wdata;
                req_raw_dev_link   <= raw_req_dev;
                req_raw_tog_link   <= ~req_raw_tog_link;
            end
        end
    end

    (* ASYNC_REG = "TRUE" *) reg [2:0] link_rst_cfg_s   = 3'b111;
    (* ASYNC_REG = "TRUE" *) reg [2:0] req_cfg_tog_s    = 3'd0;
    (* ASYNC_REG = "TRUE" *) reg [2:0] req_prog_tog_s   = 3'd0;
    (* ASYNC_REG = "TRUE" *) reg [2:0] req_delta_tog_s  = 3'd0;
    (* ASYNC_REG = "TRUE" *) reg [2:0] req_raw_tog_s    = 3'd0;
    (* ASYNC_REG = "TRUE" *) reg [1:0] sys_locked_s     = 2'd0;
    (* ASYNC_REG = "TRUE" *) reg [1:0] eth_locked_s     = 2'd0;

    always @(posedge cfgmclk) begin
        if (cfg_por_rst) begin
            link_rst_cfg_s  <= 3'b111;
            req_cfg_tog_s   <= 3'd0;
            req_prog_tog_s  <= 3'd0;
            req_delta_tog_s <= 3'd0;
            req_raw_tog_s   <= 3'd0;
            sys_locked_s    <= 2'd0;
            eth_locked_s    <= 2'd0;
        end else begin
            link_rst_cfg_s  <= {link_rst_cfg_s[1:0], link_rst};
            req_cfg_tog_s   <= {req_cfg_tog_s[1:0],   req_cfg_tog_link};
            req_prog_tog_s  <= {req_prog_tog_s[1:0],  req_prog_tog_link};
            req_delta_tog_s <= {req_delta_tog_s[1:0], req_delta_tog_link};
            req_raw_tog_s   <= {req_raw_tog_s[1:0],   req_raw_tog_link};
            sys_locked_s    <= {sys_locked_s[0],      sys_mmcm_locked};
            eth_locked_s    <= {eth_locked_s[0],      eth_mmcm_locked};
        end
    end

    wire link_active_cfg = sys_locked_s[1] && (!ENABLE_ETH || eth_locked_s[1]) && !link_rst_cfg_s[1];
    wire req_cfg_edge    = link_active_cfg && (req_cfg_tog_s[2]   ^ req_cfg_tog_s[1]);
    wire req_prog_edge   = link_active_cfg && (req_prog_tog_s[2]  ^ req_prog_tog_s[1]);
    wire req_delta_edge  = link_active_cfg && (req_delta_tog_s[2] ^ req_delta_tog_s[1]);
    wire req_raw_edge    = link_active_cfg && (req_raw_tog_s[2]   ^ req_raw_tog_s[1]);

    // -------------------------------------------------------------------------
    // 4. Si549 I2C Controller in Always-On CFGMCLK Domain
    // -------------------------------------------------------------------------
    reg        xo_use_ext_clk_cfg = 1'b0;
    reg        xo_req_500m_cfg    = BOOT_FREQ_500M;
    reg        xo_prog_start_cfg  = 1'b0;
    reg        xo_prog_500m_cfg   = BOOT_FREQ_500M;
    reg        xo_delta_start_cfg = 1'b0;
    reg [23:0] xo_delta_m_cfg     = 24'd0;
    reg        xo_raw_valid_cfg   = 1'b0;
    reg        xo_raw_rw_cfg      = 1'b0;
    reg [7:0]  xo_raw_reg_cfg     = 8'd0;
    reg [7:0]  xo_raw_wdata_cfg   = 8'd0;
    reg [6:0]  xo_raw_dev_cfg     = 7'd0;
    wire        fe_g_valid, fe_g_ready, fe_g_rvalid, fe_g_rerr;
    wire [6:0]  fe_g_dev;
    wire [2:0]  fe_g_wl;
    wire [31:0] fe_g_wd;
    wire [1:0]  fe_g_rl;
    wire [15:0] fe_g_rd;

    wire       xo_raw_ready_cfg;
    wire       xo_raw_resp_valid_cfg, xo_raw_resp_err_cfg;
    wire [7:0] xo_raw_resp_rdata_cfg;
    wire       xo_i2c_busy, xo_i2c_prog_done, xo_i2c_active_500m, xo_i2c_ack_err;
    wire       xo_i2c_delta_clamped;
    wire [15:0] xo_i2c_ack_err_cnt;

    hk_xo_ctrl #(
        .SI549_ADDR         (SI549_ADDR),
        .CLK_DIV            (HK_CLK_DIV),
        .FCAL_WAIT_CYC      (XO_FCAL_WAIT_CYC),
        .ENABLE_DELTA_CLAMP (ENABLE_ETH)
    ) u_hk_xo (
        .clk              (cfgmclk),
        .rst              (cfg_por_rst),
        .use_ext_clk      (xo_use_ext_clk_cfg),
        .clk_sel_t        (clk_sel_t),
        .prog_start       (xo_prog_start_cfg),
        .prog_freq_500m   (xo_prog_500m_cfg),
        .delta_start      (xo_delta_start_cfg),
        .delta_m          (xo_delta_m_cfg),
        .raw_req_valid    (xo_raw_valid_cfg),
        .raw_req_ready    (xo_raw_ready_cfg),
        .raw_req_rw       (xo_raw_rw_cfg),
        .raw_req_reg      (xo_raw_reg_cfg),
        .raw_req_wdata    (xo_raw_wdata_cfg),
        .raw_req_dev      (xo_raw_dev_cfg),
        .gen_req_valid    (fe_g_valid),
        .gen_req_ready    (fe_g_ready),
        .gen_req_dev      (fe_g_dev),
        .gen_req_wr_len   (fe_g_wl),
        .gen_req_wdata    (fe_g_wd),
        .gen_req_rd_len   (fe_g_rl),
        .gen_resp_valid   (fe_g_rvalid),
        .gen_resp_rdata   (fe_g_rd),
        .gen_resp_err     (fe_g_rerr),
        .raw_resp_valid   (xo_raw_resp_valid_cfg),
        .raw_resp_rdata   (xo_raw_resp_rdata_cfg),
        .raw_resp_err     (xo_raw_resp_err_cfg),
        .busy             (xo_i2c_busy),
        .prog_done        (xo_i2c_prog_done),
        .active_freq_500m (xo_i2c_active_500m),
        .ack_err          (xo_i2c_ack_err),
        .ack_err_cnt      (xo_i2c_ack_err_cnt),
        .delta_clamped    (xo_i2c_delta_clamped),
        .xo_scl_t         (xo_scl_t),
        .xo_scl_in        (xo_scl_in),
        .xo_sda_t         (xo_sda_t),
        .xo_sda_in        (xo_sda_in)
    );

    // Rev08 G-2/G-3/G-6: front-end expanders, RFFC5072 and PE4312 sequencer on hk_xo_ctrl's client port
    fe_ctrl u_fe_ctrl (
        .link_clk       (link_clk),
        .link_rst       (link_rst),
        .cmd_p          (fe_cmd_p),
        .cmd_word       (fe_cmd_word),
        .busy_link      (fe_busy_link),
        .stat_link      (fe_stat_link),
        .rffc_link      (fe_rffc_link),
        .clk            (cfgmclk),
        .rst            (cfg_por_rst),
        .gen_req_valid  (fe_g_valid),
        .gen_req_ready  (fe_g_ready),
        .gen_req_dev    (fe_g_dev),
        .gen_req_wr_len (fe_g_wl),
        .gen_req_wdata  (fe_g_wd),
        .gen_req_rd_len (fe_g_rl),
        .gen_resp_valid (fe_g_rvalid),
        .gen_resp_rdata (fe_g_rd),
        .gen_resp_err   (fe_g_rerr)
    );

    // -------------------------------------------------------------------------
    // 5. Safe-Boot & Runtime Mode-Switch + DRP RMW FSM (cfgmclk)
    // -------------------------------------------------------------------------
    localparam [3:0]
        ST_BOOT_START    = 4'd0,
        ST_XO_LAUNCH     = 4'd1,
        ST_XO_WAIT       = 4'd2,
        ST_DRP_SYS_RD    = 4'd3,
        ST_DRP_SYS_RD_W  = 4'd4,
        ST_DRP_SYS_WR_W  = 4'd5,
        ST_DRP_ETH_RD    = 4'd6,
        ST_DRP_ETH_RD_W  = 4'd7,
        ST_DRP_ETH_WR_W  = 4'd8,
        ST_MMCM_REL_WAIT = 4'd9,
        ST_MMCM_WAIT_LK  = 4'd10,
        ST_IDLE          = 4'd11;

    reg [3:0]  state         = ST_BOOT_START;
    reg [3:0]  wait_sub      = 4'd0;
    reg [31:0] tmo_cnt       = 32'd0;
    reg        is_boot_seq   = 1'b1;
    reg        seq_busy_cfg  = 1'b1;
    reg        boot_done_cfg = 1'b0;
    reg        boot_err_cfg  = 1'b0;
    reg        switch_done_cfg = 1'b0;
    reg        active_500m_cfg = BOOT_FREQ_500M;

    reg        raw_resp_tog_cfg   = 1'b0;
    reg [7:0]  raw_resp_rdata_cfg = 8'd0;
    reg        raw_resp_err_cfg   = 1'b0;

    wire [13:0] target_drp_div = xo_prog_500m_cfg ? DRP_DIVCLK_5 : DRP_DIVCLK_4;

    always @(posedge cfgmclk) begin
        if (cfg_por_rst) begin
            state              <= ST_BOOT_START;
            wait_sub           <= 4'd0;
            tmo_cnt            <= 32'd0;
            is_boot_seq        <= 1'b1;
            seq_busy_cfg       <= 1'b1;
            boot_done_cfg      <= 1'b0;
            boot_err_cfg       <= 1'b0;
            switch_done_cfg    <= 1'b0;
            active_500m_cfg    <= BOOT_FREQ_500M;
            mmcm_rst           <= 1'b1;
            xo_use_ext_clk_cfg <= 1'b0;
            xo_req_500m_cfg    <= BOOT_FREQ_500M;
            xo_prog_start_cfg  <= 1'b0;
            xo_prog_500m_cfg   <= BOOT_FREQ_500M;
            xo_delta_start_cfg <= 1'b0;
            xo_delta_m_cfg     <= 24'd0;
            xo_raw_valid_cfg   <= 1'b0;
            xo_raw_rw_cfg      <= 1'b0;
            xo_raw_reg_cfg     <= 8'd0;
            xo_raw_wdata_cfg   <= 8'd0;
            sys_den            <= 1'b0;
            sys_dwe            <= 1'b0;
            sys_daddr          <= 7'd0;
            sys_di             <= 16'd0;
            eth_den            <= 1'b0;
            eth_dwe            <= 1'b0;
            eth_daddr          <= 7'd0;
            eth_di             <= 16'd0;
            raw_resp_tog_cfg   <= 1'b0;
            raw_resp_rdata_cfg <= 8'd0;
            raw_resp_err_cfg   <= 1'b0;
        end else begin
            xo_prog_start_cfg  <= 1'b0;
            xo_delta_start_cfg <= 1'b0;
            xo_raw_valid_cfg   <= 1'b0;
            sys_den            <= 1'b0;
            sys_dwe            <= 1'b0;
            eth_den            <= 1'b0;
            eth_dwe            <= 1'b0;

            if (xo_raw_resp_valid_cfg) begin
                raw_resp_rdata_cfg <= xo_raw_resp_rdata_cfg;
                raw_resp_err_cfg   <= xo_raw_resp_err_cfg;
                raw_resp_tog_cfg   <= ~raw_resp_tog_cfg;
            end

            case (state)
                ST_BOOT_START: begin
                    mmcm_rst         <= 1'b1;
                    seq_busy_cfg     <= 1'b1;
                    is_boot_seq      <= 1'b1;
                    xo_prog_500m_cfg <= BOOT_FREQ_500M;
                    xo_req_500m_cfg  <= BOOT_FREQ_500M;
                    if (xo_raw_ready_cfg) begin
                        xo_prog_start_cfg <= 1'b1;
                        tmo_cnt           <= BOOT_TMO_CYC;
                        wait_sub          <= 4'd0;
                        state             <= ST_XO_LAUNCH;
                    end
                end

                ST_XO_LAUNCH: begin
                    // Wait 2 cycles for u_hk_xo.busy to assert
                    if (wait_sub == 4'd2)
                        state <= ST_XO_WAIT;
                    else
                        wait_sub <= wait_sub + 4'd1;
                end

                ST_XO_WAIT: begin
                    if (tmo_cnt != 32'd0)
                        tmo_cnt <= tmo_cnt - 32'd1;
                    if (!xo_i2c_busy || (tmo_cnt == 32'd0)) begin
                        if (is_boot_seq && (xo_i2c_ack_err || (tmo_cnt == 32'd0)))
                            boot_err_cfg <= 1'b1;
                        state <= ST_DRP_SYS_RD;
                    end
                end

                ST_DRP_SYS_RD: begin
                    sys_daddr <= 7'h16;
                    sys_den   <= 1'b1;
                    sys_dwe   <= 1'b0;
                    state     <= ST_DRP_SYS_RD_W;
                end

                ST_DRP_SYS_RD_W: begin
                    if (sys_drdy) begin
                        sys_daddr <= 7'h16;
                        sys_den   <= 1'b1;
                        sys_dwe   <= 1'b1;
                        sys_di    <= {sys_do[15:14], target_drp_div};
                        state     <= ST_DRP_SYS_WR_W;
                    end
                end

                ST_DRP_SYS_WR_W: begin
                    if (sys_drdy) begin
                        if (ENABLE_ETH)
                            state <= ST_DRP_ETH_RD;
                        else begin
                            wait_sub <= 4'd0;
                            state    <= ST_MMCM_REL_WAIT;
                        end
                    end
                end

                ST_DRP_ETH_RD: begin
                    eth_daddr <= 7'h16;
                    eth_den   <= 1'b1;
                    eth_dwe   <= 1'b0;
                    state     <= ST_DRP_ETH_RD_W;
                end

                ST_DRP_ETH_RD_W: begin
                    if (eth_drdy) begin
                        eth_daddr <= 7'h16;
                        eth_den   <= 1'b1;
                        eth_dwe   <= 1'b1;
                        eth_di    <= {eth_do[15:14], target_drp_div};
                        state     <= ST_DRP_ETH_WR_W;
                    end
                end

                ST_DRP_ETH_WR_W: begin
                    if (eth_drdy) begin
                        wait_sub <= 4'd0;
                        state    <= ST_MMCM_REL_WAIT;
                    end
                end

                ST_MMCM_REL_WAIT: begin
                    if (wait_sub == 4'd4) begin
                        mmcm_rst <= 1'b0;
                        state    <= ST_MMCM_WAIT_LK;
                    end else begin
                        wait_sub <= wait_sub + 4'd1;
                    end
                end

                ST_MMCM_WAIT_LK: begin
                    if (sys_locked_s[1] && (!ENABLE_ETH || eth_locked_s[1])) begin
                        active_500m_cfg <= xo_prog_500m_cfg;
                        boot_done_cfg   <= 1'b1;
                        switch_done_cfg <= 1'b1;
                        seq_busy_cfg    <= 1'b0;
                        is_boot_seq     <= 1'b0;
                        state           <= ST_IDLE;
                    end
                end

                ST_IDLE: begin
                    if (req_cfg_edge) begin
                        xo_use_ext_clk_cfg <= req_ctrl_lat_link[0];
                        xo_req_500m_cfg    <= req_ctrl_lat_link[1];
                    end
                    if (req_prog_edge) begin
                        mmcm_rst           <= 1'b1;
                        seq_busy_cfg       <= 1'b1;
                        switch_done_cfg    <= 1'b0;
                        is_boot_seq        <= 1'b0;
                        xo_use_ext_clk_cfg <= req_prog_lat_link[0];
                        xo_req_500m_cfg    <= req_prog_lat_link[1];
                        xo_prog_500m_cfg   <= req_prog_lat_link[1];
                        xo_prog_start_cfg  <= 1'b1;
                        tmo_cnt            <= BOOT_TMO_CYC;
                        wait_sub           <= 4'd0;
                        state              <= ST_XO_LAUNCH;
                    end else if (req_delta_edge && xo_raw_ready_cfg) begin
                        xo_delta_m_cfg     <= req_delta_lat_link;
                        xo_delta_start_cfg <= 1'b1;
                    end else if (req_raw_edge && xo_raw_ready_cfg) begin
                        xo_raw_rw_cfg    <= req_raw_rw_link;
                        xo_raw_reg_cfg   <= req_raw_reg_link;
                        xo_raw_wdata_cfg <= req_raw_wdata_link;
                        xo_raw_dev_cfg   <= req_raw_dev_link;
                        xo_raw_valid_cfg <= 1'b1;
                    end
                end

                default: state <= ST_IDLE;
            endcase
        end
    end

    // -------------------------------------------------------------------------
    // 6. cfgmclk -> link_clk Status & Raw-I2C Response Sync
    // -------------------------------------------------------------------------
    wire busy_cfg     = seq_busy_cfg || xo_i2c_busy;
    wire prog_done_cfg = switch_done_cfg && (!is_boot_seq ? xo_i2c_prog_done : boot_done_cfg);

    (* ASYNC_REG = "TRUE" *) reg [1:0] busy_s         = 2'b11;
    (* ASYNC_REG = "TRUE" *) reg [1:0] prog_done_s    = 2'd0;
    (* ASYNC_REG = "TRUE" *) reg [1:0] active_500m_s  = {2{BOOT_FREQ_500M}};
    (* ASYNC_REG = "TRUE" *) reg [1:0] ack_err_s      = 2'd0;
    (* ASYNC_REG = "TRUE" *) reg [1:0] boot_done_s    = 2'd0;
    (* ASYNC_REG = "TRUE" *) reg [1:0] boot_err_s     = 2'd0;
    (* ASYNC_REG = "TRUE" *) reg [1:0] clamped_s      = 2'd0;
    (* ASYNC_REG = "TRUE" *) reg [1:0] use_ext_s      = 2'd0;
    (* ASYNC_REG = "TRUE" *) reg [1:0] req_500m_s     = {2{BOOT_FREQ_500M}};
    (* ASYNC_REG = "TRUE" *) reg [1:0] raw_ready_s    = 2'd0;
    (* ASYNC_REG = "TRUE" *) reg [2:0] raw_resp_tog_s = 3'd0;
    reg [1:0]  raw_resp_blank_cnt = 2'd3;
    reg [15:0] ack_err_cnt_sync1 = 16'd0;

    always @(posedge link_clk) begin
        if (link_rst) begin
            busy_s              <= 2'b11;
            prog_done_s         <= 2'd0;
            active_500m_s       <= {2{BOOT_FREQ_500M}};
            ack_err_s           <= 2'd0;
            boot_done_s         <= 2'd0;
            boot_err_s          <= 2'd0;
            clamped_s           <= 2'd0;
            use_ext_s           <= 2'd0;
            req_500m_s          <= {2{BOOT_FREQ_500M}};
            raw_ready_s         <= 2'd0;
            raw_resp_tog_s      <= {raw_resp_tog_s[1:0], raw_resp_tog_cfg};
            raw_resp_blank_cnt  <= 2'd3;
            raw_req_ready_link  <= 1'b0;
            raw_resp_valid_link <= 1'b0;
            raw_resp_rdata_link <= 8'd0;
            raw_resp_err_link   <= 1'b0;
            ack_err_cnt_sync1   <= 16'd0;
            xo_ack_err_cnt_link <= 16'd0;
        end else begin
            busy_s         <= {busy_s[0],         busy_cfg};
            prog_done_s    <= {prog_done_s[0],    prog_done_cfg};
            active_500m_s  <= {active_500m_s[0],  active_500m_cfg};
            ack_err_s      <= {ack_err_s[0],      xo_i2c_ack_err};
            boot_done_s    <= {boot_done_s[0],    boot_done_cfg};
            boot_err_s     <= {boot_err_s[0],     boot_err_cfg};
            clamped_s      <= {clamped_s[0],      xo_i2c_delta_clamped};
            use_ext_s      <= {use_ext_s[0],      xo_use_ext_clk_cfg};
            req_500m_s     <= {req_500m_s[0],     xo_req_500m_cfg};
            raw_ready_s    <= {raw_ready_s[0],    xo_raw_ready_cfg};
            raw_resp_tog_s <= {raw_resp_tog_s[1:0], raw_resp_tog_cfg};
            if (raw_resp_blank_cnt != 2'd0)
                raw_resp_blank_cnt <= raw_resp_blank_cnt - 2'd1;

            raw_req_ready_link <= raw_ready_s[1] && !busy_s[1];

            raw_resp_valid_link <= 1'b0;
            if ((raw_resp_blank_cnt == 2'd0) && (raw_resp_tog_s[2] ^ raw_resp_tog_s[1])) begin
                raw_resp_valid_link <= 1'b1;
                raw_resp_rdata_link <= raw_resp_rdata_cfg;
                raw_resp_err_link   <= raw_resp_err_cfg;
            end

            ack_err_cnt_sync1   <= xo_i2c_ack_err_cnt;
            xo_ack_err_cnt_link <= ack_err_cnt_sync1;
        end
    end

    assign xo_busy_link          = busy_s[1];
    assign xo_prog_done_link     = prog_done_s[1];
    assign xo_active_500m_link   = active_500m_s[1];
    assign radar_dis_cfg         = seq_busy_cfg | active_500m_cfg;
    assign xo_ack_err_link       = ack_err_s[1];
    assign xo_boot_done_link     = boot_done_s[1];
    assign xo_boot_err_link      = boot_err_s[1];
    assign xo_delta_clamped_link = clamped_s[1];
    assign xo_use_ext_clk_link   = use_ext_s[1];
    assign xo_req_500m_link      = req_500m_s[1];

endmodule
`default_nettype wire
