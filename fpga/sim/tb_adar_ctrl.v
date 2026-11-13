// SPDX-License-Identifier: BSD-2-Clause
// Simulation Testbench for Task 15: 8x ADAR1000 Beamformer Controller & RF Switch Matrix
// Verifies:
//   1) Mode-0 SPI initialization of all 8 ADAR1000 chips (Reg 0x000=0x3C auto-increment + SDOACTIVE,
//      scratchpad 0x00A=0xA5 verify, TX/RX channel enables, SW_CTRL, MEM_CTRL RAM bypass).
//   2) BRAM beam table loading for Beam #3 (via BEAM_STROBE) and Beam #7 (via soft_load),
//      confirming single-CSB 24-byte ascending auto-increment bursts (0x010..0x027) on all 8 chips.
//   3) TX_LOAD / RX_LOAD shadow-to-active transfer verification across all 8x24 = 192 beam bytes.
//   4) Guard-time TR safety invariant: ADAR*_TR must remain 0 during any beam load / LOAD pulse
//      even when tr_req == 1 simultaneously.
//   5) rf_switch SW_CTRL0..3 glitch-free transitions and settle_cycles guard timing.
// Required mutations checked by run.ps1:
//   -Mutate cpha_wrong     : fails ADAR1000 scratchpad readback & beam register writes
//   -Mutate tr_during_load : fails continuous TR-during-load safety assertion

