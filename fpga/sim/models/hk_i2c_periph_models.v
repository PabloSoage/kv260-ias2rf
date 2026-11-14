// SPDX-License-Identifier: BSD-2-Clause
// Behavioral Open-Drain I2C Slave Model for Housekeeping & Si549 XO
// Used for TMP1075 (0x48), CAT24C02 EEPROM (0x50), and Si549 XO (0x55).

`timescale 1ps/10fs

module sim_hk_i2c_slave #(
    parameter [6:0]   SLAVE_ADDR = 7'h50,
    parameter integer NUM_REGS   = 256
) (
    input  wire scl,
    inout  wire sda,
    input  wire enable_ack
);
    reg [7:0] mem [0:NUM_REGS-1];
    reg       sda_drv_low = 1'b0;
    assign sda = sda_drv_low ? 1'b0 : 1'bz;

    reg       prev_scl = 1'b1, prev_sda = 1'b1;
    reg [2:0] state = 3'd0;
    reg [3:0] bit_cnt = 4'd0;
    reg [7:0] shift_reg = 8'd0, reg_ptr = 8'd0;
    reg       have_reg_ptr = 1'b0, rw_bit = 1'b0, addr_match = 1'b0, ack_done = 1'b0;

    integer idx;
    initial begin
        for (idx = 0; idx < NUM_REGS; idx = idx + 1)
            mem[idx] = 8'h00;
    end

    always @(scl or sda) begin
        if (scl === 1'b1 && prev_scl === 1'b1 && prev_sda === 1'b1 && sda === 1'b0) begin
            state <= 3'd1; bit_cnt <= 4'd0; ack_done <= 1'b0; sda_drv_low <= 1'b0;
        end else if (scl === 1'b1 && prev_scl === 1'b1 && prev_sda === 1'b0 && sda === 1'b1) begin
            state <= 3'd0; have_reg_ptr <= 1'b0; ack_done <= 1'b0; sda_drv_low <= 1'b0;
        end else if (scl === 1'b1 && prev_scl === 1'b0) begin
            if (state == 3'd1 || state == 3'd2 || state == 3'd3) begin
                if (bit_cnt < 4'd8) begin
                    shift_reg <= {shift_reg[6:0], (sda !== 1'b0)};
                    bit_cnt   <= bit_cnt + 4'd1;
                end else bit_cnt <= 4'd0;
            end else if (state == 3'd4) begin
                if (bit_cnt < 4'd8) bit_cnt <= bit_cnt + 4'd1;
                else begin
                    bit_cnt <= 4'd0;
                    if (sda === 1'b0) reg_ptr <= reg_ptr + 8'd1;
                    else              state   <= 3'd0;
                end
            end
        end else if (scl === 1'b0 && prev_scl === 1'b1) begin
            if (state == 3'd1 && bit_cnt == 4'd8) begin
                addr_match  = (shift_reg[7:1] == SLAVE_ADDR) && enable_ack;
                rw_bit      = shift_reg[0];
                ack_done   <= 1'b1;
                sda_drv_low <= addr_match ? 1'b1 : 1'b0;
            end else if ((state == 3'd1 || state == 3'd2 || state == 3'd3) && ack_done && (bit_cnt == 4'd0)) begin
                ack_done    <= 1'b0;
                sda_drv_low <= 1'b0;
                if (state == 3'd1) begin
                    if (!addr_match) state <= 3'd0;
                    else if (rw_bit) begin
                        state       <= 3'd4;
                        shift_reg   <= mem[reg_ptr];
                        sda_drv_low <= ~mem[reg_ptr][7];
                    end else state <= have_reg_ptr ? 3'd3 : 3'd2;
                end else if (state == 3'd2) begin
                    reg_ptr <= shift_reg; have_reg_ptr <= 1'b1; state <= 3'd3;
                end else if (state == 3'd3) begin
                    mem[reg_ptr] <= shift_reg; reg_ptr <= reg_ptr + 8'd1;
                end
            end else if ((state == 3'd2 || state == 3'd3) && bit_cnt == 4'd8) begin
                ack_done <= 1'b1; sda_drv_low <= 1'b1;
            end else if (state == 3'd4) begin
                if (bit_cnt == 4'd8) sda_drv_low <= 1'b0;
                else if (bit_cnt == 4'd0) begin
                    shift_reg <= mem[reg_ptr]; sda_drv_low <= ~mem[reg_ptr][7];
                end else sda_drv_low <= ~shift_reg[7 - bit_cnt[2:0]];
            end else sda_drv_low <= 1'b0;
        end
        prev_scl <= scl;
        prev_sda <= sda;
    end
endmodule
