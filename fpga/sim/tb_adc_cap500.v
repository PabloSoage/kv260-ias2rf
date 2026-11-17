// SPDX-License-Identifier: Apache-2.0
// Rev08 G-7 bench: adc_capture in 500 MSPS mode (mode_500 = 1).
// The AD9484 model of tb_adc_ddc at 500 MSPS: 250 MHz inverted DCO, per-bit skew -90..+5 ps, +/-80 ps edge
// uncertainty (2.000 ns UI). link_clk is the DCO divided by 2 (frequency-locked, as on the board, where both
// come from the 500 MHz master clock), refclk_200m is free-running.
// Checks:
//   1. With the DCO MMCM held in reset (mmcm_locked = 0), training on refclk_200m locks, eye >= 4 taps
//   2. After training, a ramp (sample n = n mod 256): every d2_word holds four consecutive codes, earliest in
//      [8:0], each word following the last, over 4000 words, d2_valid every link_clk cycle, no slip
//   3. mode_500 = 0 afterwards: the MMCM locks and 400 MSPS training still works at a 200 MHz DCO
// Mutation: d2_word_order (pairs swapped in the word) fails check 2.

`timescale 1ns/1ps

module tb_adc_cap500;
    reg refclk_200m = 1'b0;
    always #2.500 refclk_200m = ~refclk_200m;

    reg  fast = 1'b1;                 // 1: 500 MSPS, 0: 400 MSPS
    reg  clk_adc = 1'b0;              // sample clock
    reg  dco_true = 1'b0;
    reg  link_clk = 1'b0;
    always begin #(fast ? 1.000 : 1.250); clk_adc = ~clk_adc; end
    initial begin
        #1.400;
        forever begin #(fast ? 2.000 : 2.500); dco_true = ~dco_true; end
    end
    // link_clk = DCO / 2 in 500 MSPS mode
    always @(posedge dco_true) if (fast) link_clk <= #0.7 ~link_clk;

    reg rst = 1'b1, mode_500 = 1'b1, d2_link_rst = 1'b1;
    reg train_start = 1'b0, train_pattern_en = 1'b1;

    integer sample_idx = 0;
    reg [7:0] adc_sample_raw = 8'hAA;
    always @(posedge clk_adc) begin
        adc_sample_raw <= train_pattern_en ? (sample_idx[0] ? 8'h55 : 8'hAA) : sample_idx[7:0];
        sample_idx <= sample_idx + 1;
    end

    reg [31:0] eye_prng = 32'hCAFE_BABE;
    always @(posedge clk_adc)
        eye_prng <= {eye_prng[30:0], eye_prng[31] ^ eye_prng[21] ^ eye_prng[1] ^ eye_prng[0]};
    reg dco_board_del = 1'b0;
    always @(dco_true) dco_board_del <= #0.250 dco_true;
    wire adcr_dco_n_pin = ~dco_board_del;
    wire adcr_dco_p_pin =  dco_board_del;

    reg [7:0] d_e = 8'd0, d_c = 8'd0, d_l = 8'd0;
    genvar gb;
    generate
        for (gb = 0; gb < 8; gb = gb + 1) begin : g_skew
            localparam real DEL = 0.160 + 0.095 * gb / 7.0;
            always @(adc_sample_raw[gb]) begin
                d_e[gb] <= #(DEL - 0.080) adc_sample_raw[gb];
                d_c[gb] <= #DEL adc_sample_raw[gb];
                d_l[gb] <= #(DEL + 0.080) adc_sample_raw[gb];
            end
        end
    endgenerate
    wire [7:0] adcr_d_p = ((d_e ^ d_l) & {8{eye_prng[0]}}) ? ~d_c : d_c;
    wire [7:0] adcr_d_n = ~adcr_d_p;

    wire        clk_400m_cap, clk_100m_cap, mmcm_locked;
    wire [7:0]  cap_data;
    wire        cap_or, cap_valid, adc_trained, dco_phase_err;
    wire [39:0] tap_flat;
    wire [5:0]  eye_width_min;
    wire [35:0] d2_word;
    wire        d2_valid, d2_slip;

    adc_capture #(.DCO_INVERT(1'b1), .DCO_PERIOD_NS(5.000), .REFCLK_FREQ_MHZ(200.0), .INST_IDELAYCTRL(1'b1)) dut (
        .rst(rst), .refclk_200m(refclk_200m),
        .adcr_d_p(adcr_d_p), .adcr_d_n(adcr_d_n), .adcr_or_p(1'b0), .adcr_or_n(1'b1),
        .adcr_dco_n_pin(adcr_dco_n_pin), .adcr_dco_p_pin(adcr_dco_p_pin),
        .train_start(train_start), .train_pattern_en(train_pattern_en),
        .mode_500(mode_500), .link_clk(link_clk), .d2_link_rst(d2_link_rst), .d2_slip_clr(1'b0),
        .d2_word(d2_word), .d2_valid(d2_valid), .d2_slip(d2_slip),
        .clk_400m(clk_400m_cap), .clk_100m(clk_100m_cap), .mmcm_locked(mmcm_locked),
        .adc_data(cap_data), .adc_or(cap_or), .adc_valid(cap_valid),
        .adc_trained(adc_trained), .dco_phase_err(dco_phase_err), .tap_flat(tap_flat), .eye_width_min(eye_width_min));

    // ramp check on link_clk
    integer n_words = 0, n_bad = 0, n_gap = 0, k;
    reg     checking = 1'b0, have_last = 1'b0;
    reg [7:0] last_code, exp_code;
    always @(posedge link_clk) begin
        if (checking) begin
            if (!d2_valid) n_gap = n_gap + 1;
            else begin
                for (k = 0; k < 4; k = k + 1) begin
                    exp_code = last_code + 8'd1 + k[7:0];
                    if (have_last && d2_word[9 * k +: 8] !== exp_code) begin
                        n_bad = n_bad + 1;
                        if (n_bad < 6) $display("[CAP500] word %0d lane %0d: %h after %h (%h)", n_words, k,
                                                d2_word[9 * k +: 8], last_code, d2_word);
                    end
                end
                if (!have_last && (d2_word[16:9] !== d2_word[7:0] + 8'd1 || d2_word[25:18] !== d2_word[7:0] + 8'd2
                                   || d2_word[34:27] !== d2_word[7:0] + 8'd3)) n_bad = n_bad + 1;
                last_code = d2_word[34:27];
                have_last = 1'b1;
                n_words = n_words + 1;
            end
        end
    end

    task train(output ok);
        integer wt;
        begin
            train_pattern_en = 1'b1;
            #100.0 train_start = 1'b1;
            #50.0  train_start = 1'b0;
            wt = 0;
            while (!adc_trained && !dco_phase_err && wt < 40000) begin #5.0; wt = wt + 1; end
            ok = adc_trained && !dco_phase_err && eye_width_min >= 4;
            $display("[CAP500] %s training: trained %0d err %0d eye %0d taps (D0 tap %0d), MMCM locked %0d",
                     fast ? "500 MSPS" : "400 MSPS", adc_trained, dco_phase_err, eye_width_min, tap_flat[4:0],
                     mmcm_locked);
        end
    endtask

    integer errors = 0;
    reg ok;
    initial begin
        #200.0 rst = 1'b0;
        #500.0 d2_link_rst = 1'b0;
        train(ok);
        if (!ok || mmcm_locked) errors = errors + 1;
        train_pattern_en = 1'b0;
        #400.0 checking = 1'b1;
        wait (n_words >= 4000);
        @(posedge link_clk) checking = 1'b0;
        $display("[CAP500] ramp: %0d words, %0d bad lanes, %0d gaps, slip %0d", n_words, n_bad, n_gap, d2_slip);
        if (n_bad != 0 || n_gap != 0 || d2_slip) errors = errors + 1;

        // back to 400 MSPS: reset, mode_500 = 0, 200 MHz DCO
        rst = 1'b1; d2_link_rst = 1'b1;
        #100.0 fast = 1'b0; mode_500 = 1'b0;
        #200.0 rst = 1'b0;
        begin : wait_lock
            integer w;
            w = 0;
            while (!mmcm_locked && w < 20000) begin #5.0; w = w + 1; end
        end
        #200.0 train(ok);
        if (!ok || !mmcm_locked) errors = errors + 1;

        if (errors == 0) $display("PASS: tb_adc_cap500");
        else             $display("FAIL: tb_adc_cap500, %0d errors", errors);
        $finish;
    end

    initial begin
        #2000000.0;
        $display("FAIL: tb_adc_cap500 timeout");
        $finish;
    end
endmodule
