// SPDX-License-Identifier: BSD-2-Clause
// Artix-7 Pmod J1102 SPI Slave & Fallback DDC Readout (XC7A50T-FTG256-2)
//
// Implements a 40-bit SPI Mode 0 (CPOL=0, CPHA=0) register + FIFO bridge on
// Artix Bank 15 J1102 (VCCO = 3.3V, LVCMOS33):
//   Pin  Net          FPGA Pin  Bank  IOSTANDARD  Notes
//   1    PMOD_CS      H16       15    LVCMOS33    SPI active-low chip select
//   3    PMOD_MOSI    G16       15    LVCMOS33    SPI master-out slave-in
//   5    PMOD_MISO    J15       15    LVCMOS33    SPI master-in slave-out (tristate on CS_n=1)
//   7    PMOD_SCLK    D13       15    LVCMOS33    SPI clock (IO_L6N_T0_VREF_15, non-CC!)
//
// Because D13 is NOT a clock-capable pin, pmod_spi oversamples SCLK/CS_n/MOSI
// synchronously in the system `clk` domain (>= 100 MHz for f_SCLK <= 12.5 MHz),
// avoiding non-dedicated clock routing in Vivado.
//
// SPI Frame Format (MSB first, 40 SCLK cycles per CS_n assertion):
//   [39]    : rw (1 = Write, 0 = Read)
//   [38:32] : word-aligned byte address addr[6:0] (LSB [1:0] ignored)
//   [31:0]  : write payload (MOSI) or readback data (MISO)
//
// Register Map (LINK_PROTOCOL.md Section 7.2 + Pmod Fallback DDC FIFO):
//   0x00 LINK_CTRL      (R/W) : [0] soft_rst, [1] loopback_en, [2] retrain (pulse),
//                               [3] tap_override_en, [4] prbs7_tx_en, [5] prbs7_rx_chk_en,
//                               [6] clr_err (W1C pulse), [8] fallback_en
//   0x04 LINK_STATUS    (RO)  : [2:0] train_state, [3] l0_block_lock, [4] l1_block_lock,
//                               [5] deskew_lock, [6] link_up, [7] idelayctrl_rdy,
//                               [23:16] remote_status
//   0x08 IDELAY_CTRL_L0 (R/W) : [8:0] cfg_tap_l0, [24:16] active_tap_l0 (RO), [31] force_ld_l0
//   0x0C IDELAY_CTRL_L1 (R/W) : [8:0] cfg_tap_l1, [24:16] active_tap_l1 (RO), [31] force_ld_l1
//   0x10 ERR_CNT_SH_L0  (RO)
//   0x14 ERR_CNT_SH_L1  (RO)
//   0x18 ERR_CNT_CRC    (RO)
//   0x1C PKT_CNT_RX     (RO)
//   0x20 PKT_CNT_DROP   (RO)  : [23:0] tx_dropped_cnt, [31:24] rx_drop_cnt
//   0x24 DESKEW_STATUS  (RO)  : [7:0] skew_blocks, [23:8] am_seq
//   0x28 PRBS_ERR_CNT   (RO)
//   0x2C EYE_SCAN_L0    (RO)  : [8:0] eye_left_l0, [24:16] eye_right_l0
//   0x30 EYE_SCAN_L1    (RO)  : [8:0] eye_left_l1, [24:16] eye_right_l1
//   0x34 FB_FIFO_STATUS (RO)  : [6:0] fb_count, [14] fb_empty, [15] fb_full
//   0x38 FB_FIFO_DATA   (RO)  : {bb_q[15:0], bb_i[15:0]} (pops 1 entry per SPI read)
//
// Mutation support:
//   -DMUTATE_BAD_CPOL_CPHA : switches SCLK sampling/shifting edges to CPHA=1 (fails Mode 0 master)

