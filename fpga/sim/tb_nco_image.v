// tb_nco_image: image rejection of the AERIS DDC's NCO (nco_400m_enhanced inside ddc_400m_enhanced).
//
// The NCO's output L[k] = cos + j*sin should be a pure e^{j*theta[k]}, theta = 2*pi*0.3*k at the 120 MHz LO.
// Any component at e^{-j*theta[k]} mirrors the input around the LO, so a tone 1.5625 MHz above the LO also comes
// out 1.5625 MHz below it. The bench probes the NCO outputs, correlates them with e^{-j*theta} and e^{+j*theta}
// over windows of 40,000 samples (a multiple of 10, so the two references are orthogonal), and requires
// |conjugate| / |wanted| < -70 dB in every window:
//   phase 1: 4 windows at the default FTW (0x4CCCCCCD), from reset;
//   phase 2: 8 windows with ftw_override = 0x4CCCCCCD + 64, so the accumulator's position inside a truncation
//            cell (1/256 cycle) drifts by 1/256 cycle per 2.6e5 samples and the windows see different truncation
//            patterns.
// The upstream NCO left -46 to -61 dB here depending on that position, which tb_system's S3 then read as
// 48 to 61 dB of image rejection from one build to the next.
// Mutations: nco_int_lut (upstream integer-step quarter-wave table), nco_no_phase_dither (truncation without
// dither) each fail.
`timescale 1ns / 1ps

module tb_nco_image;
    localparam real    PI      = 3.14159265358979323846;
    localparam integer WIN     = 40000;
    localparam real    LIM_DB  = -70.0;

    reg clk_400m = 1'b0;
    reg clk_100m = 1'b0;
    always #1.25 clk_400m = ~clk_400m;
    always #5.0  clk_100m = ~clk_100m;

    reg        reset_n = 1'b0;
    reg [31:0] ftw_ovrd = 32'd0;

    ddc_400m_enhanced dut (
        .clk_400m(clk_400m), .clk_100m(clk_100m), .reset_n(reset_n), .mixers_enable(1'b1),
        .adc_data(8'h80), .adc_data_valid_i(1'b1), .adc_data_valid_q(1'b1),
        .baseband_i(), .baseband_q(), .baseband_valid_i(), .baseband_valid_q(),
        .ddc_status(), .ddc_diagnostics(), .mixer_saturation(), .filter_overflow(),
        .test_mode(2'b00), .test_phase_inc(16'd0), .force_saturation(1'b0), .reset_monitors(1'b0),
        .ftw_override(ftw_ovrd), .debug_sample_count(), .debug_internal_i(), .debug_internal_q()
    );

    wire signed [15:0] nco_cos = dut.cos_out;
    wire signed [15:0] nco_sin = dut.sin_out;
    wire               nco_rdy = dut.nco_ready;

    integer errors = 0;
    integer k, w;
    real    th, c, s, a_re, a_im, b_re, b_im, ratio_db, worst_db, a_mag;

    task run_window(input integer idx);
        begin
            a_re = 0.0; a_im = 0.0; b_re = 0.0; b_im = 0.0;
            for (k = 0; k < WIN; k = k + 1) begin
                @(posedge clk_400m);
                th = 2.0 * PI * 0.3 * k;
                c  = $itor(nco_cos);
                s  = $itor(nco_sin);
                // (c + js) * e^{-j th}
                a_re = a_re + c * $cos(th) + s * $sin(th);
                a_im = a_im + s * $cos(th) - c * $sin(th);
                // (c + js) * e^{+j th}
                b_re = b_re + c * $cos(th) - s * $sin(th);
                b_im = b_im + s * $cos(th) + c * $sin(th);
            end
            a_mag    = $sqrt(a_re * a_re + a_im * a_im) / WIN;
            ratio_db = 20.0 * $log10(($sqrt(b_re * b_re + b_im * b_im) / WIN + 1.0e-9) / a_mag);
            if (ratio_db > worst_db) worst_db = ratio_db;
            $display("[NCO] window %0d ftw=%08h |wanted|=%0.1f image=%0.1f dB", idx, dut.phase_inc_dithered,
                     a_mag, ratio_db);
            if (a_mag < 32000.0) begin
                $display("FAIL: window %0d wanted amplitude %0.1f < 32000 (NCO not running?)", idx, a_mag);
                errors = errors + 1;
            end
            if (ratio_db > LIM_DB) begin
                $display("FAIL: window %0d image %0.1f dB > %0.1f dB", idx, ratio_db, LIM_DB);
                errors = errors + 1;
            end
        end
    endtask

    initial begin
        worst_db = -300.0;
        repeat (20) @(posedge clk_100m);
        reset_n = 1'b1;
        wait (nco_rdy);
        repeat (16) @(posedge clk_400m);
        for (w = 0; w < 4; w = w + 1) run_window(w);
        ftw_ovrd = 32'h4CCCCCCD + 32'd64;
        repeat (64) @(posedge clk_400m);
        for (w = 4; w < 12; w = w + 1) run_window(w);
        if (errors == 0)
            $display("PASS: tb_nco_image worst_image_db=%0.1f windows=12", worst_db);
        else
            $display("FAIL: tb_nco_image %0d error(s) worst_image_db=%0.1f", errors, worst_db);
        $finish;
    end
endmodule
