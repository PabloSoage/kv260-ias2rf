// SPDX-License-Identifier: Apache-2.0
// Unit Testbench for kria_radar_proc (64x16 Range-Doppler FFT + CA-CFAR Multi-Target Check)
`timescale 1ns/1ps

module tb_kria_radar_proc;
    reg clk = 1'b0;
    always #5.0 clk = ~clk;

    reg                rst = 1'b1;
    reg                in_valid = 1'b0;
    wire               in_ready;
    reg signed [15:0]  in_i = 16'sd0, in_q = 16'sd0;
    reg                cpi_sync_start = 1'b0;

    wire               rd_out_valid, rd_out_det, cpi_done_pulse;
    wire [5:0]         rd_out_rbin, peak_rbin;
    wire [3:0]         rd_out_dbin, peak_dbin;
    wire [31:0]        rd_out_pwr, peak_pwr;
    wire [15:0]        cpi_det_cnt;

    kria_radar_proc #(
        .RANGE_N   (64),
        .DOPPLER_M (16)
    ) dut (
        .clk               (clk),
        .rst               (rst),
        .in_valid          (in_valid),
        .in_ready          (in_ready),
        .in_i              (in_i),
        .in_q              (in_q),
        .cpi_sync_start    (cpi_sync_start),
        .cfg_win_en        (1'b1),
        .cfg_cfar_alpha_q8 (16'd1536), // 6.0x CA-CFAR threshold
        .cfg_cfar_min_pwr  (32'd50000),
        .rd_out_valid      (rd_out_valid),
        .rd_out_rbin       (rd_out_rbin),
        .rd_out_dbin       (rd_out_dbin),
        .rd_out_pwr        (rd_out_pwr),
        .rd_out_det        (rd_out_det),
        .cpi_done_pulse    (cpi_done_pulse),
        .cpi_det_cnt       (cpi_det_cnt),
        .peak_rbin         (peak_rbin),
        .peak_dbin         (peak_dbin),
        .peak_pwr          (peak_pwr)
    );

    localparam real PI = 3.141592653589793;
    integer m, n;
    real    re_s, im_s;
    integer det_t1 = 0, det_t2 = 0, det_total = 0;

    always @(posedge clk) begin
        if (rd_out_valid && rd_out_det) begin
            det_total = det_total + 1;
            $display("[RADAR DET] rbin=%0d dbin=%0d pwr=%0d", rd_out_rbin, rd_out_dbin, rd_out_pwr);
            if (rd_out_rbin >= 11 && rd_out_rbin <= 13 && rd_out_dbin >= 2 && rd_out_dbin <= 4)
                det_t1 = 1;
            if (rd_out_rbin >= 39 && rd_out_rbin <= 41 && rd_out_dbin >= 11 && rd_out_dbin <= 13)
                det_t2 = 1;
        end
    end

    initial begin
        repeat (5) @(negedge clk);
        rst = 1'b0;

        // Inject CPI: 16 chirps x 64 fast-time samples
        // Target 1 (strong): range bin 12, Doppler bin 3, amp 6000
        // Target 2 (weak, -26 dB): range bin 40, Doppler bin 12, amp 300
        for (m = 0; m < 16; m = m + 1) begin
            for (n = 0; n < 64; n = n + 1) begin
                while (!in_ready) @(posedge clk);
                @(negedge clk);
                re_s = 6000.0 * $cos(2.0 * PI * (12.0 * n / 64.0 + 3.0 * m / 16.0))
                     +  300.0 * $cos(2.0 * PI * (40.0 * n / 64.0 + 12.0 * m / 16.0));
                im_s = 6000.0 * $sin(2.0 * PI * (12.0 * n / 64.0 + 3.0 * m / 16.0))
                     +  300.0 * $sin(2.0 * PI * (40.0 * n / 64.0 + 12.0 * m / 16.0));
                in_valid = 1'b1;
                in_i     = $rtoi(re_s);
                in_q     = $rtoi(im_s);
            end
            @(negedge clk);
            in_valid = 1'b0;
            // Wait for range FFT to finish chirp before streaming next chirp
            while (!in_ready) @(posedge clk);
        end

        // Wait for Doppler FFT + CA-CFAR scan completion
        while (!cpi_done_pulse) @(posedge clk);
        repeat (5) @(posedge clk);

        $display("[RADAR SUMMARY] peak=(%0d,%0d pwr=%0d) det_cnt=%0d det_t1=%0d det_t2=%0d",
                 peak_rbin, peak_dbin, peak_pwr, det_total, det_t1, det_t2);
        if (peak_rbin == 6'd12 && peak_dbin == 4'd3 && det_t1 == 1 && det_t2 == 1)
            $display("PASS: tb_kria_radar_proc (64x16 2D-FFT + CA-CFAR strong+weak targets detected)");
        else
            $display("FAIL: tb_kria_radar_proc missed target or peak mismatch");
        $finish;
    end
endmodule
