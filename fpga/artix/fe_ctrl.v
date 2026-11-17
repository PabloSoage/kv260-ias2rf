// SPDX-License-Identifier: Apache-2.0
// Rev08 G-2, G-3, G-6: front-end control over the XO I2C bus (docs/REV08_PLAN.md section 7)
//
// Two TCA6416A expanders share the XO_SCL/XO_SDA bus with the Si549, through hk_xo_ctrl's client port:
//   U1313 at 0x20 (RX_VU): preselectors, LNA and converter switches, bias tee, and the three-wire bus of the
//     RFFC5072 (ENX, SCLK, SDATA, RESETX, ENBL, lock detect) and the PE4312 step attenuator (SCLK, SDATA, LE)
//   U1501 at 0x21 (STATUS): P00..P07 sink the eight status LEDs (low = lit), P10..P17 unused (inputs)
// The expanders' INT outputs are not connected: inputs are read on request (POLL), never by interrupt.
//
// Port 1 of U1313, bit by bit (RX_VU_SPEC section 1.2):
//   0 P10 VU_BIAS_FLT_N in    1 P11 VU_ENX out      2 P12 VU_SCLK out    3 P13 VU_SDATA out/in
//   4 P14 VU_LD        in     5 P15 VU_RESETX out   6 P16 VU_ATT_LE out  7 P17 VU_ENBL out
// The serial engine owns ENX, SCLK, SDATA and ATT_LE; software owns port 0, RESETX and ENBL.
//
// Nothing is sent unless a command asks (the receiver must not see bus traffic it did not request). The first
// command after reset, or after an I2C error, is preceded by INIT. INIT writes the output registers before the
// configuration registers, so no pin glitches when it turns from input to output; it drives ATT_LE low, which
// latches the PE4312 at its power-up 31.5 dB. LE must stay low whenever SCLK moves: with LE high the PE4312's
// latch is transparent [PE4312 data sheet, serial interface], and SCLK and SDATA are shared with the RFFC5072.
//
// Commands (cmd_word[31:28]; written to CSR 0x110 FE_CMD on the link clock, carried here by a toggle):
//   1 INIT
//   2 EXP_OUT   [15:0] = {port1, port0}: port 0, and RESETX (bit 13) and ENBL (bit 15); written on change only
//   3 POLL      read U1313's input ports into res_inputs
//   4 RFFC_WR   [22:16] register, [15:0] data
//   5 RFFC_RD   [22:16] register; the 16-bit value lands in res_rffc
//   6 ATT       [5:0] attenuation in 0.5 dB steps (C16..C0.5), MSB first, then an LE pulse
//   7 LED       [7:0] one bit per LED, 1 = lit (D1501..D1508); written on change only
// Three-wire framing as HackRF drives the RFFC5071 (docs/RFFC5072_PROGRAMMING.md section 2): two clocks with
// ENX high, ENX low, a 9-bit header (0, R/W, 7-bit address) and 16 data bits MSB first, data set while SCLK is low
// and sampled on the rising edge; for a read SDATA turns to an input after the header, with one turnaround clock.
// Each SCLK or SDATA edge is one write of U1313's output port 1: 59 writes for a register write, 82 I2C
// transactions for a read: about 26 ms and 37 ms at the nominal 65 kHz bus (17 to 52 ms for a write over CFGMCLK's
// +/-50 % spread).
//
// Mutations (run.ps1 -Mutate): le_high (LE left high, the attenuator follows the RFFC5072 traffic),
// no_shadow (EXP_OUT and LED written even when unchanged), lsb_first (attenuator word LSB first).

`timescale 1ns/1ps
`default_nettype none

