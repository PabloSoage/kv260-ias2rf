// SPDX-License-Identifier: BSD-2-Clause
// Behavioral 8-Chip ADAR1000 SPI Slave Array Model
//
// Models:
//   - 8 independent ADAR1000 chips selected by adar_csb[7:0] (active-low).
//   - 24-bit SPI read/write transactions with SDO muxing (bit4 reg 0x00) and address
//     auto-increment (bit5 reg 0x00), latching active registers on adar_tx_load/rx_load.
//   - Real-time safety monitor flagging T/R guard violations whenever adar_tr is
//     asserted while adar_csb != 8'hFF or adar_tx_load/rx_load != 8'h00.

`timescale 1ps/10fs

module sim_adar1000_array (
    input  wire       chk_clk,
    input  wire       chk_rst,
    input  wire       adar_sclk,
    input  wire       adar_sdio,
    output wire       adar_sdo,
    input  wire [7:0] adar_csb,
    input  wire [7:0] adar_rx_load,
    input  wire [7:0] adar_tx_load,
    input  wire [7:0] adar_tr,
    output integer    tr_viol,
    output integer    tx_load_cnt
);
    reg [7:0] adar_regs   [0:7][0:63];
    reg [7:0] adar_active [0:7][0:63];

    integer    as_bit  = 0;
    integer    as_chip = -1;
    integer    c_i, r_i;
    reg [15:0] as_hdr  = 16'd0;
    reg [14:0] as_addr = 15'd0;
    reg        as_rw   = 1'b0;
    reg [7:0]  as_dat  = 8'd0;
    reg [7:0]  as_rsh  = 8'd0;
    reg        as_sdo  = 1'b0;

    assign adar_sdo = as_sdo;

    initial begin
        tr_viol     = 0;
        tx_load_cnt = 0;
        for (c_i = 0; c_i < 8; c_i = c_i + 1) begin
            for (r_i = 0; r_i < 64; r_i = r_i + 1) begin
                adar_regs[c_i][r_i]   = 8'd0;
                adar_active[c_i][r_i] = 8'd0;
            end
        end
    end

    always @(adar_csb) begin
        if (adar_csb == 8'hFF) begin
            as_chip = -1;
            as_sdo <= 1'b0;
        end else begin
            as_bit  = 0;
            as_hdr  = 16'd0;
            as_sdo <= 1'b0;
            as_chip = -1;
            for (c_i = 0; c_i < 8; c_i = c_i + 1) begin
                if (adar_csb[c_i] == 1'b0)
                    as_chip = c_i;
            end
        end
    end

    always @(posedge adar_sclk) if (as_chip >= 0) begin
        if (as_bit < 16) begin
            as_hdr = {as_hdr[14:0], adar_sdio};
            as_bit = as_bit + 1;
            if (as_bit == 16) begin
                as_rw   = as_hdr[15];
                as_addr = as_hdr[14:0];
                as_rsh  = (as_rw && as_addr < 64) ? adar_regs[as_chip][as_addr[5:0]] : 8'h00;
            end
        end else begin
            as_dat = {as_dat[6:0], adar_sdio};
            as_bit = as_bit + 1;
            if (as_bit == 24) begin
                if (!as_rw && as_addr < 64) begin
                    adar_regs[as_chip][as_addr[5:0]] <= as_dat;
                    if (adar_regs[as_chip][0][5])
                        as_addr = as_addr + 15'd1;
                end
                as_bit = 16;
            end
        end
    end

    always @(negedge adar_sclk) begin
        if (as_chip >= 0 && as_bit >= 16 && as_rw && adar_regs[as_chip][0][4]) begin
            as_sdo <= as_rsh[7];
            as_rsh <= {as_rsh[6:0], 1'b0};
        end else begin
            as_sdo <= 1'b0;
        end
    end

    always @(posedge adar_tx_load[0]) begin
        tx_load_cnt <= tx_load_cnt + 1;
        for (c_i = 0; c_i < 8; c_i = c_i + 1) begin
            for (r_i = 16; r_i <= 39; r_i = r_i + 1)
                adar_active[c_i][r_i] <= adar_regs[c_i][r_i];
        end
    end

    always @(posedge chk_clk) if (!chk_rst) begin
        if ((adar_tr != 8'h00) && (adar_csb != 8'hFF || adar_tx_load != 8'h00 || adar_rx_load != 8'h00))
            tr_viol <= tr_viol + 1;
    end
endmodule
