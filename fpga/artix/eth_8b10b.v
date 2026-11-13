// SPDX-License-Identifier: BSD-2-Clause
// IEEE 802.3 Clause 36 8b/10b Encoder and Decoder
// code[9:0] = {j, h, g, f, i, e, d, c, b, a}, transmitted LSB-first (bit[0]=a).

`timescale 1ns/1ps
`default_nettype none

module eth_8b10b_enc (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    input  wire       din_k,
    input  wire [7:0] din,
    output reg  [9:0] dout,
    output reg        rd_pos
);
    wire [4:0] x = din[4:0];
    wire [2:0] y = din[7:5];

    reg [5:0] s6;
    reg       rd6_flip;
    always @(*) begin
        if (din_k) begin
            case (x)
                5'd23: begin s6 = rd_pos ? 6'b101000 : 6'b010111; rd6_flip = 1'b1; end // K23.7 (msb abcdei=111010 -> lsb 010111)
                5'd27: begin s6 = rd_pos ? 6'b100100 : 6'b011011; rd6_flip = 1'b1; end // K27.7 (110110 -> 011011)
                5'd28: begin s6 = rd_pos ? 6'b000011 : 6'b111100; rd6_flip = 1'b1; end // K28.x (001111 -> 111100)
                5'd29: begin s6 = rd_pos ? 6'b100010 : 6'b011101; rd6_flip = 1'b1; end // K29.7 (101110 -> 011101)
                5'd30: begin s6 = rd_pos ? 6'b100001 : 6'b011110; rd6_flip = 1'b1; end // K30.7 (011110 -> 011110)
                default: begin s6 = rd_pos ? 6'b000011 : 6'b111100; rd6_flip = 1'b1; end
            endcase
        end else begin
            case (x)
                5'd 0: begin s6 = rd_pos ? 6'b000110 : 6'b111001; rd6_flip = 1'b1; end
                5'd 1: begin s6 = rd_pos ? 6'b010001 : 6'b101110; rd6_flip = 1'b1; end
                5'd 2: begin s6 = rd_pos ? 6'b010010 : 6'b101101; rd6_flip = 1'b1; end
                5'd 3: begin s6 = 6'b100011; rd6_flip = 1'b0; end
                5'd 4: begin s6 = rd_pos ? 6'b010100 : 6'b101011; rd6_flip = 1'b1; end
                5'd 5: begin s6 = 6'b100101; rd6_flip = 1'b0; end
                5'd 6: begin s6 = 6'b100110; rd6_flip = 1'b0; end
                5'd 7: begin s6 = rd_pos ? 6'b111000 : 6'b000111; rd6_flip = 1'b0; end
                5'd 8: begin s6 = rd_pos ? 6'b011000 : 6'b100111; rd6_flip = 1'b1; end
                5'd 9: begin s6 = 6'b101001; rd6_flip = 1'b0; end
                5'd10: begin s6 = 6'b101010; rd6_flip = 1'b0; end
                5'd11: begin s6 = 6'b001011; rd6_flip = 1'b0; end
                5'd12: begin s6 = 6'b101100; rd6_flip = 1'b0; end
                5'd13: begin s6 = 6'b001101; rd6_flip = 1'b0; end
                5'd14: begin s6 = 6'b001110; rd6_flip = 1'b0; end
                5'd15: begin s6 = rd_pos ? 6'b000101 : 6'b111010; rd6_flip = 1'b1; end
                5'd16: begin s6 = rd_pos ? 6'b001001 : 6'b110110; rd6_flip = 1'b1; end
                5'd17: begin s6 = 6'b110001; rd6_flip = 1'b0; end
                5'd18: begin s6 = 6'b110010; rd6_flip = 1'b0; end
                5'd19: begin s6 = 6'b010011; rd6_flip = 1'b0; end
                5'd20: begin s6 = 6'b110100; rd6_flip = 1'b0; end
                5'd21: begin s6 = 6'b010101; rd6_flip = 1'b0; end
                5'd22: begin s6 = 6'b010110; rd6_flip = 1'b0; end
                5'd23: begin s6 = rd_pos ? 6'b101000 : 6'b010111; rd6_flip = 1'b1; end
                5'd24: begin s6 = rd_pos ? 6'b001100 : 6'b110011; rd6_flip = 1'b1; end
                5'd25: begin s6 = 6'b011001; rd6_flip = 1'b0; end
                5'd26: begin s6 = 6'b011010; rd6_flip = 1'b0; end
                5'd27: begin s6 = rd_pos ? 6'b100100 : 6'b011011; rd6_flip = 1'b1; end
                5'd28: begin s6 = 6'b011100; rd6_flip = 1'b0; end
                5'd29: begin s6 = rd_pos ? 6'b100010 : 6'b011101; rd6_flip = 1'b1; end
                5'd30: begin s6 = rd_pos ? 6'b100001 : 6'b011110; rd6_flip = 1'b1; end
                5'd31: begin s6 = rd_pos ? 6'b001010 : 6'b110101; rd6_flip = 1'b1; end
            endcase
        end
    end

    wire rd_mid = rd_pos ^ rd6_flip;
    wire use_alt7 = !din_k && (y == 3'd7) && ((!rd_mid && (x == 5'd17 || x == 5'd18 || x == 5'd20)) || (rd_mid && (x == 5'd11 || x == 5'd13 || x == 5'd14)));
    reg [3:0] s4;
    reg       rd4_flip;
    always @(*) begin
        if (din_k) begin
            // Wait: for K28.y, RD_in determines 4b when balanced or flips with rd_mid; check direct Table 36-2:
            case ({y, (x == 5'd28)})
                // Generated per-K 4-bit mapping directly indexed by rd_pos (before symbol) for exact Table 36-2:
                {3'd0, 1'b1}: begin s4 = rd_pos ? 4'b1101 : 4'b0010; rd4_flip = 1'b1; end
                {3'd1, 1'b1}: begin s4 = rd_pos ? 4'b0110 : 4'b1001; rd4_flip = 1'b0; end
                {3'd2, 1'b1}: begin s4 = rd_pos ? 4'b0101 : 4'b1010; rd4_flip = 1'b0; end
                {3'd3, 1'b1}: begin s4 = rd_pos ? 4'b0011 : 4'b1100; rd4_flip = 1'b0; end
                {3'd4, 1'b1}: begin s4 = rd_pos ? 4'b1011 : 4'b0100; rd4_flip = 1'b1; end
                {3'd5, 1'b1}: begin s4 = rd_pos ? 4'b1010 : 4'b0101; rd4_flip = 1'b0; end
                {3'd6, 1'b1}: begin s4 = rd_pos ? 4'b1001 : 4'b0110; rd4_flip = 1'b0; end
                {3'd7, 1'b1}: begin s4 = rd_pos ? 4'b1110 : 4'b0001; rd4_flip = 1'b1; end
                default: begin s4 = rd_pos ? 4'b1110 : 4'b0001; rd4_flip = 1'b1; end // K23/27/29/30.7
            endcase
        end else if (use_alt7) begin
            s4 = rd_mid ? 4'b0001 : 4'b1110; // msb fghj=1000 -> lsb 0001 (RD+), fghj=0111 -> lsb 1110 (RD-)
            rd4_flip = 1'b1;
        end else begin
            case (y)
                3'd0: begin s4 = rd_mid ? 4'b0010 : 4'b1101; rd4_flip = 1'b1; end
                3'd1: begin s4 = 4'b1001; rd4_flip = 1'b0; end
                3'd2: begin s4 = 4'b1010; rd4_flip = 1'b0; end
                3'd3: begin s4 = rd_mid ? 4'b1100 : 4'b0011; rd4_flip = 1'b0; end
                3'd4: begin s4 = rd_mid ? 4'b0100 : 4'b1011; rd4_flip = 1'b1; end
                3'd5: begin s4 = 4'b0101; rd4_flip = 1'b0; end
                3'd6: begin s4 = 4'b0110; rd4_flip = 1'b0; end
                3'd7: begin s4 = rd_mid ? 4'b1000 : 4'b0111; rd4_flip = 1'b1; end
            endcase
        end
    end

    wire rd_next = rd_mid ^ rd4_flip;
    always @(posedge clk) begin
        if (rst) begin
            dout   <= 10'h17C; // K28.5 RD-
            rd_pos <= 1'b0;
        end else if (en) begin
            dout   <= {s4, s6};
            rd_pos <= rd_next;
        end
    end
endmodule

module eth_8b10b_dec (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    input  wire [9:0] din,
    output reg        dout_k,
    output reg  [7:0] dout,
    output reg        code_err,
    output reg        disp_err,
    output reg        rd_pos
);
    reg       dec_valid;
    reg       dec_k;
    reg [7:0] dec_byte;
    reg [1:0] dec_exp_rd; // 2'd0=req RD-, 2'd1=req RD+, 2'd2=either
    reg       dec_rd_out; // only meaningful if neutral/determines next RD
    reg       dec_flip;
    always @(*) begin
        dec_valid  = 1'b0;
        dec_k      = 1'b0;
        dec_byte   = 8'h00;
        dec_exp_rd = 2'd2;
        dec_flip   = 1'b0;
        case (din)
            10'h04B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hEB; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h04D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hED; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h04E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hEE; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h057: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'hF7; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h05B: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'hFB; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h05D: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'hFD; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h05E: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'hFE; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h07C: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'hFC; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h08B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h0B; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h08D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h0D; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h08E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h0E; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h093: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h13; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h095: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h15; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h096: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h16; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h097: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h17; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h099: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h19; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h09A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h1A; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h09B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h1B; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h09C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h1C; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h09D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h1D; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h09E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h1E; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0A3: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h03; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0A5: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h05; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0A6: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h06; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0A7: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h08; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0A9: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h09; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0AA: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h0A; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0AB: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h04; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0AC: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h0C; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0AD: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h02; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0AE: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h01; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0B1: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h11; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0B2: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h12; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0B3: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h18; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0B4: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h14; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0B5: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h1F; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0B6: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h10; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0B8: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h07; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0B9: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h00; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0BA: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h0F; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0BC: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'h1C; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0C3: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'h7C; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0C5: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h6F; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0C6: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h60; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0C7: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h67; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0C9: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h70; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0CA: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h7F; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0CB: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h6B; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0CC: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h78; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0CD: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h6D; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0CE: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h6E; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0D1: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h61; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0D2: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h62; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0D3: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h73; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0D4: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h64; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0D5: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h75; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0D6: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h76; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0D8: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h68; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0D9: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h79; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0DA: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h7A; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0DC: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h7C; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0E1: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h7E; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0E2: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h7D; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0E3: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h63; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0E4: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h7B; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0E5: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h65; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0E6: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h66; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0E8: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h77; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h0E9: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h69; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0EA: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h6A; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0EC: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h6C; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0F1: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h71; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0F2: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h72; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h0F4: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h74; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h10B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h8B; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h10D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h8D; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h10E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h8E; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h113: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h93; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h115: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h95; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h116: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h96; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h117: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h97; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h119: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h99; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h11A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h9A; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h11B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h9B; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h11C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h9C; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h11D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h9D; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h11E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h9E; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h123: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h83; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h125: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h85; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h126: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h86; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h127: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h88; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h129: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h89; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h12A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h8A; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h12B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h84; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h12C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h8C; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h12D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h82; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h12E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h81; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h131: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h91; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h132: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h92; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h133: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h98; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h134: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h94; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h135: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h9F; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h136: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h90; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h138: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h87; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h139: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h80; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h13A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h8F; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h13C: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'h9C; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h143: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'h5C; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h145: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hAF; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h146: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hA0; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h147: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hA7; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h149: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hB0; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h14A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hBF; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h14B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hAB; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h14C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hB8; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h14D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hAD; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h14E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hAE; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h151: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hA1; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h152: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hA2; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h153: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hB3; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h154: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hA4; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h155: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hB5; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h156: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hB6; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h157: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hB7; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h158: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hA8; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h159: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hB9; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h15A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hBA; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h15B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hBB; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h15C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hBC; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h15D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hBD; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h15E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hBE; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h161: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hBE; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h162: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hBD; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h163: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hA3; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h164: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hBB; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h165: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hA5; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h166: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hA6; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h167: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hA8; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h168: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hB7; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h169: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hA9; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h16A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hAA; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h16B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hA4; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h16C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hAC; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h16D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hA2; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h16E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hA1; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h171: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hB1; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h172: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hB2; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h173: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hB8; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h174: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hB4; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h175: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hBF; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h176: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hB0; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h178: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hA7; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h179: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hA0; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h17A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hAF; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h17C: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'hBC; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h183: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'h3C; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h185: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hCF; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h186: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hC0; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h187: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hC7; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h189: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hD0; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h18A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hDF; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h18B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hCB; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h18C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hD8; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h18D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hCD; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h18E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hCE; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h191: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hC1; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h192: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hC2; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h193: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hD3; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h194: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hC4; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h195: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hD5; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h196: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hD6; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h197: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hD7; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h198: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hC8; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h199: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hD9; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h19A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hDA; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h19B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hDB; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h19C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hDC; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h19D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hDD; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h19E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hDE; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1A1: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hDE; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h1A2: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hDD; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h1A3: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hC3; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h1A4: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hDB; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h1A5: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hC5; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h1A6: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hC6; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h1A7: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hC8; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1A8: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hD7; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h1A9: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hC9; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h1AA: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hCA; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h1AB: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hC4; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1AC: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hCC; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h1AD: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hC2; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1AE: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hC1; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1B1: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hD1; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h1B2: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hD2; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h1B3: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hD8; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1B4: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hD4; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h1B5: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hDF; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1B6: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hD0; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1B8: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hC7; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h1B9: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hC0; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1BA: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hCF; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1BC: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'hDC; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1C5: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hEF; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h1C6: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE0; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h1C7: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE7; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1C9: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF0; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h1CA: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hFF; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h1CB: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hEB; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1CC: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF8; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h1CD: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hED; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1CE: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hEE; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1D1: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE1; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h1D2: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE2; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h1D3: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF3; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1D4: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE4; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h1D5: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF5; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1D6: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF6; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1D8: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE8; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h1D9: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF9; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1DA: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hFA; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1DC: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hFC; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1E1: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hFE; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h1E2: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hFD; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h1E3: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE3; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1E4: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hFB; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h1E5: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE5; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1E6: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE6; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1E8: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF7; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h1E9: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE9; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1EA: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hEA; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h1EC: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hEC; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h213: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF3; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h215: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF5; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h216: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF6; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h217: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF7; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h219: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF9; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h21A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hFA; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h21B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hFB; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h21C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hFC; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h21D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hFD; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h21E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hFE; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h223: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE3; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h225: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE5; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h226: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE6; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h227: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE8; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h229: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE9; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h22A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hEA; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h22B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE4; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h22C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hEC; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h22D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE2; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h22E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE1; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h231: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF1; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h232: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF2; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h233: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF8; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h234: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF4; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h235: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hFF; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h236: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF0; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h238: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE7; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h239: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hE0; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h23A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hEF; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h243: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'hDC; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h245: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h2F; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h246: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h20; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h247: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h27; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h249: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h30; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h24A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h3F; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h24B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h2B; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h24C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h38; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h24D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h2D; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h24E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h2E; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h251: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h21; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h252: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h22; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h253: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h33; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h254: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h24; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h255: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h35; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h256: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h36; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h257: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h37; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h258: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h28; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h259: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h39; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h25A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h3A; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h25B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h3B; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h25C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h3C; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h25D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h3D; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h25E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h3E; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h261: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h3E; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h262: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h3D; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h263: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h23; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h264: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h3B; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h265: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h25; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h266: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h26; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h267: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h28; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h268: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h37; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h269: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h29; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h26A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h2A; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h26B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h24; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h26C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h2C; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h26D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h22; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h26E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h21; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h271: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h31; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h272: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h32; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h273: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h38; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h274: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h34; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h275: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h3F; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h276: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h30; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h278: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h27; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h279: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h20; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h27A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h2F; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h27C: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'h3C; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h283: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'hBC; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h285: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h4F; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h286: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h40; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h287: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h47; dec_exp_rd=2'd0; dec_flip=1'b0; end
            10'h289: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h50; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h28A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h5F; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h28B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h4B; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h28C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h58; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h28D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h4D; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h28E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h4E; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h291: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h41; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h292: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h42; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h293: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h53; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h294: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h44; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h295: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h55; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h296: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h56; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h297: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h57; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h298: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h48; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h299: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h59; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h29A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h5A; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h29B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h5B; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h29C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h5C; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h29D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h5D; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h29E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h5E; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2A1: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h5E; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h2A2: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h5D; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h2A3: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h43; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h2A4: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h5B; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h2A5: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h45; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h2A6: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h46; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h2A7: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h48; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2A8: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h57; dec_exp_rd=2'd1; dec_flip=1'b1; end
            10'h2A9: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h49; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h2AA: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h4A; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h2AB: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h44; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2AC: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h4C; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h2AD: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h42; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2AE: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h41; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2B1: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h51; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h2B2: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h52; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h2B3: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h58; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2B4: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h54; dec_exp_rd=2'd2; dec_flip=1'b0; end
            10'h2B5: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h5F; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2B6: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h50; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2B8: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h47; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h2B9: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h40; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2BA: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h4F; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2BC: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'h5C; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2C3: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'h9C; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h2C5: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h8F; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h2C6: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h80; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h2C7: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h87; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2C9: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h90; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h2CA: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h9F; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h2CB: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h8B; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2CC: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h98; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h2CD: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h8D; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2CE: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h8E; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2D1: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h81; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h2D2: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h82; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h2D3: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h93; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2D4: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h84; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h2D5: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h95; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2D6: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h96; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2D8: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h88; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h2D9: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h99; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2DA: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h9A; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2DC: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h9C; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2E1: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h9E; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h2E2: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h9D; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h2E3: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h83; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2E4: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h9B; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h2E5: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h85; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2E6: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h86; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2E8: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h97; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h2E9: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h89; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2EA: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h8A; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2EC: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h8C; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2F1: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h91; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2F2: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h92; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h2F4: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h94; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h30B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h6B; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h30D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h6D; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h30E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h6E; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h313: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h73; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h315: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h75; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h316: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h76; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h317: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h77; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h319: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h79; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h31A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h7A; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h31B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h7B; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h31C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h7C; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h31D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h7D; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h31E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h7E; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h323: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h63; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h325: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h65; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h326: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h66; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h327: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h68; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h329: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h69; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h32A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h6A; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h32B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h64; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h32C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h6C; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h32D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h62; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h32E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h61; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h331: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h71; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h332: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h72; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h333: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h78; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h334: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h74; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h335: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h7F; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h336: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h70; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h338: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h67; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h339: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h60; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h33A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h6F; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h33C: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'h7C; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h343: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'h1C; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h345: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h0F; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h346: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h00; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h347: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h07; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h349: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h10; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h34A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h1F; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h34B: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h0B; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h34C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h18; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h34D: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h0D; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h34E: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h0E; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h351: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h01; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h352: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h02; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h353: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h13; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h354: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h04; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h355: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h15; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h356: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h16; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h358: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h08; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h359: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h19; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h35A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h1A; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h35C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h1C; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h361: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h1E; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h362: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h1D; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h363: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h03; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h364: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h1B; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h365: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h05; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h366: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h06; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h368: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h17; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h369: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h09; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h36A: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h0A; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h36C: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h0C; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h371: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h11; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h372: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h12; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h374: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'h14; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h383: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'hFC; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h3A1: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'hFE; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h3A2: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'hFD; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h3A4: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'hFB; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h3A8: begin dec_valid=1'b1; dec_k=1'b1; dec_byte=8'hF7; dec_exp_rd=2'd1; dec_flip=1'b0; end
            10'h3B1: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF1; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h3B2: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF2; dec_exp_rd=2'd0; dec_flip=1'b1; end
            10'h3B4: begin dec_valid=1'b1; dec_k=1'b0; dec_byte=8'hF4; dec_exp_rd=2'd0; dec_flip=1'b1; end
            default: begin dec_valid=1'b0; end
        endcase
    end

    wire bad_disp = (dec_exp_rd != 2'd2) && (dec_exp_rd[0] != rd_pos);
    wire [3:0] ones_cnt = din[0]+din[1]+din[2]+din[3]+din[4]+din[5]+din[6]+din[7]+din[8]+din[9];
    always @(posedge clk) begin
        if (rst) begin
            dout_k   <= 1'b0;
            dout     <= 8'h00;
            code_err <= 1'b0;
            disp_err <= 1'b0;
            rd_pos   <= 1'b0;
        end else if (en) begin
            dout_k   <= dec_valid ? dec_k : 1'b0;
            dout     <= dec_valid ? dec_byte : 8'h00;
            code_err <= ~dec_valid;
            disp_err <= dec_valid && bad_disp;
            if (!dec_valid)
                rd_pos <= (ones_cnt > 4'd5) ? 1'b1 : (ones_cnt < 4'd5) ? 1'b0 : rd_pos;
            else if (dec_exp_rd != 2'd2)
                rd_pos <= dec_exp_rd[0] ^ dec_flip;
            else
                rd_pos <= rd_pos ^ dec_flip;
        end
    end
endmodule
`default_nettype wire
