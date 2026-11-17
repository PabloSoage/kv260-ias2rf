// SPDX-License-Identifier: Apache-2.0
// Rev08 G-7 bench: ddc_500, the 500 MSPS DDC (four samples per 125 MHz clock, 25 MSPS out).
// A real tone through an 8-bit ADC model (code = floor(u) + 128, Gaussian noise of 0.4 LSB) in words of four
// samples; the output measured by correlation at the expected baseband frequency.
// Checks:
//   gain    NCO 101.3 MHz, offsets +1, +5, +9, -7 MHz: |bb| within 0.25 dB of 97.63 * A * CIC droop
//   image   the +5 MHz tone at least 60 dB down at -5 MHz; with CONJ the tone at -5 MHz and +5 MHz 60 dB down
//   alias   +103 MHz (folds to +3 at 100 MSPS) at least 60 dB down; +21 MHz (folds to -4 at 25 MSPS) 40 dB down
//   lanes   NCO 187.5 MHz, +3 MHz: a lane-order error puts the real input's negative frequency at -3 MHz;
//           at least 50 dB down
//   SNR     A = 120, +2.1 MHz: at least 50 dB in the 25 MSPS band (about 54 dB expected for 0.4 LSB noise)
//   rate    exactly one output per 5 clocks
//   packets 512-byte packets, monotonic sequence, no drops, payload = the bb samples
// Mutations: d2_nco_lane0 (fails gain), d2_lane_swap (fails lanes).

