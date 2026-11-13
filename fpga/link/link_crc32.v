// SPDX-License-Identifier: BSD-2-Clause
// Parallel 64-bit IEEE 802.3 CRC-32 Step (Poly 0xEDB88320, LSB-first)

`timescale 1ns/1ps

module link_crc32 (
    input  wire [31:0] crc_in,
    input  wire [63:0] data_in,
    output reg  [31:0] crc_out
);
    integer i;
    reg [31:0] c;

    always @* begin
        c = crc_in;
        for (i = 0; i < 64; i = i + 1) begin
            if ((c[0] ^ data_in[i]) == 1'b1)
                c = (c >> 1) ^ 32'hEDB8_8320;
            else
                c = (c >> 1);
        end
        crc_out = c;
    end
endmodule
