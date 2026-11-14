// SPDX-License-Identifier: BSD-2-Clause
// Behavioral AD9253 Dual 14-bit Serial LVDS SDR ADC + 3-Wire SPI Model
//
// Models:
//   - 3-wire SPI register file (Chip ID 0x8F at 0x01; active after reg 0x08/0x21 init).
//   - Dual coherent tones: Ch A = 6.25 MHz (Fs/8), Ch B = 12.5 MHz (Fs/4) @ 50 MSPS.
//   - Board LVDS skew from lvds_skew.py (ADCS_D0 -8 ps, ADCS_D1 -34 ps, ADCS_FCO -18 ps vs DCO)
//     modeled with 25 ps transport margin so FCO/data edges stay centered.

`timescale 1ps/10fs

module sim_ad9253_model (
    input  wire spi_csb,
    input  wire spi_sclk,
    inout  wire spi_sdio,

    output wire adcs_dco_p,
    output wire adcs_dco_n,
    output wire adcs_fco_p,
    output wire adcs_fco_n,
    output wire adcs_d0_p,
    output wire adcs_d0_n,
    output wire adcs_d1_p,
    output wire adcs_d1_n
);
    reg adcs_dco_400m = 1'b0;
    always #1250.000 adcs_dco_400m = ~adcs_dco_400m; // 400 MHz DDR DCO (8 * 50 MSPS)

    reg adcs_dco_quad = 1'b0;
    always @(adcs_dco_400m) adcs_dco_quad <= #625.000 adcs_dco_400m;

    // -------------------------------------------------------------------------
    // 3-Wire SPI Slave (Chip ID 0x8F)
    // -------------------------------------------------------------------------
    reg [7:0]  regs [0:255];
    reg [4:0]  s_bit  = 5'd0;
    reg [23:0] s_cmd  = 24'd0;
    reg [7:0]  s_addr = 8'd0;
    reg [7:0]  s_rsh  = 8'd0;
    reg        s_rw   = 1'b0;
    reg        s_oe   = 1'b0;
    reg        s_out  = 1'b0;
    integer    ri;

    assign spi_sdio = s_oe ? s_out : 1'bz;

    initial begin
        for (ri = 0; ri < 256; ri = ri + 1) regs[ri] = 8'h00;
        regs[8'h01] = 8'h8F;
    end

    always @(negedge spi_csb) begin
        s_bit <= 5'd0; s_cmd <= 24'd0; s_rw <= 1'b0; s_oe <= 1'b0;
    end
    always @(posedge spi_csb) begin
        s_oe <= 1'b0;
    end
    always @(posedge spi_sclk) if (!spi_csb) begin
        s_cmd <= {s_cmd[22:0], spi_sdio};
        s_bit <= s_bit + 5'd1;
        if (s_bit == 5'd15) begin
            s_rw   <= s_cmd[14];
            s_addr <= {s_cmd[6:0], spi_sdio};
            if (s_cmd[14]) s_rsh <= regs[{s_cmd[6:0], spi_sdio}];
        end else if (s_bit == 5'd23 && !s_rw) begin
            regs[s_addr] <= {s_cmd[6:0], spi_sdio};
        end
    end
    always @(negedge spi_sclk) begin
        if (!spi_csb && s_bit >= 5'd16 && s_bit <= 5'd23 && s_rw) begin
            s_oe  <= 1'b1;
            s_out <= s_rsh[7];
            s_rsh <= {s_rsh[6:0], 1'b0};
        end else begin
            s_oe  <= 1'b0;
        end
    end

    wire configured = (regs[8'h08] == 8'h00) && (regs[8'h21] == 8'h40);

    function signed [13:0] tone_a(input [2:0] k);
        case (k)
            3'd0: tone_a =  14'sd0;     3'd1: tone_a =  14'sd4243;
            3'd2: tone_a =  14'sd6000;  3'd3: tone_a =  14'sd4243;
            3'd4: tone_a =  14'sd0;     3'd5: tone_a = -14'sd4243;
            3'd6: tone_a = -14'sd6000;  3'd7: tone_a = -14'sd4243;
        endcase
    endfunction

    function signed [13:0] tone_b(input [1:0] k);
        case (k)
            2'd0: tone_b =  14'sd4000; 2'd1: tone_b =  14'sd0;
            2'd2: tone_b = -14'sd4000; 2'd3: tone_b =  14'sd0;
        endcase
    endfunction

    localparam [15:0] FCO_W = 16'hFF00;
    reg [3:0]  ui_idx = 4'd3;
    reg [2:0]  s_idx  = 3'd0;
    reg [15:0] fa = 16'd0, fb = 16'd0;
    reg        fco_raw = 1'b0, d0_raw = 1'b0, d1_raw = 1'b0;

    always @(adcs_dco_400m) begin
        if (!configured) begin
            fco_raw <= 1'b0; d0_raw <= 1'b0; d1_raw <= 1'b0;
            ui_idx <= 4'd3; s_idx <= 3'd0;
            fa <= {tone_a(3'd0), 2'b00}; fb <= {tone_b(2'd0), 2'b00};
        end else begin
            fco_raw <= FCO_W[15 - ui_idx];
            d0_raw  <= fa[15 - ui_idx];
            d1_raw  <= fb[15 - ui_idx];
            if (ui_idx == 4'd15) begin
                ui_idx <= 4'd0;
                s_idx  <= s_idx + 3'd1;
                fa     <= {tone_a(s_idx + 3'd1), 2'b00};
                fb     <= {tone_b(s_idx[1:0] + 2'd1), 2'b00};
            end else begin
                ui_idx <= ui_idx + 4'd1;
            end
        end
    end

    // Apply board LVDS flight times (390 ps DCO ref -> FCO -18 ps, D0 -8 ps, D1 -34 ps)
    reg dco_del = 1'b0, fco_del = 1'b0, d0_del = 1'b0, d1_del = 1'b0;
    always @(adcs_dco_quad) dco_del <= #390.000 adcs_dco_quad;
    always @(fco_raw)       fco_del <= #372.000 fco_raw;
    always @(d0_raw)        d0_del  <= #382.000 d0_raw;
    always @(d1_raw)        d1_del  <= #356.000 d1_raw;

    assign adcs_dco_p =  dco_del; assign adcs_dco_n = ~dco_del;
    assign adcs_fco_p =  fco_del; assign adcs_fco_n = ~fco_del;
    assign adcs_d0_p  =  d0_del;  assign adcs_d0_n  = ~d0_del;
    assign adcs_d1_p  =  d1_del;  assign adcs_d1_n  = ~d1_del;
endmodule