`timescale 1ns/1ps

module pmod_spi #(
    parameter integer FB_FIFO_DEPTH = 64
) (
    input  wire        clk,
    input  wire        rst,

    // Physical J1102 SPI pins
    input  wire        pmod_cs_n,
    input  wire        pmod_sclk,
    input  wire        pmod_mosi,
    output reg         pmod_miso,
    output wire        pmod_miso_oe,

    // Link Control outputs (0x00, 0x08, 0x0C)
    output reg         ctrl_soft_rst,
    output reg         ctrl_loopback_en,
    output reg         ctrl_retrain_pulse,
    output reg         ctrl_tap_override_en,
    output reg         ctrl_prbs7_tx_en,
    output reg         ctrl_prbs7_rx_chk_en,
    output reg         ctrl_clr_err_pulse,
    output reg         ctrl_fallback_en,
    output reg  [8:0]  cfg_tap_l0,
    output reg         cfg_load_l0,
    output reg  [8:0]  cfg_tap_l1,
    output reg         cfg_load_l1,

    // Link Status & Diagnostic inputs (0x04 .. 0x30)
    input  wire [2:0]  st_train_state,
    input  wire        st_l0_block_lock,
    input  wire        st_l1_block_lock,
    input  wire        st_deskew_lock,
    input  wire        st_link_up,
    input  wire        st_idelayctrl_rdy,
    input  wire [7:0]  st_remote_status,
    input  wire [8:0]  active_tap_l0,
    input  wire [8:0]  active_tap_l1,
    input  wire [31:0] err_cnt_sh_l0,
    input  wire [31:0] err_cnt_sh_l1,
    input  wire [31:0] err_cnt_crc,
    input  wire [31:0] pkt_cnt_rx,
    input  wire [23:0] tx_dropped_cnt,
    input  wire [7:0]  rx_drop_cnt,
    input  wire [7:0]  skew_blocks,
    input  wire [15:0] am_seq,
    input  wire [31:0] prbs_err_cnt,
    input  wire [8:0]  eye_left_l0,
    input  wire [8:0]  eye_right_l0,
    input  wire [8:0]  eye_left_l1,
    input  wire [8:0]  eye_right_l1,

    // Fallback DDC baseband stream (clk domain)
    input  wire [15:0] fb_ddc_i,
    input  wire [15:0] fb_ddc_q,
    input  wire        fb_ddc_valid
);

    localparam integer FB_AW = $clog2(FB_FIFO_DEPTH);

    // -------------------------------------------------------------------------
    // Input Synchronizers (2-stage + edge-detect FF in clk domain)
    // -------------------------------------------------------------------------
    (* ASYNC_REG = "TRUE" *) reg [2:0] cs_n_sync;
    (* ASYNC_REG = "TRUE" *) reg [2:0] sclk_sync;
    (* ASYNC_REG = "TRUE" *) reg [2:0] mosi_sync;

    always @(posedge clk) begin
        if (rst) begin
            cs_n_sync <= 3'b111;
            sclk_sync <= 3'b000;
            mosi_sync <= 3'b000;
        end else begin
            cs_n_sync <= {cs_n_sync[1:0], pmod_cs_n};
            sclk_sync <= {sclk_sync[1:0], pmod_sclk};
            mosi_sync <= {mosi_sync[1:0], pmod_mosi};
        end
    end

    wire cs_active = ~cs_n_sync[1];
    wire cs_fall   =  cs_n_sync[2] & ~cs_n_sync[1];
    wire sclk_rise = ~sclk_sync[2] &  sclk_sync[1];
    wire sclk_fall =  sclk_sync[2] & ~sclk_sync[1];
    wire mosi_bit  =  mosi_sync[1];

`ifdef MUTATE_BAD_CPOL_CPHA
    // Intentionally wrong CPHA=1 edge polarity for negative testing
    wire sample_edge = sclk_fall;
    wire shift_edge  = sclk_rise;
