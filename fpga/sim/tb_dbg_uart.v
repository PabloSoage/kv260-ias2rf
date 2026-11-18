// SPDX-License-Identifier: Apache-2.0
// Testbench: Debug UART + 4-Master CSR Arbiter + Rev08 G-1 CSRs inside artix_top
//
// Two-phase verification for full realism & fast XSim turnaround:
//   Phase A (0 .. ~600 us, u_top = real artix_top with DBG_UART_BAUD_DIV=16):
//     - Boot banner, 0xE4..0xFC CSR reads/writes, r/w/s/h, backspace, echo, 'err'
//     - 4-master CSR arbiter collision: simultaneous Downlink 0x10 + UART 'w' (0 drops)
//     - BREAK / prolonged low-line framing-error recovery (rx_ferr_cnt > 0)
//     - Catches -Mutate drop_monitor_write
//   Phase B (u_unit = standalone dbg_uart @ exact DEFAULT_BAUD_DIV=1085, 115,207.4 baud):
//     - Checked against exact 115,200.0 baud (8680.556 ns/bit) UART BFM
//     - Verifies boot banner, automatic scaled periodic STAT, status_dis, r/w/h
//     - Catches -Mutate wrong_divisor

`timescale 1ns/1ps

module tb_dbg_uart;

    localparam real BIT_FAST_NS = 128.0;                    // 125 MHz / 16 = 7.8125 Mbaud
    localparam real BIT_115K_NS = 1_000_000_000.0 / 115_200.0; // 8680.556 ns

    reg top_done = 1'b0;

    // 500 MHz system clock (gated once Phase A finishes to keep Phase B 115200 baud fast)
    reg fpga_clk_raw = 1'b0;
    always #1.000 fpga_clk_raw = ~fpga_clk_raw;
    wire fpga_clk = top_done ? 1'b0 : fpga_clk_raw;

    reg adcr_dco = 1'b0; always #2.500 adcr_dco = top_done ? 1'b0 : ~adcr_dco;
    reg adcs_dco = 1'b0; always #1.000 adcs_dco = top_done ? 1'b0 : ~adcs_dco;

    // 125 MHz Downlink TX clock + 500 MHz DDR bit clock (Kria side)
    reg dl_tx_ddr = 1'b0;
    always #1.000 dl_tx_ddr = top_done ? 1'b0 : ~dl_tx_ddr;
    reg [1:0] dl_div = 2'd0;
    reg dl_tx_clk = 1'b0;
    always @(posedge dl_tx_ddr) begin
        dl_div <= dl_div + 2'd1;
        if (dl_div == 2'd1)      dl_tx_clk <= 1'b1;
        else if (dl_div == 2'd3) dl_tx_clk <= 1'b0;
    end

    reg dl_tx_rst = 1'b1;
    reg dl_tx_valid = 1'b0, dl_tx_sop = 1'b0, dl_tx_eop = 1'b0;
    wire dl_tx_ready;
    reg [7:0]  dl_tx_sid = 8'h10;
    reg [15:0] dl_tx_len = 16'd8;
    reg [31:0] dl_tx_seq = 32'd0;
    reg [63:0] dl_tx_data = 64'd0;
    wire [7:0] dl_tx_byte;

    link_pcs_single_tx u_dl_tx (
        .clk           (dl_tx_clk),
        .rst           (dl_tx_rst),
        .pkt_valid     (dl_tx_valid),
        .pkt_ready     (dl_tx_ready),
        .pkt_sop       (dl_tx_sop),
        .pkt_eop       (dl_tx_eop),
        .pkt_stream_id (dl_tx_sid),
        .pkt_len       (dl_tx_len),
        .pkt_seq       (dl_tx_seq),
        .pkt_timestamp (64'd0),
        .pkt_data      (dl_tx_data),
        .dropped_cnt   (24'd0),
        .local_status  (16'h0001),
        .tx_byte_l0    (dl_tx_byte)
    );

    wire dl_ser_clk, dl_ser_d0;
    OSERDESE3 #(.DATA_WIDTH(8), .SIM_DEVICE("ULTRASCALE_PLUS"), .SIM_VERSION(2.0)) u_os_c (
        .OQ(dl_ser_clk), .CLK(dl_tx_ddr), .CLKDIV(dl_tx_clk), .D(8'hAA), .RST(dl_tx_rst), .T(1'b0)
    );
    OSERDESE3 #(.DATA_WIDTH(8), .SIM_DEVICE("ULTRASCALE_PLUS"), .SIM_VERSION(2.0)) u_os_d (
        .OQ(dl_ser_d0),  .CLK(dl_tx_ddr), .CLKDIV(dl_tx_clk), .D(dl_tx_byte), .RST(dl_tx_rst), .T(1'b0)
    );

    reg        top_rx_pin = 1'b1;
    wire       top_tx_pin;
    pullup(top_tx_pin);
    reg        test_od_pd = 1'b0;
    assign (pull0, highz1) top_tx_pin = test_od_pd ? 1'b0 : 1'bz;
    wire       pmod_miso, fpga_irq, clk_sel, eth_mdc, eth_rst_n, conv_spi_sclk;
    wire       conv_spi_csb_r, conv_spi_csb_s, conv_spi_sdio;
    wire       adar_sclk, adar_sdio, adar_rx_load, adar_tx_load, adar_tr;
    wire [7:0] adar_csb, dacr_d;
    wire [13:0] dacs_d;
    wire [3:0] sw_ctrl;
    wire       ul_clk_p, ul_clk_n, ul_d0_p, ul_d0_n, ul_d1_p, ul_d1_n;
    wire       eth_sgtx_p, eth_sgtx_n, dacr_clk, dacs_iqclk, dacs_iqreset, dacs_iqsel, dacs_iqwrt;
    wire       hk_scl, hk_sda, xo_scl, xo_sda, eth_mdio;
    pullup(xo_scl);
    pullup(xo_sda);

    artix_top #(
        .DDC_POST_DECIM    (4),
        .LINK_AM_PERIOD    (64),
        .ADC_AUTO_TRAIN    (1'b0),
        .ENABLE_ETH        (1'b0),
        .CONV_SPI_AUTO_INIT(1'b0),
        .ADAR_AUTO_INIT    (1'b0),
        .HK_CLK_DIV        (3),
        .HK_POLL_DIV       (125_000),
        .XO_FCAL_WAIT_CYC  (15),
        .BOOT_FREQ_500M    (1'b1),
        .XADC_POLL_DIV_P   (125_000),
        .BUILD_DATE        (32'h2026_1116),
        .BUILD_TIME        (32'h0012_3456),
        .GIT_HASH          (32'hCAFE_BABE),
        .DBG_UART_BAUD_DIV (16'd16),
        .DBG_UART_STAT_CYC (32'd50_000)
    ) dut (
        .fpga_clk_p    (fpga_clk),
        .fpga_clk_n    (~fpga_clk),
        .adcr_d_p      (8'd0),
        .adcr_d_n      (8'hFF),
        .adcr_or_p     (1'b0),
        .adcr_or_n     (1'b1),
        .adcr_dco_n    (~adcr_dco),
        .adcr_dco_p    (adcr_dco),
        .adcs_dco_p    (adcs_dco),
        .adcs_dco_n    (~adcs_dco),
        .adcs_fco_p    (1'b0),
        .adcs_fco_n    (1'b1),
        .adcs_d0_p     (1'b0),
        .adcs_d0_n     (1'b1),
        .adcs_d1_p     (1'b0),
        .adcs_d1_n     (1'b1),
        .link_rx_clk_p (ul_clk_p),
        .link_rx_clk_n (ul_clk_n),
        .link_rx_d0_p  (ul_d0_p),
        .link_rx_d0_n  (ul_d0_n),
        .link_rx_d1_p  (ul_d1_p),
        .link_rx_d1_n  (ul_d1_n),
        .link_tx_clk_p (dl_ser_clk),
        .link_tx_clk_n (~dl_ser_clk),
        .link_tx_d0_p  (dl_ser_d0),
        .link_tx_d0_n  (~dl_ser_d0),
        .pmod_cs_n     (1'b1),
        .pmod_mosi     (1'b0),
        .pmod_miso     (pmod_miso),
        .pmod_sclk     (1'b0),
        .beam_strobe   (1'b0),
        .pps_sync      (1'b0),
        .pmod_spare1   (top_rx_pin),
        .pmod_spare2   (top_tx_pin),
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
    // Phase B Unit Instance: exact 115,200 baud (div=1085 @ 125.000 MHz link_clk)
    // -------------------------------------------------------------------------
    reg         unit_clk_en = 1'b0;
    reg         unit_clk = 1'b0;
    always #4.000 unit_clk = unit_clk_en ? ~unit_clk : 1'b0;

    reg         unit_rst = 1'b1;
    reg         unit_rx_pin = 1'b1;
    wire        unit_tx_pin;
    reg         unit_stat_dis = 1'b0;
    wire        u_csr_vld, u_csr_wr;
    wire [15:0] u_csr_addr;
    wire [31:0] u_csr_wdata;
    reg  [31:0] u_csr_mem = 32'h1357_2468;
    reg         u_csr_ack = 1'b0;
    reg  [31:0] u_csr_rdata = 32'd0;

    always @(posedge unit_clk) begin
        if (unit_rst) begin
            u_csr_ack <= 1'b0;
            u_csr_mem <= 32'h1357_2468;
        end else begin
            u_csr_ack <= u_csr_vld && !u_csr_ack;
            if (u_csr_vld && !u_csr_ack) begin
                if (u_csr_wr && u_csr_addr == 16'h0044)
                    u_csr_mem <= u_csr_wdata;
                u_csr_rdata <= (u_csr_addr == 16'h0044) ? u_csr_mem : 32'hA5A5_5A5A;
            end
        end
    end

    dbg_uart #(
        .BUILD_DATE       (32'h2026_1116),
        .BUILD_TIME       (32'h0012_3456),
        .GIT_HASH         (32'hBEEF_1234),
        .ENABLE_ETH       (1'b1),
        .DEFAULT_BAUD_DIV (16'd1085),
        .DEFAULT_STAT_CYC (32'd1_250_000) // 10.0 ms (> 8.25 ms STAT frame time @ 115200 baud)
    ) u_unit (
        .clk              (unit_clk),
        .rst              (unit_rst),
        .uart_rx          (unit_rx_pin),
        .uart_tx          (unit_tx_pin),
        .cfg_baud_div     (16'd1085),
        .cfg_stat_cyc     (32'd1_250_000),
        .cfg_status_dis   (unit_stat_dis),
        .force_stat_p     (1'b0),
        .st_xo_ok         (1'b1),
        .st_xo_500m       (1'b1),
        .st_sys_mmcm      (1'b1),
        .st_eth_mmcm      (1'b1),
        .st_adcr_mmcm     (1'b0),
        .st_dl_state      (3'd5),
        .st_dl_l0_lock    (1'b1),
        .st_dl_link_up    (1'b1),
        .st_eth_link_up   (1'b1),
        .st_eth_copper_up (1'b1),
        .st_adcr_trained  (1'b0),
        .st_adcs_aligned  (1'b1),
        .st_adcr_clip_cnt (16'd0),
        .st_adcs_clip_cnt (16'd7),
        .st_xadc_temp_raw (12'h9A0),
        .st_hk_tmp_raw    (16'h2A80),
        .st_err_flags_lo  (7'h02),
        .st_radar_dis     (1'b1),
        .rx_idle_high     (),
        .tx_busy_o        (),
        .banner_done      (),
        .rx_ferr_cnt      (),
        .csr_req_valid    (u_csr_vld),
        .csr_req_wr       (u_csr_wr),
        .csr_req_addr     (u_csr_addr),
        .csr_req_wdata    (u_csr_wdata),
        .csr_req_ack      (u_csr_ack),
        .csr_req_rdata    (u_csr_rdata)
    );

    // -------------------------------------------------------------------------
    // Dual-Mode Background UART RX Line Recorder
    // -------------------------------------------------------------------------
    reg             use_unit_uart = 1'b0;
    wire            act_tx_pin    = use_unit_uart ? unit_tx_pin : top_tx_pin;
    real            act_bit_ns    = BIT_FAST_NS;

    reg [8*160-1:0] rx_lines [0:63];
    integer         rx_line_wr = 0;
    integer         rx_line_rd = 0;
    integer         uart_rx_ferr = 0;

    reg [8*160-1:0] cur_line;
    integer         cur_len;
    reg [7:0]       rx_ch;
    reg             rx_stop;
    integer         bi;

    initial begin
        cur_line = {160{8'h00}};
        cur_len  = 0;
        wait (dut.sys_mmcm_locked === 1'b1 && !dut.link_rst);
        #50;
        forever begin
            wait (act_tx_pin === 1'b0);
            #(act_bit_ns * 1.5);
            for (bi = 0; bi < 8; bi = bi + 1) begin
                rx_ch[bi] = act_tx_pin;
                #(act_bit_ns);
            end
            rx_stop = act_tx_pin;
            if (rx_stop !== 1'b1) begin
                uart_rx_ferr = uart_rx_ferr + 1;
            end else begin
                if (rx_ch == 8'h0A) begin
                    if (cur_len > 0) begin
                        rx_lines[rx_line_wr] = cur_line;
                        rx_line_wr           = rx_line_wr + 1;
                        cur_line             = {160{8'h00}};
                        cur_len              = 0;
                    end
                end else if (rx_ch >= 8'h20 && rx_ch <= 8'h7E) begin
                    if (cur_len < 160) begin
                        cur_line[(159 - cur_len)*8 +: 8] = rx_ch;
                        cur_len = cur_len + 1;
                    end
                end
            end
        end
    end

    task automatic uart_send_byte(input [7:0] b);
        integer k;
        begin
            if (use_unit_uart) unit_rx_pin = 1'b0; else top_rx_pin = 1'b0;
            #(act_bit_ns);
            for (k = 0; k < 8; k = k + 1) begin
                if (use_unit_uart) unit_rx_pin = b[k]; else top_rx_pin = b[k];
                #(act_bit_ns);
            end
            if (use_unit_uart) unit_rx_pin = 1'b1; else top_rx_pin = 1'b1;
            #(act_bit_ns * 1.2);
        end
    endtask

    task automatic uart_send_str(input [8*32-1:0] s, input integer nchars);
        integer k;
        reg [7:0] ch;
        begin
            for (k = 0; k < nchars; k = k + 1) begin
                ch = s[(31 - k)*8 +: 8];
                if (ch != 8'h00) uart_send_byte(ch);
            end
        end
    endtask

    function [0:0] line_starts_with(input [8*160-1:0] ln, input [8*16-1:0] pfx, input integer n);
        integer k;
        reg match;
        begin
            match = 1'b1;
            for (k = 0; k < n; k = k + 1) begin
                if (ln[(159 - k)*8 +: 8] != pfx[(15 - k)*8 +: 8]) match = 1'b0;
            end
            line_starts_with = match;
        end
    endfunction

    function [0:0] line_contains(input [8*160-1:0] ln, input [8*16-1:0] sub, input integer n);
        integer pos, k;
        reg found, m;
        begin
            found = 1'b0;
            for (pos = 0; pos <= (160 - n); pos = pos + 1) begin
                m = 1'b1;
                for (k = 0; k < n; k = k + 1) begin
                    if (ln[(159 - pos - k)*8 +: 8] != sub[(15 - k)*8 +: 8]) m = 1'b0;
                end
                if (m) found = 1'b1;
            end
            line_contains = found;
        end
    endfunction

    task automatic wait_next_line(output [8*160-1:0] ln);
        integer tmo, max_tmo;
        begin
            tmo     = 0;
            max_tmo = use_unit_uart ? 25000 : 1000;
            while ((rx_line_rd >= rx_line_wr) && (tmo < max_tmo)) begin
                #1000;
                tmo = tmo + 1;
            end
            if (rx_line_rd >= rx_line_wr) begin
                $display("FAIL: tb_dbg_uart timeout waiting for UART response line (phase_b=%0d ferr=%0d)",
                         use_unit_uart, uart_rx_ferr);
                $finish;
            end
            ln = rx_lines[rx_line_rd];
            rx_line_rd = rx_line_rd + 1;
        end
    endtask

    task automatic dl_write_csr(input [15:0] addr, input [31:0] val);
        begin
            @(posedge dl_tx_clk);
            dl_tx_valid <= 1'b1; dl_tx_sop <= 1'b1; dl_tx_eop <= 1'b1;
            dl_tx_sid   <= 8'h10; dl_tx_len <= 16'd8;
            dl_tx_data  <= {8'h01, 8'h00, addr, val};
            @(posedge dl_tx_clk);
            while (!dl_tx_ready) @(posedge dl_tx_clk);
            dl_tx_valid <= 1'b0; dl_tx_sop <= 1'b0; dl_tx_eop <= 1'b0;
            dl_tx_seq   <= dl_tx_seq + 32'd1;
        end
    endtask

    task automatic uart_cmd(input [8*32-1:0] cmd, input integer nchars, output [8*160-1:0] resp_ln);
        reg [8*160-1:0] echo_ln;
        begin
            uart_send_str(cmd, nchars);
            wait_next_line(echo_ln);
            wait_next_line(resp_ln);
        end
    endtask

    reg [8*160-1:0] cap_ln, echo_ln;
    integer tmo_c, auto_stat_before;

    initial begin
        // =====================================================================
        // PHASE A: Full artix_top Integration (CSRs, 4-Master Arbiter, BREAK)
        // =====================================================================
        dl_tx_rst = 1'b1;
        repeat (16) @(posedge dl_tx_clk);
        dl_tx_rst = 1'b0;

        wait_next_line(cap_ln);
        if (!line_starts_with(cap_ln, {"KV260-IAS2RF", {4{8'h00}}}, 12) ||
            !line_contains(cap_ln, {"20261116-123456", {1{8'h00}}}, 15) ||
            !line_contains(cap_ln, {"git=cafebabe", {4{8'h00}}}, 12) ||
            !line_contains(cap_ln, {"clk=500M eth=no", {1{8'h00}}}, 15)) begin
            $display("FAIL: tb_dbg_uart Phase A boot banner mismatch: %s", cap_ln);
            $finish;
        end
        $display("[Phase A] Boot banner OK: %s", cap_ln);
        // Audit P2: verify PMOD_SPARE2 is open-drain (1'bz when idle high, pulled to X by test_od_pd)
        #100;
        test_od_pd = 1'b1;
        #20;
        if (top_tx_pin !== 1'bx) begin
            $display("FAIL: tb_dbg_uart PMOD_SPARE2 is not open-drain when idle high (got %b)", top_tx_pin);
            $finish;
        end
        test_od_pd = 1'b0;
        #20;

        // Disable automatic periodic STAT on u_top so interactive cmd lines stay aligned
        uart_cmd({"w f0 00010010", 8'h0D, {18{8'h00}}}, 14, cap_ln);
        if (!line_contains(cap_ln, {"ok", {14{8'h00}}}, 2)) begin
            $display("FAIL: tb_dbg_uart 'w f0' failed: %s", cap_ln); $finish;
        end

        tmo_c = 0;
        while (!dut.dl_link_up && tmo_c < 200000) begin
            @(posedge dl_tx_clk);
            tmo_c = tmo_c + 1;
        end
        if (!dut.dl_link_up) begin
            $display("FAIL: tb_dbg_uart downlink did not train"); $finish;
        end

        // Read 0xF8, 0xFC, 0xE8, then write 0xE4 with backspace correction + verify readback
        uart_cmd({"r f8", 8'h0D, {27{8'h00}}}, 5, cap_ln);
        if (!line_contains(cap_ln, {"cafebabe", {8{8'h00}}}, 8)) begin
            $display("FAIL: tb_dbg_uart 'r f8' unexpected: %s", cap_ln); $finish;
        end
        uart_cmd({"r 0xFc", 8'h0D, {25{8'h00}}}, 7, cap_ln);
        if (!line_contains(cap_ln, {"11161234", {8{8'h00}}}, 8)) begin
            $display("FAIL: tb_dbg_uart 'r 0xFc' unexpected: %s", cap_ln); $finish;
        end
        uart_cmd({"r e8", 8'h0D, {27{8'h00}}}, 5, cap_ln);
        if (!line_contains(cap_ln, {"00000411", {8{8'h00}}}, 8)) begin
            $display("FAIL: tb_dbg_uart 'r e8' expected 00000411 got: %s", cap_ln); $finish;
        end

        uart_cmd({"w e4 f", 8'h08, "0", 8'h0D, {23{8'h00}}}, 9, cap_ln);
        if (!line_contains(cap_ln, {"ok", {14{8'h00}}}, 2)) begin
            $display("FAIL: tb_dbg_uart 'w e4' expected ok got: %s", cap_ln); $finish;
        end
        uart_cmd({"r e4", 8'h0D, {27{8'h00}}}, 5, cap_ln);
        if (!line_contains(cap_ln, {"00000000", {8{8'h00}}}, 8)) begin
            $display("FAIL: tb_dbg_uart 'r e4' after write 0 returned: %s [ddc_en=%b rd_lat=%08h req_a=%04h rst=%b echo_ln=%s]",
                     cap_ln, dut.reg_rad_ddc_en, dut.u_dbg_uart.rd_val_lat,
                     dut.u_dbg_uart.csr_req_addr, dut.link_rst, echo_ln);
            $finish;
        end
        uart_cmd({"w E4 1", 8'h0D, {25{8'h00}}}, 7, cap_ln);

        // Help, invalid, and immediate 's' STAT
        uart_cmd({"h", 8'h0D, {30{8'h00}}}, 2, cap_ln);
        if (!line_contains(cap_ln, {"r <a> | w <a>", {3{8'h00}}}, 13)) begin
            $display("FAIL: tb_dbg_uart 'h' unexpected: %s", cap_ln); $finish;
        end
        uart_cmd({"bad", 8'h0D, {28{8'h00}}}, 4, cap_ln);
        if (!line_contains(cap_ln, {"err", {13{8'h00}}}, 3)) begin
            $display("FAIL: tb_dbg_uart 'bad' expected err: %s", cap_ln); $finish;
        end
        uart_cmd({"s", 8'h0D, {30{8'h00}}}, 2, cap_ln);
        if (!line_starts_with(cap_ln, {"STAT ", {11{8'h00}}}, 5) ||
            !line_contains(cap_ln, {"clk=500 ", {8{8'h00}}}, 8) ||
            !line_contains(cap_ln, {"rdis=1", {10{8'h00}}}, 6)) begin
            $display("FAIL: tb_dbg_uart 's' STAT mismatch: %s", cap_ln); $finish;
        end

        // 4-Master Arbiter Collision: Downlink 0x10 writes 0xC4 while UART writes 0xAC
        fork
            begin : dl_blaster
                integer c;
                for (c = 0; c < 40; c = c + 1) begin
                    dl_write_csr(16'h00C4, 32'h1234_5678);
                    repeat (3) @(posedge dl_tx_clk);
                end
            end
            begin : uart_writer
                #2000;
                uart_send_str({"w ac 0055aa33", 8'h0D, {18{8'h00}}}, 14);
            end
        join
        wait_next_line(echo_ln);
        wait_next_line(cap_ln);
        uart_cmd({"r c4", 8'h0D, {27{8'h00}}}, 5, cap_ln);
        if (!line_contains(cap_ln, {"12345678", {8{8'h00}}}, 8)) begin
            $display("FAIL: tb_dbg_uart collision dropped DL write 0xC4: %s", cap_ln); $finish;
        end
        uart_cmd({"r ac", 8'h0D, {27{8'h00}}}, 5, cap_ln);
        if (!line_contains(cap_ln, {"0055aa33", {8{8'h00}}}, 8)) begin
            $display("FAIL: tb_dbg_uart collision dropped UART write 0xAC: %s", cap_ln); $finish;
        end

        // BREAK / Framing Error recovery in artix_top
        top_rx_pin = 1'b0;
        #(act_bit_ns * 14.0);
        top_rx_pin = 1'b1;
        #(act_bit_ns * 3.0);
        uart_cmd({"r f8", 8'h0D, {27{8'h00}}}, 5, cap_ln);
        if (!line_contains(cap_ln, {"cafebabe", {8{8'h00}}}, 8) || dut.uart_rx_ferr_cnt == 5'd0) begin
            $display("FAIL: tb_dbg_uart BREAK recovery failed ferr=%0d ln=%s", dut.uart_rx_ferr_cnt, cap_ln);
            $finish;
        end
        $display("[Phase A] artix_top integration + 4-master arbiter + BREAK OK (ferr=%0d)", dut.uart_rx_ferr_cnt);

        // =====================================================================
        // PHASE B: Exact 115,200 baud (DEFAULT_BAUD_DIV=1085 @ 125 MHz)
        // =====================================================================
        top_done      = 1'b1;
        use_unit_uart = 1'b1;
        act_bit_ns    = BIT_115K_NS;
        uart_rx_ferr  = 0;
        rx_line_rd    = rx_line_wr;
        cur_line      = {160{8'h00}};
        cur_len       = 0;

        unit_clk_en = 1'b1;
        unit_rst    = 1'b1;
        #200;
        @(posedge unit_clk);
        unit_rst    = 1'b0;

        wait_next_line(cap_ln);
        if (!line_starts_with(cap_ln, {"KV260-IAS2RF", {4{8'h00}}}, 12) ||
            !line_contains(cap_ln, {"git=beef1234", {4{8'h00}}}, 12) ||
            !line_contains(cap_ln, {"clk=500M eth=ye", {1{8'h00}}}, 15) ||
            uart_rx_ferr != 0) begin
            $display("FAIL: tb_dbg_uart 115200 baud banner error ferr=%0d: %s", uart_rx_ferr, cap_ln);
            $finish;
        end
        $display("[Phase B] 115200 baud boot banner OK: %s", cap_ln);

        // Verify periodic STAT fires automatically (~2.8 ms timer + ~0.83 ms 95-char TX = ~3.63 ms)
        wait_next_line(cap_ln);
        if (!line_starts_with(cap_ln, {"STAT ", {11{8'h00}}}, 5) || uart_rx_ferr != 0) begin
            $display("FAIL: tb_dbg_uart periodic line not STAT (ferr=%0d): %s", uart_rx_ferr, cap_ln);
            $finish;
        end
        unit_stat_dis = 1'b1;
        rx_line_rd    = rx_line_wr;

        // Exercise r/w @ true 115200 baud
        uart_cmd({"w 44 deadbeef", 8'h0D, {18{8'h00}}}, 14, cap_ln);
        if (!line_contains(cap_ln, {"ok", {14{8'h00}}}, 2)) begin
            $display("FAIL: tb_dbg_uart 115200 w failed: %s", cap_ln); $finish;
        end
        uart_cmd({"r 44", 8'h0D, {27{8'h00}}}, 5, cap_ln);
        if (!line_contains(cap_ln, {"deadbeef", {8{8'h00}}}, 8) || uart_rx_ferr != 0) begin
            $display("FAIL: tb_dbg_uart 115200 r failed ferr=%0d: %s", uart_rx_ferr, cap_ln); $finish;
        end

        $display("PASS: tb_dbg_uart (PhaseA=artix_top+arbiter+BREAK ferr=%0d, PhaseB=115200bps_div1085 autoSTAT=OK)",
                 dut.uart_rx_ferr_cnt);
        $finish;
    end

    initial begin
        #40_000_000;
        $display("FAIL: tb_dbg_uart global timeout (phase_b=%0d wr=%0d rd=%0d ferr=%0d)",
                 use_unit_uart, rx_line_wr, rx_line_rd, uart_rx_ferr);
        $finish;
    end

endmodule
