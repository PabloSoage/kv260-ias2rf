// SPDX-License-Identifier: Apache-2.0
// Rev08 G-5: AGC of the VHF/UHF front end (docs/REV08_PLAN.md section 7).
//
// adc_peak (ADC clock): the largest |code - 128| of the AD9484's offset-binary codes in each window of 2^WIN_LOG2
// samples (65,536: 164 us at 400 MSPS, 131 us at 500), handed to the link clock with a toggle; the over-range pin
// is OR-ed in as a full-scale peak.
//
// fe_agc (link clock): acts on those peaks through fe_ctrl's command port (FE_CMD), the PE4312 first and the LNA
// bypass last:
//   attack  peak >= high threshold: attenuation +3 dB (6 steps), up to 31.5 dB; at 31.5 dB with the LNA in and
//           LNA control allowed, bypass the LNA instead
//   release every hold-off period with all peaks below the low threshold: -0.5 dB, down to 0; at 0 dB with the
//           LNA bypassed, put it back only when the peaks are below low/8 (18 dB under, the LNA's gain plus margin)
//   hold-off after any change no further change for HOLD ms, so a burst does not make it chatter
// Each change is one command (ATT: 15 writes, about 5 ms; EXP_OUT: one write), issued only when fe_ctrl is idle.
// While the AGC is on, software must not send ATT itself; it sets port 0 through FE_CMD as usual and the AGC keeps
// a copy of the last EXP_OUT word to flip the LNA bit (port 0 bit 5, VU_LNA_ON).
//
// FE_AGC_CTRL (0x120): [0] enable, [1] LNA bypass allowed, [14:8] high threshold (default 96, -2.5 dBFS),
//   [22:16] low threshold (default 24, -14.5 dBFS), [31:24] hold-off in ms (default 50)
// FE_AGC_STAT (0x124): [31] LNA in, [29:24] attenuation code, [22:16] last peak, [15:0] changes made
//
// Mutation (run.ps1 -Mutate): no_holdoff (changes on every window), checked by tb_fe_agc.

`timescale 1ns/1ps
`default_nettype none

