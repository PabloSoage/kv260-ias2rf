// SPDX-License-Identifier: Apache-2.0
// Bench models for the Rev08 front-end control (tb_fe_ctrl): TCA6416A I/O expander, RFFC5072 three-wire port,
// PE4312 serial step attenuator. Behavioural, built from the data sheets' register maps and serial timing.

`timescale 1ns/1ps

// TCA6416A: 16-bit I2C expander. Registers 0/1 input, 2/3 output, 4/5 polarity, 6/7 configuration (1 = input,
// the power-up state); a multi-byte access toggles between the two registers of a pair [TCA6416A data sheet].
// pin_in is what the outside world drives on each pin; pin_out/pin_oe are what the expander drives.
module tca6416a_model #(
    parameter [6:0] ADDR = 7'h20
) (
    input  wire        scl,
    inout  wire        sda,
    input  wire [15:0] pin_in,
    output wire [15:0] pin_out,
    output wire [15:0] pin_oe,
    output reg  [31:0] n_writes      // completed data-byte writes, to check write-on-change
);
    reg [7:0] r [0:7];
    integer i;
    initial begin
        r[0] = 8'h00; r[1] = 8'h00; r[2] = 8'hFF; r[3] = 8'hFF;
        r[4] = 8'h00; r[5] = 8'h00; r[6] = 8'hFF; r[7] = 8'hFF;
        n_writes = 0;
    end
    assign pin_oe  = ~{r[7], r[6]};
    assign pin_out = {r[3], r[2]};
    wire [15:0] pin_val = (pin_oe & pin_out) | (~pin_oe & pin_in);

    reg sda_low = 1'b0;
    assign sda = sda_low ? 1'b0 : 1'bz;
    wire sda_v = (sda !== 1'b0);

    reg [3:0] bitn;
    reg [7:0] sh, tx;
    reg [2:0] st;            // 0 idle, 1 address, 2 register, 3 write data, 4 read data
    reg       ackph, rd, me;
    reg [2:0] ptr;
    initial begin st = 0; bitn = 0; ackph = 0; ptr = 0; end

    function [7:0] rdreg(input [2:0] a);
        rdreg = (a == 3'd0) ? pin_val[7:0] : (a == 3'd1) ? pin_val[15:8] : r[a];
    endfunction

    // START (also repeated) and STOP
    always @(negedge sda) if (scl === 1'b1) begin st = 3'd1; bitn = 0; ackph = 0; sda_low = 1'b0; end
    always @(posedge sda) if (scl === 1'b1) begin st = 3'd0; ackph = 0; sda_low = 1'b0; end

    always @(posedge scl) begin
        if (st != 0 && !ackph && bitn < 8) begin
            if (st != 3'd4) sh = {sh[6:0], sda_v};
            bitn = bitn + 1;
        end else if (st == 3'd4 && ackph && sda_v) begin
            st = 3'd0;                       // master NACK: the read ends
        end
    end

    always @(negedge scl) begin
        if (st == 0) begin
            sda_low = 1'b0;
        end else if (!ackph && bitn == 8) begin
            ackph = 1;
            case (st)
                3'd1: begin me = (sh[7:1] == ADDR); rd = sh[0]; sda_low = me; if (!me) st = 3'd0; end
                3'd2: begin ptr = sh[2:0]; sda_low = 1'b1; end
                3'd3: begin
                    if (ptr != 3'd0 && ptr != 3'd1) r[ptr] = sh;
                    n_writes = n_writes + 1;
                    ptr = {ptr[2:1], ~ptr[0]};
                    sda_low = 1'b1;
                end
                default: sda_low = 1'b0;     // read byte sent: the master drives ACK/NACK
            endcase
        end else if (ackph) begin
            ackph = 0; bitn = 0;
            case (st)
                3'd1: if (rd) begin st = 3'd4; tx = rdreg(ptr); ptr = {ptr[2:1], ~ptr[0]}; sda_low = ~tx[7]; end
                      else begin st = 3'd2; sda_low = 1'b0; end
                3'd2: begin st = 3'd3; sda_low = 1'b0; end
                3'd4: begin tx = rdreg(ptr); ptr = {ptr[2:1], ~ptr[0]}; sda_low = ~tx[7]; end
                default: sda_low = 1'b0;
            endcase
        end else if (st == 3'd4) begin
            sda_low = ~tx[7 - bitn];
        end else begin
            sda_low = 1'b0;
        end
    end
endmodule


// RFFC5072 three-wire port: register file 0x00..0x1F, framing as HackRF drives it (RFFC5072_PROGRAMMING.md
// section 2). A read of 0x1F returns the register READSEL selects; here READSEL = 0 gives the device ID 0x8A01
// and READSEL = 1 puts the lock flag in bit 15. lock goes high 1 us after ENBL rises.
module rffc5072_model (
    input  wire enx,
    input  wire sclk,
    inout  wire sdata,
    input  wire enbl,
    input  wire resetx,
    output reg  ld,
    output reg [31:0] n_frames
);
    reg [15:0] r [0:31];
    integer i;
    initial begin for (i = 0; i < 32; i = i + 1) r[i] = 16'h0000; ld = 1'b0; n_frames = 0; end

    integer    cnt;          // rising edges since ENX fell
    reg [24:0] sh;
    reg        rdmode, drive, ta_fall;
    reg [6:0]  addr;
    reg [15:0] rdv;
    assign sdata = drive ? rdv[15] : 1'bz;

    always @(negedge enx) begin cnt = 0; sh = 0; rdmode = 1'b0; drive = 1'b0; ta_fall = 1'b0; end
    always @(posedge enx) begin
        drive = 1'b0;
        if (!rdmode && cnt == 25) begin r[sh[22:16]] = sh[15:0]; n_frames = n_frames + 1; end
        if (rdmode) n_frames = n_frames + 1;
    end
    always @(posedge sclk) if (enx === 1'b0) begin
        if (!rdmode) begin
            sh  = {sh[23:0], (sdata === 1'b1)};
            cnt = cnt + 1;
            if (cnt == 9 && sh[7]) begin          // header {0, R/W, A6..A0} complete, R/W = 1
                rdmode = 1'b1;
                addr   = sh[6:0];
                cnt    = 0;
            end
        end else begin
            if (cnt == 0) begin                   // turnaround clock: drive the word, MSB first
                rdv     = (addr == 7'h1F) ? ((r[5'h1D][15:12] == 4'd1) ? {ld, 15'd0} : 16'h8A01) : r[addr[4:0]];
                drive   = 1'b1;
                ta_fall = 1'b1;
            end
            cnt = cnt + 1;
        end
    end
    always @(negedge sclk) if (enx === 1'b0 && rdmode && drive) begin
        if (ta_fall) ta_fall = 1'b0;             // no shift on the turnaround's falling edge
        else rdv = {rdv[14:0], 1'b0};
    end
    always @(posedge enbl) begin ld = 1'b0; #1000 ld = enbl; end
    always @(negedge enbl) ld = 1'b0;
endmodule


// PE4312: 6-bit shift register (MSB first, sampled on SCLK rising) behind a latch that is transparent while LE
// is high and holds when LE goes low [PE4312 data sheet, serial interface]. Powers up at 31.5 dB (0x3F).
module pe4312_model (
    input  wire sclk,
    input  wire sdata,
    input  wire le,
    output reg [5:0] att,
    output reg [31:0] n_changes   // times the attenuation changed
);
    reg [5:0] sh;
    initial begin sh = 6'h3F; att = 6'h3F; n_changes = 0; end
    always @(posedge sclk) sh <= {sh[4:0], (sdata === 1'b1)};
    always @* if (le === 1'b1 && att !== sh) begin att = sh; n_changes = n_changes + 1; end
endmodule
