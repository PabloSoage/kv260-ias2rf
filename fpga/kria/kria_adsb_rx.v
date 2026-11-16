// SPDX-License-Identifier: Apache-2.0
// 1090 MHz Mode-S Extended Squitter (ADS-B) PPM Preamble Detector & CRC-24 Decoder
//
// Placed in Kria PL (0 DSP48E2) behind IAS1. Processes complex I/Q stream,
// optionally averaging cfg_chip_osr (default 2 -> 4 MSPS input down to 2.0 MSPS
// 0.5 us Mode-S chips), detects the 8 us 4-pulse preamble [1,0,1,0,0,0,0,1,0,1,0,0,0,0,0,0],
// slices 112 Manchester/PPM data bits (0.5 us chips -> 1 bit/us), and checks the
// ICAO Annex 10 24-bit CRC polynomial G(x) = 0x1FFF409 (x^24+x^23+...+x^10+x^3+1).

`timescale 1ns/1ps

module kria_adsb_rx (
    input  wire               clk,
    input  wire               rst,
    input  wire               in_valid,
    input  wire signed [15:0] in_i,
    input  wire signed [15:0] in_q,

    // Configuration
    input  wire [7:0]         cfg_chip_osr,   // Input samples per 0.5 us chip (e.g., 1 @ 2MSPS, 2 @ 4MSPS, 5 @ 10MSPS)
    input  wire [15:0]        cfg_min_hi_sum, // Minimum summed 4-pulse preamble amplitude

    // Decoded DF17 / Mode-S message outputs
    output reg                msg_valid,
    output reg                msg_crc_ok,
    output reg  [111:0]       msg_data,
    output reg  [15:0]        msg_snr_est,
    output reg  [31:0]        preamble_cnt,
    output reg  [31:0]        crc_ok_cnt,
    output reg  [31:0]        crc_err_cnt
);
`ifdef MUTATE_BAD_CRC_POLY
    localparam [23:0] MODE_S_CRC_POLY = 24'hAFE409; // MUTATION: wrong ICAO CRC-24 generator