`timescale 1ns/1ps

module tb_ddc_500;
    localparam real PI = 3.14159265358979323846;
    localparam real FS = 500.0e6;
    reg clk = 0;
    always #4 clk = ~clk;                       // link_clk, 125 MHz

    reg         rst = 1, en = 0, conj = 0;
    reg  [31:0] ftw = 32'd0;
    reg  [35:0] word = 36'd0;
    reg         word_valid = 0;
    wire [7:0]  pk_code;
    wire        pk_or, pk_valid;
    wire        bb_valid;
    wire signed [15:0] bb_i, bb_q;
    wire        pkt_valid, pkt_sop, pkt_eop;
    wire [7:0]  pkt_sid;
    wire [15:0] pkt_len;
    wire [31:0] pkt_seq;
    wire [63:0] pkt_ts, pkt_data;
    wire [23:0] dropped;
    reg  [63:0] ts = 64'd0;
    always @(posedge clk) ts <= ts + 1;

    ddc_500 dut (.clk(clk), .rst(rst), .en(en), .ftw(ftw), .conj(conj), .word(word), .word_valid(word_valid),
        .pk_code(pk_code), .pk_or(pk_or), .pk_valid(pk_valid),
        .bb_valid(bb_valid), .bb_i(bb_i), .bb_q(bb_q), .timestamp_cnt(ts),
        .pkt_valid(pkt_valid), .pkt_ready(1'b1), .pkt_sop(pkt_sop), .pkt_eop(pkt_eop), .pkt_stream_id(pkt_sid),
        .pkt_len(pkt_len), .pkt_seq(pkt_seq), .pkt_timestamp(pkt_ts), .pkt_data(pkt_data), .dropped_cnt(dropped), .pkt_busy());

    integer errors = 0;
    function real droop(input real d);           // |CIC5 R5| at offset d
        real h;
        begin
            h = (d == 0.0) ? 1.0 : $sin(5.0 * PI * d / FS) / (5.0 * $sin(PI * d / FS));
            h = h * h * h * h * h;
            droop = (h < 0.0) ? -h : h;
        end
    endfunction

    // ---------------------------------------------------------------- measurement
    real    fm1, fm2, a1r, a1i, a2r, a2i, ptot, ph, wh, wsum, a0r, a0i;
    integer n_out, n_skip, n_clk, n_val, c_first, c_last;
    reg     collecting = 0;
    always @(posedge clk) begin
        if (collecting) n_clk = n_clk + 1;
        if (collecting && bb_valid) begin
            if (n_val == 0) c_first = n_clk;
            c_last = n_clk;
            n_val = n_val + 1;
            if (n_skip > 0) n_skip = n_skip - 1;
            else begin
                wh  = 0.5 - 0.5 * $cos(2.0 * PI * n_out / 2048.0);   // Hann: leakage far below the checks
                wsum = wsum + wh;
                ph  = 2.0 * PI * fm1 * n_out / 25.0e6;
                a0r = a0r + bb_i * $cos(ph) + bb_q * $sin(ph);     // unweighted: the least-squares tone for SNR
                a0i = a0i + bb_q * $cos(ph) - bb_i * $sin(ph);
                a1r = a1r + wh * (bb_i * $cos(ph) + bb_q * $sin(ph));
                a1i = a1i + wh * (bb_q * $cos(ph) - bb_i * $sin(ph));
                ph  = 2.0 * PI * fm2 * n_out / 25.0e6;
                a2r = a2r + wh * (bb_i * $cos(ph) + bb_q * $sin(ph));
                a2i = a2i + wh * (bb_q * $cos(ph) - bb_i * $sin(ph));
                ptot = ptot + 1.0 * bb_i * bb_i + 1.0 * bb_q * bb_q;
                n_out = n_out + 1;
            end
        end
    end

    // ---------------------------------------------------------------- packet check: payload against bb
    reg [31:0] bbq [0:16383];
    integer    bb_wr = 0, bb_rd = 0, pkt_err = 0, n_pkt = 0;
    reg [31:0] last_seq;
    reg        first_pkt = 1;
    always @(posedge clk) begin
        if (rst) begin bb_wr = 0; bb_rd = 0; first_pkt = 1; end
        if (bb_valid && en && !rst) begin bbq[bb_wr % 16384] = {bb_q, bb_i}; bb_wr = bb_wr + 1; end
        if (pkt_valid && !rst) begin
            if (pkt_sop) begin
                if (pkt_sid != 8'h01 || pkt_len != 16'd512) pkt_err = pkt_err + 1;
                if (!first_pkt && pkt_seq != last_seq + 1) pkt_err = pkt_err + 1;
                first_pkt = 0;
                last_seq = pkt_seq; n_pkt = n_pkt + 1;
            end
            if (pkt_data[31:0] !== bbq[bb_rd % 16384] || pkt_data[63:32] !== bbq[(bb_rd + 1) % 16384])
                pkt_err = pkt_err + 1;
            bb_rd = bb_rd + 2;
        end
    end

    // ---------------------------------------------------------------- stimulus
    integer seed = 7;
    function [8:0] adc(input real u);
        real f;
        integer c;
        begin
            f = $floor(u);
            c = $rtoi(f) + 128;
            if (c > 255) c = 255;
            if (c < 0) c = 0;
            adc = {1'b0, c[7:0]};
        end
    endfunction

    // run: NCO f_nco, tone at f_nco + d (real, amplitude amp codes), measure at m1 and m2 (Hz at 25 MSPS)
    task run(input real f_nco, input real d, input real amp, input real m1, input real m2, input c,
             output real g1_db, output real g2_db, output real snr_db);
        integer k, w;
        real    u, a_ref, a0, a1, a2, pn;
        reg [35:0] wd;
        begin
            rst = 1; en = 0; conj = c; word_valid = 0;
            ftw = $rtoi(f_nco / FS * 4294967296.0 + 0.5);
            repeat (8) @(posedge clk);
            rst = 0; en = 1;
            fm1 = m1; fm2 = m2; a1r = 0; a1i = 0; a2r = 0; a2i = 0; ptot = 0; wsum = 0; a0r = 0; a0i = 0; n_out = 0; n_skip = 200;
            n_clk = 0; n_val = 0; collecting = 1;
            w = 0;
            while (n_out < 2048) begin
                @(negedge clk);
                for (k = 0; k < 4; k = k + 1) begin
                    u = amp * $cos(2.0 * PI * (f_nco + d) * (4.0 * w + k) / FS + 0.3)
                        + $dist_normal(seed, 0, 400) / 1000.0;
                    wd[9 * k +: 9] = adc(u);
                end
                word = wd; word_valid = 1;
                w = w + 1;
            end
            collecting = 0;
            a_ref = 97.63 * amp * droop(d);
            a1 = $sqrt(a1r * a1r + a1i * a1i) / wsum;
            a2 = $sqrt(a2r * a2r + a2i * a2i) / wsum;
            g1_db = 20.0 * $log10(a1 / a_ref + 1.0e-12);
            g2_db = 20.0 * $log10(a2 / a_ref + 1.0e-12);
            a0 = $sqrt(a0r * a0r + a0i * a0i) / n_out;
            pn = ptot / n_out - a0 * a0;
            snr_db = 10.0 * $log10(a0 * a0 / (pn > 1.0e-9 ? pn : 1.0e-9));
            if ((c_last - c_first) != 5 * (n_val - 1)) begin
                $display("[D2] rate: %0d outputs in %0d clocks", n_val, c_last - c_first);
                errors = errors + 1;
            end
        end
    endtask

    real g, gi, snr, x1, x2, x3;
    initial begin
        // gain and image, NCO 101.3 MHz
        run(101.3e6,  1.0e6, 100.0,  1.0e6, -1.0e6, 0, g, gi, snr);
        $display("[D2] +1 MHz: gain %.3f dB, image %.1f dB", g, gi);
        if (g < -0.25 || g > 0.25) errors = errors + 1;
        run(101.3e6,  5.0e6, 100.0,  5.0e6, -5.0e6, 0, g, gi, snr);
        $display("[D2] +5 MHz: gain %.3f dB, image %.1f dB", g, gi);
        if (g < -0.25 || g > 0.25 || gi > -60.0) errors = errors + 1;
        run(101.3e6,  9.0e6, 100.0,  9.0e6, -9.0e6, 0, g, gi, snr);
        $display("[D2] +9 MHz: gain %.3f dB, image %.1f dB", g, gi);
        if (g < -0.25 || g > 0.25) errors = errors + 1;
        run(101.3e6, -7.0e6, 100.0, -7.0e6,  7.0e6, 0, g, gi, snr);
        $display("[D2] -7 MHz: gain %.3f dB, image %.1f dB", g, gi);
        if (g < -0.25 || g > 0.25 || gi > -60.0) errors = errors + 1;
        // CONJ
        run(101.3e6,  5.0e6, 100.0, -5.0e6,  5.0e6, 1, g, gi, snr);
        $display("[D2] CONJ +5 MHz: at -5 MHz %.3f dB, at +5 MHz %.1f dB", g, gi);
        if (g < -0.25 || g > 0.25 || gi > -60.0) errors = errors + 1;
        // aliases (the reference is the tone's own expected level at the measured offset)
        run(101.3e6, 103.0e6, 100.0, 3.0e6, 3.0e6, 0, g, gi, snr);
        x1 = g + 20.0 * $log10(droop(103.0e6) / droop(3.0e6));
        $display("[D2] +103 MHz -> +3 MHz: %.1f dB", x1);
        if (x1 > -60.0) errors = errors + 1;
        run(101.3e6, 21.0e6, 100.0, -4.0e6, -4.0e6, 0, g, gi, snr);
        x2 = g + 20.0 * $log10(droop(21.0e6) / droop(4.0e6));
        $display("[D2] +21 MHz -> -4 MHz: %.1f dB", x2);
        if (x2 > -40.0) errors = errors + 1;
        // lane order
        run(187.5e6, 3.0e6, 100.0, 3.0e6, -3.0e6, 0, g, gi, snr);
        $display("[D2] NCO 187.5 MHz +3 MHz: gain %.3f dB, at -3 MHz %.1f dB", g, gi);
        if (g < -0.25 || g > 0.25 || gi > -50.0) errors = errors + 1;
        // SNR
        run(101.3e6, 2.1e6, 120.0, 2.1e6, -2.1e6, 0, g, gi, snr);
        $display("[D2] A = 120 +2.1 MHz: gain %.3f dB, SNR %.1f dB", g, snr);
        if (snr < 50.0) errors = errors + 1;
        repeat (2000) @(posedge clk);
        $display("[D2] packets %0d, packet errors %0d, dropped %0d", n_pkt, pkt_err, dropped);
        if (n_pkt < 5 || pkt_err != 0 || dropped != 0) errors = errors + 1;
        if (errors == 0) $display("PASS: tb_ddc_500");
        else             $display("FAIL: tb_ddc_500, %0d errors", errors);
        $finish;
    end
endmodule
