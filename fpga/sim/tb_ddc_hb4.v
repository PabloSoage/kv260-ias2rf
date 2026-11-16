// SPDX-License-Identifier: Apache-2.0
// Rev08 G-8 bench: ddc_hb4, the radar DDC's anti-alias decimation 100 -> 25 MSPS.
// A complex tone at 100 MSPS; the output's amplitude at the tone's (folded) frequency, by correlation.
// Checks: gain within 0.2 dB of 1 at 1, 5 and 9 MHz; tones at 30 and -40 MHz (folding to 5 and 10 MHz) at
// least 40 dB down. Mutation no_aa_filter (one sample in four, the old behaviour) fails the alias checks.

`timescale 1ns/1ps

module tb_ddc_hb4;
    reg clk = 0;
    always #5 clk = ~clk;
    reg rst = 1;
    reg in_valid = 0;
    reg signed [15:0] in_i = 0, in_q = 0;
    wire out_valid;
    wire signed [15:0] out_i, out_q;
    ddc_hb4 dut (.clk(clk), .rst(rst), .in_valid(in_valid), .in_i(in_i), .in_q(in_q),
        .out_valid(out_valid), .out_i(out_i), .out_q(out_q));

    localparam real PI = 3.14159265358979;
    real f_in, f_out, acc_r, acc_i, ph;
    integer n_in, n_out, errors;
    reg collecting;

    always @(posedge clk) begin
        if (collecting && out_valid) begin
            ph = 2.0 * PI * f_out * n_out / 25.0e6;
            acc_r = acc_r + out_i * $cos(ph) + out_q * $sin(ph);
            acc_i = acc_i + out_q * $cos(ph) - out_i * $sin(ph);
            n_out = n_out + 1;
        end
    end

    task tone(input real f, input real f_fold, output real gain_db);
        integer k;
        begin
            rst = 1; repeat (4) @(posedge clk); rst = 0;
            f_out = f_fold; acc_r = 0; acc_i = 0; n_out = 0; collecting = 0;
            for (k = 0; k < 8192; k = k + 1) begin
                @(negedge clk);
                in_valid = 1;
                in_i = $rtoi(16000.0 * $cos(2.0 * PI * f * k / 100.0e6));
                in_q = $rtoi(16000.0 * $sin(2.0 * PI * f * k / 100.0e6));
                if (k == 400) collecting = 1;          // past the filters' fill
            end
            @(negedge clk); in_valid = 0; collecting = 0;
            gain_db = 20.0 * $log10($sqrt(acc_r * acc_r + acc_i * acc_i) / n_out / 16000.0 + 1.0e-12);
        end
    endtask

    real g1, g5, g9, a30, a40;
    initial begin
        errors = 0;
        tone(1.0e6, 1.0e6, g1);
        tone(5.0e6, 5.0e6, g5);
        tone(9.0e6, 9.0e6, g9);
        tone(30.0e6, 5.0e6, a30);
        tone(-40.0e6, 10.0e6, a40);
        $display("[HB4] pass 1/5/9 MHz %.3f %.3f %.3f dB, 30 MHz -> 5 MHz %.1f dB, -40 MHz -> 10 MHz %.1f dB",
                 g1, g5, g9, a30, a40);
        if (g1 < -0.2 || g1 > 0.2 || g5 < -0.2 || g5 > 0.2 || g9 < -0.2 || g9 > 0.2) errors = errors + 1;
        if (a30 > -40.0) errors = errors + 1;
        if (a40 > -40.0) errors = errors + 1;
        if (errors == 0) $display("PASS: tb_ddc_hb4");
        else $display("FAIL: tb_ddc_hb4, %0d errors", errors);
        $finish;
    end
endmodule