`else
    localparam [23:0] MODE_S_CRC_POLY = 24'hFFF409;
`endif

    // Alpha-max plus beta-min envelope magnitude |I + jQ| (0 DSP48)
    wire [15:0] abs_i = in_i[15] ? (~in_i + 16'd1) : in_i;
    wire [15:0] abs_q = in_q[15] ? (~in_q + 16'd1) : in_q;
    wire [15:0] mag_max = (abs_i >= abs_q) ? abs_i : abs_q;
    wire [15:0] mag_min = (abs_i >= abs_q) ? abs_q : abs_i;
    wire [16:0] env_inst = {1'b0, mag_max} + {2'b0, mag_min[15:1]} - {5'b0, mag_max[15:4]};

    // Integrate/average over cfg_chip_osr[6:0] (+1 on odd chips when cfg_chip_osr[7]=1 for .5 rates,
    // e.g. 8'h8C = 12.5 samples/chip @ 25.0 MSPS -> exact 2.000 MSPS Mode-S chip timing).
    reg [6:0]  osr_cnt;
    reg        osr_odd;
    reg [23:0] chip_acc;
    reg        chip_valid;
    reg [15:0] chip_amp;
    wire [6:0] osr_base = (cfg_chip_osr[6:0] == 7'd0) ? 7'd1 : cfg_chip_osr[6:0];
    wire [6:0] osr_eff  = osr_base + {6'd0, (cfg_chip_osr[7] & osr_odd)};

    always @(posedge clk) begin
        if (rst) begin
            osr_cnt    <= 7'd0;
            osr_odd    <= 1'b0;
            chip_acc   <= 24'd0;
            chip_valid <= 1'b0;
            chip_amp   <= 16'd0;
        end else begin
            chip_valid <= 1'b0;
            if (in_valid) begin
                if (osr_cnt >= (osr_eff - 7'd1)) begin
                    osr_cnt    <= 7'd0;
                    osr_odd    <= ~osr_odd;
                    chip_amp   <= (chip_acc + {{7{1'b0}}, env_inst}) / osr_eff;
                    chip_acc   <= 24'd0;
                    chip_valid <= 1'b1;
                end else begin
                    osr_cnt  <= osr_cnt + 7'd1;
                    chip_acc <= chip_acc + {{7{1'b0}}, env_inst};
                end
            end
        end
    end

    // 16-chip sliding preamble history: p[0] = oldest (T=0), p[15] = newest (T=7.5 us)
    reg [15:0] p [0:15];
    reg        rx_active;
    reg        chip_phase;    // 0 = first half-bit chip, 1 = second half-bit chip
    reg [15:0] first_chip;
    reg [6:0]  bit_idx;
    reg [111:0] msg_shift;
    reg [23:0] crc_reg;
    integer    k;

    wire [17:0] p_hi_sum = {2'b0, p[1]}  + {2'b0, p[3]}  + {2'b0, p[8]}  + {2'b0, p[10]}; // shifted prev cycle vs cur
    // Check aligned slots inside p[0..15] where newest chip is chip_amp at slot 15!
    // Slot indices when preamble aligns: 0=H, 1=L, 2=H, 3=L, 4=L, 5=L, 6=L, 7=H, 8=L, 9=H, 10..15=L
    // With p[1..15] shifted and current chip_amp as slot 15:
    //   slot 0=p[1], 1=p[2], 2=p[3], 3=p[4], 4=p[5], 5=p[6], 6=p[7], 7=p[8],
    //   slot 8=p[9], 9=p[10], 10=p[11], 11=p[12], 12=p[13], 13=p[14], 14=p[15], 15=chip_amp
    wire [17:0] hi4 = {2'b0, p[1]} + {2'b0, p[3]} + {2'b0, p[8]} + {2'b0, p[10]};
    wire [19:0] lo12 = {4'b0, p[2]} + {4'b0, p[4]} + {4'b0, p[5]} + {4'b0, p[6]}
                     + {4'b0, p[7]} + {4'b0, p[9]} + {4'b0, p[11]} + {4'b0, p[12]}
                     + {4'b0, p[13]} + {4'b0, p[14]} + {4'b0, p[15]} + {4'b0, chip_amp};

    wire [15:0] half_hi_mean = hi4[17:3]; // 0.5 * mean(4 preamble pulses)
    wire pre_shape_ok = (p[1]  > {p[2][14:0], 1'b0})  &&
                        (p[3]  > {p[2][14:0], 1'b0})  && (p[3] > {p[4][14:0], 1'b0}) &&
                        (p[8]  > {p[7][14:0], 1'b0})  && (p[8] > {p[9][14:0], 1'b0}) &&
                        (p[10] > {p[9][14:0], 1'b0})  && (p[10] > {p[11][14:0], 1'b0}) &&
                        (p[5]  < half_hi_mean) && (p[6]  < half_hi_mean) && (p[7]  < half_hi_mean) &&
                        (p[12] < half_hi_mean) && (p[13] < half_hi_mean) && (p[14] < half_hi_mean) &&
                        (p[15] < half_hi_mean) && (chip_amp < half_hi_mean);
    wire pre_thr_ok   = (hi4 >= {2'b0, cfg_min_hi_sum}) && (({2'b0, hi4} * 20'd3) > (lo12 * 20'd2));
    wire pre_hit      = chip_valid && !rx_active && pre_shape_ok && pre_thr_ok;

    function automatic [23:0] crc24_step;
        input [23:0] cur;
        input        bit_in;
        reg          fb;
        begin
            fb = cur[23] ^ bit_in;
            crc24_step = {cur[22:0], 1'b0} ^ (fb ? MODE_S_CRC_POLY : 24'd0);
        end
    endfunction

    always @(posedge clk) begin
        if (rst) begin
            for (k = 0; k < 16; k = k + 1) p[k] <= 16'd0;
            rx_active    <= 1'b0;
            chip_phase   <= 1'b0;
            first_chip   <= 16'd0;
            bit_idx      <= 7'd0;
            msg_shift    <= 112'd0;
            crc_reg      <= 24'd0;
            msg_valid    <= 1'b0;
            msg_crc_ok   <= 1'b0;
            msg_data     <= 112'd0;
            msg_snr_est  <= 16'd0;
            preamble_cnt <= 32'd0;
            crc_ok_cnt   <= 32'd0;
            crc_err_cnt  <= 32'd0;
        end else begin
            msg_valid <= 1'b0;

            if (chip_valid) begin
                for (k = 0; k < 15; k = k + 1)
                    p[k] <= p[k + 1];
                p[15] <= chip_amp;

                if (rx_active) begin
                    if (!chip_phase) begin
                        first_chip <= chip_amp;
                        chip_phase <= 1'b1;
                    end else begin : blk_bit
                        reg        dec_b;
                        reg [23:0] crc_nxt;
                        reg [111:0] msg_nxt;
                        dec_b   = (first_chip >= chip_amp); // PPM: 10='1', 01='0'
                        msg_nxt = {msg_shift[110:0], dec_b};
                        crc_nxt = crc24_step(crc_reg, dec_b);
                        msg_shift  <= msg_nxt;
                        crc_reg    <= crc_nxt;
                        chip_phase <= 1'b0;

                        if (bit_idx == 7'd111) begin
                            rx_active  <= 1'b0;
                            msg_valid  <= 1'b1;
                            msg_data   <= msg_nxt;
                            msg_crc_ok <= (crc_nxt == 24'd0);
                            if (crc_nxt == 24'd0)
                                crc_ok_cnt <= crc_ok_cnt + 32'd1;
                            else
                                crc_err_cnt <= crc_err_cnt + 32'd1;
                        end else begin
                            bit_idx <= bit_idx + 7'd1;
                        end
                    end
                end else if (pre_hit) begin
                    rx_active    <= 1'b1;
                    chip_phase   <= 1'b0;
                    bit_idx      <= 7'd0;
                    crc_reg      <= 24'd0;
                    msg_shift    <= 112'd0;
                    msg_snr_est  <= hi4[17:2];
                    preamble_cnt <= preamble_cnt + 32'd1;
                end
            end
        end
    end
endmodule
