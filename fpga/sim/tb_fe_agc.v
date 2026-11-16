// SPDX-License-Identifier: Apache-2.0
// Rev08 G-5 bench: adc_peak + fe_agc in a closed loop. The ADC sees a tone whose amplitude is the antenna level
// less the attenuation the AGC has programmed (0.5 dB per step) and less 15 dB with the LNA bypassed; a stand-in
// for fe_ctrl is busy for a while after each command and applies it.
// Checks: off = no commands and follows software's settings; a strong signal converges between the thresholds;
// changes are never closer than the hold-off; a one-window burst causes one change only; an overload beyond
// 31.5 dB bypasses the LNA; when the signal goes, the attenuation returns to 0 and the LNA comes back.
// Mutation no_holdoff fails the spacing check.

`timescale 1ns/1ps

module tb_fe_agc;
    reg clk = 0, aclk = 0;
    always #4   clk  = ~clk;     // link clock, 125 MHz
    always #2.5 aclk = ~aclk;    // ADC clock (scaled)
    reg rst = 1;

    localparam integer CPM = 200;          // link cycles per "ms" (scaled)
    reg  [31:0] ctrl = 32'd0;
    reg  [15:0] exp_sw = 16'hA0A0;         // ENBL, RESETX high; port 0: converter on, LNA in (bit 5)
    reg  [5:0]  att_sw = 6'd10;

    // the antenna and the front end
    real a_ant = 0.0;                      // tone amplitude at the ADC with 0 dB attenuation and the LNA in (codes)
    reg  [5:0] att_hw = 6'h3F;
    reg        lna_hw = 1'b1;
    real a_adc, ph = 0.0;
    reg  [7:0] code = 8'd128;
    reg        ovr = 1'b0;
    always @(posedge aclk) begin
        a_adc = a_ant * $pow(10.0, -0.5 * att_hw / 20.0) * (lna_hw ? 1.0 : 0.178);
        ph = ph + 0.7;
        if (a_adc * $sin(ph) > 127.0)       begin code <= 8'd255; ovr <= 1'b1; end
        else if (a_adc * $sin(ph) < -128.0) begin code <= 8'd0;   ovr <= 1'b1; end
        else begin code <= 8'd128 + $rtoi(a_adc * $sin(ph)); ovr <= 1'b0; end
    end

    wire       ptog;
    wire [127:0] pks;
    adc_peak #(.WIN_LOG2(8)) u_pk (.clk(aclk), .rst(rst), .code(code), .valid(1'b1), .ovr(ovr),
        .peak_tog(ptog), .peak_set(pks));
    wire [6:0] pk = dut.pk;

    // fe_ctrl stand-in: busy 300 cycles per command, then applies it
    reg  busy = 0;
    integer bcnt = 0;
    wire        cmd_p;
    wire [31:0] cmd_word;
    wire [31:0] stat;
    integer ncmd = 0;
    time    last_cmd = 0, min_gap = 64'h7FFFFFFFFFFFFFFF;
    always @(posedge clk) begin
        if (cmd_p) begin
            busy <= 1; bcnt <= 300; ncmd = ncmd + 1;
            if (last_cmd != 0 && ($time - last_cmd) < min_gap) min_gap = $time - last_cmd;
            last_cmd = $time;
            if (cmd_word[31:28] == 4'h6) att_hw <= cmd_word[5:0];
            if (cmd_word[31:28] == 4'h2) lna_hw <= cmd_word[5];
        end else if (bcnt > 0) begin
            bcnt <= bcnt - 1; if (bcnt == 1) busy <= 0;
        end
    end

    fe_agc #(.CYC_PER_MS(CPM)) dut (.clk(clk), .rst(rst), .ctrl(ctrl), .peak_tog_async(ptog), .peak_set_async(pks),
        .exp_sw(exp_sw), .att_sw(att_sw), .fe_busy(busy), .cmd_block(1'b0), .cmd_p(cmd_p), .cmd_word(cmd_word),
        .stat(stat));

    integer errors = 0;
    task check(input cond, input [8*72-1:0] what);
        begin
            if (!cond) begin errors = errors + 1; $display("FAIL: %0s", what); end
            else $display("ok:   %0s", what);
        end
    endtask
    task ms(input integer n); begin repeat (n * CPM) @(posedge clk); end endtask

    integer n0;
    localparam [31:0] HOLD = 32'd10;   // ms
    initial begin
        repeat (20) @(posedge clk); rst = 0;
        att_hw = 6'd10;                                      // software set 5 dB, LNA in
        a_ant = 60.0;
        ms(30);
        check(ncmd == 0, "AGC off: no commands");
        check(stat[29:24] == 6'd10 && stat[31] == 1'b1, "AGC off: follows software's attenuation and LNA");

        // strong signal: 300 codes at 0 dB (8 dB over full scale at the 5 dB start)
        a_ant = 300.0;
        ctrl = {HOLD[7:0], 1'b0, 7'd24, 1'b0, 7'd96, 6'd0, 1'b1, 1'b1};
        ms(400);
        check(pk >= 7'd24 && pk < 7'd96, "strong signal settles between the thresholds");
        check(min_gap >= HOLD * CPM * 8, "changes no closer than the hold-off");
        n0 = ncmd;
        ms(200);
        check(ncmd == n0, "settled: no further changes");

        // a one-window burst 20 dB up
        a_ant = 3000.0; repeat (300) @(posedge aclk); a_ant = 300.0;
        ms(5);
        check(ncmd <= n0 + 1, "one-window burst: at most one change");
        ms(300);

        // overload beyond 31.5 dB: the LNA is bypassed
        a_ant = 30000.0;
        ms(600);
        check(att_hw == 6'h3F && lna_hw == 1'b0, "overload: 31.5 dB and the LNA bypassed");
        check(stat[31] == 1'b0, "status shows the LNA bypassed");

        // the signal goes: back to 0 dB and the LNA in
        a_ant = 1.0;
        ms(1200);
        check(att_hw == 6'd0, "quiet: attenuation back to 0 dB");
        check(lna_hw == 1'b1, "quiet: the LNA back in");

        if (errors == 0) $display("PASS: tb_fe_agc changes=%0d min_gap=%0t", stat[15:0], min_gap);
        else $display("FAIL: tb_fe_agc, %0d errors", errors);
        $finish;
    end
    initial begin #200_000_000; $display("FAIL: tb_fe_agc timeout"); $finish; end
endmodule
