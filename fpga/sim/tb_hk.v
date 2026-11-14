// SPDX-License-Identifier: BSD-2-Clause
// Testbench for Task 16: HK I2C (TMP1075 + M24C02), XO I2C (Si549 + CLK_SEL), XADC & PPS_SYNC
//
// Mutations checked via run.ps1 -Mutate:
//   - missing_ack   : ignores I2C slave NACK -> non-existent 0x7D probe fails to report ack_err
//   - wrong_pps_clk : runs PPS period/PPM counter on sys_clk (100 MHz) instead of adc_clk (125 MHz)

`timescale 1ns/1ps

module tb_i2c_slave #(
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

    reg       prev_scl = 1'b1;
    reg       prev_sda = 1'b1;
    reg [2:0] state = 3'd0; // 0=IDLE, 1=ADDR, 2=REG, 3=WDATA, 4=RDATA
    reg [3:0] bit_cnt = 4'd0;
    reg [7:0] shift_reg = 8'd0;
    reg [7:0] reg_ptr = 8'd0;
    reg       have_reg_ptr = 1'b0;
    reg       rw_bit = 1'b0;
    reg       addr_match = 1'b0;
    reg       ack_done = 1'b0;

    integer idx;
    initial begin
        for (idx = 0; idx < NUM_REGS; idx = idx + 1)
            mem[idx] = 8'h00;
    end

    always @(scl or sda) begin
        // START or Repeated START: SDA falls while SCL is high
        if (scl === 1'b1 && prev_scl === 1'b1 && prev_sda === 1'b1 && sda === 1'b0) begin
            state       <= 3'd1;
            bit_cnt     <= 4'd0;
            ack_done    <= 1'b0;
            sda_drv_low <= 1'b0;
        end else if (scl === 1'b1 && prev_scl === 1'b1 && prev_sda === 1'b0 && sda === 1'b1) begin
            // STOP: SDA rises while SCL is high
            state        <= 3'd0;
            have_reg_ptr <= 1'b0;
            ack_done     <= 1'b0;
            sda_drv_low  <= 1'b0;
        end else if (scl === 1'b1 && prev_scl === 1'b0) begin
            // Rising edge of SCL: sample SDA
            if (state == 3'd1 || state == 3'd2 || state == 3'd3) begin
                if (bit_cnt < 4'd8) begin
                    shift_reg <= {shift_reg[6:0], (sda !== 1'b0)};
                    bit_cnt   <= bit_cnt + 4'd1;
                end else begin
                    // Bit 8 = ACK slot rising edge
                    bit_cnt <= 4'd0;
                end
            end else if (state == 3'd4) begin
                if (bit_cnt < 4'd8) begin
                    bit_cnt <= bit_cnt + 4'd1;
                end else begin
                    // Master ACK/NACK on bit 8: 0 = ACK -> continue reading, 1 = NACK -> stop
                    bit_cnt <= 4'd0;
                    if (sda === 1'b0) begin
                        reg_ptr <= reg_ptr + 8'd1;
                    end else begin
                        state <= 3'd0;
                    end
                end
            end
        end else if (scl === 1'b0 && prev_scl === 1'b1) begin
            // Falling edge of SCL: drive ACK or read data bit
            if (state == 3'd1 && bit_cnt == 4'd8) begin
                addr_match  = (shift_reg[7:1] == SLAVE_ADDR) && enable_ack;
                rw_bit      = shift_reg[0];
                ack_done   <= 1'b1;
                sda_drv_low <= addr_match ? 1'b1 : 1'b0;
            end else if ((state == 3'd1 || state == 3'd2 || state == 3'd3) && ack_done && (bit_cnt == 4'd0)) begin
                // End of ACK clock -> advance state
                ack_done    <= 1'b0;
                sda_drv_low <= 1'b0;
                if (state == 3'd1) begin
                    if (!addr_match) begin
                        state <= 3'd0;
                    end else if (rw_bit) begin
                        state       <= 3'd4;
                        shift_reg   <= mem[reg_ptr];
                        sda_drv_low <= ~mem[reg_ptr][7];
                    end else begin
                        state <= have_reg_ptr ? 3'd3 : 3'd2;
                    end
                end else if (state == 3'd2) begin
                    reg_ptr      <= shift_reg;
                    have_reg_ptr <= 1'b1;
                    state        <= 3'd3;
                end else if (state == 3'd3) begin
                    mem[reg_ptr] <= shift_reg;
                    reg_ptr      <= reg_ptr + 8'd1;
                end
            end else if ((state == 3'd2 || state == 3'd3) && bit_cnt == 4'd8) begin
                ack_done    <= 1'b1;
                sda_drv_low <= 1'b1; // Drive ACK low for received byte
            end else if (state == 3'd4) begin
                if (bit_cnt == 4'd8) begin
                    sda_drv_low <= 1'b0; // Release SDA for Master ACK/NACK
                end else if (bit_cnt == 4'd0) begin
                    shift_reg   <= mem[reg_ptr];
                    sda_drv_low <= ~mem[reg_ptr][7];
                end else begin
                    sda_drv_low <= ~shift_reg[7 - bit_cnt[2:0]];
                end
            end else begin
                sda_drv_low <= 1'b0;
            end
        end
        prev_scl <= scl;
        prev_sda <= sda;
    end
endmodule

module tb_hk;
    reg sys_clk = 1'b0;
    reg adc_clk = 1'b0;
    reg sys_rst = 1'b1;
    reg adc_rst = 1'b1;

    always #5.0 sys_clk = ~sys_clk; // 100 MHz sys_clk
    always #4.0 adc_clk = ~adc_clk; // 125 MHz adc_clk

    // -------------------------------------------------------------------------
    // 1. HK I2C Bus (TMP1075 0x48 + M24C02 0x50 + ALERT#)
    // -------------------------------------------------------------------------
    tri1 hk_scl_w, hk_sda_w;
    wire hk_scl_t, hk_sda_t;
    assign hk_scl_w = hk_scl_t ? 1'bz : 1'b0;
    assign hk_sda_w = hk_sda_t ? 1'bz : 1'b0;

    reg hk_alert_n = 1'b1;

    tb_i2c_slave #(.SLAVE_ADDR(7'h48)) u_tmp1075 (
        .scl        (hk_scl_w),
        .sda        (hk_sda_w),
        .enable_ack (1'b1)
    );

    tb_i2c_slave #(.SLAVE_ADDR(7'h50)) u_m24c02 (
        .scl        (hk_scl_w),
        .sda        (hk_sda_w),
        .enable_ack (1'b1)
    );

    reg        hk_poll_en     = 1'b0;
    reg        hk_req_valid   = 1'b0;
    wire       hk_req_ready;
    reg [6:0]  hk_req_dev     = 7'd0;
    reg [2:0]  hk_req_wr_len  = 3'd0;
    reg [31:0] hk_req_wdata   = 32'd0;
    reg [1:0]  hk_req_rd_len  = 2'd0;
    wire       hk_req_done;
    wire       hk_req_ack_err;
    wire [15:0] hk_req_rdata;
    wire [15:0] tmp_raw;
    wire       tmp_valid, alert_active, hk_last_ack_err, hk_busy;
    wire [15:0] hk_ack_err_cnt;

    hk_i2c_master #(
        .CLK_DIV  (3),
        .POLL_DIV (500)
    ) u_hk_i2c (
        .clk          (sys_clk),
        .rst          (sys_rst),
        .poll_en      (hk_poll_en),
        .req_valid    (hk_req_valid),
        .req_ready    (hk_req_ready),
        .req_dev_addr (hk_req_dev),
        .req_wr_len   (hk_req_wr_len),
        .req_wdata    (hk_req_wdata),
        .req_rd_len   (hk_req_rd_len),
        .req_done     (hk_req_done),
        .req_ack_err  (hk_req_ack_err),
        .req_rdata    (hk_req_rdata),
        .tmp_raw      (tmp_raw),
        .tmp_valid    (tmp_valid),
        .alert_active (alert_active),
        .last_ack_err (hk_last_ack_err),
        .ack_err_cnt  (hk_ack_err_cnt),
        .busy         (hk_busy),
        .hk_scl_t     (hk_scl_t),
        .hk_scl_in    (hk_scl_w),
        .hk_sda_t     (hk_sda_t),
        .hk_sda_in    (hk_sda_w),
        .hk_alert_n   (hk_alert_n)
    );

    // -------------------------------------------------------------------------
    // 2. XO I2C Bus (Si549 0x55 + CLK_SEL)
    // -------------------------------------------------------------------------
    tri1 xo_scl_w, xo_sda_w;
    wire xo_scl_t, xo_sda_t;
    assign xo_scl_w = xo_scl_t ? 1'bz : 1'b0;
    assign xo_sda_w = xo_sda_t ? 1'bz : 1'b0;

    tb_i2c_slave #(.SLAVE_ADDR(7'h55)) u_si549 (
        .scl        (xo_scl_w),
        .sda        (xo_sda_w),
        .enable_ack (1'b1)
    );

    reg        use_ext_clk    = 1'b0;
    wire       clk_sel_t;
    reg        xo_prog_start  = 1'b0;
    reg        xo_freq_500m   = 1'b0;
    reg        xo_delta_start = 1'b0;
    reg [23:0] xo_delta_m     = 24'd0;
    wire       xo_busy, xo_prog_done, xo_active_500m, xo_ack_err;
    wire [15:0] xo_ack_err_cnt;

    hk_xo_ctrl #(
        .SI549_ADDR    (7'h55),
        .CLK_DIV       (3),
        .FCAL_WAIT_CYC (32)
    ) u_xo_ctrl (
        .clk              (sys_clk),
        .rst              (sys_rst),
        .use_ext_clk      (use_ext_clk),
        .clk_sel_t        (clk_sel_t),
        .prog_start       (xo_prog_start),
        .prog_freq_500m   (xo_freq_500m),
        .delta_start      (xo_delta_start),
        .delta_m          (xo_delta_m),
        .raw_req_valid    (1'b0),
        .raw_req_ready    (),
        .raw_req_rw       (1'b0),
        .raw_req_reg      (8'd0),
        .raw_req_wdata    (8'd0),
        .raw_resp_valid   (),
        .raw_resp_rdata   (),
        .raw_resp_err     (),
        .busy             (xo_busy),
        .prog_done        (xo_prog_done),
        .active_freq_500m (xo_active_500m),
        .ack_err          (xo_ack_err),
        .ack_err_cnt      (xo_ack_err_cnt),
        .xo_scl_t         (xo_scl_t),
        .xo_scl_in        (xo_scl_w),
        .xo_sda_t         (xo_sda_t),
        .xo_sda_in        (xo_sda_w)
    );

    // -------------------------------------------------------------------------
    // 3. XADC + PPS_SYNC Timestamp & PPM Unit
    // -------------------------------------------------------------------------
    reg        pps_sync = 1'b0;
    reg [31:0] nom_period_cyc = 32'd1250;
    reg [15:0] ts_step_q8 = 16'h0800; // 8.0 ns @ 125 MHz
    reg        pps_disc_en = 1'b0;
    wire [11:0] xadc_temp_raw, xadc_vccint_raw, xadc_vccaux_raw;
    wire       xadc_valid, xadc_overtemp;
    wire [63:0] ts_adc, ts_sys, pps_latch_ts;
    wire [31:0] pps_period_cyc, pps_cnt;
    wire signed [31:0] pps_ppm_err;
    wire       pps_locked;

    hk_xadc_pps #(
        .DEFAULT_NOM_CYC (32'd1250),
        .DEFAULT_STEP_Q8 (16'h0800),
        .XADC_POLL_DIV   (64)
    ) u_xadc_pps (
        .sys_clk            (sys_clk),
        .sys_rst            (sys_rst),
        .adc_clk            (adc_clk),
        .adc_rst            (adc_rst),
        .pps_sync           (pps_sync),
        .cfg_nom_period_cyc (nom_period_cyc),
        .cfg_ts_step_q8     (ts_step_q8),
        .cfg_pps_disc_en    (pps_disc_en),
        .cfg_ts_clear       (1'b0),
        .xadc_temp_raw      (xadc_temp_raw),
        .xadc_vccint_raw    (xadc_vccint_raw),
        .xadc_vccaux_raw    (xadc_vccaux_raw),
        .xadc_valid         (xadc_valid),
        .xadc_overtemp      (xadc_overtemp),
        .timestamp_ns_adc   (ts_adc),
        .timestamp_ns_sys   (ts_sys),
        .pps_latch_ts       (pps_latch_ts),
        .pps_period_cyc     (pps_period_cyc),
        .pps_ppm_err        (pps_ppm_err),
        .pps_cnt            (pps_cnt),
        .pps_locked         (pps_locked)
    );

    task automatic hk_do_txn;
        input [6:0]  dev;
        input [2:0]  wlen;
        input [31:0] wdat;
        input [1:0]  rlen;
        output       err_o;
        output [15:0] rdat_o;
        integer wc;
        begin
            wc = 0;
            while (!hk_req_ready && wc < 5000) begin
                @(posedge sys_clk);
                wc = wc + 1;
            end
            if (!hk_req_ready) begin
                $display("FAIL: tb_hk hk_req_ready timeout");
                $finish;
            end
            hk_req_dev    <= dev;
            hk_req_wr_len <= wlen;
            hk_req_wdata  <= wdat;
            hk_req_rd_len <= rlen;
            hk_req_valid  <= 1'b1;
            @(posedge sys_clk);
            hk_req_valid  <= 1'b0;
            wc = 0;
            while (!hk_req_done && wc < 20000) begin
                @(posedge sys_clk);
                wc = wc + 1;
            end
            if (!hk_req_done) begin
                $display("FAIL: tb_hk hk_req_done timeout");
                $finish;
            end
            err_o  = hk_req_ack_err;
            rdat_o = hk_req_rdata;
        end
    endtask

    integer wc;
    reg ack_e;
    reg [15:0] rd_v;
    reg [63:0] ts_before, ts_after;
    reg [42:0] fb_readback;

    initial begin
        // Preload TMP1075 temperature register 0x00 = +42.5 C (0x2A80)
        u_tmp1075.mem[0] = 8'h2A;
        u_tmp1075.mem[1] = 8'h80;

        repeat (20) @(posedge sys_clk);
        sys_rst <= 1'b0;
        adc_rst <= 1'b0;
        repeat (10) @(posedge sys_clk);

        // Test 1: Automatic TMP1075 polling + ALERT# monitoring
        hk_poll_en <= 1'b1;
        wc = 0;
        while (!tmp_valid && wc < 20000) begin
            @(posedge sys_clk);
            wc = wc + 1;
        end
        if (!tmp_valid || tmp_raw !== 16'h2A80) begin
            $display("FAIL: tb_hk TMP1075 poll failed valid=%b tmp_raw=%04x (exp 2A80)", tmp_valid, tmp_raw);
            $finish;
        end
        hk_poll_en <= 1'b0;
        while (hk_busy) @(posedge sys_clk);

        hk_alert_n <= 1'b0;
        repeat (5) @(posedge sys_clk);
        if (alert_active !== 1'b1) begin
            $display("FAIL: tb_hk ALERT# not asserted");
            $finish;
        end
        hk_alert_n <= 1'b1;
        repeat (5) @(posedge sys_clk);

        // Test 2: M24C02 EEPROM (7'h50) byte write + random readback
        hk_do_txn(7'h50, 3'd2, 32'h0000_C31A, 2'd0, ack_e, rd_v); // Addr 0x1A = 0xC3
        if (ack_e || u_m24c02.mem[8'h1A] !== 8'hC3) begin
            $display("FAIL: tb_hk M24C02 write failed err=%b mem=%02x", ack_e, u_m24c02.mem[8'h1A]);
            $finish;
        end
        hk_do_txn(7'h50, 3'd1, 32'h0000_001A, 2'd1, ack_e, rd_v);
        if (ack_e || rd_v[7:0] !== 8'hC3) begin
            $display("FAIL: tb_hk M24C02 readback mismatch err=%b rd=%02x (exp C3)", ack_e, rd_v[7:0]);
            $finish;
        end

        // Test 3: Missing I2C slave NACK detection (probe non-existent 7'h7D)
        hk_do_txn(7'h7D, 3'd1, 32'h0000_0000, 2'd1, ack_e, rd_v);
        if (ack_e !== 1'b1 || hk_ack_err_cnt == 16'd0) begin
            $display("FAIL: tb_hk missing ACK NOT detected on 0x7D (ack_e=%b cnt=%0d)", ack_e, hk_ack_err_cnt);
            $finish;
        end

        // Test 4: Si549 XO programming (400 MHz -> 500 MHz -> ADPLL_DELTA_M -> CLK_SEL)
        if (clk_sel_t !== 1'b1) begin
            $display("FAIL: tb_hk default clk_sel_t expected 1 (Hi-Z Si549)");
            $finish;
        end
        use_ext_clk <= 1'b1;
        @(posedge sys_clk);
        if (clk_sel_t !== 1'b0) begin
            $display("FAIL: tb_hk ext clk_sel_t expected 0");
            $finish;
        end
        use_ext_clk <= 1'b0;

        xo_freq_500m <= 1'b0;
        xo_prog_start <= 1'b1;
        @(posedge sys_clk);
        xo_prog_start <= 1'b0;
        repeat (2) @(posedge sys_clk);
        wc = 0;
        while (!xo_prog_done && wc < 50000) begin
            @(posedge sys_clk);
            wc = wc + 1;
        end
        fb_readback = {u_si549.mem[31][2:0], u_si549.mem[30], u_si549.mem[29],
                       u_si549.mem[28], u_si549.mem[27], u_si549.mem[26]};
        if (!xo_prog_done || xo_ack_err || u_si549.mem[23] !== 8'h1C ||
            fb_readback !== 43'h049_64FDA6C1 || u_si549.mem[17] !== 8'h01) begin
            $display("FAIL: tb_hk Si549 400MHz config mismatch hs=%02x fb=%011x en=%02x",
                     u_si549.mem[23], fb_readback, u_si549.mem[17]);
            $finish;
        end

        xo_freq_500m <= 1'b1;
        xo_prog_start <= 1'b1;
        @(posedge sys_clk);
        xo_prog_start <= 1'b0;
        repeat (2) @(posedge sys_clk);
        wc = 0;
        while (!xo_prog_done && wc < 50000) begin
            @(posedge sys_clk);
            wc = wc + 1;
        end
        fb_readback = {u_si549.mem[31][2:0], u_si549.mem[30], u_si549.mem[29],
                       u_si549.mem[28], u_si549.mem[27], u_si549.mem[26]};
        if (!xo_prog_done || xo_ack_err || !xo_active_500m ||
            u_si549.mem[23] !== 8'h16 || fb_readback !== 43'h048_15791F34) begin
            $display("FAIL: tb_hk Si549 500MHz config mismatch hs=%02x fb=%011x",
                     u_si549.mem[23], fb_readback);
            $finish;
        end

        xo_delta_m     <= 24'h123456;
        xo_delta_start <= 1'b1;
        @(posedge sys_clk);
        xo_delta_start <= 1'b0;
        repeat (5) @(posedge sys_clk);
        wc = 0;
        while (xo_busy && wc < 20000) begin
            @(posedge sys_clk);
            wc = wc + 1;
        end
        if ({u_si549.mem[233], u_si549.mem[232], u_si549.mem[231]} !== 24'h123456) begin
            $display("FAIL: tb_hk Si549 ADPLL_DELTA_M mismatch %02x%02x%02x",
                     u_si549.mem[233], u_si549.mem[232], u_si549.mem[231]);
            $finish;
        end

        // Test 5: XADC DRP polling
        wc = 0;
        while (!xadc_valid && wc < 20000) begin
            @(posedge sys_clk);
            wc = wc + 1;
        end
        if (!xadc_valid) begin
            $display("FAIL: tb_hk XADC did not produce valid DRP telemetry");
            $finish;
        end

        // Test 6: PPS_SYNC period & +800 ppm measurement on adc_clk (1251 vs 1250 nominal)
        ts_before = ts_adc;
        @(posedge adc_clk);
        pps_sync <= 1'b1;
        repeat (8) @(posedge adc_clk);
        pps_sync <= 1'b0;
        repeat (1243) @(posedge adc_clk); // Total = 1251 adc_clk cycles!
        pps_sync <= 1'b1;
        repeat (8) @(posedge adc_clk);
        pps_sync <= 1'b0;
        repeat (1243) @(posedge adc_clk); // Second 1251-cycle period
        pps_sync <= 1'b1;
        repeat (8) @(posedge adc_clk);
        pps_sync <= 1'b0;

        repeat (100) @(posedge sys_clk);
        ts_after = ts_adc;
        if (!pps_locked || pps_period_cyc !== 32'd1251 || pps_ppm_err !== 32'sd800 ||
            ts_after <= ts_before || pps_latch_ts == 64'd0) begin
            $display("FAIL: tb_hk PPS measurement mismatch locked=%b per=%0d (exp 1251) ppm=%0d (exp +800) latch=%0d",
                     pps_locked, pps_period_cyc, pps_ppm_err, pps_latch_ts);
            $finish;
        end

        $display("PASS: tb_hk tmp=%04x eeprom=C3 ack_err_cnt=%0d si549_400/500=ok xadc_t=%03x pps_per=%0d pps_ppm=+%0d",
                 tmp_raw, hk_ack_err_cnt, xadc_temp_raw, pps_period_cyc, pps_ppm_err);
        $finish;
    end
endmodule
`default_nettype wire
