// SPDX-License-Identifier: BSD-2-Clause
// 3-wire 1.8 V SPI Master for Converter Configuration (Bank 35: AD9253 + AD9484)
// Shared bus: CONV_SPI_SCLK, CONV_SPI_SDIO (bidirectional), CONV_SPI_CSB_R (AD9484), CONV_SPI_CSB_S (AD9253).
//
// AD9253 Rev. E Register & Power-Up Reference (Table 17, pp. 30-38, and Figure 74):
//   SPI Frame (24 bits, MSB first, Mode 0 CPOL=0/CPHA=0, f_SCLK <= 25 MHz / t_CLK >= 40 ns):
//     Bit[23]    : R/W# (0 = Write, 1 = Read)
//     Bits[22:21]: W1:W0 (00 = 1 byte)
//     Bits[20:8] : A12:A0 register address
//     Bits[7:0]  : D7:D0 write data (host drives) / read data (ADC drives during last 8 bits)
//
//   Quoted AD9253 Table 17 / p. 38 Power-Up Sequence Used:
//     Step 0 : 0x08 = 0x03  Power modes (global)        : Digital Reset assert (Bits[1:0]=11)
//     Step 1 : 0x08 = 0x00  Power modes (global)        : Chip run (Bits[1:0]=00); wait >= 2.9M sample clocks
//     Step 2 : 0x05 = 0x3F  Device index                : Select DCO, FCO, Ch D, Ch C, Ch B, Ch A
//     Step 3 : 0x0B = 0x07  Clock divide (global)       : Divide-by-8 (Bits[2:0]=111; 400/500 MHz -> 50/62.5 MSPS)
//     Step 4 : 0x09 = 0x01  Clock (global)              : Duty cycle stabilizer enabled (Bit 0=1)
//     Step 5 : 0x14 = 0x01  Output mode                 : LVDS-ANSI (Bit 6=0), non-inv (Bit 2=0), 2's comp (Bit 0=1)
//     Step 6 : 0x18 = 0x04  VREF                        : Internal VREF = 2.0 V p-p (Bits[2:0]=100)
//     Step 7 : 0x21 = 0x40  Serial output data control  : MSB-first (Bit 7=0), DDR one-lane (Bits[6:4]=100), 16-bit (Bits[1:0]=00)
//     Step 8 : 0x05 = 0x0C  Device index                : Select unused Ch C & Ch D only (Bits[3:2]=11)
//     Step 9 : 0x22 = 0x03  Serial channel status       : Channel output reset (Bit 1=1) + Channel powerdown (Bit 0=1)
//     Step 10: 0x05 = 0x33  Device index                : Re-select DCO, FCO, Ch B, Ch A
//     Step 11: 0x0D = 0x00  Test mode                   : Off / normal ADC output
//     Step 12: Read 0x01                                : AD9253 Chip ID (expected 0x8F)
//     Step 13: Read 0x01 on CSB_R                       : AD9484 Chip ID (expected 0x6C)

