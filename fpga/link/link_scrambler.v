// SPDX-License-Identifier: BSD-2-Clause
// 64b/66b Scrambler / Encoder and Self-Synchronous Descrambler / Decoder
// IEEE 802.3 Clause 49 polynomial: G(x) = 1 + x^39 + x^58
// Sync header sync[1:0] is never scrambled; payload[63:0] is processed LSB-first.

`timescale 1ns/1ps

module link_64b66b_enc #(
    parameter BAD_SCRAMBLER = 0
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        in_valid,
    output wire        in_ready,
    input  wire [1:0]  in_sync,
    input  wire [63:0] in_data,
    output reg         out_valid,
    input  wire        out_ready,
    output reg  [65:0] out_block
);
    reg  [57:0] scr_state;
    reg  [57:0] scr_next;
    reg  [63:0] scrambled;
    integer     i;
    reg         tap_a;
    reg         sbit;

    assign in_ready = (!out_valid) || out_ready;

    always @* begin
        scr_next = scr_state;
        for (i = 0; i < 64; i = i + 1) begin
            tap_a = (BAD_SCRAMBLER != 0) ? scr_next[37] : scr_next[38];
            sbit = in_data[i] ^ tap_a ^ scr_next[57];
            scrambled[i] = sbit;
            scr_next = {scr_next[56:0], sbit};
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            scr_state <= 58'h3FF_FFFF_FFFF_FFFF;
            out_valid <= 1'b0;
            out_block <= 66'd0;
        end else begin
            if (in_valid && in_ready) begin
                scr_state <= scr_next;
                out_block <= {scrambled, in_sync};
                out_valid <= 1'b1;
            end else if (out_valid && out_ready) begin
                out_valid <= 1'b0;
            end
        end
    end
endmodule

module link_64b66b_dec #(
    parameter BAD_SCRAMBLER = 0
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        in_valid,
    input  wire [65:0] in_block,
    output reg         out_valid,
    output reg  [1:0]  out_sync,
    output reg  [63:0] out_data,
    output reg         sync_err
);
    reg  [57:0] scr_state;
    reg  [57:0] scr_next;
    reg  [63:0] descrambled;
    integer     i;
    reg         tap_a;
    reg         rxbit;

    always @* begin
        scr_next = scr_state;
        for (i = 0; i < 64; i = i + 1) begin
            rxbit = in_block[2 + i];
            tap_a = (BAD_SCRAMBLER != 0) ? scr_next[37] : scr_next[38];
            descrambled[i] = rxbit ^ tap_a ^ scr_next[57];
            scr_next = {scr_next[56:0], rxbit};
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            scr_state <= 58'h3FF_FFFF_FFFF_FFFF;
            out_valid <= 1'b0;
            out_sync  <= 2'b00;
            out_data  <= 64'd0;
            sync_err  <= 1'b0;
        end else begin
            out_valid <= in_valid;
            if (in_valid) begin
                scr_state <= scr_next;
                out_sync  <= in_block[1:0];
                out_data  <= descrambled;
                sync_err  <= (in_block[1:0] == 2'b00) || (in_block[1:0] == 2'b11);
            end
        end
    end
endmodule
