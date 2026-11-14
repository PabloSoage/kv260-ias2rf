// SPDX-License-Identifier: BSD-2-Clause
// Behavioral AD9484 8-bit 400 MSPS DDR LVDS ADC + 3-Wire SPI + RF Echo Target
//
// Models:
//   - 3-wire SPI register file (Chip ID 0x6C at addr 0x01) shared with CONV_SPI.
//   - PCB inverted DCO routing (ADCR_DCO_N -> N14 MRCC_P, ADCR_DCO_P -> P14 MRCC_N).
//   - Per-bit LVDS board+package skew from lvds_skew.py (-90..+5 ps vs ADCR_DCO)
//     plus 16..25 ps eye spread from SIGNAL_INTEGRITY.md §3.3 / §8.
//   - Modes:
//       mode=0 : Alternating 0xAA / 0x55 calibration pattern for IDELAYE2 training
//       mode=1 : Precision 121.5625 MHz IF CW tone (+1.5625 MHz baseband @ 25 MSPS)
//       mode=2 : RF Target Echo Loopback sampling real dacr_d/dacr_clk, delaying by
//                ECHO_DELAY_DAC_CYC clocks, upconverting to 120 MHz IF + thermal noise

`timescale 1ps/10fs

module sim_ad9484_model #(
    parameter integer ECHO_DELAY_DAC_CYC = 250, // 2.000 us @ 125 MHz DAC clock
    parameter integer SEED               = 32'hA484_1001
) (
    input  wire        clk_400m_adc,
    input  wire        dco_true,
    input  wire [1:0]  mode,
    input  wire        no_echo_mut,

    // Real AD9708 DAC RF TX stimulus for closed-loop radar echo
    input  wire        dacr_clk,
    input  wire [7:0]  dacr_d,

    // 3-wire CONV_SPI slave (target CSB_R)
    input  wire        spi_csb,
    input  wire        spi_sclk,
    inout  wire        spi_sdio,

    // Differential LVDS pins to Artix-7 Bank 14
    output reg  [7:0]  adcr_d_p,
    output reg  [7:0]  adcr_d_n,
    output reg         adcr_or_p,
    output reg         adcr_or_n,
    output wire        adcr_dco_p,
    output wire        adcr_dco_n
);
    localparam real PI = 3.14159265358979323846;

    // -------------------------------------------------------------------------
    // 3-Wire SPI Slave (Chip ID 0x6C at 0x01)
    // -------------------------------------------------------------------------
    reg [7:0]  regs [0:255];
    reg [4:0]  s_bit   = 5'd0;
    reg [23:0] s_cmd   = 24'd0;
    reg [7:0]  s_addr  = 8'd0;
    reg [7:0]  s_rsh   = 8'd0;
    reg        s_rw    = 1'b0;
    reg        s_oe    = 1'b0;
    reg        s_out   = 1'b0;
    integer    ri;

    assign spi_sdio = s_oe ? s_out : 1'bz;

    initial begin
        for (ri = 0; ri < 256; ri = ri + 1) regs[ri] = 8'h00;
        regs[8'h01] = 8'h6C;
    end

    always @(negedge spi_csb) begin
        s_bit <= 5'd0;
        s_cmd <= 24'd0;
        s_rw  <= 1'b0;
        s_oe  <= 1'b0;
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
            if (s_cmd[14])
                s_rsh <= regs[{s_cmd[6:0], spi_sdio}];
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

    // -------------------------------------------------------------------------
    // Closed-Loop DAC Echo Delay Line (125 MSPS -> 400 MSPS @ 120 MHz IF)
    // -------------------------------------------------------------------------
    reg signed [8:0] echo_ring [0:1023];
    reg [9:0]        echo_wr_ptr = 10'd0;
    integer          ei;
    initial begin
        for (ei = 0; ei < 1024; ei = ei + 1) echo_ring[ei] = 9'sd0;
    end

    always @(posedge dacr_clk) begin
        echo_ring[echo_wr_ptr] <= $signed({1'b0, dacr_d}) - 9'sd128;
        echo_wr_ptr            <= echo_wr_ptr + 10'd1;
    end

    // Delayed DAC sample updated smoothly at ADC rate
    wire [9:0] echo_rd_idx = echo_wr_ptr - ECHO_DELAY_DAC_CYC[9:0];
    wire signed [8:0] echo_dac_samp = echo_ring[echo_rd_idx];

    reg [31:0] noise_prng = SEED;
    reg [7:0]  adcr_samp  = 8'h55;
    integer    samp_idx   = 0;
    real       if_lo, echo_scaled, adc_val_r;
    integer    noise_lsb;

    always @(posedge clk_400m_adc) begin
        noise_prng = {noise_prng[30:0], noise_prng[31] ^ noise_prng[21] ^ noise_prng[1] ^ noise_prng[0]};
        noise_lsb  = $signed(noise_prng[1:0]) - 1; // -1..+2 LSB thermal floor

        if (mode == 2'd0) begin
            adcr_samp <= (adcr_samp == 8'hAA) ? 8'h55 : 8'hAA;
        end else if (mode == 2'd1) begin
            // 121.5625 MHz IF CW tone at 400 MSPS -> +1.5625 MHz baseband
            adc_val_r = 128.0 + 105.0 * $cos(2.0 * PI * 0.30390625 * samp_idx);
            adcr_samp <= $rtoi(adc_val_r + 0.5);
        end else begin
            // Radar Echo Loopback: echo_dac_samp mixed onto 120.0 MHz IF carrier (0.300 * fs)
            if_lo = $cos(2.0 * PI * 0.3000 * samp_idx);
            if (no_echo_mut)
                echo_scaled = 0.0;
            else
                echo_scaled = ($itor(echo_dac_samp) / 128.0) * 96.0 * if_lo;
            adc_val_r = 128.0 + echo_scaled + $itor(noise_lsb);
            if (adc_val_r < 1.0)   adc_val_r = 1.0;
            if (adc_val_r > 254.0) adc_val_r = 254.0;
            adcr_samp <= $rtoi(adc_val_r + 0.5);
        end
        samp_idx <= samp_idx + 1;
    end

    // -------------------------------------------------------------------------
    // LVDS Skew & Spread Output (lvds_skew.py delays: DCO=371, D0..7=276..377 ps)
    // Preserves ~200 ps data-to-DCO window like tb_artix_top while applying real
    // per-bit skew deltas (-90..+5 ps relative to DCO) + <=20 ps spread.
    // -------------------------------------------------------------------------
    reg dco_board_del = 1'b0;
    always @(dco_true) dco_board_del <= #250.000 dco_true;
    assign adcr_dco_p =  dco_board_del;
    assign adcr_dco_n = ~dco_board_del;

    function real bit_dly_ps(input integer b);
        begin
            case (b)
                0: bit_dly_ps = 190.0; // -27 ps rel
                1: bit_dly_ps = 140.0; // -87 ps rel
                2: bit_dly_ps = 139.0; // -88 ps rel
                3: bit_dly_ps = 137.0; // -90 ps rel
                4: bit_dly_ps = 225.0; // +5 ps rel
                5: bit_dly_ps = 166.0; // -54 ps rel
                6: bit_dly_ps = 142.0; // -78 ps rel
                7: bit_dly_ps = 162.0; // -58 ps rel
                default: bit_dly_ps = 200.0;
            endcase
        end
    endfunction

    initial begin
        adcr_d_p  = 8'h55;
        adcr_d_n  = 8'hAA;
        adcr_or_p = 1'b0;
        adcr_or_n = 1'b1;
    end

    genvar gi;
    generate
        for (gi = 0; gi < 8; gi = gi + 1) begin : g_dly
            always @(adcr_samp[gi]) begin
                adcr_d_p[gi] <= #(bit_dly_ps(gi))  adcr_samp[gi];
                adcr_d_n[gi] <= #(bit_dly_ps(gi)) ~adcr_samp[gi];
            end
        end
    endgenerate

    always @(posedge clk_400m_adc) begin
        adcr_or_p <= #260.0 1'b0;
        adcr_or_n <= #260.0 1'b1;
    end
endmodule
