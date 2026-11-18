// SPDX-License-Identifier: Apache-2.0
// Integrated Top-Level Verification Testbench for artix_top:
//   Tests Tasks 13-16 wired into artix_top over the live IAS1 2-lane Uplink + 1-lane Downlink:
//     - adcs_capture + conv_spi (3-wire AD9253/AD9484 SPI) + sdr_ddc (Streams 0x04/0x05)
//     - dac_radar (AD9708 ODDR LFM chirp) + dac_sdr (AD9767 via downlink Stream 0x12)
//     - 8x adar_ctrl SPI + beam table + TX/RX_LOAD + TR safety + rf_switch SW_CTRL[3:0]
//     - hk_i2c_master (TMP1075 0x48 + missing-ACK 0x7D), hk_xo_ctrl (Si549 0x55 + CLK_SEL),
//                hk_xadc_pps (XADC + PPS_SYNC 1251-cyc PPM)
//     - Register R/W protocol: Downlink Stream 0x10 -> Register Bank 0x34..0xE0 -> Uplink Stream 0x11
//
// Mutations checked via run.ps1 -Mutate:
//   - no_reg_resp : suppresses downlink register R/W response in artix_top -> readback timeout FAIL
//   - missing_ack : ignores I2C NACK in hk_i2c_master -> 0x7D probe fails to increment ack_err_cnt

`timescale 1ns/1ps

module tb_top_i2c_slave #(
    parameter [6:0] SLAVE_ADDR = 7'h50,
    parameter integer NUM_REGS = 256
) (
    input  wire       scl,
    inout  wire       sda,
    input  wire       enable_ack
);
    reg [7:0] mem [0:NUM_REGS-1];
    reg       sda_drv_low = 1'b0;
    assign sda = sda_drv_low ? 1'b0 : 1'bz;

    reg       prev_scl = 1'b1, prev_sda = 1'b1;
    reg [2:0] state = 3'd0;
    reg [3:0] bit_cnt = 4'd0;
    reg [7:0] shift_reg = 8'd0, reg_ptr = 8'd0;
    reg       have_reg_ptr = 1'b0, rw_bit = 1'b0, addr_match = 1'b0, ack_done = 1'b0;

    integer idx;
    initial begin
        for (idx = 0; idx < NUM_REGS; idx = idx + 1)
            mem[idx] = 8'h00;
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

module tb_artix_top;
    // -------------------------------------------------------------------------
    // Clocks
    // -------------------------------------------------------------------------
`ifdef FPGA_CLK_400M
    localparam [0:0] TB_BOOT_500M = 1'b0;
    real fpga_clk_half = 1.250; // 400 MHz