`else
    // Mode 0 (CPOL=0, CPHA=0): sample MOSI on rising SCLK, update MISO on falling SCLK
    wire sample_edge = sclk_rise;
    wire shift_edge  = sclk_fall;
`endif

    assign pmod_miso_oe = cs_active;

    // -------------------------------------------------------------------------
    // Fallback DDC Synchronous FIFO (32-bit packed {Q[15:0], I[15:0]})
    // -------------------------------------------------------------------------
    reg  [31:0] fb_mem [0:FB_FIFO_DEPTH-1];
    reg  [FB_AW:0] fb_wr_ptr, fb_rd_ptr;
    wire [FB_AW:0] fb_count = fb_wr_ptr - fb_rd_ptr;
    wire           fb_empty = (fb_count == {(FB_AW+1){1'b0}});
    wire           fb_full  = (fb_count == FB_FIFO_DEPTH[FB_AW:0]);

    reg         fb_rd_pulse;
    wire        fb_wr_en = ctrl_fallback_en & fb_ddc_valid & ~fb_full;
    wire [31:0] fb_head  = fb_empty ? 32'd0 : fb_mem[fb_rd_ptr[FB_AW-1:0]];

    always @(posedge clk) begin
        if (rst || ctrl_soft_rst) begin
            fb_wr_ptr <= {(FB_AW+1){1'b0}};
            fb_rd_ptr <= {(FB_AW+1){1'b0}};
        end else begin
            if (fb_wr_en) begin
                fb_mem[fb_wr_ptr[FB_AW-1:0]] <= {fb_ddc_q, fb_ddc_i};
                fb_wr_ptr <= fb_wr_ptr + {{FB_AW{1'b0}}, 1'b1};
            end
            if (fb_rd_pulse && !fb_empty) begin
                fb_rd_ptr <= fb_rd_ptr + {{FB_AW{1'b0}}, 1'b1};
            end
        end
    end

    // -------------------------------------------------------------------------
    // Register Read Multiplexer
    // -------------------------------------------------------------------------
    function [31:0] reg_read_mux;
        input [6:0] byte_addr;
        begin
            case (byte_addr[6:2])
                5'h00: reg_read_mux = {23'd0, ctrl_fallback_en, 1'b0,
                                       1'b0, ctrl_prbs7_rx_chk_en, ctrl_prbs7_tx_en,
                                       ctrl_tap_override_en, 1'b0,
                                       ctrl_loopback_en, ctrl_soft_rst};
                5'h01: reg_read_mux = {8'd0, st_remote_status, 8'd0,
                                       st_idelayctrl_rdy, st_link_up, st_deskew_lock,
                                       st_l1_block_lock, st_l0_block_lock, st_train_state};
                5'h02: reg_read_mux = {7'd0, active_tap_l0, 7'd0, cfg_tap_l0};
                5'h03: reg_read_mux = {7'd0, active_tap_l1, 7'd0, cfg_tap_l1};
                5'h04: reg_read_mux = err_cnt_sh_l0;
                5'h05: reg_read_mux = err_cnt_sh_l1;
                5'h06: reg_read_mux = err_cnt_crc;
                5'h07: reg_read_mux = pkt_cnt_rx;
                5'h08: reg_read_mux = {rx_drop_cnt, tx_dropped_cnt};
                5'h09: reg_read_mux = {8'd0, am_seq, skew_blocks};
                5'h0A: reg_read_mux = prbs_err_cnt;
                5'h0B: reg_read_mux = {7'd0, eye_right_l0, 7'd0, eye_left_l0};
                5'h0C: reg_read_mux = {7'd0, eye_right_l1, 7'd0, eye_left_l1};
                5'h0D: reg_read_mux = {16'd0, fb_full, fb_empty,
                                       {(14-(FB_AW+1)){1'b0}}, fb_count};
                5'h0E: reg_read_mux = fb_head;
                default: reg_read_mux = 32'hDEAD_BEEF;
            endcase
        end
    endfunction

    // -------------------------------------------------------------------------
    // SPI Deserializer / Serializer & Control Registers
    // -------------------------------------------------------------------------
    reg [5:0]  bit_cnt;
    reg [6:0]  cmd_shift;
    reg        rw_latched;
    reg [6:0]  addr_latched;
    reg [31:0] wdata_shift;
    reg [31:0] rdata_shift;

    wire [7:0]  hdr_byte = {cmd_shift[6:0], mosi_bit};
    wire [31:0] wr_word  = {wdata_shift[30:0], mosi_bit};

    always @(posedge clk) begin
        if (rst) begin
            ctrl_soft_rst        <= 1'b0;
            ctrl_loopback_en     <= 1'b0;
            ctrl_retrain_pulse   <= 1'b0;
            ctrl_tap_override_en <= 1'b0;
            ctrl_prbs7_tx_en     <= 1'b0;
            ctrl_prbs7_rx_chk_en <= 1'b0;
            ctrl_clr_err_pulse   <= 1'b0;
            ctrl_fallback_en     <= 1'b0;
            cfg_tap_l0           <= 9'd0;
            cfg_load_l0          <= 1'b0;
            cfg_tap_l1           <= 9'd0;
            cfg_load_l1          <= 1'b0;
            fb_rd_pulse          <= 1'b0;
            bit_cnt              <= 6'd0;
            cmd_shift            <= 7'd0;
            rw_latched           <= 1'b0;
            addr_latched         <= 7'd0;
            wdata_shift          <= 32'd0;
            rdata_shift          <= 32'd0;
            pmod_miso            <= 1'b0;
        end else begin
            // One-cycle self-clearing pulses
            ctrl_retrain_pulse <= 1'b0;
            ctrl_clr_err_pulse <= 1'b0;
            cfg_load_l0        <= 1'b0;
            cfg_load_l1        <= 1'b0;
            fb_rd_pulse        <= 1'b0;

            if (!cs_active || cs_fall) begin
                bit_cnt   <= 6'd0;
                pmod_miso <= 1'b0;
            end else begin
                if (sample_edge) begin
                    if (bit_cnt < 6'd7) begin
                        cmd_shift <= {cmd_shift[5:0], mosi_bit};
                        bit_cnt   <= bit_cnt + 6'd1;
                    end else if (bit_cnt == 6'd7) begin
                        rw_latched   <= hdr_byte[7];
                        addr_latched <= hdr_byte[6:0];
                        if (!hdr_byte[7]) begin
                            rdata_shift <= reg_read_mux(hdr_byte[6:0]);
                            if (hdr_byte[6:2] == 5'h0E)
                                fb_rd_pulse <= 1'b1;
                        end
                        bit_cnt <= 6'd8;
                    end else if (bit_cnt < 6'd39) begin
                        wdata_shift <= {wdata_shift[30:0], mosi_bit};
                        bit_cnt     <= bit_cnt + 6'd1;
                    end else if (bit_cnt == 6'd39) begin
                        wdata_shift <= wr_word;
                        if (rw_latched) begin
                            case (addr_latched[6:2])
                                5'h00: begin
                                    ctrl_soft_rst        <= wr_word[0];
                                    ctrl_loopback_en     <= wr_word[1];
                                    ctrl_retrain_pulse   <= wr_word[2];
                                    ctrl_tap_override_en <= wr_word[3];
                                    ctrl_prbs7_tx_en     <= wr_word[4];
                                    ctrl_prbs7_rx_chk_en <= wr_word[5];
                                    ctrl_clr_err_pulse   <= wr_word[6];
                                    ctrl_fallback_en     <= wr_word[8];
                                end
                                5'h02: begin
                                    cfg_tap_l0  <= wr_word[8:0];
                                    cfg_load_l0 <= wr_word[31];
                                end
                                5'h03: begin
                                    cfg_tap_l1  <= wr_word[8:0];
                                    cfg_load_l1 <= wr_word[31];
                                end
                                default: ;
                            endcase
                        end
                        bit_cnt <= 6'd40;
                    end
                end

                if (shift_edge && (bit_cnt >= 6'd8) && (bit_cnt <= 6'd39) && !rw_latched) begin
                    pmod_miso   <= rdata_shift[31];
                    rdata_shift <= {rdata_shift[30:0], 1'b0};
                end
            end
        end
    end

endmodule