module fe_ctrl #(
    parameter [6:0] EXP_ADDR = 7'h20,
    parameter [6:0] LED_ADDR = 7'h21
) (
    // link clock side: CSR 0x110 write and the status words read back
    input  wire        link_clk,
    input  wire        link_rst,
    input  wire        cmd_p,            // one-cycle pulse on a write of FE_CMD
    input  wire [31:0] cmd_word,
    output reg         busy_link,        // from the write until the command has finished
    output reg  [31:0] stat_link,        // {err, init_done, overrun, 5'd0, ops[7:0], res_inputs[15:0]}
    output reg  [15:0] rffc_link,        // last RFFC_RD value

    // I2C side (cfgmclk, hk_xo_ctrl's domain)
    input  wire        clk,
    input  wire        rst,
    output reg         gen_req_valid,
    input  wire        gen_req_ready,
    output reg  [6:0]  gen_req_dev,
    output reg  [2:0]  gen_req_wr_len,
    output reg  [31:0] gen_req_wdata,
    output reg  [1:0]  gen_req_rd_len,
    input  wire        gen_resp_valid,
    input  wire [15:0] gen_resp_rdata,
    input  wire        gen_resp_err
);

    localparam [3:0] OP_INIT = 4'd1, OP_EXP = 4'd2, OP_POLL = 4'd3, OP_RFW = 4'd4, OP_RFR = 4'd5,
                     OP_ATT = 4'd6, OP_LED = 4'd7;

    localparam [7:0] B_ENX = 8'h02, B_SCLK = 8'h04, B_SDATA = 8'h08, B_RESETX = 8'h20, B_LE = 8'h40,
                     B_ENBL = 8'h80;
    localparam [7:0] CFG1_OUT = 8'h11;   // P10, P14 inputs
    localparam [7:0] CFG1_RD  = 8'h19;   // and P13 (SDATA) while the RFFC5072 drives it

    // ------------------------------------------------------------------ link -> cfg: command toggle
    reg        cmd_tog_link = 1'b0;
    reg [31:0] cmd_hold_link = 32'd0;
    reg        overrun_link = 1'b0;
    (* ASYNC_REG = "TRUE" *) reg [2:0] done_tog_ls = 3'd0;
    reg        done_tog_cfg = 1'b0;

    // ------------------------------------------------------------------ cfg -> link: result snapshot
    reg        res_err = 1'b0, res_init = 1'b0;
    reg [7:0]  res_ops = 8'd0;           // I2C transactions of the last command
    reg [15:0] res_inputs = 16'd0;
    reg [15:0] res_rffc = 16'd0;

    always @(posedge link_clk) begin
        if (link_rst) begin
            cmd_tog_link  <= 1'b0;
            cmd_hold_link <= 32'd0;
            overrun_link  <= 1'b0;
            busy_link     <= 1'b0;
            done_tog_ls   <= 3'd0;
            stat_link     <= 32'd0;
            rffc_link     <= 16'd0;
        end else begin
            done_tog_ls <= {done_tog_ls[1:0], done_tog_cfg};
            if (done_tog_ls[2] ^ done_tog_ls[1]) begin
                busy_link <= 1'b0;
                // the cfg side holds these steady from its done toggle until the next command starts
                stat_link <= {res_err, res_init, overrun_link, 5'd0, res_ops, res_inputs};
                rffc_link <= res_rffc;
            end
            if (cmd_p) begin
                if (busy_link) begin
                    overrun_link <= 1'b1;            // dropped: software must wait for busy to clear
                end else begin
                    cmd_hold_link <= cmd_word;
                    cmd_tog_link  <= ~cmd_tog_link;
                    busy_link     <= 1'b1;
                    overrun_link  <= 1'b0;
                end
            end
        end
    end

    (* ASYNC_REG = "TRUE" *) reg [2:0] cmd_tog_s = 3'd0;
    wire cmd_edge = cmd_tog_s[2] ^ cmd_tog_s[1];

    // ------------------------------------------------------------------ cfg side: sequencer
    localparam [2:0] S_IDLE = 3'd0, S_ISSUE = 3'd1, S_WAIT = 3'd2, S_DONE = 3'd3, S_PREP = 3'd4, S_PREP2 = 3'd5;
    reg [2:0]  st;
    reg [3:0]  op;            // command being run
    reg        pre_init;      // INIT runs first
    reg [31:0] arg;
    reg [6:0]  k;             // step within the command
    reg [7:0]  p0_sh, p1_user, led_sh;   // shadows of what the expanders hold
    reg        init_done;
    reg [15:0] rd_shift;

    // software-owned bits of port 1 with the engine's idle state (ENX high, SCLK, SDATA, LE low)
`ifdef MUTATE_LE_HIGH
    wire [7:0] le_idle = B_LE;           // the mutation: LE never brought low
`else
    wire [7:0] le_idle = 8'h00;
`endif
    wire [7:0] base = (p1_user & (B_RESETX | B_ENBL)) | le_idle;
    wire [7:0] idle = base | B_ENX;

    // one step of a command: kind 0 = write port 1 of U1313, 1 = write U1313 config 1, 2 = read U1313 inputs
    // (and shift SDATA into rd_shift), 3 = a full two-byte write (INIT, EXP_OUT, LED), 7 = end.
    // The table is registered (kind, val, dev, wr3) for timing at the 100 MHz worst-case CFGMCLK: the sequencer
    // passes through S_PREP after every change of op, k or pre_init, so the registered step matches them in S_ISSUE.
    reg [2:0]  kind_c, kind;
    reg [7:0]  val_c, val;
    reg [6:0]  dev_c, dev;
    reg [23:0] wr3_c, wr3;    // {byte1, byte0, register} for kind 3
    reg [24:0] frame;
    reg [8:0]  hdr;
    reg [5:0]  att;
    integer    j;

    always @* begin
        kind_c = 3'd7; val_c = 8'h00; dev_c = EXP_ADDR; wr3_c = 24'd0;
        frame = {2'b00, arg[22:16], arg[15:0]};
        hdr   = {2'b01, arg[22:16]};
`ifdef MUTATE_LSB_FIRST
        att   = {arg[0], arg[1], arg[2], arg[3], arg[4], arg[5]};
`else
        att   = arg[5:0];
`endif
        j = 0;
        if (pre_init) begin
            case (k)
                7'd0: begin kind_c = 3'd3; dev_c = EXP_ADDR; wr3_c = {idle | le_idle, p0_sh, 8'h02}; end
                7'd1: begin kind_c = 3'd3; dev_c = EXP_ADDR; wr3_c = {CFG1_OUT, 8'h00, 8'h06}; end
                7'd2: begin kind_c = 3'd3; dev_c = LED_ADDR; wr3_c = {8'hFF, ~led_sh, 8'h02}; end
                7'd3: begin kind_c = 3'd3; dev_c = LED_ADDR; wr3_c = {8'hFF, 8'h00, 8'h06}; end
                default: kind_c = 3'd7;
            endcase
        end else begin
            case (op)
                OP_EXP: if (k == 7'd0) begin kind_c = 3'd3; dev_c = EXP_ADDR;
                            wr3_c = {(arg[15:8] & (B_RESETX | B_ENBL)) | B_ENX | le_idle, arg[7:0], 8'h02}; end
                OP_LED: if (k == 7'd0) begin kind_c = 3'd3; dev_c = LED_ADDR; wr3_c = {8'hFF, ~arg[7:0], 8'h02}; end
                OP_POLL: if (k == 7'd0) kind_c = 3'd2;
                OP_RFW: begin
                    kind_c = 3'd0;
                    if (k < 7'd4)       val_c = idle | ((k[0] == 1'b0) ? B_SCLK : 8'h00);
                    else if (k == 7'd4) val_c = base;
                    else if (k < 7'd55) begin
                        j   = (k - 7'd5) >> 1;
                        val_c = base | (frame[24 - j] ? B_SDATA : 8'h00) | (((k - 7'd5) & 1) ? B_SCLK : 8'h00);
                    end
                    else if (k == 7'd55) val_c = base;
                    else if (k == 7'd56) val_c = idle;
                    else if (k == 7'd57) val_c = idle | B_SCLK;
                    else if (k == 7'd58) val_c = idle;
                    else kind_c = 3'd7;
                end
                OP_RFR: begin
                    kind_c = 3'd0;
                    if (k < 7'd4)       val_c = idle | ((k[0] == 1'b0) ? B_SCLK : 8'h00);
                    else if (k == 7'd4) val_c = base;
                    else if (k < 7'd23) begin
                        j   = (k - 7'd5) >> 1;
                        val_c = base | (hdr[8 - j] ? B_SDATA : 8'h00) | (((k - 7'd5) & 1) ? B_SCLK : 8'h00);
                    end
                    else if (k == 7'd23) val_c = base;
                    else if (k == 7'd24) begin kind_c = 3'd1; val_c = CFG1_RD; end
                    else if (k == 7'd25) val_c = base | B_SCLK;          // turnaround clock
                    else if (k == 7'd26) val_c = base;
                    else if (k < 7'd75) begin
                        case ((k - 7'd27) % 3)
                            0:       val_c = base | B_SCLK;
                            1:       kind_c = 3'd2;                      // sample after the rising edge
                            default: val_c = base;
                        endcase
                    end
                    else if (k == 7'd75) begin kind_c = 3'd1; val_c = CFG1_OUT; end
                    else if (k == 7'd76) val_c = idle;
                    else if (k == 7'd77) val_c = idle | B_SCLK;
                    else if (k == 7'd78) val_c = idle;
                    else kind_c = 3'd7;
                end
                OP_ATT: begin
                    kind_c = 3'd0;
                    if (k < 7'd12) begin
                        j   = k >> 1;
                        val_c = idle | le_idle | (att[5 - j] ? B_SDATA : 8'h00) | (k[0] ? B_SCLK : 8'h00);
                    end
                    else if (k == 7'd12) val_c = idle | le_idle;
                    else if (k == 7'd13) val_c = idle | B_LE;
                    else if (k == 7'd14) val_c = idle | le_idle;
                    else kind_c = 3'd7;
                end
                default: kind_c = 3'd7;
            endcase
        end
    end

    always @(posedge clk) begin
        kind <= kind_c; val <= val_c; dev <= dev_c; wr3 <= wr3_c;
    end

    always @(posedge clk) begin
        if (rst) begin
            cmd_tog_s     <= 3'd0;
            st            <= S_IDLE;
            op            <= 4'd0;
            pre_init      <= 1'b0;
            arg           <= 32'd0;
            k             <= 7'd0;
            p0_sh         <= 8'h80;          // preselectors straight, LNA and converter off, bias tee off
            p1_user       <= B_RESETX;       // RESETX high, ENBL low
            led_sh        <= 8'h00;
            init_done     <= 1'b0;
            rd_shift      <= 16'd0;
            gen_req_valid <= 1'b0;
            gen_req_dev   <= EXP_ADDR;
            gen_req_wr_len <= 3'd0;
            gen_req_wdata <= 32'd0;
            gen_req_rd_len <= 2'd0;
            done_tog_cfg  <= 1'b0;
            res_err       <= 1'b0;
            res_init      <= 1'b0;
            res_ops       <= 8'd0;
            res_inputs    <= 16'd0;
            res_rffc      <= 16'd0;
        end else begin
            cmd_tog_s     <= {cmd_tog_s[1:0], cmd_tog_link};
            if (gen_req_valid && gen_req_ready)
                gen_req_valid <= 1'b0;                   // held until hk_xo_ctrl takes it
            case (st)
                S_IDLE: if (cmd_edge) begin
                    op       <= cmd_hold_link[31:28];      // steady since before the toggle
                    arg      <= cmd_hold_link;
                    k        <= 7'd0;
                    res_ops  <= 8'd0;
                    res_err  <= 1'b0;
                    pre_init <= !init_done || (cmd_hold_link[31:28] == OP_INIT);
                    st       <= S_PREP;
                    // write-on-change: an unchanged EXP_OUT or LED costs no bus traffic
`ifndef MUTATE_NO_SHADOW
                    if (init_done && cmd_hold_link[31:28] == OP_EXP &&
                        cmd_hold_link[7:0] == p0_sh &&
                        (cmd_hold_link[15:8] & (B_RESETX | B_ENBL)) == p1_user)
                        st <= S_DONE;
                    if (init_done && cmd_hold_link[31:28] == OP_LED && cmd_hold_link[7:0] == led_sh)
                        st <= S_DONE;
`endif
                end

                S_ISSUE: begin
                    if (kind == 3'd7) begin
                        if (pre_init) begin
                            pre_init  <= 1'b0;
                            init_done <= 1'b1;
                            k         <= 7'd0;
                            st        <= (op == OP_INIT) ? S_DONE : S_PREP;
                        end else begin
                            st <= S_DONE;
                        end
                    end else begin
                        gen_req_valid <= 1'b1;
                        gen_req_dev   <= (kind == 3'd3) ? dev : EXP_ADDR;
                        case (kind)
                            3'd0: begin gen_req_wr_len <= 3'd2; gen_req_wdata <= {16'd0, val, 8'h03}; gen_req_rd_len <= 2'd0; end
                            3'd1: begin gen_req_wr_len <= 3'd2; gen_req_wdata <= {16'd0, val, 8'h07}; gen_req_rd_len <= 2'd0; end
                            3'd2: begin gen_req_wr_len <= 3'd1; gen_req_wdata <= 32'h00000000;       gen_req_rd_len <= 2'd2; end
                            default: begin gen_req_wr_len <= 3'd3; gen_req_wdata <= {8'd0, wr3}; gen_req_rd_len <= 2'd0; end
                        endcase
                        st <= S_WAIT;
                    end
                end

                S_WAIT: if (gen_resp_valid) begin
                    res_ops <= res_ops + 8'd1;
                    if (gen_resp_err) begin
                        res_err   <= 1'b1;
                        init_done <= 1'b0;               // the next command starts with INIT again
                        pre_init  <= 1'b0;
                        st        <= S_DONE;
                    end else begin
                        if (kind == 3'd2) begin
                            res_inputs <= gen_resp_rdata;          // [7:0] port 0, [15:8] port 1
                            rd_shift   <= {rd_shift[14:0], gen_resp_rdata[11]};   // P13 = SDATA
                        end
                        if (kind == 3'd3 && !pre_init && op == OP_EXP) begin
                            p0_sh   <= arg[7:0];
                            p1_user <= arg[15:8] & (B_RESETX | B_ENBL);
                        end
                        if (kind == 3'd3 && !pre_init && op == OP_LED)
                            led_sh <= arg[7:0];
                        k  <= k + 7'd1;
                        st <= S_PREP;
                    end
                end

                // The registered step catches up with op, k, pre_init, arg and the shadows. Two cycles: the step
                // table is a 19-level decode that passed or failed at CFGMCLK's 100 MHz worst case from build to
                // build, so it is a 2-cycle multicycle path (xc7a50t.xdc); its inputs change only on the way here.
                S_PREP:  st <= S_PREP2;
                S_PREP2: st <= S_ISSUE;

                default: begin   // S_DONE
                    if (op == OP_RFR && !res_err) res_rffc <= rd_shift;
                    res_init     <= init_done;
                    done_tog_cfg <= ~done_tog_cfg;
                    st           <= S_IDLE;
                end
            endcase
        end
    end

endmodule
`default_nettype wire
