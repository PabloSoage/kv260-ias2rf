// SPDX-License-Identifier: BSD-2-Clause
// Testbench: Artix-7 J1102 Pmod SPI Slave & Fallback DDC FIFO (pmod_spi)
//
// Checks:
//   1. Mode 0 (CPOL=0, CPHA=0) 40-bit SPI write & readback across LINK_CTRL (0x00),
//      IDELAY_CTRL_L0 (0x08), and IDELAY_CTRL_L1 (0x0C), including self-clearing pulses
//      (retrain, clr_err, force_load_l0/l1).
//   2. Readback of all LINK_PROTOCOL.md Section 7.2 RO status/counter/eye-scan regs (0x04..0x30).
//   3. Fallback DDC capture enable -> 8 I/Q samples pushed -> FB_FIFO_STATUS (0x34)
//      and FB_FIFO_DATA (0x38) pop readout matching {bb_q, bb_i} order.
//
// Mutations:
//   -Mutate bad_cpol_cpha : switches slave SCLK edge to CPHA=1 -> Mode 0 master fails

`timescale 1ns/1ps

module tb_pmod_spi;

    reg clk = 1'b0;
    always #5.0 clk = ~clk; // 100 MHz system clock

    reg rst = 1'b1;

    reg  pmod_cs_n = 1'b1;
    reg  pmod_sclk = 1'b0;
    reg  pmod_mosi = 1'b0;
    wire pmod_miso;
    wire pmod_miso_oe;

    wire       ctrl_soft_rst, ctrl_loopback_en, ctrl_retrain_pulse;
    wire       ctrl_tap_override_en, ctrl_prbs7_tx_en, ctrl_prbs7_rx_chk_en;
    wire       ctrl_clr_err_pulse, ctrl_fallback_en;
    wire [8:0] cfg_tap_l0, cfg_tap_l1;
    wire       cfg_load_l0, cfg_load_l1;

    reg [15:0] fb_ddc_i     = 16'd0;
    reg [15:0] fb_ddc_q     = 16'd0;
    reg        fb_ddc_valid = 1'b0;

    // Pulse stretchers / latches to observe 1-cycle self-clearing pulses
    reg seen_retrain = 1'b0;
    reg seen_clr_err = 1'b0;
    reg seen_ld_l0   = 1'b0;
    reg seen_ld_l1   = 1'b0;
    always @(posedge clk) begin
        if (rst) begin
            seen_retrain <= 1'b0;
            seen_clr_err <= 1'b0;
            seen_ld_l0   <= 1'b0;
            seen_ld_l1   <= 1'b0;
        end else begin
            if (ctrl_retrain_pulse) seen_retrain <= 1'b1;
            if (ctrl_clr_err_pulse) seen_clr_err <= 1'b1;
            if (cfg_load_l0)        seen_ld_l0   <= 1'b1;
            if (cfg_load_l1)        seen_ld_l1   <= 1'b1;
        end
    end

    pmod_spi #(
        .FB_FIFO_DEPTH (64)
    ) dut (
        .clk                  (clk),
        .rst                  (rst),
        .pmod_cs_n            (pmod_cs_n),
        .pmod_sclk            (pmod_sclk),
        .pmod_mosi            (pmod_mosi),
        .pmod_miso            (pmod_miso),
        .pmod_miso_oe         (pmod_miso_oe),
        .ctrl_soft_rst        (ctrl_soft_rst),
        .ctrl_loopback_en     (ctrl_loopback_en),
        .ctrl_retrain_pulse   (ctrl_retrain_pulse),
        .ctrl_tap_override_en (ctrl_tap_override_en),
        .ctrl_prbs7_tx_en     (ctrl_prbs7_tx_en),
        .ctrl_prbs7_rx_chk_en (ctrl_prbs7_rx_chk_en),
        .ctrl_clr_err_pulse   (ctrl_clr_err_pulse),
        .ctrl_fallback_en     (ctrl_fallback_en),
        .cfg_tap_l0           (cfg_tap_l0),
        .cfg_load_l0          (cfg_load_l0),
        .cfg_tap_l1           (cfg_tap_l1),
        .cfg_load_l1          (cfg_load_l1),
        .st_train_state       (3'd5),
        .st_l0_block_lock     (1'b1),
        .st_l1_block_lock     (1'b0),
        .st_deskew_lock       (1'b1),
        .st_link_up           (1'b1),
        .st_idelayctrl_rdy    (1'b1),
        .st_remote_status     (8'hA7),
        .active_tap_l0        (9'd15),
        .active_tap_l1        (9'd21),
        .err_cnt_sh_l0        (32'h0000_0003),
        .err_cnt_sh_l1        (32'h0000_0001),
        .err_cnt_crc          (32'h0000_0002),
        .pkt_cnt_rx           (32'h0000_1234),
        .tx_dropped_cnt       (24'h000055),
        .rx_drop_cnt          (8'h07),
        .skew_blocks          (8'hFE),
        .am_seq               (16'h4B3C),
        .prbs_err_cnt         (32'h0000_0000),
        .eye_left_l0          (9'd3),
        .eye_right_l0         (9'd28),
        .eye_left_l1          (9'd7),
        .eye_right_l1         (9'd30),
        .fb_ddc_i             (fb_ddc_i),
        .fb_ddc_q             (fb_ddc_q),
        .fb_ddc_valid         (fb_ddc_valid)
    );

    // -------------------------------------------------------------------------
    // SPI Mode 0 Master BFM (10 MHz SCLK: 50 ns low, 50 ns high)
    // -------------------------------------------------------------------------
    task spi_xfer40;
        input  [39:0] tx_frame;
        output [39:0] rx_frame;
        integer b;
        begin
            rx_frame  = 40'd0;
            pmod_sclk = 1'b0;
            pmod_mosi = tx_frame[39];
            #40.0;
            pmod_cs_n = 1'b0;
            #60.0;
            for (b = 39; b >= 0; b = b - 1) begin
                pmod_mosi = tx_frame[b];
                #50.0;
                pmod_sclk = 1'b1;
                rx_frame[b] = pmod_miso;
                #50.0;
                pmod_sclk = 1'b0;
            end
            #50.0;
            pmod_cs_n = 1'b1;
            pmod_mosi = 1'b0;
            #80.0;
        end
    endtask

    task spi_write32;
        input [6:0]  addr;
        input [31:0] data;
        reg   [39:0] dummy;
        begin
            spi_xfer40({1'b1, addr, data}, dummy);
        end
    endtask

    task spi_read32;
        input  [6:0]  addr;
        output [31:0] data;
        reg    [39:0] rx;
        begin
            spi_xfer40({1'b0, addr, 32'd0}, rx);
            data = rx[31:0];
        end
    endtask

    task check_eq;
        input [255:0] label;
        input [31:0]  got;
        input [31:0]  exp;
        begin
            if (got !== exp) begin
                $display("FAIL: tb_pmod_spi %0s got=0x%08x expected=0x%08x", label, got, exp);
                $finish;
            end
        end
    endtask

    reg [31:0] rval;
    integer    k;
    reg [15:0] exp_i, exp_q;

    initial begin
        #100.0;
        @(posedge clk);
        rst = 1'b0;
        repeat (4) @(posedge clk);

        // 1. Write & readback LINK_CTRL (0x00) including fallback_en [8] & pulses [2],[6]
        spi_write32(7'h00, 32'h0000_017E); // lb=1, retrain=1, tap_ov=1, prbs_tx=1, prbs_rx=1, clr=1, fb=1
        repeat (4) @(posedge clk);
        if (!seen_retrain || !seen_clr_err) begin
            $display("FAIL: tb_pmod_spi self-clearing control pulses not observed (ret=%0d clr=%0d)",
                     seen_retrain, seen_clr_err);
            $finish;
        end
        if (ctrl_retrain_pulse || ctrl_clr_err_pulse) begin
            $display("FAIL: tb_pmod_spi self-clearing pulses stayed asserted");
            $finish;
        end
        if (!ctrl_loopback_en || !ctrl_tap_override_en || !ctrl_prbs7_tx_en ||
            !ctrl_prbs7_rx_chk_en || !ctrl_fallback_en) begin
            $display("FAIL: tb_pmod_spi persistent LINK_CTRL bits mismatch");
            $finish;
        end
        spi_read32(7'h00, rval);
        check_eq("LINK_CTRL", rval, 32'h0000_013A);

        // 2. Write & readback IDELAY_CTRL_L0 (0x08) and IDELAY_CTRL_L1 (0x0C)
        spi_write32(7'h08, 32'h8000_0013);
        spi_write32(7'h0C, 32'h8000_000B);
        repeat (4) @(posedge clk);
        if (!seen_ld_l0 || !seen_ld_l1) begin
            $display("FAIL: tb_pmod_spi IDELAY load pulses missing (%0d/%0d)", seen_ld_l0, seen_ld_l1);
            $finish;
        end
        spi_read32(7'h08, rval);
        check_eq("IDELAY_CTRL_L0", rval, {7'd0, 9'd15, 7'd0, 9'd19});
        spi_read32(7'h0C, rval);
        check_eq("IDELAY_CTRL_L1", rval, {7'd0, 9'd21, 7'd0, 9'd11});

        // 3. Verify all RO diagnostic registers (0x04, 0x10..0x30)
        spi_read32(7'h04, rval); check_eq("LINK_STATUS",   rval, 32'h00A7_00ED);
        spi_read32(7'h10, rval); check_eq("ERR_CNT_SH_L0", rval, 32'h0000_0003);
        spi_read32(7'h14, rval); check_eq("ERR_CNT_SH_L1", rval, 32'h0000_0001);
        spi_read32(7'h18, rval); check_eq("ERR_CNT_CRC",   rval, 32'h0000_0002);
        spi_read32(7'h1C, rval); check_eq("PKT_CNT_RX",    rval, 32'h0000_1234);
        spi_read32(7'h20, rval); check_eq("PKT_CNT_DROP",  rval, 32'h0700_0055);
        spi_read32(7'h24, rval); check_eq("DESKEW_STATUS", rval, 32'h004B_3CFE);
        spi_read32(7'h28, rval); check_eq("PRBS_ERR_CNT",  rval, 32'h0000_0000);
        spi_read32(7'h2C, rval); check_eq("EYE_SCAN_L0",   rval, {7'd0, 9'd28, 7'd0, 9'd3});
        spi_read32(7'h30, rval); check_eq("EYE_SCAN_L1",   rval, {7'd0, 9'd30, 7'd0, 9'd7});

        // 4. Push 8 DDC baseband samples into fallback FIFO & pop over SPI
        spi_read32(7'h34, rval);
        check_eq("FB_FIFO_EMPTY_STATUS", rval, 32'h0000_4000);
        for (k = 0; k < 8; k = k + 1) begin
            @(posedge clk);
            fb_ddc_i     <= $signed(16'h1000 + k * 16'h0111);
            fb_ddc_q     <= $signed(16'hF000 - k * 16'h0055);
            fb_ddc_valid <= 1'b1;
            @(posedge clk);
            fb_ddc_valid <= 1'b0;
        end
        repeat (3) @(posedge clk);
        spi_read32(7'h34, rval);
        check_eq("FB_FIFO_STATUS_8", rval, 32'h0000_0008);

        for (k = 0; k < 8; k = k + 1) begin
            exp_i = 16'h1000 + k * 16'h0111;
            exp_q = 16'hF000 - k * 16'h0055;
            spi_read32(7'h38, rval);
            check_eq("FB_FIFO_DATA", rval, {exp_q, exp_i});
        end
        spi_read32(7'h34, rval);
        check_eq("FB_FIFO_EMPTY_AFTER", rval, 32'h0000_4000);

        $display("PASS: tb_pmod_spi regs=13 fb_samples=8 mode=0");
        $finish;
    end

endmodule
