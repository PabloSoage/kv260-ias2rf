// SPDX-License-Identifier: BSD-2-Clause
// 66:8 TX Gearbox, 8:66 RX Gearbox with unified 1-UI bit slip,
// and IEEE 802.3 Clause 49.2.13 Block Lock FSM (64 good -> lock, 16/64 bad -> unlock).

`timescale 1ns/1ps

module link_gearbox_tx (
    input  wire        clk,
    input  wire        rst,
    input  wire        in_valid,
    output wire        in_ready,
    input  wire [65:0] in_block,
    output reg  [7:0]  out_byte
);
    reg [131:0] buf_bits;
    reg [7:0]   bit_cnt;

    assign in_ready = (bit_cnt <= 8'd65);

    always @(posedge clk) begin
        if (rst) begin
            buf_bits <= 132'd0;
            bit_cnt  <= 8'd0;
            out_byte <= 8'd0;
        end else begin
            // Append incoming block (or Idle fill if buffer < 8 bits) then emit 8 LSBs.
            if (in_ready && in_valid) begin
                buf_bits <= (buf_bits | ({66'd0, in_block} << bit_cnt)) >> 8;
                bit_cnt  <= bit_cnt + 8'd58; // +66 - 8
                if (bit_cnt == 8'd0)
                    out_byte <= in_block[7:0];
                else if (bit_cnt < 8'd8)
                    out_byte <= (buf_bits[7:0] | (in_block[7:0] << bit_cnt));
                else
                    out_byte <= buf_bits[7:0];
            end else if (bit_cnt < 8'd8) begin
                // Startup / starvation guard: insert valid Idle sync/btype so wire stays active.
                buf_bits <= (buf_bits | ({66'd0, 64'h0000_0000_0000_001E, 2'b10} << bit_cnt)) >> 8;
                bit_cnt  <= bit_cnt + 8'd58;
                if (bit_cnt == 8'd0)
                    out_byte <= 8'h7A; // {8'h1E[5:0], 2'b10} = 8'h7A
                else
                    out_byte <= (buf_bits[7:0] | (8'h7A << bit_cnt));
            end else begin
                out_byte <= buf_bits[7:0];
                buf_bits <= buf_bits >> 8;
                bit_cnt  <= bit_cnt - 8'd8;
            end
        end
    end
endmodule

module link_gearbox_rx (
    input  wire        clk,
    input  wire        rst,
    input  wire [7:0]  in_byte,
    input  wire        rx_slip,
    output reg         out_valid,
    output reg  [65:0] out_block
);
    reg [139:0] buf_bits;
    reg [7:0]   bit_cnt;

    reg [139:0] work_bits;
    reg [7:0]   work_cnt;

    always @* begin
        work_bits = buf_bits | ({132'd0, in_byte} << bit_cnt);
        work_cnt  = bit_cnt + 8'd8;
    end

    always @(posedge clk) begin
        if (rst) begin
            buf_bits  <= 140'd0;
            bit_cnt   <= 8'd0;
            out_valid <= 1'b0;
            out_block <= 66'd0;
        end else if (rx_slip) begin
            // Discard 1 UI bit to advance the 66-bit extraction boundary by +1 bit.
            buf_bits  <= work_bits >> 1;
            bit_cnt   <= work_cnt - 8'd1;
            out_valid <= 1'b0;
        end else if (work_cnt >= 8'd66) begin
            out_block <= work_bits[65:0];
            out_valid <= 1'b1;
            buf_bits  <= work_bits >> 66;
            bit_cnt   <= work_cnt - 8'd66;
        end else begin
            buf_bits  <= work_bits;
            bit_cnt   <= work_cnt;
            out_valid <= 1'b0;
        end
    end
endmodule

module link_block_lock (
    input  wire        clk,
    input  wire        rst,
    input  wire        rx_valid,
    input  wire [1:0]  rx_sync,
    output reg         block_lock,
    output reg         rx_slip,
    output reg  [31:0] sh_err_cnt
);
    reg [6:0] good_cnt;
    reg [5:0] win_cnt;
    reg [4:0] bad_cnt;
    reg       slip_holdoff;

    wire sh_ok = (rx_sync == 2'b01) || (rx_sync == 2'b10);

    always @(posedge clk) begin
        if (rst) begin
            block_lock   <= 1'b0;
            rx_slip      <= 1'b0;
            sh_err_cnt   <= 32'd0;
            good_cnt     <= 7'd0;
            win_cnt      <= 6'd0;
            bad_cnt      <= 5'd0;
            slip_holdoff <= 1'b0;
        end else begin
            rx_slip <= 1'b0;

            if (rx_valid) begin
                if (slip_holdoff) begin
                    // Allow the 8:66 slip boundary transition to settle for one block.
                    slip_holdoff <= 1'b0;
                end else if (!block_lock) begin
                    if (sh_ok) begin
                        if (good_cnt == 7'd63) begin
                            block_lock <= 1'b1;
                            good_cnt   <= 7'd0;
                            win_cnt    <= 6'd0;
                            bad_cnt    <= 5'd0;
                        end else begin
                            good_cnt <= good_cnt + 7'd1;
                        end
                    end else begin
                        good_cnt     <= 7'd0;
                        rx_slip      <= 1'b1;
                        slip_holdoff <= 1'b1;
                        if (sh_err_cnt != 32'hFFFF_FFFF)
                            sh_err_cnt <= sh_err_cnt + 32'd1;
                    end
                end else begin
                    // Clause 49.2.13: lose lock on 16 invalid sync headers within 64 blocks.
                    if (!sh_ok) begin
                        if (sh_err_cnt != 32'hFFFF_FFFF)
                            sh_err_cnt <= sh_err_cnt + 32'd1;
                        if (bad_cnt == 5'd15) begin
                            block_lock   <= 1'b0;
                            good_cnt     <= 7'd0;
                            bad_cnt      <= 5'd0;
                            win_cnt      <= 6'd0;
                            rx_slip      <= 1'b1;
                            slip_holdoff <= 1'b1;
                        end else begin
                            bad_cnt <= bad_cnt + 5'd1;
                            if (win_cnt == 6'd63) begin
                                win_cnt <= 6'd0;
                                bad_cnt <= 5'd0;
                            end else begin
                                win_cnt <= win_cnt + 6'd1;
                            end
                        end
                    end else begin
                        if (win_cnt == 6'd63) begin
                            win_cnt <= 6'd0;
                            bad_cnt <= 5'd0;
                        end else begin
                            win_cnt <= win_cnt + 6'd1;
                        end
                    end
                end
            end
        end
    end
endmodule