`timescale 1ns/1ps

module conv_spi #(
    parameter integer CLK_DIV           = 8,         // Half-SCLK in clk cycles (e.g. 125MHz/(2*8) = 7.81 MHz)
    parameter integer RESET_WAIT_CYCLES = 7_500_000, // 60 ms @ 125 MHz (> 2.9M sample clocks @ 50 MSPS)
    parameter [0:0]   AUTO_INIT         = 1'b1,
    parameter [0:0]   CHECK_AD9484      = 1'b1
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        start_init,

    // Host SPI request interface (accepted after init_done or anytime idle)
    input  wire        req_valid,
    output wire        req_ready,
    input  wire        req_target,   // 0 = AD9484 (CSB_R), 1 = AD9253 (CSB_S)
    input  wire        req_rw,       // 0 = Write, 1 = Read
    input  wire [12:0] req_addr,
    input  wire [7:0]  req_wdata,
    output reg         resp_valid,
    output reg  [7:0]  resp_rdata,

    // Status
    output reg         init_done,
    output reg         init_err,
    output reg  [7:0]  ad9253_id,
    output reg  [7:0]  ad9484_id,

    // 3-wire SPI pins
    output reg         spi_sclk,
    output reg         spi_csb_r,
    output reg         spi_csb_s,
    output reg         spi_sdio_o,
    output reg         spi_sdio_t,   // 1 = high-Z / input, 0 = drive output
    input  wire        spi_sdio_i
);
    localparam [3:0] NUM_INIT_STEPS = 4'd14;

    localparam [3:0] ST_IDLE      = 4'd0,
                     ST_SEQ_FETCH = 4'd1,
                     ST_SPI_SETUP = 4'd2,
                     ST_SPI_LOW   = 4'd3,
                     ST_SPI_HIGH  = 4'd4,
                     ST_SPI_CSH   = 4'd5,
                     ST_SPI_GAP   = 4'd6,
                     ST_WAIT_RST  = 4'd7;

    reg [3:0]  state;
    reg [3:0]  seq_idx;
    reg        seq_active;
    reg        init_pending;

    reg        cur_target;
    reg        cur_rw;
    reg [23:0] shift_tx;
    reg [7:0]  shift_rx;
    reg [4:0]  bit_idx;    // 23 down to 0
    reg [31:0] wait_cnt;

    assign req_ready = (state == ST_IDLE) && !init_pending && !start_init;

    // Power-up LUT: {target(1=AD9253,0=AD9484), rw(1=R,0=W), addr[12:0], wdata[7:0]}
    reg        lut_target;
    reg        lut_rw;
    reg [12:0] lut_addr;
    reg [7:0]  lut_wdata;

    always @* begin
        lut_target = 1'b1;
        lut_rw     = 1'b0;
        lut_addr   = 13'h0000;
        lut_wdata  = 8'h00;
        case (seq_idx)
            4'd0:  begin lut_target = 1'b1; lut_rw = 1'b0; lut_addr = 13'h0008; lut_wdata = 8'h03; end // Digital Reset assert
            4'd1:  begin lut_target = 1'b1; lut_rw = 1'b0; lut_addr = 13'h0008; lut_wdata = 8'h00; end // Digital Reset release (+wait)
            4'd2:  begin lut_target = 1'b1; lut_rw = 1'b0; lut_addr = 13'h0005; lut_wdata = 8'h3F; end // Device index: all
            4'd3:  begin lut_target = 1'b1; lut_rw = 1'b0; lut_addr = 13'h000B; lut_wdata = 8'h07; end // Clock divide = 8
            4'd4:  begin lut_target = 1'b1; lut_rw = 1'b0; lut_addr = 13'h0009; lut_wdata = 8'h01; end // DCS enable
            4'd5:  begin lut_target = 1'b1; lut_rw = 1'b0; lut_addr = 13'h0014; lut_wdata = 8'h01; end // LVDS-ANSI, 2's comp
            4'd6:  begin lut_target = 1'b1; lut_rw = 1'b0; lut_addr = 13'h0018; lut_wdata = 8'h04; end // VREF = 2.0 Vpp
            4'd7:  begin lut_target = 1'b1; lut_rw = 1'b0; lut_addr = 13'h0021; lut_wdata = 8'h40; end // DDR 1-lane 16-bit 1x
            4'd8:  begin lut_target = 1'b1; lut_rw = 1'b0; lut_addr = 13'h0005; lut_wdata = 8'h0C; end // Select Ch C & Ch D
            4'd9:  begin lut_target = 1'b1; lut_rw = 1'b0; lut_addr = 13'h0022; lut_wdata = 8'h03; end // Powerdown & reset Ch C/D
            4'd10: begin lut_target = 1'b1; lut_rw = 1'b0; lut_addr = 13'h0005; lut_wdata = 8'h33; end // Select DCO, FCO, Ch B/A
            4'd11: begin lut_target = 1'b1; lut_rw = 1'b0; lut_addr = 13'h000D; lut_wdata = 8'h00; end // Normal ADC mode
            4'd12: begin lut_target = 1'b1; lut_rw = 1'b1; lut_addr = 13'h0001; lut_wdata = 8'h00; end // Read AD9253 Chip ID (0x8F)
            4'd13: begin lut_target = 1'b0; lut_rw = 1'b1; lut_addr = 13'h0001; lut_wdata = 8'h00; end // Read AD9484 Chip ID (0x6C)
            default: ;
        endcase
    end

    task automatic start_xfer;
        input        t_target;
        input        t_rw;
        input [12:0] t_addr;
        input [7:0]  t_wdata;
        begin
            cur_target <= t_target;
            cur_rw     <= t_rw;
            shift_tx   <= {t_rw, 2'b00, t_addr, t_wdata};
            shift_rx   <= 8'h00;
            bit_idx    <= 5'd23;
            spi_sclk   <= 1'b0;
            spi_csb_r  <= (t_target == 1'b0) ? 1'b0 : 1'b1;
            spi_csb_s  <= (t_target == 1'b1) ? 1'b0 : 1'b1;
            spi_sdio_o <= t_rw;
            spi_sdio_t <= 1'b0;
            wait_cnt   <= (CLK_DIV > 1) ? (CLK_DIV - 1) : 32'd0;
            state      <= ST_SPI_SETUP;
        end
    endtask

    always @(posedge clk) begin
        if (rst) begin
            state        <= ST_IDLE;
            seq_idx      <= 4'd0;
            seq_active   <= 1'b0;
            init_pending <= AUTO_INIT;
            init_done    <= 1'b0;
            init_err     <= 1'b0;
            ad9253_id    <= 8'h00;
            ad9484_id    <= 8'h00;
            resp_valid   <= 1'b0;
            resp_rdata   <= 8'h00;
            spi_sclk     <= 1'b0;
            spi_csb_r    <= 1'b1;
            spi_csb_s    <= 1'b1;
            spi_sdio_o   <= 1'b0;
            spi_sdio_t   <= 1'b1;
            wait_cnt     <= 32'd0;
            cur_target   <= 1'b1;
            cur_rw       <= 1'b0;
            shift_tx     <= 24'd0;
            shift_rx     <= 8'd0;
            bit_idx      <= 5'd0;
        end else begin
            resp_valid <= 1'b0;

            case (state)
                ST_IDLE: begin
                    spi_sclk   <= 1'b0;
                    spi_csb_r  <= 1'b1;
                    spi_csb_s  <= 1'b1;
                    spi_sdio_t <= 1'b1;
                    if (init_pending || start_init) begin
                        init_pending <= 1'b0;
                        init_done    <= 1'b0;
                        init_err     <= 1'b0;
                        seq_active   <= 1'b1;
                        seq_idx      <= 4'd0;
                        state        <= ST_SEQ_FETCH;
                    end else if (req_valid) begin
                        seq_active <= 1'b0;
                        start_xfer(req_target, req_rw, req_addr, req_wdata);
                    end
                end

                ST_SEQ_FETCH: begin
                    if (seq_idx >= NUM_INIT_STEPS) begin
                        seq_active <= 1'b0;
                        init_done  <= 1'b1;
                        init_err   <= (ad9253_id != 8'h8F) || (CHECK_AD9484 && (ad9484_id != 8'h6C));
                        state      <= ST_IDLE;
                    end else if ((seq_idx == 4'd13) && !CHECK_AD9484) begin
                        seq_active <= 1'b0;
                        init_done  <= 1'b1;
                        init_err   <= (ad9253_id != 8'h8F);
                        state      <= ST_IDLE;
                    end else begin
                        start_xfer(lut_target, lut_rw, lut_addr, lut_wdata);
                    end
                end

                // CSB asserted low, SDIO MSB stable before first rising SCLK
                ST_SPI_SETUP: begin
                    if (wait_cnt != 32'd0) begin
                        wait_cnt <= wait_cnt - 32'd1;
                    end else begin
                        spi_sclk <= 1'b1;
                        wait_cnt <= (CLK_DIV > 1) ? (CLK_DIV - 1) : 32'd0;
                        state    <= ST_SPI_HIGH;
                    end
                end

                // SCLK high phase: slave samples write bit on rising edge; master captures read bit during high phase
                ST_SPI_HIGH: begin
                    if (wait_cnt != 32'd0) begin
                        wait_cnt <= wait_cnt - 32'd1;
                    end else begin
                        if (cur_rw && (bit_idx <= 5'd7)) begin
                            shift_rx <= {shift_rx[6:0], spi_sdio_i};
                        end
                        spi_sclk <= 1'b0;
                        wait_cnt <= (CLK_DIV > 1) ? (CLK_DIV - 1) : 32'd0;
                        if (bit_idx == 5'd0) begin
                            state <= ST_SPI_CSH;
                        end else begin
                            bit_idx    <= bit_idx - 5'd1;
                            shift_tx   <= {shift_tx[22:0], 1'b0};
                            spi_sdio_o <= shift_tx[22];
                            spi_sdio_t <= cur_rw && ((bit_idx - 5'd1) <= 5'd7);
                            state      <= ST_SPI_LOW;
                        end
                    end
                end

                // SCLK low phase: drive next data bit (or tri-state SDIO for read data)
                ST_SPI_LOW: begin
                    if (wait_cnt != 32'd0) begin
                        wait_cnt <= wait_cnt - 32'd1;
                    end else begin
                        spi_sclk <= 1'b1;
                        wait_cnt <= (CLK_DIV > 1) ? (CLK_DIV - 1) : 32'd0;
                        state    <= ST_SPI_HIGH;
                    end
                end

                // SCLK back low; hold CSB low for one half-SCLK after final bit
                ST_SPI_CSH: begin
                    if (wait_cnt != 32'd0) begin
                        wait_cnt <= wait_cnt - 32'd1;
                    end else begin
                        spi_csb_r  <= 1'b1;
                        spi_csb_s  <= 1'b1;
                        spi_sdio_t <= 1'b1;
                        wait_cnt   <= (CLK_DIV > 1) ? (CLK_DIV - 1) : 32'd0;
                        if (seq_active) begin
                            if (seq_idx == 4'd12)
                                ad9253_id <= shift_rx;
                            else if (seq_idx == 4'd13)
                                ad9484_id <= shift_rx;
                        end else begin
                            resp_valid <= 1'b1;
                            resp_rdata <= shift_rx;
                        end
                        state <= ST_SPI_GAP;
                    end
                end

                ST_SPI_GAP: begin
                    if (wait_cnt != 32'd0) begin
                        wait_cnt <= wait_cnt - 32'd1;
                    end else if (seq_active) begin
                        if (seq_idx == 4'd1) begin
                            wait_cnt <= (RESET_WAIT_CYCLES > 0) ? (RESET_WAIT_CYCLES - 1) : 32'd0;
                            state    <= ST_WAIT_RST;
                        end else begin
                            seq_idx <= seq_idx + 4'd1;
                            state   <= ST_SEQ_FETCH;
                        end
                    end else begin
                        state <= ST_IDLE;
                    end
                end

                ST_WAIT_RST: begin
                    if (wait_cnt != 32'd0) begin
                        wait_cnt <= wait_cnt - 32'd1;
                    end else begin
                        seq_idx <= seq_idx + 4'd1;
                        state   <= ST_SEQ_FETCH;
                    end
                end

                default: state <= ST_IDLE;
            endcase
        end
    end
endmodule