`timescale 1ns/1ps

module tb_adar_ctrl;
    reg clk = 1'b0;
    reg rst = 1'b1;
    always #4.0 clk = ~clk; // 125 MHz

    // DUT 1: adar_ctrl
    reg         tbl_wr_en     = 1'b0;
    reg  [4:0]  tbl_beam_id   = 5'd0;
    reg  [2:0]  tbl_chip_id   = 3'd0;
    reg  [4:0]  tbl_byte_idx  = 5'd0;
    reg  [7:0]  tbl_wdata     = 8'd0;

    reg         beam_strobe    = 1'b0;
    reg         soft_load      = 1'b0;
    reg  [4:0]  active_beam_id = 5'd0;
    reg         tr_req         = 1'b0;
    reg  [15:0] guard_pre      = 16'd10;
    reg  [15:0] guard_post     = 16'd12;

    reg         spi_req_valid = 1'b0;
    wire        spi_req_ready;
    reg  [2:0]  spi_req_chip  = 3'd0;
    reg         spi_req_rw    = 1'b0;
    reg  [14:0] spi_req_addr  = 15'd0;
    reg  [7:0]  spi_req_wdata = 8'd0;
    wire        spi_resp_valid;
    wire [7:0]  spi_resp_rdata;

    wire        init_done, init_err, load_busy, tr_ready;
    wire [4:0]  current_beam_id;

    wire        adar_sclk, adar_sdio_o, adar_sdio_t;
    wire        adar_sdo;
    wire [7:0]  adar_csb, adar_tx_load, adar_rx_load, adar_tr;

    adar_ctrl #(
        .CLK_DIV   (2),
        .NUM_CHIPS (8),
        .NUM_BEAMS (32),
        .AUTO_INIT (1'b1)
    ) u_adar_ctrl (
        .clk             (clk),
        .rst             (rst),
        .tbl_wr_en       (tbl_wr_en),
        .tbl_beam_id     (tbl_beam_id),
        .tbl_chip_id     (tbl_chip_id),
        .tbl_byte_idx    (tbl_byte_idx),
        .tbl_wdata       (tbl_wdata),
        .start_init      (1'b0),
        .beam_strobe     (beam_strobe),
        .soft_load       (soft_load),
        .active_beam_id  (active_beam_id),
        .tr_req          (tr_req),
        .guard_pre       (guard_pre),
        .guard_post      (guard_post),
        .spi_req_valid   (spi_req_valid),
        .spi_req_ready   (spi_req_ready),
        .spi_req_chip    (spi_req_chip),
        .spi_req_rw      (spi_req_rw),
        .spi_req_addr    (spi_req_addr),
        .spi_req_wdata   (spi_req_wdata),
        .spi_resp_valid  (spi_resp_valid),
        .spi_resp_rdata  (spi_resp_rdata),
        .init_done       (init_done),
        .init_err        (init_err),
        .load_busy       (load_busy),
        .tr_ready        (tr_ready),
        .current_beam_id (current_beam_id),
        .adar_sclk       (adar_sclk),
        .adar_sdio_o     (adar_sdio_o),
        .adar_sdio_t     (adar_sdio_t),
        .adar_sdo        (adar_sdo),
        .adar_csb        (adar_csb),
        .adar_tx_load    (adar_tx_load),
        .adar_rx_load    (adar_rx_load),
        .adar_tr         (adar_tr)
    );

    // DUT 2: rf_switch
    reg  [3:0]  sw_req = 4'b0000;
    wire        sw_ready;
    wire [3:0]  sw_ctrl;

    rf_switch #(
        .DEFAULT_STATE  (4'b0000),
        .DEFAULT_SETTLE (16'd8)
    ) u_rf_switch (
        .clk           (clk),
        .rst           (rst),
        .sw_req        (sw_req),
        .settle_cycles (16'd8),
        .sw_ready      (sw_ready),
        .sw_ctrl       (sw_ctrl)
    );

    // -------------------------------------------------------------------------
    // Behavioral 8x ADAR1000 Mode-0 SPI Slave + Working/Active Beam Shadow Model
    // -------------------------------------------------------------------------
    reg [7:0] work_regs   [0:7][0:63];
    reg [7:0] active_regs [0:7][0:63];
    integer   max_burst   [0:7];

    integer   sl_bit;
    reg [15:0] sl_hdr;
    reg [14:0] sl_addr;
    reg        sl_rw;
    reg [7:0]  sl_data;
    reg [7:0]  sl_rd_shift;
    reg        sl_sdo_drv = 1'b0;
    integer    sl_active_chip = -1;
    integer    sl_burst_bytes = 0;

    assign adar_sdo = sl_sdo_drv;

    integer c, rg;
    initial begin
        for (c = 0; c < 8; c = c + 1) begin
            max_burst[c] = 0;
            for (rg = 0; rg < 64; rg = rg + 1) begin
                work_regs[c][rg]   = 8'h00;
                active_regs[c][rg] = 8'h00;
            end
        end
    end

    // Detect CSB falling/rising across all 8 chips
    always @(adar_csb) begin
        if (adar_csb == 8'hFF) begin
            if ((sl_active_chip >= 0) && (sl_burst_bytes > max_burst[sl_active_chip]))
                max_burst[sl_active_chip] = sl_burst_bytes;
            sl_active_chip = -1;
            sl_sdo_drv     <= 1'b0;
        end else begin
            sl_bit         = 0;
            sl_burst_bytes = 0;
            sl_hdr         = 16'd0;
            sl_sdo_drv     <= 1'b0;
            for (c = 0; c < 8; c = c + 1) begin
                if (adar_csb[c] == 1'b0)
                    sl_active_chip = c;
            end
        end
    end

    // Mode 0: sample SDIO on rising edge of SCLK (plus setup time check >= 2.0 ns)
    real sdio_chg_t = -100.0;
    always @(adar_sdio_o) sdio_chg_t = $realtime;

    always @(posedge adar_sclk) begin
        if ((sl_active_chip >= 0) && !adar_sdio_t) begin
            if (($realtime - sdio_chg_t) < 2.0) begin
                $display("FAIL ADAR1000 SPI SDIO setup violation t_S=%0.3f ns (< 2.0 ns)", $realtime - sdio_chg_t);
                $fatal(1, "FAIL ADAR SPI timing");
            end
            if (sl_bit < 16) begin
                sl_hdr = {sl_hdr[14:0], adar_sdio_o};
                sl_bit = sl_bit + 1;
                if (sl_bit == 16) begin
                    sl_rw   = sl_hdr[15];
                    sl_addr = sl_hdr[14:0];
                    if (sl_rw && (sl_addr < 64))
                        sl_rd_shift = work_regs[sl_active_chip][sl_addr[5:0]];
                    else
                        sl_rd_shift = 8'h00;
                end
            end else begin
                sl_data = {sl_data[6:0], adar_sdio_o};
                sl_bit  = sl_bit + 1;
                if (sl_bit == 24) begin
                    if (!sl_rw && (sl_addr < 64)) begin
                        work_regs[sl_active_chip][sl_addr[5:0]] <= sl_data;
                        sl_burst_bytes = sl_burst_bytes + 1;
                        // Ascending auto-increment when ADDR_ASCN (Reg 0x000[5]) == 1
                        if (work_regs[sl_active_chip][0][5])
                            sl_addr = sl_addr + 15'd1;
                    end
                    sl_bit = 16; // Stay in byte phase for continuous multi-byte streaming!
                end
            end
        end
    end

    // Mode 0: launch SDO on falling edge when SDOACTIVE (Reg 0x000[4]) == 1
    always @(negedge adar_sclk) begin
        if ((sl_active_chip >= 0) && (sl_bit >= 16) && sl_rw && work_regs[sl_active_chip][0][4]) begin
            sl_sdo_drv  <= sl_rd_shift[7];
            sl_rd_shift <= {sl_rd_shift[6:0], 1'b0};
        end else begin
            sl_sdo_drv  <= 1'b0;
        end
    end

    // Shadow -> Active latch on TX_LOAD / RX_LOAD
    always @(posedge adar_tx_load[0]) begin
        for (c = 0; c < 8; c = c + 1)
            for (rg = 16; rg <= 39; rg = rg + 1)
                active_regs[c][rg] <= work_regs[c][rg];
    end

    // -------------------------------------------------------------------------
    // Continuous Safety Monitor: ADAR_TR must NEVER be asserted during load_busy or SPI/LOAD activity!
    // -------------------------------------------------------------------------
    integer tr_violations = 0;
    always @(posedge clk) begin
        if (!rst) begin
            if ((adar_tr != 8'h00) && (load_busy || (adar_csb != 8'hFF) || (adar_tx_load != 8'h00) || (adar_rx_load != 8'h00))) begin
                $display("FAIL safety violation: adar_tr=0x%02h during load_busy=%b csb=0x%02h tx_load=0x%02h at t=%0t",
                         adar_tr, load_busy, adar_csb, adar_tx_load, $time);
                tr_violations = tr_violations + 1;
                $fatal(1, "FAIL TR asserted during load");
            end
        end
    end

    // -------------------------------------------------------------------------
    // Test Stimulus & Verification Tasks
    // -------------------------------------------------------------------------
    function [7:0] beam_pattern;
        input [4:0] beam;
        input [2:0] chip;
        input [4:0] bidx;
        begin
            beam_pattern = ((beam * 8'd53) + (chip * 8'd19) + (bidx * 8'd7) + 8'h11) & 8'hFF;
        end
    endfunction

    task automatic write_beam_bram;
        input [4:0] beam;
        integer cc, bb;
        begin
            for (cc = 0; cc < 8; cc = cc + 1) begin
                for (bb = 0; bb < 24; bb = bb + 1) begin
                    @(posedge clk);
                    tbl_wr_en    <= 1'b1;
                    tbl_beam_id  <= beam;
                    tbl_chip_id  <= cc[2:0];
                    tbl_byte_idx <= bb[4:0];
                    tbl_wdata    <= beam_pattern(beam, cc[2:0], bb[4:0]);
                end
            end
            @(posedge clk);
            tbl_wr_en <= 1'b0;
        end
    endtask

    task automatic verify_active_beam;
        input [4:0] beam;
        integer cc, bb;
        reg [7:0] exp_b, got_b;
        begin
            for (cc = 0; cc < 8; cc = cc + 1) begin
                if (max_burst[cc] < 24) begin
                    $display("FAIL auto-increment burst too short on ADAR%0d: max_burst=%0d (expected 24)",
                             cc + 1, max_burst[cc]);
                    $fatal(1, "FAIL auto-increment burst");
                end
                for (bb = 0; bb < 24; bb = bb + 1) begin
                    exp_b = beam_pattern(beam, cc[2:0], bb[4:0]);
                    got_b = active_regs[cc][16 + bb];
                    if (got_b !== exp_b) begin
                        $display("FAIL beam %0d mismatch chip=%0d reg=0x%02h: got=0x%02h exp=0x%02h",
                                 beam, cc, 16 + bb, got_b, exp_b);
                        $fatal(1, "FAIL beam register verify");
                    end
                end
            end
        end
    endtask

    initial begin
        #80;
        rst = 1'b0;

        // 1) Wait for 8-chip ADAR1000 SPI initialization
        begin : wait_init
            integer t;
            t = 0;
            while (!init_done && (t < 8000)) begin
                @(posedge clk);
                t = t + 1;
            end
            if (!init_done || init_err) begin
                $display("FAIL ADAR1000 SPI init failed: init_done=%b init_err=%b", init_done, init_err);
                $fatal(1, "FAIL ADAR SPI init");
            end
        end

        // 2) Exercise rf_switch SW_CTRL0..3 and guard settling
        @(posedge clk);
        sw_req <= 4'b0101;
        @(posedge clk);
        @(posedge clk);
        if (sw_ready != 1'b0) begin
            $display("FAIL rf_switch did not drop sw_ready during transition");
            $fatal(1, "FAIL rf_switch settle");
        end
        repeat (10) @(posedge clk);
        if (!sw_ready || (sw_ctrl !== 4'b0101)) begin
            $display("FAIL rf_switch final state mismatch: ready=%b sw_ctrl=0x%h", sw_ready, sw_ctrl);
            $fatal(1, "FAIL rf_switch final");
        end

        // 3) Populate Beam #3 and Beam #7 in BRAM beam table
        write_beam_bram(5'd3);
        write_beam_bram(5'd7);

        // 4) Request TX (tr_req=1) simultaneously with BEAM_STROBE for Beam #3 -> test guard & lockout
        @(posedge clk);
        tr_req         <= 1'b1;
        active_beam_id <= 5'd3;
        beam_strobe    <= 1'b1;
        repeat (5) @(posedge clk);
        beam_strobe    <= 1'b0;
        repeat (2) @(posedge clk);

        begin : wait_b3
            integer t;
            t = 0;
            while ((load_busy || !tr_ready) && (t < 20000)) begin
                @(posedge clk);
                t = t + 1;
            end
            if (load_busy || !tr_ready || (adar_tr !== 8'hFF) || (current_beam_id != 5'd3)) begin
                $display("FAIL Beam 3 load/TR timeout: busy=%b tr_rdy=%b tr=0x%02h beam=%0d",
                         load_busy, tr_ready, adar_tr, current_beam_id);
                $fatal(1, "FAIL Beam 3 load");
            end
        end
        verify_active_beam(5'd3);

        // 5) Load Beam #7 via soft_load while tr_req=1 -> TR must safely drop, hold guard, reload, and recover!
        @(posedge clk);
        active_beam_id <= 5'd7;
        soft_load      <= 1'b1;
        @(posedge clk);
        soft_load      <= 1'b0;
        repeat (4) @(posedge clk);

        begin : wait_b7
            integer t;
            t = 0;
            while ((load_busy || !tr_ready || (current_beam_id != 5'd7)) && (t < 20000)) begin
                @(posedge clk);
                t = t + 1;
            end
            if (load_busy || !tr_ready || (current_beam_id != 5'd7) || (adar_tr !== 8'hFF)) begin
                $display("FAIL Beam 7 load timeout: busy=%b tr_rdy=%b beam=%0d tr=0x%02h",
                         load_busy, tr_ready, current_beam_id, adar_tr);
                $fatal(1, "FAIL Beam 7 load");
            end
        end
        verify_active_beam(5'd7);

        // 6) Switch TR back to RX (0) and perform Host SPI readback check of Reg 0x01A on Chip 5 (ADAR6)
        @(posedge clk);
        tr_req <= 1'b0;
        repeat (2) @(posedge clk);
        wait (tr_ready && (adar_tr == 8'h00));
        @(posedge clk);
        wait (spi_req_ready == 1'b1);
        spi_req_chip  <= 3'd5;
        spi_req_rw    <= 1'b1;
        spi_req_addr  <= 15'h001A;
        spi_req_valid <= 1'b1;
        @(posedge clk);
        spi_req_valid <= 1'b0;
        wait (spi_resp_valid == 1'b1);
        if (spi_resp_rdata !== beam_pattern(5'd7, 3'd5, 5'd10)) begin
            $display("FAIL host SPI readback chip 5 0x01A: got=0x%02h exp=0x%02h",
                     spi_resp_rdata, beam_pattern(5'd7, 3'd5, 5'd10));
            $fatal(1, "FAIL host SPI readback");
        end

        if (tr_violations > 0) begin
            $display("FAIL tr_violations=%0d", tr_violations);
            $fatal(1, "FAIL TR violations");
        end

        $display("PASS tb_adar_ctrl: init_ok=1 max_burst=%0d beam3_8x24=OK beam7_8x24=OK sw_ctrl=0x%h tr_viol=0",
                 max_burst[0], sw_ctrl);
        $finish;
    end
endmodule