module adc_peak #(
    parameter integer WIN_LOG2 = 16
) (
    input  wire         clk,
    input  wire         rst,
    input  wire [7:0]   code,
    input  wire         valid,
    input  wire         ovr,
    output reg          peak_tog,       // toggles once per window
    output reg  [127:0] peak_set = 128'd0 // bit k set: a sample of magnitude k in the window; steady between toggles
);
    // At 400/500 MHz a compare-and-select running maximum does not close in one cycle, so the window's peak is
    // kept as a set: each sample's magnitude becomes a one-hot bit (a decoder, no feedback) and the window ORs them
    // (one LUT in the loop). The set is handed over whole; fe_agc finds its highest bit on the link clock.
    //   stage 1  magnitude: offset binary to two's complement is an MSB flip; the one's complement stands in for
    //            the negation (at most 1 LSB low)
    //   stage 2  one-hot
    //   stage 3  OR into the window's set; at the window's end, hand it over (over-range sets bit 127)
    reg [WIN_LOG2-1:0] n;
    reg                v1, o1, last1, o2, last2;
    // the 128-bit data registers start from their power-up value and take no reset: a reset fanned out to
    // 3 x 128 flip-flops did not reach them within the 400 MHz cycle. After a reset the first window may carry
    // stale bits, which only delays the AGC's first step by one window.
    reg [6:0]          m1 = 7'd0;
    reg [127:0]        oh2 = 128'd0, hits = 128'd0;
    wire [7:0]         s = code ^ 8'h80;
    always @(posedge clk) begin
        if (rst) begin
            n <= 0; v1 <= 1'b0; o1 <= 1'b0; last1 <= 1'b0; o2 <= 1'b0; last2 <= 1'b0;
            peak_tog <= 1'b0;
        end else begin
            v1    <= valid;
            o1    <= ovr && valid;
            m1    <= s[7] ? ~s[6:0] : s[6:0];
            last1 <= valid && (&n);
            if (valid) n <= n + 1'b1;

            o2    <= o1;
            last2 <= v1 && last1;
            oh2   <= v1 ? (128'd1 << m1) : 128'd0;

            if (last2) begin
                peak_set <= hits | oh2 | {o2, 127'd0};
                peak_tog <= ~peak_tog;
                hits     <= 128'd0;
            end else begin
                hits <= hits | oh2 | {o2, 127'd0};
            end
        end
    end
endmodule


module fe_agc #(
    parameter integer CYC_PER_MS = 125_000        // link clock
) (
    input  wire        clk,
    input  wire        rst,
    input  wire [31:0] ctrl,                       // FE_AGC_CTRL
    input  wire        peak_tog_async,             // from adc_peak
    input  wire [127:0] peak_set_async,           // adc_peak's set, steady for a window around the toggle
    input  wire [15:0] exp_sw,                     // last EXP_OUT word software wrote through FE_CMD
    input  wire [5:0]  att_sw,                     // last ATT code software wrote (31.5 dB until then)
    input  wire        fe_busy,
    input  wire        cmd_block,                  // a CSR or LED command takes this cycle
    output reg         cmd_p,
    output reg  [31:0] cmd_word,
    output wire [31:0] stat,
    output wire        pending                      // a change waits for fe_ctrl (lower-priority users hold off)
);
    wire       en      = ctrl[0];
    wire       lna_ok  = ctrl[1];
    wire [6:0] th_hi   = (ctrl[14:8]  == 7'd0) ? 7'd96 : ctrl[14:8];
    wire [6:0] th_lo   = (ctrl[22:16] == 7'd0) ? 7'd24 : ctrl[22:16];
    wire [7:0] hold_ms = (ctrl[31:24] == 8'd0) ? 8'd50 : ctrl[31:24];

    (* ASYNC_REG = "TRUE" *) reg [2:0] tog_s;

    // highest set bit of the peak set (8 ns on the link clock is plenty for a 128-input priority encoder)
    function automatic [6:0] top_bit(input [127:0] v);
        integer i;
        begin
            top_bit = 7'd0;
            for (i = 0; i < 128; i = i + 1)
                if (v[i]) top_bit = i[6:0];
        end
    endfunction
    reg  [6:0]  pk;
    reg         pk_new;
    reg  [6:0]  pk_max;                // largest peak since the last decision
    reg  [5:0]  att;
    reg         lna_in;
    reg  [15:0] changes;
    reg  [31:0] hold;
    reg  [31:0] obs;                   // observation period for release: one hold-off long, restarted at its end
    reg         obs_end;
    reg         want;                  // a change is pending until fe_ctrl is free
    reg  [31:0] want_word;

    assign stat = {lna_in, 1'b0, att, 1'b0, pk, changes};
    assign pending = want;

    always @(posedge clk) begin
        if (rst) begin
            tog_s <= 3'd0; pk <= 7'd0; pk_new <= 1'b0; pk_max <= 7'd0;
            att <= 6'h3F; lna_in <= 1'b1; changes <= 16'd0; hold <= 32'd0; obs <= 32'd0; obs_end <= 1'b0;
            want <= 1'b0; want_word <= 32'd0; cmd_p <= 1'b0; cmd_word <= 32'd0;
        end else begin
            cmd_p  <= 1'b0;
            tog_s  <= {tog_s[1:0], peak_tog_async};
            pk_new <= 1'b0;
            if (tog_s[2] ^ tog_s[1]) begin
                pk     <= top_bit(peak_set_async);    // steady for a whole window before and after the toggle
                pk_new <= 1'b1;
            end
            if (pk_new && pk > pk_max) pk_max <= pk;
            if (hold != 32'd0) hold <= hold - 32'd1;
            obs_end <= 1'b0;
            if (obs != 32'd0) obs <= obs - 32'd1;
            else begin obs <= hold_ms * CYC_PER_MS; obs_end <= 1'b1; end

            if (!en) begin
                // off: follow what software set, so turning the AGC on starts from the real state
                want <= 1'b0; pk_max <= 7'd0; att <= att_sw; lna_in <= exp_sw[5];
            end else if (want) begin
                if (!fe_busy && !cmd_block) begin
                    cmd_p    <= 1'b1;
                    cmd_word <= want_word;
                    want     <= 1'b0;
                    changes  <= changes + 16'd1;
`ifdef MUTATE_NO_HOLDOFF
                    hold     <= 32'd0;
`else
                    hold     <= hold_ms * CYC_PER_MS;
`endif
                    pk_max   <= 7'd0;
                    obs      <= hold_ms * CYC_PER_MS;   // the next observation period starts with the hold-off
                end
            end else if (pk_new && pk >= th_hi && (hold == 32'd0)) begin
                // attack
                if (att != 6'h3F) begin
                    att       <= (att > 6'd57) ? 6'h3F : att + 6'd6;
                    want_word <= {4'h6, 22'd0, ((att > 6'd57) ? 6'h3F : att + 6'd6)};
                    want      <= 1'b1;
                end else if (lna_ok && lna_in) begin
                    lna_in    <= 1'b0;
                    want_word <= {4'h2, 12'd0, exp_sw[15:8], exp_sw[7:0] & ~8'h20};
                    want      <= 1'b1;
                end
            end else if (obs_end) begin
                pk_max <= 7'd0;                          // a new observation period starts
                // release: a whole period of quiet windows, and no change during it
                if (hold == 32'd0 && pk_max < th_lo) begin
                if (att != 6'd0) begin
                    att       <= att - 6'd1;
                    want_word <= {4'h6, 22'd0, att - 6'd1};
                    want      <= 1'b1;
                end else if (lna_ok && !lna_in && pk_max < (th_lo >> 3)) begin
                    lna_in    <= 1'b1;
                    want_word <= {4'h2, 12'd0, exp_sw[15:8], exp_sw[7:0] | 8'h20};
                    want      <= 1'b1;
                end
                end
            end
        end
    end
endmodule
`default_nettype wire
