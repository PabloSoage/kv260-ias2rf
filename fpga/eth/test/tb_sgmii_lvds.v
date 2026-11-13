// SPDX-License-Identifier: BSD-2-Clause
// tb_sgmii_lvds.v - XSim testbench for XAPP523-style 1.25 Gb/s asynchronous SGMII
// oversampling receiver (sgmii_lvds_rx) against +/-100 ppm PRBS-7 streams.
//
// Tests:
//   1) +100 ppm offset (UI = 799.920 ps): 64x K28.5 commas + 30,000 PRBS-7 bits
//      (> 3.0 UI total phase walk across P/N phase boundaries) -> 0 errors.
//   2) -100 ppm offset (UI = 800.080 ps): 64x K28.5 commas + 30,000 PRBS-7 bits
//      (> 3.0 UI total phase walk in opposite direction) -> 0 errors.
//
// Mutation (via xvlog -d MUTATE_NO_PHASE_SELECT):
//   Freezes phase_sel at 0 without phase handover; must fail under +/-100 ppm drift.

`timescale 1ps/1fs
`default_nettype none

module tb_sgmii_lvds;

    localparam [9:0] K28_5_RD_NEG = 10'h17C;
    localparam [9:0] K28_5_RD_POS = 10'h283;
    localparam integer NUM_COMMAS     = 80;
    localparam integer NUM_PRBS_WORDS = 3000; // 30,000 bits => +/-3.0 UI walk @ +/-100 ppm

    // Local 625 MHz (1600 ps period), 312.5 MHz, and 125 MHz receiver clocks
    reg clk_625_0 = 1'b0;
    always #800.000 clk_625_0 = ~clk_625_0;

    wire #400.000 clk_625_90 = clk_625_0;

    reg clk_312p5 = 1'b0;
    always @(posedge clk_625_0) clk_312p5 <= ~clk_312p5;

    wire #400.000 clk_312p5_45 = clk_312p5;

    reg clk_125 = 1'b0;
    always #4000.000 clk_125 = ~clk_125;

    reg clk_200m = 1'b0;
    always #2500.000 clk_200m = ~clk_200m;

    reg  rst_312p5 = 1'b1;
    reg  rst_125   = 1'b1;
    reg  rst_200m  = 1'b1;
    reg  sgmii_rx_p = 1'b0;
    wire sgmii_rx_n = ~sgmii_rx_p;

    wire idelayctrl_rdy;
    (* IODELAY_GROUP = "bank14_idelay_grp" *)
    IDELAYCTRL u_tb_idelayctrl (
        .RDY    (idelayctrl_rdy),
        .REFCLK (clk_200m),
        .RST    (rst_200m)
    );

    wire [9:0]  rx_code_125;
    wire        rx_valid_125;
    wire        rx_comma_aligned;
    wire        rx_prbs_locked;
    wire [31:0] rx_prbs_err_cnt;
    wire        phase_sel_mon;
    wire [31:0] phase_switch_cnt;

    sgmii_lvds_rx #(
        .DIFF_TERM_EN (1'b0)
    ) dut (
        .sgmii_rx_p       (sgmii_rx_p),
        .sgmii_rx_n       (sgmii_rx_n),
        .clk_625_0        (clk_625_0),
        .clk_625_90       (clk_625_90),
        .clk_312p5        (clk_312p5),
        .clk_312p5_45     (clk_312p5_45),
        .clk_125          (clk_125),
        .rst_312p5        (rst_312p5),
        .rst_125          (rst_125),
        .rx_code_125      (rx_code_125),
        .rx_valid_125     (rx_valid_125),
        .rx_comma_aligned (rx_comma_aligned),
        .rx_prbs_locked   (rx_prbs_locked),
        .rx_prbs_err_cnt  (rx_prbs_err_cnt),
        .phase_sel_mon    (phase_sel_mon),
        .phase_switch_cnt (phase_switch_cnt)
    );

    // Count PRBS payload words observed after lock
    integer rx_payload_words = 0;
    always @(posedge clk_125) begin
        if (rst_125) begin
            rx_payload_words <= 0;
        end else if (rx_valid_125 && rx_prbs_locked &&
                     (rx_code_125 != K28_5_RD_NEG) && (rx_code_125 != K28_5_RD_POS)) begin
            rx_payload_words <= rx_payload_words + 1;
        end
    end

    function [16:0] prbs7_step10(input [6:0] st);
        reg [6:0] s;
        reg [9:0] bits;
        reg       fb;
        integer   k;
        begin
            s = st;
            for (k = 0; k < 10; k = k + 1) begin
                fb      = s[6] ^ s[5];
                bits[k] = fb;
                s       = {s[5:0], fb};
            end
            prbs7_step10 = {bits, s};
        end
    endfunction

    task automatic send_10b_word(input [9:0] w, input real ui_ps);
        integer b;
        begin
            for (b = 0; b < 10; b = b + 1) begin
                sgmii_rx_p = w[b];
                #(ui_ps);
            end
        end
    endtask

    task automatic run_ppm_case(input integer case_id, input real ui_ps, input real init_phase_ps);
        integer      w;
        reg [6:0]    lfsr;
        reg [16:0]   nxt;
        reg [9:0]    cword;
        reg [31:0]   sw_before;
        integer      words_before;
        integer      words_case;
        integer      err_cnt_local;
        reg          comma_ok;
        reg          prbs_ok;
        reg [31:0]   sw_delta;
        begin
            // Hold resets across glbl.GSR + IDELAYCTRL lock, then release cleanly
            rst_200m   = 1'b1;
            rst_312p5  = 1'b1;
            rst_125    = 1'b1;
            sgmii_rx_p = 1'b0;
            repeat (40) @(posedge clk_200m);
            rst_200m   = 1'b0;
            wait (idelayctrl_rdy === 1'b1);
            repeat (16) @(posedge clk_312p5);
            rst_312p5  = 1'b0;
            repeat (8) @(posedge clk_125);
            rst_125    = 1'b0;

            // Arbitrary asynchronous arrival phase before training starts
            #(init_phase_ps);
            sw_before    = phase_switch_cnt;
            words_before = rx_payload_words;

            // Send K28.5 comma preamble so guardband monitor settles and aligner locks
            for (w = 0; w < NUM_COMMAS; w = w + 1) begin
                cword = w[0] ? K28_5_RD_POS : K28_5_RD_NEG;
                send_10b_word(cword, ui_ps);
            end

            // Send NUM_PRBS_WORDS (30,000 bits) + 20 flush PRBS words continuously at exact ui_ps
            lfsr = 7'h7F;
            for (w = 0; w < (NUM_PRBS_WORDS + 20); w = w + 1) begin
                nxt  = prbs7_step10(lfsr);
                lfsr = nxt[6:0];
                send_10b_word(nxt[16:7], ui_ps);
            end

            // Sample status while FIFO pipeline has flushed all 30,000 payload bits
            comma_ok      = rx_comma_aligned;
            prbs_ok       = rx_prbs_locked;
            err_cnt_local = rx_prbs_err_cnt;
            words_case    = rx_payload_words - words_before;
            sw_delta      = phase_switch_cnt - sw_before;

            $display("CASE %0d (ui=%0.3f ps): comma=%0b prbs_lock=%0b words=%0d err=%0d switches=%0d",
                     case_id, ui_ps, comma_ok, prbs_ok, words_case, err_cnt_local, sw_delta);

            if (!comma_ok || !prbs_ok || (words_case < 2900) ||
                (err_cnt_local != 0) || (sw_delta < 3)) begin
                $display("FAIL: tb_sgmii_lvds case %0d (ui=%0.3f ps) err=%0d locked=%0b sw=%0d",
                         case_id, ui_ps, err_cnt_local, prbs_ok, sw_delta);
                $finish(1);
            end
        end
    endtask

    initial begin
        // Wait past glbl.GSR (100 ns)
        #120000.0;

        // Case 1: +100 ppm faster remote clock (UI = 800 / 1.0001 = 799.920 ps), 250 ps offset
        run_ppm_case(1, 799.920, 250.000);

        // Case 2: -100 ppm slower remote clock (UI = 800 / 0.9999 = 800.080 ps), 650 ps offset
        run_ppm_case(2, 800.080, 650.000);

        $display("PASS: tb_sgmii_lvds (+100/-100 ppm 60,000 bits, 0 errors)");
        $finish;
    end

endmodule
`default_nettype wire