`else
    localparam [0:0] TB_BOOT_500M = 1'b1;
    real fpga_clk_half = 1.000; // 500 MHz
`endif
    reg fpga_clk_100m = 1'b0;
    initial forever #(fpga_clk_half) fpga_clk_100m = ~fpga_clk_100m;
    always @(*) begin
        if (u_si549.mem[23] == 8'h1C)      fpga_clk_half = 1.250;
        else if (u_si549.mem[23] == 8'h16) fpga_clk_half = 1.000;
    end
    reg adcr_clk_400m = 1'b0; always #1.250 adcr_clk_400m = ~adcr_clk_400m; // 400 MSPS AD9484
    reg adcs_dco_400m = 1'b0; initial forever #(fpga_clk_half) adcs_dco_400m = ~adcs_dco_400m; // 500M (62.5 MSPS) / 400M (50 MSPS) AD9253 DCO
    reg kria_ref_300m = 1'b0; always #1.666 kria_ref_300m = ~kria_ref_300m;
    reg kria_tx_ddr   = 1'b0; always #1.000 kria_tx_ddr   = ~kria_tx_ddr;

    reg dco_true = 1'b0;
    initial begin dco_true = 1'b0; #1.750; forever #2.500 dco_true = ~dco_true; end
    // Rev08 G-7: at 500 MHz the AD9484 runs from the master clock (500 MSPS, DCO = master / 2), as on the board
    wire tb_500 = (fpga_clk_half == 1.000);
    reg  dco_500 = 1'b0;
    always @(posedge fpga_clk_100m) dco_500 <= ~dco_500;
    wire dco_src = tb_500 ? dco_500 : dco_true;
    reg dco_board_del = 1'b0;
    always @(dco_src) dco_board_del <= #0.250 dco_src;

    reg [1:0] kria_tx_div = 2'b00;
    reg       kria_tx_clk = 1'b0;
    always @(posedge kria_tx_ddr) begin
        kria_tx_div <= kria_tx_div + 2'd1;
        if (kria_tx_div == 2'd1)      kria_tx_clk <= 1'b1;
        else if (kria_tx_div == 2'd3) kria_tx_clk <= 1'b0;
    end

    // AD9484 alternating 0xAA / 0x55 (matching tb_adc_ddc polarity & board delay) -> continuous stream 8'h01 traffic
    reg [7:0] adcr_samp = 8'h55;
    wire adcr_samp_clk = tb_500 ? fpga_clk_100m : adcr_clk_400m;
    always @(posedge adcr_samp_clk) adcr_samp <= (adcr_samp == 8'hAA) ? 8'h55 : 8'hAA;
    reg [7:0] adcr_d_del = 8'h55;
    always @(adcr_samp) adcr_d_del <= #0.200 adcr_samp;
    wire [7:0] adcr_d_p =  adcr_d_del;
    wire [7:0] adcr_d_n = ~adcr_d_del;

    // -------------------------------------------------------------------------
    // Physical Board Wires
    // -------------------------------------------------------------------------
    wire       ul_tx_clk_p, ul_tx_clk_n, ul_tx_d0_p, ul_tx_d0_n, ul_tx_d1_p, ul_tx_d1_n;
    wire       dl_rx_clk_p, dl_rx_clk_n, dl_rx_d0_p, dl_rx_d0_n;
    wire       pmod_miso, pmod_spare2, fpga_irq;
    reg        beam_strobe = 1'b0;
    reg        pps_sync    = 1'b0;

    wire       dacr_clk;
    wire [7:0] dacr_d;
    wire [13:0] dacs_d;
    wire       dacs_iqclk, dacs_iqreset, dacs_iqsel, dacs_iqwrt;
    wire [3:0] sw_ctrl;
    tri1       xo_scl, xo_sda, hk_scl, hk_sda;
    wire       clk_sel;

    wire       conv_spi_csb_r, conv_spi_csb_s, conv_spi_sclk;
    tri1       conv_spi_sdio;
    wire       adar_sclk, adar_sdo;
    tri1       adar_sdio;
    wire [7:0] adar_csb, adar_rx_load, adar_tx_load, adar_tr;
    wire       eth_sgtx_p, eth_sgtx_n, eth_mdc, eth_rst_n;
    tri1       eth_mdio;

    // AD9253 16-bit DDR Wordwise transmitter (50 MSPS, Ch A=6.25 MHz, Ch B=12.5 MHz)
    reg        fco_serial = 1'b0, d0_serial = 1'b0, d1_serial = 1'b0;
    reg        adcs_dco_quad = 1'b0;
    always @(adcs_dco_400m) adcs_dco_quad <= #(fpga_clk_half * 0.5) adcs_dco_400m;

    // Behavioral AD9253 & AD9484 3-wire SPI slaves
    reg [7:0]  ad9253_regs [0:255], ad9484_regs [0:255];
    reg [4:0]  cspi_bit;
    reg [23:0] cspi_cmd;
    reg [7:0]  cspi_addr, cspi_rshift;
    reg        cspi_rw, conv_sl_oe = 1'b0, conv_sl_out = 1'b0;
    assign conv_spi_sdio = conv_sl_oe ? conv_sl_out : 1'bz;

    integer ri;
    initial begin
        for (ri = 0; ri < 256; ri = ri + 1) begin
            ad9253_regs[ri] = 8'h00; ad9484_regs[ri] = 8'h00;
        end
        ad9253_regs[8'h01] = 8'h8F; ad9484_regs[8'h01] = 8'h6C;
    end
    always @(negedge conv_spi_csb_s or negedge conv_spi_csb_r) begin
        cspi_bit <= 5'd0; cspi_cmd <= 24'd0; cspi_rw <= 1'b0; conv_sl_oe <= 1'b0;
    end
    always @(posedge conv_spi_csb_s or posedge conv_spi_csb_r) begin
        if (conv_spi_csb_s && conv_spi_csb_r) conv_sl_oe <= 1'b0;
    end
    always @(posedge conv_spi_sclk) if (!conv_spi_csb_s || !conv_spi_csb_r) begin
        cspi_cmd <= {cspi_cmd[22:0], conv_spi_sdio};
        cspi_bit <= cspi_bit + 5'd1;
        if (cspi_bit == 5'd15) begin
            cspi_rw   <= cspi_cmd[14];
            cspi_addr <= {cspi_cmd[6:0], conv_spi_sdio};
            if (cspi_cmd[14])
                cspi_rshift <= !conv_spi_csb_s ? ad9253_regs[{cspi_cmd[6:0], conv_spi_sdio}] :
                                                 ad9484_regs[{cspi_cmd[6:0], conv_spi_sdio}];
        end else if (cspi_bit == 5'd23 && !cspi_rw) begin
            if (!conv_spi_csb_s) ad9253_regs[cspi_addr] <= {cspi_cmd[6:0], conv_spi_sdio};
            else                 ad9484_regs[cspi_addr] <= {cspi_cmd[6:0], conv_spi_sdio};
        end
    end
    always @(negedge conv_spi_sclk) begin
        if ((!conv_spi_csb_s || !conv_spi_csb_r) && cspi_bit >= 5'd16 && cspi_bit <= 5'd23 && cspi_rw) begin
            conv_sl_oe <= 1'b1; conv_sl_out <= cspi_rshift[7]; cspi_rshift <= {cspi_rshift[6:0], 1'b0};
        end else conv_sl_oe <= 1'b0;
    end

    wire ad9253_configured = (ad9253_regs[8'h08] == 8'h00) && (ad9253_regs[8'h21] == 8'h40);

    function signed [13:0] tone_a(input [2:0] k);
        case (k)
            3'd0: tone_a =  14'sd0;     3'd1: tone_a =  14'sd4243;
            3'd2: tone_a =  14'sd6000;  3'd3: tone_a =  14'sd4243;
            3'd4: tone_a =  14'sd0;     3'd5: tone_a = -14'sd4243;
            3'd6: tone_a = -14'sd6000;  3'd7: tone_a = -14'sd4243;
        endcase
    endfunction
    function signed [13:0] tone_b(input [1:0] k);
        case (k)
            2'd0: tone_b =  14'sd4000; 2'd1: tone_b = 14'sd0;
            2'd2: tone_b = -14'sd4000; 2'd3: tone_b = 14'sd0;
        endcase
    endfunction

    reg [3:0]  ui_idx = 4'd3;
    reg [2:0]  s_idx  = 3'd0;
    reg [15:0] fa = 16'd0, fb = 16'd0;
    localparam [15:0] FCO_W = 16'hFF00;
    always @(adcs_dco_400m) begin
        if (!ad9253_configured) begin
            fco_serial <= 1'b0; d0_serial <= 1'b0; d1_serial <= 1'b0;
            ui_idx <= 4'd3; s_idx <= 3'd0;
            fa <= {tone_a(3'd0), 2'b00}; fb <= {tone_b(2'd0), 2'b00};
        end else begin
            fco_serial <= FCO_W[15 - ui_idx];
            d0_serial  <= fa[15 - ui_idx];
            d1_serial  <= fb[15 - ui_idx];
            if (ui_idx == 4'd15) begin
                ui_idx <= 4'd0;
                s_idx  <= s_idx + 3'd1;
                fa     <= {tone_a(s_idx + 3'd1), 2'b00};
                fb     <= {tone_b(s_idx[1:0] + 2'd1), 2'b00};
            end else ui_idx <= ui_idx + 4'd1;
        end
    end

    // Behavioral 8x ADAR1000 SPI Slaves
    reg [7:0] adar_regs [0:7][0:63];
    reg [7:0] adar_active [0:7][0:63];
    integer   as_bit, as_chip = -1, c_i, r_i;
    reg [15:0] as_hdr; reg [14:0] as_addr; reg as_rw; reg [7:0] as_dat, as_rsh; reg as_sdo = 1'b0;
    assign adar_sdo = as_sdo;
    initial begin
        for (c_i = 0; c_i < 8; c_i = c_i + 1)
            for (r_i = 0; r_i < 64; r_i = r_i + 1) begin
                adar_regs[c_i][r_i] = 8'd0; adar_active[c_i][r_i] = 8'd0;
            end
    end
    always @(adar_csb) begin
        if (adar_csb == 8'hFF) begin
            as_chip = -1; as_sdo <= 1'b0;
        end else begin
            as_bit = 0; as_hdr = 16'd0; as_sdo <= 1'b0;
            for (c_i = 0; c_i < 8; c_i = c_i + 1) if (adar_csb[c_i] == 1'b0) as_chip = c_i;
        end
    end
    always @(posedge adar_sclk) if (as_chip >= 0) begin
        if (as_bit < 16) begin
            as_hdr = {as_hdr[14:0], adar_sdio};
            as_bit = as_bit + 1;
            if (as_bit == 16) begin
                as_rw   = as_hdr[15]; as_addr = as_hdr[14:0];
                as_rsh  = (as_rw && as_addr < 64) ? adar_regs[as_chip][as_addr[5:0]] : 8'h00;
            end
        end else begin
            as_dat = {as_dat[6:0], adar_sdio};
            as_bit = as_bit + 1;
            if (as_bit == 24) begin
                if (!as_rw && as_addr < 64) begin
                    adar_regs[as_chip][as_addr[5:0]] <= as_dat;
                    if (adar_regs[as_chip][0][5]) as_addr = as_addr + 15'd1;
                end
                as_bit = 16;
            end
        end
    end
    always @(negedge adar_sclk) begin
        if (as_chip >= 0 && as_bit >= 16 && as_rw && adar_regs[as_chip][0][4]) begin
            as_sdo <= as_rsh[7]; as_rsh <= {as_rsh[6:0], 1'b0};
        end else as_sdo <= 1'b0;
    end
    always @(posedge adar_tx_load[0]) begin
        for (c_i = 0; c_i < 8; c_i = c_i + 1)
            for (r_i = 16; r_i <= 39; r_i = r_i + 1)
                adar_active[c_i][r_i] <= adar_regs[c_i][r_i];
    end

    // Behavioral I2C Slaves (TMP1075 @ 0x48, M24C02 @ 0x50, Si549 @ 0x55)
    tb_top_i2c_slave #(.SLAVE_ADDR(7'h48)) u_tmp1075 (.scl(hk_scl), .sda(hk_sda), .enable_ack(1'b1));
    tb_top_i2c_slave #(.SLAVE_ADDR(7'h50)) u_m24c02  (.scl(hk_scl), .sda(hk_sda), .enable_ack(1'b1));
    tb_top_i2c_slave #(.SLAVE_ADDR(7'h55)) u_si549   (.scl(xo_scl), .sda(xo_sda), .enable_ack(1'b1));
    initial begin
        u_tmp1075.mem[8'h00] = 8'h2A;
        u_tmp1075.mem[8'h01] = 8'h80;
    end

    // -------------------------------------------------------------------------
    // DUT: artix_top
    // -------------------------------------------------------------------------
    reg hk_alert_n = 1'b1;
    artix_top #(
        .DDC_POST_DECIM      (4),
        .LINK_AM_PERIOD      (64),
        .ADC_AUTO_TRAIN      (1'b1),
        .ENABLE_ETH          (1'b0),
        .CONV_SPI_CLK_DIV    (2),
        .CONV_SPI_RST_CYC    (16),
        .CONV_SPI_AUTO_INIT  (1'b1),
        .ADAR_CLK_DIV        (2),
        .ADAR_AUTO_INIT      (1'b1),
        .HK_CLK_DIV          (3),
        .HK_POLL_DIV         (500000),
        .XO_FCAL_WAIT_CYC    (32),
        .BOOT_FREQ_500M      (TB_BOOT_500M),
        .XADC_POLL_DIV_P     (64),
        .PPS_DEFAULT_NOM_CYC (32'd1250)
    ) u_artix (
        .fpga_clk_p    (fpga_clk_100m),
        .fpga_clk_n    (~fpga_clk_100m),
        .adcr_d_p      (adcr_d_p),
        .adcr_d_n      (adcr_d_n),
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
        .beam_strobe   (beam_strobe),
        .pps_sync      (pps_sync),
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
        .hk_alert_n    (hk_alert_n),
        .fpga_irq      (fpga_irq),
        .conv_spi_csb_r(conv_spi_csb_r),
        .conv_spi_csb_s(conv_spi_csb_s),
        .conv_spi_sclk (conv_spi_sclk),
        .conv_spi_sdio (conv_spi_sdio),
        .adar_sclk     (adar_sclk),
        .adar_sdio     (adar_sdio),
        .adar_sdo      (adar_sdo),
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
    // Kria-side 2-Lane Uplink RX + 1-Lane Downlink TX (with PCB/Pkg delays)
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

    wire rx_out_v, rx_out_sop, rx_out_eop, rx_done_v, rx_done_ok, rx_done_err;
    wire [7:0]  rx_out_sid;
    wire [15:0] rx_rem_status;
    wire [63:0] rx_out_data;
    wire l0_lock, l1_lock, deskew_lock, ul_link_up, l0_bv, l0_bo, l1_bv, l1_bo;
    wire [31:0] ul_crc_err;

    link_rx_train_fsm #(.SINGLE_LANE(0),.MAX_TAP(511),.TAP_STEP(8),.TAP_DWELL_CYCLES(16'd1600),.MIN_EYE_STEPS(9'd18))
        u_ktr (.clk(rx_clkdiv),.rst(kria_rx_rst),.retrain(1'b0),.cfg_tap_override(1'b0),.cfg_tap_l0(9'd0),.cfg_tap_l1(9'd0),.rx_byte_l0(rx_byte_l0),.rx_byte_l1(rx_byte_l1),.l0_block_lock(l0_lock),.l1_block_lock(l1_lock),.deskew_lock(deskew_lock),.l0_rx_blk_valid(l0_bv),.l0_rx_blk_ok(l0_bo),.l1_rx_blk_valid(l1_bv),.l1_rx_blk_ok(l1_bo),.en_vtc(en_vtc),.load_l0(load_l0),.cntval_l0(cntval_l0),.load_l1(load_l1),.cntval_l1(cntval_l1),.train_state(),.link_up(ul_link_up),.eye_left_l0(),.eye_right_l0(),.eye_left_l1(),.eye_right_l1());

    link_pcs_rx #(.SKIP_CRC(0)) u_kul_rx (
        .clk(rx_clkdiv),.rst(kria_rx_rst),.link_ready(ul_link_up),
        .rx_byte_l0(rx_byte_l0),.rx_byte_l1(rx_byte_l1),
        .out_valid(rx_out_v),.out_sop(rx_out_sop),.out_eop(rx_out_eop),
        .out_stream_id(rx_out_sid),.out_len(),.out_seq(),.out_timestamp(),.out_data(rx_out_data),
        .pkt_done_valid(rx_done_v),.pkt_done_ok(rx_done_ok),.pkt_done_err(rx_done_err),
        .l0_block_lock(l0_lock),.l1_block_lock(l1_lock),.deskew_lock(deskew_lock),
        .skew_blocks(),.remote_status(rx_rem_status),.remote_dropped_cnt(),
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
    wire #0.650 dl_clk_w = ser_dl_clk;
    wire #0.680 dl_d0_w  = ser_dl_d0;
    assign dl_rx_clk_p = dl_clk_w; assign dl_rx_clk_n = ~dl_clk_w;
    assign dl_rx_d0_p  = dl_d0_w;  assign dl_rx_d0_n  = ~dl_d0_w;

    // -------------------------------------------------------------------------
    // Packet Monitors & AD9708/AD9767/ADAR Safety Monitors
    // -------------------------------------------------------------------------
    integer cnt_01 = 0, cnt_04 = 0, cnt_05 = 0;
    reg [7:0] active_pkt_sid = 8'd0;
    reg        resp_valid_flag = 1'b0;
    reg [15:0] resp_addr_cap   = 16'd0;
    reg [31:0] resp_data_cap   = 32'd0;

    reg signed [15:0] d2_i_cap = 16'sd0, d2_q_cap = 16'sd0;   // first sample of the last stream 0x01 packet
    always @(posedge rx_clkdiv) begin
        if (rx_out_v && rx_out_sop) begin
            active_pkt_sid <= rx_out_sid;
            if (rx_out_sid == 8'h01) begin
                d2_i_cap <= rx_out_data[15:0];
                d2_q_cap <= rx_out_data[31:16];
            end
            if (rx_out_sid == 8'h11) begin
                resp_valid_flag <= 1'b1;
                resp_addr_cap   <= rx_out_data[47:32];
                resp_data_cap   <= rx_out_data[31:0];
            end
        end
        if (rx_done_v && rx_done_ok) begin
            if (active_pkt_sid == 8'h01)      cnt_01 <= cnt_01 + 1;
            else if (active_pkt_sid == 8'h04) cnt_04 <= cnt_04 + 1;
            else if (active_pkt_sid == 8'h05) cnt_05 <= cnt_05 + 1;
        end
    end

    integer dacr_clk_edges = 0, dacs_clk_edges = 0, dacs_wrt_edges = 0, tr_viol = 0, dacr_t_errs = 0;
    real dacr_d_t = -100.0, dacr_c_t = -100.0;
    always @(dacr_d) begin
        dacr_d_t = $realtime;
        if (dacr_clk_edges > 2 && dacr_c_t > 0.0 && ($realtime - dacr_c_t) < 1.5) dacr_t_errs = dacr_t_errs + 1;
    end
    always @(posedge dacr_clk) begin
        dacr_clk_edges = dacr_clk_edges + 1;
        if (dacr_clk_edges > 2 && ($realtime - dacr_d_t) < 2.0) dacr_t_errs = dacr_t_errs + 1;
        dacr_c_t = $realtime;
    end
    always @(posedge dacs_iqclk) dacs_clk_edges = dacs_clk_edges + 1;
    always @(posedge dacs_iqwrt) dacs_wrt_edges = dacs_wrt_edges + 1;
    always @(posedge u_artix.link_clk) if (!u_artix.link_rst) begin
        if ((adar_tr != 8'h00) && (adar_csb != 8'hFF || adar_tx_load != 8'h00 || adar_rx_load != 8'h00))
            tr_viol = tr_viol + 1;
    end

    // -------------------------------------------------------------------------
    // Helper Tasks: Send 8'h10 Register Write/Read over Downlink & Read 8'h11 Back
    // -------------------------------------------------------------------------
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

    task automatic rd_reg(input [15:0] addr, output [31:0] data_o);
        integer tmo;
        begin
            @(posedge rx_clkdiv); resp_valid_flag <= 1'b0;
            dl_send_word(8'h10, 16'd8, {8'h02, 8'h00, addr, 32'd0});
            tmo = 0;
            while ((!resp_valid_flag || (resp_addr_cap != addr)) && tmo < 3000) begin
                @(posedge rx_clkdiv);
                tmo = tmo + 1;
            end
            if (!resp_valid_flag || (resp_addr_cap != addr)) begin
                $display("FAIL: tb_artix_top reg readback timeout on addr=0x%04h dl_up=%b dl_rx_pkt=%0d dl_crc=%0d resp_pend=%b arb=%0d cnt01=%0d ul_crc=%0d flag=%b raddr=0x%04h dl_st=%0d dl_tap=%0d dl_sh=%0d dl_ov=%b dl_rdy=%b fr_st=%0d",
                         addr, u_artix.dl_link_up, u_artix.dl_pkt_rx_cnt, u_artix.dl_crc_err_cnt, u_artix.resp_pkt_pend, u_artix.arb_owner, cnt_01, ul_crc_err, resp_valid_flag, resp_addr_cap, u_artix.dl_train_state, u_artix.dl_tap_active, u_artix.dl_sh_err_cnt, u_artix.dl_out_valid, dl_tx_ready, u_kdl_tx.u_framer.state);
                $finish;
            end
            data_o = resp_data_cap;
        end
    endtask

    // -------------------------------------------------------------------------
    // Main Verification Sequence
    // -------------------------------------------------------------------------
    reg [31:0] rval;
    integer wait_c, pi;
    reg [31:0] fe_e4, fe_r;

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

        kria_rx_rst = 1'b1; kria_tx_rst = 1'b1;
        repeat (16) @(posedge kria_tx_clk);
        kria_tx_rst = 1'b0;
        wait (u_artix.sys_mmcm_locked === 1'b1);
        repeat (32) @(posedge rx_clkdiv);
        // Audit 2.6: FPGA_IRQ must stay low before link training even with hk_alert_n asserted
        hk_alert_n = 1'b0;
        repeat (8) @(posedge rx_clkdiv);
        if (fpga_irq !== 1'b0) begin
            $display("FAIL: tb_artix_top fpga_irq asserted before link training");
            $finish;
        end
        hk_alert_n = 1'b1;
        repeat (8) @(posedge rx_clkdiv);
        kria_rx_rst = 1'b0;

        // 1. Wait for BOTH Uplink (Kria) and Downlink (Artix) links + eye training
        wait_c = 0;
        while ((!ul_link_up || !deskew_lock || !u_artix.dl_link_up) && wait_c < 200000) begin
            @(posedge rx_clkdiv);
            wait_c = wait_c + 1;
        end
        if (!ul_link_up || !deskew_lock || !u_artix.dl_link_up) begin
            $display("FAIL: tb_artix_top ul_link_up=%b deskew=%b dl_up=%b dl_st=%0d ul_st=%0d l0=%b l1=%b tap=%0d len0=%0d len1=%0d idcr=%b",
                     ul_link_up, deskew_lock, u_artix.dl_link_up, u_artix.dl_train_state,
                     u_ktr.train_state, l0_lock, l1_lock, u_ktr.scan_tap, u_ktr.best_len0, u_ktr.best_len1, idelayctrl_rdy);
            $finish;
        end

        wait_c = 0;
        while (wait_c < 8000) begin @(posedge kria_tx_clk); wait_c = wait_c + 1; end

        // Audit 2.6: FPGA_IRQ works once link_trained (dl_up_sync[1]) is high
        hk_alert_n = 1'b0;
        repeat (8) @(posedge rx_clkdiv);
        if (fpga_irq !== 1'b1) begin
            $display("FAIL: tb_artix_top fpga_irq did not assert on alert after link training");
            $finish;
        end
        hk_alert_n = 1'b1;
        repeat (8) @(posedge rx_clkdiv);

        // 2. Check ADCS_STATUS (0x38): aligned, conv_init_done, ad9253_id == 0x8F
        rd_reg(16'h0038, rval);
        if (!rval[0] || !rval[16] || rval[17] || (rval[31:24] !== 8'h8F)) begin
            $display("FAIL: tb_artix_top ADCS_STATUS=0x%08h (exp aligned=1, init_done=1, id=8F)", rval);
            $finish;
        end

        // 3. Manual CONV_SPI read of AD9484 Chip ID (0x01 == 0x6C)
        wr_reg(16'h003C, 32'h8020_0100); // start=1, target=0 (AD9484), rw=1, addr=0x001
        repeat (400) @(posedge kria_tx_clk);
        rd_reg(16'h0040, rval);
        if (!rval[8] || (rval[7:0] !== 8'h6C)) begin
            $display("FAIL: tb_artix_top AD9484 SPI readback=0x%08h (exp valid=1, id=6C)", rval);
            $finish;
        end

        // 4. Configure SDR DDC Ch A & Ch B & enable streams 0x04 / 0x05 alongside Radar 0x01
        wr_reg(16'h0044, 32'h2000_0000); // NCO A = f_S/8 (6.25 MHz)
        wr_reg(16'h0048, 32'h4000_0000); // NCO B = f_S/4 (12.5 MHz)
        wr_reg(16'h004C, 32'h0008_0004); // 8 words/pkt (64B), decim=4
        wr_reg(16'h0034, 32'h0000_000D); // adcs_enable=1, ch_enable=2'b11

        // 5. AD9708 Chirp (0x54..0x6C) + AD9767 SDR TX (0x70 + 8'h12 IQ stream)
        wr_reg(16'h0058, 32'h28F5_C28F); // 20 MHz @ 125 MHz
        wr_reg(16'h005C, 32'h0014_0000);
        wr_reg(16'h0060, 32'd32);
        wr_reg(16'h0064, 32'd0);
        wr_reg(16'h0054, 32'h00FF_0003); // chirp_enable + trig
        wr_reg(16'h0070, 32'h0000_0001); // DACS enable
        @(posedge kria_tx_clk);
        dl_tx_valid <= 1'b1; dl_tx_sid <= 8'h12; dl_tx_len <= 16'd32;
        for (pi = 0; pi < 4; pi = pi + 1) begin
            dl_tx_sop  <= (pi == 0); dl_tx_eop <= (pi == 3);
            dl_tx_data <= {16'sd1000, 16'sd2000, 16'sd1500, 16'sd2500};
            @(posedge kria_tx_clk);
            while (!dl_tx_ready) @(posedge kria_tx_clk);
        end
        dl_tx_valid <= 1'b0; dl_tx_sop <= 1'b0; dl_tx_eop <= 1'b0; dl_tx_seq <= dl_tx_seq + 32'd1;

        // 6. ADAR1000 init verify + Beam #3 write + soft_load + RF Switch 4'b1010
        rd_reg(16'h0090, rval);
        if (!rval[0] || rval[1]) begin
            $display("FAIL: tb_artix_top ADAR_STATUS=0x%08h (exp init_done=1, init_err=0)", rval);
            $finish;
        end
        wr_reg(16'h0088, 32'h8003_003A); // beam=3, chip=0, byte=0, data=0x3A
        wr_reg(16'h0080, 32'h0008_0006); // guard pre=6, post=8
        wr_reg(16'h0084, 32'd8);          // rf_sw settle=8
        wr_reg(16'h007C, 32'h0000_0A43); // rf_sw=1010, soft_load=1, tr_req=0, beam=3
        repeat (500) @(posedge kria_tx_clk);
        if (sw_ctrl !== 4'b1010) begin
            $display("FAIL: tb_artix_top sw_ctrl=%b (exp 1010)", sw_ctrl); $finish;
        end

        // 7. HK I2C (TMP1075 0x48 + missing ACK 0x7D) + Si549 XO (0xA8) + XADC/PPS (0xB8..0xE0)
        wr_reg(16'h0094, 32'h0000_0001); // poll_en=1
        wr_reg(16'h009C, 32'h0000_0000); // reg 0x00
        wr_reg(16'h0098, 32'h8000_08C8); // dev=0x48, wr_len=1, rd_len=2, trig=1
        repeat (1500) @(posedge kria_tx_clk);
        wr_reg(16'h0098, 32'h8000_08FD); // dev_addr=7'h7D ([6:0]), wr_len=1, rd_len=2 => 0x8000_08FD
        repeat (1000) @(posedge kria_tx_clk);
        rd_reg(16'h00A4, rval);
        if (rval[15:0] !== 16'h2A80) begin
            $display("FAIL: tb_artix_top TMP1075 tmp_raw=0x%04h (exp 2a80)", rval[15:0]); $finish;
        end
        if (rval[31:16] == 16'd0) begin
            $display("FAIL: tb_artix_top missing ACK on 0x7D NOT detected (ack_err_cnt=0)"); $finish;
        end

        // Verify pre-switch A-1 status (500M: radar disabled, SDR works; 400M: radar works)
        rd_reg(16'h00E8, rval);
        if (TB_BOOT_500M) begin
            if (!rval[0] || (cnt_01 != 0)) begin
                $display("FAIL: tb_artix_top 500M A-1 leak 0xE8=0x%08h cnt_01=%0d", rval, cnt_01);
                $finish;
            end
            // Rev08 G-7: D2 CSRs (D2 left off: this bench's AD9484 model runs at 400 MSPS only)
            wr_reg(16'h0104, 32'h1234_5678);
            rd_reg(16'h0104, rval);
            if (rval !== 32'h1234_5678) begin
                $display("FAIL: tb_artix_top D2_FTW readback 0x%08h", rval); $finish;
            end
            wr_reg(16'h0100, 32'h0000_0002);
            rd_reg(16'h0100, rval);
            if (rval !== 32'h0000_0002) begin
                $display("FAIL: tb_artix_top D2_CTRL readback 0x%08h", rval); $finish;
            end
            rd_reg(16'h0108, rval);
            if (rval[4] !== 1'b1 || rval[0] !== 1'b0 || cnt_01 != 0) begin
                $display("FAIL: tb_artix_top D2_STAT 0x%08h (exp 500 MHz, not running) cnt_01=%0d", rval, cnt_01);
                $finish;
            end
            // D2 on at 250 MHz: the 0xAA / 0x55 pattern (codes 170 / 85, i.e. +/-85 as odd 9-bit numbers) is a
            // tone at f_S / 2, mixed to DC: |I| = 85 * 4095 / 32 * 3125 / 4096 = 8299, Q = 0
            wr_reg(16'h0104, 32'h8000_0000);
            wr_reg(16'h0100, 32'h0000_0001);
            wait_c = 0; rval = 32'd0;
            while ((rval[1:0] !== 2'b11) && wait_c < 100) begin
                repeat (200) @(posedge kria_tx_clk);
                rd_reg(16'h0108, rval);
                wait_c = wait_c + 1;
            end
            begin : d2_pkts
                integer c0;
                c0 = cnt_01;
                wait_c = 0;
                while (cnt_01 < c0 + 6 && wait_c < 20000) begin @(posedge rx_clkdiv); wait_c = wait_c + 1; end
            end
            rd_reg(16'h0108, rval);
            $display("[G7] D2_STAT 0x%08h, stream 0x01 packets %0d, first sample I %0d Q %0d", rval, cnt_01,
                     d2_i_cap, d2_q_cap);
            if (rval[3:0] !== 4'b0011 || rval[13:8] < 6'd4 || cnt_01 < 6 ||
                (d2_i_cap > -16'sd8200 && d2_i_cap < 16'sd8200) || d2_i_cap > 16'sd8400 || d2_i_cap < -16'sd8400 ||
                d2_q_cap > 16'sd100 || d2_q_cap < -16'sd100) begin
                $display("FAIL: tb_artix_top D2 at 500 MSPS"); $finish;
            end
            // D2 off (mid-packet, likely): stream 0x01 must let go, or the readback below and the rest hang
            wr_reg(16'h0100, 32'h0000_0000);
            repeat (400) @(posedge kria_tx_clk);
            rd_reg(16'h0108, rval);
            if (rval[0] !== 1'b0) begin
                $display("FAIL: tb_artix_top D2_STAT 0x%08h after D2 off", rval); $finish;
            end
        end else begin
            if (rval[0]) begin
                $display("FAIL: tb_artix_top 400M unexpected radar_dis=1 0xE8=0x%08h", rval);
                $finish;
            end
            wait_c = 0;
            while ((cnt_04 < 2 || cnt_05 < 2 || cnt_01 < 4) && wait_c < 8000) begin
                @(posedge rx_clkdiv); wait_c = wait_c + 1;
            end
            if (cnt_01 < 4 || cnt_04 < 2 || cnt_05 < 2) begin
                $display("FAIL: tb_artix_top 400M pre-switch counts c01=%0d c04=%0d c05=%0d", cnt_01, cnt_04, cnt_05);
                $finish;
            end
        end

        // XO CLK_SEL = 1 (drives D8 low) + toggle mode (500M->400M or 400M->500M)
        wr_reg(16'h00A8, TB_BOOT_500M ? 32'h0000_0005 : 32'h0000_0007);
        repeat (50) @(posedge kria_tx_clk);
        if (clk_sel !== 1'b0) begin
            $display("FAIL: tb_artix_top clk_sel=%b (exp 0 when use_ext_clk=1)", clk_sel); $finish;
        end
        kria_rx_rst <= 1'b1;
        #2000;
        wait (!u_artix.u_clk_mode_ctrl.xo_busy_link && !u_artix.u_clk_mode_ctrl.mmcm_rst &&
              u_artix.sys_mmcm_locked && u_artix.eth_mmcm_locked_w && !u_artix.sys_rst);
        repeat (32) @(posedge rx_clkdiv);
        kria_rx_rst <= 1'b0;
        wait (ul_link_up && u_artix.dl_link_up);
        repeat (20) @(posedge kria_tx_clk);
        wait_c = 0;
        rval   = 32'd0;
        while (!rval[9] && wait_c < 40) begin
            repeat (300) @(posedge kria_tx_clk);
            rd_reg(16'h00A8, rval);
            wait_c = wait_c + 1;
        end
        if (!rval[9] || (rval[10] !== ~TB_BOOT_500M)) begin
            $display("FAIL: tb_artix_top XO_CTRL=0x%08h (exp xo_prog_done=1, 500m=%0d)", rval, ~TB_BOOT_500M); $finish;
        end

        if (TB_BOOT_500M) begin
            // Now in 400 MHz mode: wait for AD9484 auto-training and verify 0xE8[0]=0, 0xE8[2]=1
            wait_c = 0; rval = 32'd0;
            while ((rval[0] || !rval[2]) && wait_c < 80) begin
                repeat (200) @(posedge kria_tx_clk);
                rd_reg(16'h00E8, rval);
                wait_c = wait_c + 1;
            end
            if (rval[0] || !rval[2]) begin
                $display("FAIL: tb_artix_top post-400M switch AD9484 did not train (0xE8=0x%08h)", rval); $finish;
            end
        end else begin
            // Now in 500 MHz mode: verify A-1 re-asserts radar_dis=1
            rd_reg(16'h00E8, rval);
            if (!rval[0] || rval[1] || rval[2]) begin
                $display("FAIL: tb_artix_top post-500M switch A-1 expected dis=1,mmcm=0,tr=0 got 0x%08h", rval); $finish;
            end
        end

        // Re-trigger AD9708 chirp after XO reprogram sys_rst/dac_rst cycle (and re-enable ADCS 0x34/0x44/0x48/0x4C)
        wr_reg(16'h0044, 32'h2000_0000);
        wr_reg(16'h0048, 32'h4000_0000);
        wr_reg(16'h004C, 32'h0008_0004);
        wr_reg(16'h0034, 32'h0000_000D);
        wr_reg(16'h0058, 32'h28F5_C28F);
        wr_reg(16'h005C, 32'h0014_0000);
        wr_reg(16'h0060, 32'd32);
        wr_reg(16'h0064, 32'd0);
        wr_reg(16'h0054, 32'h00FF_0003);

        // PPS_SYNC two pulses spaced 1251 clk cycles apart (nom=1250 -> +800 ppm)
        wr_reg(16'h00C0, 32'h0001_0800); // pps_disc_en=1
        @(posedge u_artix.link_clk); pps_sync <= 1'b1; repeat (4) @(posedge u_artix.link_clk); pps_sync <= 1'b0;
        repeat (1247) @(posedge u_artix.link_clk);
        pps_sync <= 1'b1; repeat (4) @(posedge u_artix.link_clk); pps_sync <= 1'b0;
        repeat (100) @(posedge kria_tx_clk);

        rd_reg(16'h00B8, rval);
        if (!rval[24]) begin $display("FAIL: tb_artix_top XADC valid=0"); $finish; end
        rd_reg(16'h00C8, rval);
        if (rval != 32'd1251) begin $display("FAIL: tb_artix_top PPS_PERIOD_CYC=%0d (exp 1251)", rval); $finish; end
        rd_reg(16'h00CC, rval);
        if ($signed(rval) != 32'sd800) begin $display("FAIL: tb_artix_top PPS_PPM_ERR=%0d (exp +800)", $signed(rval)); $finish; end

        // Verify uplink streams & DACs & safety
        wait_c = 0;
        while ((cnt_04 < 2 || cnt_05 < 2 || (TB_BOOT_500M && cnt_01 < 4)) && wait_c < 8000) begin
            @(posedge rx_clkdiv); wait_c = wait_c + 1;
        end
        rd_reg(16'h006C, rval);
        if (cnt_01 < 4 || cnt_04 < 2 || cnt_05 < 2 || ul_crc_err != 0 ||
            rval == 0 || dacr_t_errs != 0 || dacs_wrt_edges < 4 || tr_viol != 0) begin
            $display("FAIL: tb_artix_top c01=%0d c04=%0d c05=%0d crc=%0d dacr_cnt=%0d dacr_te=%0d dacs_w=%0d tr_v=%0d | adc_tr=%b ph_err=%b eye=%0d st=%0d ddc_en=%b txv=%b drop=%0d",
                     cnt_01, cnt_04, cnt_05, ul_crc_err, rval, dacr_t_errs, dacs_wrt_edges, tr_viol,
                     u_artix.adc_trained, u_artix.adc_dco_phase_err, u_artix.adc_eye_width_min,
                     u_artix.u_adc_cap.tr_state, u_artix.u_ddc.ddc_en, u_artix.tx_pkt_valid, u_artix.tx_dropped_cnt);
            $finish;
        end

        // Rev08 CSR page 1: front-end control reaches the XO bus (no expander on this bench: the command must end
        // with an I2C error), page-0 registers do not alias into 0x1xx, and unmapped addresses read 0
        rd_reg(16'h011C, fe_r);
        if (fe_r[0] !== 1'b1) begin $display("FAIL: tb_artix_top FE_LED_CTRL reset=0x%08h (exp auto-map on)", fe_r); $finish; end
        wr_reg(16'h011C, 32'd0);                    // LED auto-map off: the bus stays quiet
        rd_reg(16'h00E4, fe_r);
        fe_e4 = fe_r;
        wr_reg(16'h01E4, ~fe_e4);                   // would hit RADAR_CTRL if page 1 aliased page 0
        rd_reg(16'h00E4, fe_r);
        if (fe_r != fe_e4) begin $display("FAIL: tb_artix_top write to 0x1E4 aliased RADAR_CTRL (0x%08h)", fe_r); $finish; end
        rd_reg(16'h01E4, fe_r);
        if (fe_r != 32'd0) begin $display("FAIL: tb_artix_top unmapped 0x1E4 reads 0x%08h", fe_r); $finish; end
        rd_reg(16'h02E4, fe_r);
        if (fe_r != 32'd0) begin $display("FAIL: tb_artix_top unmapped 0x2E4 reads 0x%08h", fe_r); $finish; end
        repeat (200) @(posedge kria_tx_clk);
        wr_reg(16'h0110, 32'h3000_0000);            // FE_CMD POLL
        rd_reg(16'h0110, fe_r);
        if (fe_r != 32'h3000_0000) begin $display("FAIL: tb_artix_top FE_CMD readback 0x%08h", fe_r); $finish; end
        wait_c = 0;
        rd_reg(16'h0114, fe_r);
        while (fe_r[28] && wait_c < 400) begin
            repeat (200) @(posedge kria_tx_clk);
            rd_reg(16'h0114, fe_r);
            wait_c = wait_c + 1;
        end
        if (fe_r[28] !== 1'b0 || fe_r[31] !== 1'b1) begin
            $display("FAIL: tb_artix_top FE_STAT=0x%08h (exp idle with an I2C error: no expander on this bench)", fe_r);
            $finish;
        end

        $display("PASS: tb_artix_top c01=%0d c04=%0d c05=%0d crc=0 sw=%b tmp=%04h pps_ppm=+800 dacr=%0d dacs_w=%0d tr_viol=0",
                 cnt_01, cnt_04, cnt_05, sw_ctrl, 16'h2A80, rval, dacs_wrt_edges);
        $finish;
    end

    initial begin
        #15_000_000;
        $display("FAIL: tb_artix_top global simulation timeout");
        $finish;
    end
endmodule
