// SPDX-License-Identifier: Apache-2.0
// Rev08 G-2/G-3/G-6 bench: fe_ctrl through hk_xo_ctrl's client port onto an I2C bus with two TCA6416A models,
// the RFFC5072 three-wire port and the PE4312 attenuator behind U1313's pins (RX_VU_SPEC section 1.2).
//
// Checks: implicit INIT before the first command; ATT_LE low before any SCLK edge (the attenuator holds 31.5 dB
// through RFFC5072 traffic); RFFC5072 register write and read-back, device ID; attenuator word; write-on-change
// of EXP_OUT and LED; lock detect through POLL; command overrun flag; raw access to 0x21 through hk_xo_ctrl.
// A second hk_xo_ctrl + fe_ctrl pair on a bus with no devices: fe_ctrl's NACKs set FE_STAT[31] but leave
// XO_CTRL[11] ack_err and ack_err_cnt at 0, while a NACK from the Si549 address still sets them.
// Mutations: le_high, no_shadow, lsb_first (fe_ctrl.v header), gen_nack_to_xo (hk_xo_ctrl.v) each fail a check.

`timescale 1ns/1ps
`include "models/fe_models.v"

module tb_fe_ctrl;
    reg link_clk = 0, cfg_clk = 0;
    always #4    link_clk = ~link_clk;     // 125 MHz
    always #7.5  cfg_clk  = ~cfg_clk;      // ~66 MHz, CFGMCLK
    reg link_rst = 1, cfg_rst = 1;

    // ------------------------------------------------------------- I2C bus (open drain, pulled up)
    wire scl_t, sda_t;
    wire scl = scl_t ? 1'b1 : 1'b0;
    wire sda;
    assign (weak1, weak0) sda = 1'b1;
    assign sda = sda_t ? 1'bz : 1'b0;

    // ------------------------------------------------------------- DUT
    reg         cmd_p = 0;
    reg  [31:0] cmd_word = 0;
    wire        busy;
    wire [31:0] stat;
    wire [15:0] rffc;

    wire        g_valid, g_ready, g_rvalid, g_rerr;
    wire [6:0]  g_dev;
    wire [2:0]  g_wl;
    wire [31:0] g_wd;
    wire [1:0]  g_rl;
    wire [15:0] g_rd;

    reg         raw_v = 0;
    reg  [6:0]  raw_dev = 0;
    reg  [7:0]  raw_reg = 0;
    wire        raw_ready, raw_rv, raw_rerr;
    wire [7:0]  raw_rd;

    hk_xo_ctrl #(.CLK_DIV(4), .FCAL_WAIT_CYC(10)) u_xo (
        .clk(cfg_clk), .rst(cfg_rst), .use_ext_clk(1'b0), .clk_sel_t(),
        .prog_start(1'b0), .prog_freq_500m(1'b0), .delta_start(1'b0), .delta_m(24'd0),
        .raw_req_valid(raw_v), .raw_req_dev(raw_dev), .raw_req_ready(raw_ready), .raw_req_rw(1'b1),
        .raw_req_reg(raw_reg), .raw_req_wdata(8'd0), .raw_resp_valid(raw_rv), .raw_resp_rdata(raw_rd),
        .raw_resp_err(raw_rerr),
        .gen_req_valid(g_valid), .gen_req_ready(g_ready), .gen_req_dev(g_dev), .gen_req_wr_len(g_wl),
        .gen_req_wdata(g_wd), .gen_req_rd_len(g_rl), .gen_resp_valid(g_rvalid), .gen_resp_rdata(g_rd),
        .gen_resp_err(g_rerr),
        .busy(), .prog_done(), .active_freq_500m(), .ack_err(), .ack_err_cnt(), .delta_clamped(),
        .xo_scl_t(scl_t), .xo_scl_in(scl), .xo_sda_t(sda_t), .xo_sda_in(sda === 1'b0 ? 1'b0 : 1'b1)
    );

    fe_ctrl dut (
        .link_clk(link_clk), .link_rst(link_rst), .cmd_p(cmd_p), .cmd_word(cmd_word),
        .busy_link(busy), .stat_link(stat), .rffc_link(rffc),
        .clk(cfg_clk), .rst(cfg_rst),
        .gen_req_valid(g_valid), .gen_req_ready(g_ready), .gen_req_dev(g_dev), .gen_req_wr_len(g_wl),
        .gen_req_wdata(g_wd), .gen_req_rd_len(g_rl), .gen_resp_valid(g_rvalid), .gen_resp_rdata(g_rd),
        .gen_resp_err(g_rerr)
    );

    // ------------------------------------------------------------- second pair on an empty bus (no RX_VU board)
    wire scl2_t, sda2_t;
    wire scl2 = scl2_t ? 1'b1 : 1'b0;
    wire sda2 = sda2_t ? 1'b1 : 1'b0;             // nothing on the bus: every address byte is a NACK
    reg         cmd2_p = 0;
    reg  [31:0] cmd2_word = 0;
    wire        busy2;
    wire [31:0] stat2;
    wire        g2_valid, g2_ready, g2_rvalid, g2_rerr;
    wire [6:0]  g2_dev;
    wire [2:0]  g2_wl;
    wire [31:0] g2_wd;
    wire [1:0]  g2_rl;
    wire [15:0] g2_rd;
    reg         raw2_v = 0;
    wire        raw2_ready, raw2_rv, raw2_rerr;
    wire        xo2_ack_err;
    wire [15:0] xo2_ack_cnt;
    hk_xo_ctrl #(.CLK_DIV(4), .FCAL_WAIT_CYC(10)) u_xo2 (
        .clk(cfg_clk), .rst(cfg_rst), .use_ext_clk(1'b0), .clk_sel_t(),
        .prog_start(1'b0), .prog_freq_500m(1'b0), .delta_start(1'b0), .delta_m(24'd0),
        .raw_req_valid(raw2_v), .raw_req_dev(7'd0), .raw_req_ready(raw2_ready), .raw_req_rw(1'b1),
        .raw_req_reg(8'd7), .raw_req_wdata(8'd0), .raw_resp_valid(raw2_rv), .raw_resp_rdata(),
        .raw_resp_err(raw2_rerr),
        .gen_req_valid(g2_valid), .gen_req_ready(g2_ready), .gen_req_dev(g2_dev), .gen_req_wr_len(g2_wl),
        .gen_req_wdata(g2_wd), .gen_req_rd_len(g2_rl), .gen_resp_valid(g2_rvalid), .gen_resp_rdata(g2_rd),
        .gen_resp_err(g2_rerr),
        .busy(), .prog_done(), .active_freq_500m(), .ack_err(xo2_ack_err), .ack_err_cnt(xo2_ack_cnt),
        .delta_clamped(),
        .xo_scl_t(scl2_t), .xo_scl_in(scl2), .xo_sda_t(sda2_t), .xo_sda_in(sda2)
    );
    fe_ctrl dut2 (
        .link_clk(link_clk), .link_rst(link_rst), .cmd_p(cmd2_p), .cmd_word(cmd2_word),
        .busy_link(busy2), .stat_link(stat2), .rffc_link(),
        .clk(cfg_clk), .rst(cfg_rst),
        .gen_req_valid(g2_valid), .gen_req_ready(g2_ready), .gen_req_dev(g2_dev), .gen_req_wr_len(g2_wl),
        .gen_req_wdata(g2_wd), .gen_req_rd_len(g2_rl), .gen_resp_valid(g2_rvalid), .gen_resp_rdata(g2_rd),
        .gen_resp_err(g2_rerr)
    );

    // ------------------------------------------------------------- U1313 and what hangs on its pins
    wire [15:0] u13_out, u13_oe;
    wire [31:0] u13_wr, u15_wr;
    wire [15:0] u15_out, u15_oe;
    wire ld;
    wire vu_sdata;
    assign vu_sdata = u13_oe[11] ? u13_out[11] : 1'bz;
    wire enx    = u13_oe[9]  ? u13_out[9]  : 1'b1;    // R1342 pull-up
    wire sclk   = u13_oe[10] ? u13_out[10] : 1'b0;
    wire resetx = u13_oe[13] ? u13_out[13] : 1'b1;    // R1344
    wire att_le = u13_oe[14] ? u13_out[14] : 1'b1;    // PE4312 internal pull-up
    wire enbl   = u13_oe[15] ? u13_out[15] : 1'b0;    // R1343
    wire [15:0] u13_in = {enbl, att_le, resetx, ld, (vu_sdata === 1'b1), sclk, enx, 1'b1, 8'h80};

    tca6416a_model #(.ADDR(7'h20)) u1313 (.scl(scl), .sda(sda), .pin_in(u13_in),
        .pin_out(u13_out), .pin_oe(u13_oe), .n_writes(u13_wr));
    tca6416a_model #(.ADDR(7'h21)) u1501 (.scl(scl), .sda(sda), .pin_in(16'hFFFF),
        .pin_out(u15_out), .pin_oe(u15_oe), .n_writes(u15_wr));
    wire [31:0] rf_frames;
    rffc5072_model u1312 (.enx(enx), .sclk(sclk), .sdata(vu_sdata), .enbl(enbl), .resetx(resetx), .ld(ld),
        .n_frames(rf_frames));
    wire [5:0]  att;
    wire [31:0] att_chg;
    pe4312_model u1330 (.sclk(sclk), .sdata(vu_sdata === 1'b1), .le(att_le), .att(att), .n_changes(att_chg));

    // the attenuator's latch must be closed (LE low) on every SCLK edge once the bench starts the bus
    integer sclk_with_le = 0;
    always @(posedge sclk) if (att_le === 1'b1) sclk_with_le = sclk_with_le + 1;

`ifdef TRACE
    always @(posedge cfg_clk) begin
        if (g_valid && g_ready) $display("%t req dev=%h wl=%0d wd=%h rl=%0d", $time, g_dev, g_wl, g_wd, g_rl);
        if (g_rvalid) $display("%t resp err=%b rd=%h", $time, g_rerr, g_rd);
    end
`endif
    // ------------------------------------------------------------- helpers
    integer errors = 0;
    task check(input cond, input [8*64-1:0] what);
        begin
            if (!cond) begin errors = errors + 1; $display("FAIL: %0s", what); end
            else $display("ok:   %0s", what);
        end
    endtask

    task cmd(input [31:0] w);
        begin
            @(posedge link_clk); cmd_word <= w; cmd_p <= 1;
            @(posedge link_clk); cmd_p <= 0;
            repeat (4) @(posedge link_clk);
            wait (!busy);
            repeat (2) @(posedge link_clk);
        end
    endtask

    integer w0, a0;
    initial begin
        repeat (20) @(posedge cfg_clk); cfg_rst = 0;
        repeat (20) @(posedge link_clk); link_rst = 0;
        repeat (50) @(posedge link_clk);

        check(att == 6'h3F, "PE4312 at its power-up 31.5 dB");
        check(u13_oe == 16'h0000 && u15_oe == 16'h0000, "no bus traffic before a command: expanders all inputs");

        // first command: implicit INIT, then an RFFC5072 register write
        cmd({4'h4, 5'd0, 7'h0B, 16'h1234});
        check(stat[30], "INIT ran before the first command");
        check(!stat[31], "no I2C error");
        check(u13_oe == 16'hEEFF, "U1313: P10 and P14 inputs, the rest outputs");
        check(att_le == 1'b0, "ATT_LE low after INIT");
        check(u1312.r[5'h0B] == 16'h1234, "RFFC5072 register 0x0B written");
        check(att == 6'h3F && att_chg == 0, "attenuator unchanged by the RFFC5072 traffic");
        check(sclk_with_le == 0, "no SCLK edge while LE is high");
        check(u15_out[7:0] == 8'hFF && u15_oe[7:0] == 8'hFF, "U1501: LED port outputs, all LEDs off");

        // read-back and device ID
        cmd({4'h5, 5'd0, 7'h0B, 16'h0000});
        check(rffc == 16'h1234, "RFFC5072 0x0B reads back 0x1234");
        cmd({4'h5, 5'd0, 7'h1F, 16'h0000});
        check(rffc == 16'h8A01, "RFFC5072 device ID through READSEL 0");
        check(u13_oe[11] == 1'b1, "SDATA back to an output after the read");

        // attenuator
        cmd({4'h6, 22'd0, 6'h15});
        check(att == 6'h15, "PE4312 set to 0x15 (10.5 dB)");
        check(att_le == 1'b0, "LE low again after the latch pulse");

        // expander outputs, write on change
        cmd({4'h2, 12'd0, 8'h20, 8'h45});
        check(u13_out[7:0] == 8'h45, "U1313 port 0 = 0x45");
        w0 = u13_wr;
        cmd({4'h2, 12'd0, 8'h20, 8'h45});
        check(u13_wr == w0, "unchanged EXP_OUT: no I2C write");

        // LEDs, write on change
        cmd({4'h7, 20'd0, 8'hA5});
        check(u15_out[7:0] == 8'h5A, "LED A5 drives U1501 port 0 = 5A (low = lit)");
        w0 = u15_wr;
        cmd({4'h7, 20'd0, 8'hA5});
        check(u15_wr == w0, "unchanged LED: no I2C write");

        // enable, lock detect through POLL
        cmd({4'h2, 12'd0, 8'hA0, 8'h45});         // ENBL and RESETX high
        check(enbl == 1'b1, "ENBL high");
        #2000;
        cmd({4'h3, 28'd0});
        check(stat[12] == 1'b1, "POLL reads lock detect (P14) high");
        cmd({4'h4, 5'd0, 7'h1D, 16'h1000});        // READSEL = 1
        cmd({4'h5, 5'd0, 7'h1F, 16'h0000});
        check(rffc[15] == 1'b1, "read-back register shows lock");
        check(att == 6'h15, "attenuator still at 0x15 after more RFFC5072 traffic");

        // overrun: a second write while busy is dropped and flagged
        @(posedge link_clk); cmd_word <= {4'h3, 28'd0}; cmd_p <= 1;
        @(posedge link_clk); cmd_p <= 0;
        @(posedge link_clk); cmd_word <= {4'h3, 28'd0}; cmd_p <= 1;
        @(posedge link_clk); cmd_p <= 0;
        repeat (4) @(posedge link_clk); wait (!busy); repeat (2) @(posedge link_clk);
        check(stat[29] == 1'b1, "overrun flagged");

        // raw access with a device address: U1501's configuration register 6
        @(posedge cfg_clk); raw_dev <= 7'h21; raw_reg <= 8'h06; raw_v <= 1;
        wait (raw_ready); @(posedge cfg_clk); raw_v <= 0;
        wait (raw_rv); @(posedge cfg_clk);
        check(raw_rd == 8'h00 && !raw_rerr, "raw read of 0x21 register 6 through hk_xo_ctrl");

        // no RX_VU board: fe_ctrl's NACKs stay in FE_STAT[31], the clock XO's ack_err is not touched
        @(posedge link_clk); cmd2_word <= {4'h7, 20'd0, 8'h3C}; cmd2_p <= 1;
        @(posedge link_clk); cmd2_p <= 0;
        repeat (4) @(posedge link_clk); wait (!busy2); repeat (2) @(posedge link_clk);
        check(stat2[31] == 1'b1, "empty bus: fe_ctrl reports its NACK in FE_STAT[31]");
        check(xo2_ack_err == 1'b0 && xo2_ack_cnt == 16'd0, "empty bus: fe_ctrl NACK leaves XO ack_err/cnt at 0");
        @(posedge cfg_clk); raw2_v <= 1;
        wait (raw2_ready); @(posedge cfg_clk); raw2_v <= 0;
        wait (raw2_rv); @(posedge cfg_clk); @(posedge cfg_clk);
        check(raw2_rerr && xo2_ack_err == 1'b1 && xo2_ack_cnt == 16'd1, "empty bus: a Si549 NACK still sets ack_err");

        if (errors == 0) $display("PASS: tb_fe_ctrl");
        else $display("FAIL: tb_fe_ctrl, %0d errors", errors);
        $finish;
    end

    initial begin #20_000_000; $display("FAIL: tb_fe_ctrl timeout"); $finish; end
endmodule
