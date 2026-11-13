// SPDX-License-Identifier: BSD-2-Clause
// Beamforming Controller for 8x ADAR1000 (Bank 35, LVCMOS18)
//
// Features:
//   - Mode-0 (CPOL=0, CPHA=0) 4-wire SPI master supporting single-register R/W and multi-byte
//     ascending auto-increment block transfers under one CSB assertion (ADAR1000 Reg 0x000 = 0x3C).
//   - Block-RAM Beam Table (32 beams x 8 chips x 24 contiguous bytes covering Regs 0x010..0x027:
//     RX gain Ch1..4, RX I/Q vector Ch1..4, TX gain Ch1..4, TX I/Q vector Ch1..4).
//   - BEAM_STROBE rising-edge / soft-trigger beam loader across ADAR1..8 followed by synchronous
//     ADAR*_TX_LOAD / ADAR*_RX_LOAD strobing.
//   - Safe T/R switching FSM with programmable guard times (guard_pre, guard_post) ensuring ADAR*_TR
//     is never asserted while a beam load or TX_LOAD/RX_LOAD update is in progress.

`timescale 1ns/1ps

module adar_ctrl #(
    parameter integer CLK_DIV       = 4,    // Half-SCLK in clk cycles (125MHz/(2*4) = 15.625 MHz)
    parameter integer NUM_CHIPS     = 8,
    parameter integer NUM_BEAMS     = 32,
    parameter [0:0]   AUTO_INIT     = 1'b1
) (
    input  wire        clk,
    input  wire        rst,

    // Beam table write port (link_clk / host control)
    input  wire        tbl_wr_en,
    input  wire [4:0]  tbl_beam_id,   // 0..31
    input  wire [2:0]  tbl_chip_id,   // 0..7 (maps to ADAR1..ADAR8)
    input  wire [4:0]  tbl_byte_idx,  // 0..23 (regs 0x010..0x027)
    input  wire [7:0]  tbl_wdata,

    // Beam load & T/R control
    input  wire        start_init,
    input  wire        beam_strobe,   // External BEAM_STROBE trigger (synchronized internally)
    input  wire        soft_load,     // Host 1-cycle beam load request
    input  wire [4:0]  active_beam_id,
    input  wire        tr_req,        // Desired T/R state: 0 = RX, 1 = TX
    input  wire [15:0] guard_pre,     // Guard cycles before TX assert / beam load
    input  wire [15:0] guard_post,    // Guard cycles after load / TR switch before tr_ready

    // Direct SPI host access (when idle)
    input  wire        spi_req_valid,
    output wire        spi_req_ready,
    input  wire [2:0]  spi_req_chip,
    input  wire        spi_req_rw,    // 0 = Write, 1 = Read
    input  wire [14:0] spi_req_addr,
    input  wire [7:0]  spi_req_wdata,
    output reg         spi_resp_valid,
    output reg  [7:0]  spi_resp_rdata,

    // Status
    output reg         init_done,
    output reg         init_err,
    output reg         load_busy,
    output reg         tr_ready,
    output reg  [4:0]  current_beam_id,

    // Shared ADAR1000 SPI bus + per-chip control pins (Bank 35, 1.8 V)
    output reg         adar_sclk,
    output reg         adar_sdio_o,
    output reg         adar_sdio_t,
    input  wire        adar_sdo,
    output reg  [7:0]  adar_csb,
    output reg  [7:0]  adar_tx_load,
    output reg  [7:0]  adar_rx_load,
    output reg  [7:0]  adar_tr
);
    // -------------------------------------------------------------------------
    // Block-RAM Beam Table: indexed {beam[4:0], chip[2:0], byte[4:0]} (8192 x 8)
    // -------------------------------------------------------------------------
    (* ram_style = "block" *)
    reg [7:0] beam_bram [0 : (NUM_BEAMS * 8 * 32) - 1];

    wire [12:0] tbl_wr_addr = {tbl_beam_id, tbl_chip_id, tbl_byte_idx};
    always @(posedge clk) begin
        if (tbl_wr_en)
            beam_bram[tbl_wr_addr] <= tbl_wdata;
    end

    // Synchronous BRAM read port for SPI streaming
    reg  [4:0] rd_beam;
    reg  [2:0] rd_chip;
    reg  [4:0] rd_byte;
    wire [12:0] bram_rd_addr = {rd_beam, rd_chip, rd_byte};
    reg  [7:0]  bram_rdata;
    always @(posedge clk) begin
        bram_rdata <= beam_bram[bram_rd_addr];
    end

    // -------------------------------------------------------------------------
    // Edge detectors & Control Synchronizers
    // -------------------------------------------------------------------------
    reg [2:0] strobe_sync;
    always @(posedge clk) begin
        if (rst) strobe_sync <= 3'b000;
        else     strobe_sync <= {strobe_sync[1:0], beam_strobe};
    end
    wire strobe_rise = (strobe_sync[2:1] == 2'b01);

    // -------------------------------------------------------------------------
    // Main FSM: Init -> Idle -> Safe Pre-Guard -> Auto-Increment Block Write -> Strobe -> Post-Guard
    // -------------------------------------------------------------------------
    localparam [3:0] ST_IDLE       = 4'd0,
                     ST_INIT_STEP  = 4'd1,
                     ST_GUARD_PRE  = 4'd2,
                     ST_BEAM_HDR   = 4'd3,
                     ST_BEAM_NEXTB = 4'd4,
                     ST_LOAD_PULSE = 4'd5,
                     ST_GUARD_POST = 4'd6,
                     ST_SPI_SETUP  = 4'd7,
                     ST_SPI_LOW    = 4'd8,
                     ST_SPI_HIGH   = 4'd9,
                     ST_SPI_CONT   = 4'd10,
                     ST_SPI_CSH    = 4'd11;

    reg [3:0]  state, ret_state;
    reg        init_pending;
    reg [2:0]  init_chip;
    reg [2:0]  init_reg_step; // 0..6 per chip
    reg [7:0]  scratch_rx;

    reg [15:0] guard_cnt;
    reg        beam_load_pending;
    reg [4:0]  pending_beam_id;

    // Active SPI transfer context
    reg [2:0]  spi_chip;
    reg        spi_rw;
    reg        spi_stream_mode; // 1 = keep CSB low after header/byte and stream 24 bytes
    reg [7:0]  spi_shift_tx;
    reg [7:0]  spi_shift_rx;
    reg [15:0] spi_hdr;
    reg [4:0]  spi_bit_cnt;     // 15..0 for header, or 7..0 for byte
    reg        spi_in_hdr;
    reg [4:0]  stream_byte_idx; // 0..23
    reg [31:0] clk_cnt;
    reg        host_spi_active;

    assign spi_req_ready = (state == ST_IDLE) && !init_pending && !start_init && !beam_load_pending && !strobe_rise && !soft_load;

    // Init register LUT: {rw(1=R,0=W), addr[14:0], wdata[7:0]}
    reg        init_rw;
    reg [14:0] init_addr;
    reg [7:0]  init_wdata;
    always @* begin
        init_rw    = 1'b0;
        init_addr  = 15'h0000;
        init_wdata = 8'h00;
        case (init_reg_step)
            3'd0: begin init_rw = 1'b0; init_addr = 15'h0000; init_wdata = 8'h3C; end // ADDR_ASCN=1, SDOACTIVE=1
            3'd1: begin init_rw = 1'b0; init_addr = 15'h000A; init_wdata = 8'hA5; end // Scratchpad write
            3'd2: begin init_rw = 1'b1; init_addr = 15'h000A; init_wdata = 8'h00; end // Scratchpad verify read
            3'd3: begin init_rw = 1'b0; init_addr = 15'h002E; init_wdata = 8'h7F; end // RX channels enable
            3'd4: begin init_rw = 1'b0; init_addr = 15'h002F; init_wdata = 8'h7F; end // TX channels enable
            3'd5: begin init_rw = 1'b0; init_addr = 15'h0031; init_wdata = 8'hB4; end // TR pin control + SW_DRV enable
            3'd6: begin init_rw = 1'b0; init_addr = 15'h0038; init_wdata = 8'h60; end // Bypass RAM -> working regs + TX/RX_LOAD
            default: ;
        endcase
    end

    task automatic begin_spi_hdr;
        input [2:0]  chip;
        input        rw;
        input [14:0] addr;
        input [7:0]  first_byte;
        input        is_stream;
        input [3:0]  next_ret;
        begin
            spi_chip        <= chip;
            spi_rw          <= rw;
            spi_stream_mode <= is_stream;
            spi_in_hdr      <= 1'b1;
            spi_hdr         <= {rw, addr};
            spi_shift_tx    <= first_byte;
            spi_shift_rx    <= 8'h00;
            spi_bit_cnt     <= 5'd15;
            ret_state       <= next_ret;
            adar_sclk       <= 1'b0;
            adar_csb        <= ~(8'd1 << chip);
            adar_sdio_t     <= 1'b0;
`ifdef MUTATE_CPHA_WRONG
            // Wrong CPHA=1: withhold MSB until first rising edge instead of Mode-0 setup before rise
            adar_sdio_o     <= 1'b0;
`else
            adar_sdio_o     <= rw; // MSB of 16-bit header
`endif
            clk_cnt         <= (CLK_DIV > 1) ? (CLK_DIV - 1) : 32'd0;
            state           <= ST_SPI_SETUP;
        end
    endtask

    // -------------------------------------------------------------------------
    // Safe T/R Control Logic (blocked during load_busy unless mutated)
    // -------------------------------------------------------------------------
`ifdef MUTATE_TR_DURING_LOAD
    wire tr_block = 1'b0;
`else
    wire tr_block = load_busy || beam_load_pending || strobe_rise || soft_load || init_pending || start_init;
`endif

    reg        tr_curr;
    reg [15:0] tr_guard_cnt;

    always @(posedge clk) begin
        if (rst) begin
            adar_tr      <= 8'h00;
            tr_curr      <= 1'b0;
            tr_guard_cnt <= 16'd0;
            tr_ready     <= 1'b0;
        end else begin
`ifdef MUTATE_TR_DURING_LOAD
            adar_tr  <= {8{tr_req}};
            tr_curr  <= tr_req;
            tr_ready <= 1'b1;
`else
            if (tr_block) begin
                adar_tr      <= 8'h00;
                tr_curr      <= 1'b0;
                tr_guard_cnt <= guard_post;
                tr_ready     <= 1'b0;
            end else if (tr_curr != tr_req) begin
                adar_tr      <= {8{tr_req}};
                tr_curr      <= tr_req;
                tr_guard_cnt <= guard_post;
                tr_ready     <= (guard_post == 16'd0);
            end else if (tr_guard_cnt != 16'd0) begin
                tr_guard_cnt <= tr_guard_cnt - 16'd1;
                tr_ready     <= 1'b0;
            end else begin
                tr_ready     <= 1'b1;
            end
`endif
        end
    end

    // -------------------------------------------------------------------------
    // Beam Loader & SPI Sequential Engine
    // -------------------------------------------------------------------------
    always @(posedge clk) begin
        if (rst) begin
            state             <= ST_IDLE;
            ret_state         <= ST_IDLE;
            init_pending      <= AUTO_INIT;
            init_chip         <= 3'd0;
            init_reg_step     <= 3'd0;
            init_done         <= 1'b0;
            init_err          <= 1'b0;
            scratch_rx        <= 8'h00;
            load_busy         <= 1'b0;
            beam_load_pending <= 1'b0;
            pending_beam_id   <= 5'd0;
            current_beam_id   <= 5'd0;
            guard_cnt         <= 16'd0;
            rd_beam           <= 5'd0;
            rd_chip           <= 3'd0;
            rd_byte           <= 5'd0;
            stream_byte_idx   <= 5'd0;
            adar_sclk         <= 1'b0;
            adar_sdio_o       <= 1'b0;
            adar_sdio_t       <= 1'b1;
            adar_csb          <= 8'hFF;
            adar_tx_load      <= 8'h00;
            adar_rx_load      <= 8'h00;
            spi_resp_valid    <= 1'b0;
            spi_resp_rdata    <= 8'h00;
            host_spi_active   <= 1'b0;
            clk_cnt           <= 32'd0;
            spi_chip          <= 3'd0;
            spi_rw            <= 1'b0;
            spi_stream_mode   <= 1'b0;
            spi_shift_tx      <= 8'd0;
            spi_shift_rx      <= 8'd0;
            spi_hdr           <= 16'd0;
            spi_bit_cnt       <= 5'd0;
            spi_in_hdr        <= 1'b0;
        end else begin
            spi_resp_valid <= 1'b0;

            if (strobe_rise || soft_load) begin
                beam_load_pending <= 1'b1;
                pending_beam_id   <= active_beam_id;
            end

            case (state)
                ST_IDLE: begin
                    adar_sclk    <= 1'b0;
                    adar_csb     <= 8'hFF;
                    adar_sdio_t  <= 1'b1;
                    adar_tx_load <= 8'h00;
                    adar_rx_load <= 8'h00;
                    load_busy    <= 1'b0;

                    if (init_pending || start_init) begin
                        init_pending  <= 1'b0;
                        init_done     <= 1'b0;
                        init_err      <= 1'b0;
                        init_chip     <= 3'd0;
                        init_reg_step <= 3'd0;
                        load_busy     <= 1'b1;
                        state         <= ST_INIT_STEP;
                    end else if (beam_load_pending) begin
                        beam_load_pending <= 1'b0;
                        load_busy         <= 1'b1;
                        rd_beam           <= pending_beam_id;
                        rd_chip           <= 3'd0;
                        rd_byte           <= 5'd0;
                        guard_cnt         <= guard_pre;
                        state             <= ST_GUARD_PRE;
                    end else if (spi_req_valid) begin
                        host_spi_active <= 1'b1;
                        begin_spi_hdr(spi_req_chip, spi_req_rw, spi_req_addr, spi_req_wdata, 1'b0, ST_IDLE);
                    end
                end

                ST_INIT_STEP: begin
                    begin_spi_hdr(init_chip, init_rw, init_addr, init_wdata, 1'b0, ST_INIT_STEP);
                    if (init_reg_step == 3'd2)
                        scratch_rx <= spi_shift_rx;
                end

                // Pre-load guard: ensures adar_tr is low >= guard_pre cycles before SPI / LOAD begins
                ST_GUARD_PRE: begin
                    if (guard_cnt != 16'd0) begin
                        guard_cnt <= guard_cnt - 16'd1;
                    end else begin
                        stream_byte_idx <= 5'd0;
                        state           <= ST_BEAM_HDR;
                    end
                end

                // Start ascending auto-increment burst at register 0x0010 for rd_chip
                ST_BEAM_HDR: begin
                    stream_byte_idx <= 5'd0;
                    begin_spi_hdr(rd_chip, 1'b0, 15'h0010, 8'h00, 1'b1, ST_BEAM_NEXTB);
                end

                // Latch next chip or pulse TX_LOAD/RX_LOAD after all 8 chips updated
                ST_BEAM_NEXTB: begin
                    if (rd_chip == (NUM_CHIPS - 1)) begin
                        adar_tx_load <= 8'hFF;
                        adar_rx_load <= 8'hFF;
                        guard_cnt    <= (CLK_DIV > 1) ? CLK_DIV[15:0] : 16'd2;
                        state        <= ST_LOAD_PULSE;
                    end else begin
                        rd_chip <= rd_chip + 3'd1;
                        rd_byte <= 5'd0;
                        state   <= ST_BEAM_HDR;
                    end
                end

                ST_LOAD_PULSE: begin
                    if (guard_cnt != 16'd0) begin
                        guard_cnt <= guard_cnt - 16'd1;
                    end else begin
                        adar_tx_load    <= 8'h00;
                        adar_rx_load    <= 8'h00;
                        current_beam_id <= rd_beam;
                        guard_cnt       <= guard_post;
                        state           <= ST_GUARD_POST;
                    end
                end

                ST_GUARD_POST: begin
                    if (guard_cnt != 16'd0) begin
                        guard_cnt <= guard_cnt - 16'd1;
                    end else begin
                        load_busy <= 1'b0;
                        state     <= ST_IDLE;
                    end
                end

                // -------------------------------------------------------------
                // Mode-0 SPI Shift Engine (supports 16b hdr + 1 or 24 bytes)
                // -------------------------------------------------------------
                ST_SPI_SETUP: begin
                    if (clk_cnt != 32'd0) begin
                        clk_cnt <= clk_cnt - 32'd1;
                    end else begin
                        adar_sclk <= 1'b1;
                        clk_cnt   <= (CLK_DIV > 1) ? (CLK_DIV - 1) : 32'd0;
                        state     <= ST_SPI_HIGH;
                    end
                end

                ST_SPI_HIGH: begin
`ifdef MUTATE_CPHA_WRONG
                    // CPHA=1 bug: change SDIO *after* SCLK rising edge instead of before it
                    if (clk_cnt == ((CLK_DIV > 1) ? (CLK_DIV - 1) : 32'd0))
                        adar_sdio_o <= spi_in_hdr ? spi_hdr[15] : spi_shift_tx[7];
`endif
                    if (clk_cnt != 32'd0) begin
                        clk_cnt <= clk_cnt - 32'd1;
                    end else begin
                        if (!spi_in_hdr && spi_rw)
                            spi_shift_rx <= {spi_shift_rx[6:0], adar_sdo};
                        adar_sclk <= 1'b0;
                        clk_cnt   <= (CLK_DIV > 1) ? (CLK_DIV - 1) : 32'd0;

                        if (spi_bit_cnt == 5'd0) begin
                            if (spi_in_hdr) begin
                                // Finished 16-bit header -> move to first 8-bit payload byte
                                spi_in_hdr  <= 1'b0;
                                spi_bit_cnt <= 5'd7;
                                if (spi_stream_mode) begin
                                    spi_shift_tx <= bram_rdata;
                                    rd_byte      <= rd_byte + 5'd1;
`ifndef MUTATE_CPHA_WRONG
                                    adar_sdio_o  <= bram_rdata[7];
`endif
                                end else begin
`ifndef MUTATE_CPHA_WRONG
                                    adar_sdio_o  <= spi_shift_tx[7];
`endif
                                end
                                adar_sdio_t <= spi_rw;
                                state       <= ST_SPI_LOW;
                            end else if (spi_stream_mode && (stream_byte_idx < 5'd23)) begin
                                // Continue ascending auto-increment burst while CSB stays LOW!
                                stream_byte_idx <= stream_byte_idx + 5'd1;
                                spi_bit_cnt     <= 5'd7;
                                spi_shift_tx    <= bram_rdata;
                                rd_byte         <= rd_byte + 5'd1;
`ifndef MUTATE_CPHA_WRONG
                                adar_sdio_o     <= bram_rdata[7];
`endif
                                state           <= ST_SPI_LOW;
                            end else begin
                                state <= ST_SPI_CSH;
                            end
                        end else begin
                            spi_bit_cnt <= spi_bit_cnt - 5'd1;
                            if (spi_in_hdr) begin
                                spi_hdr <= {spi_hdr[14:0], 1'b0};
`ifndef MUTATE_CPHA_WRONG
                                adar_sdio_o <= spi_hdr[14];
`endif
                            end else begin
                                spi_shift_tx <= {spi_shift_tx[6:0], 1'b0};
`ifndef MUTATE_CPHA_WRONG
                                adar_sdio_o <= spi_shift_tx[6];
`endif
                            end
                            state <= ST_SPI_LOW;
                        end
                    end
                end

                ST_SPI_LOW: begin
                    if (clk_cnt != 32'd0) begin
                        clk_cnt <= clk_cnt - 32'd1;
                    end else begin
                        adar_sclk <= 1'b1;
                        clk_cnt   <= (CLK_DIV > 1) ? (CLK_DIV - 1) : 32'd0;
                        state     <= ST_SPI_HIGH;
                    end
                end

                ST_SPI_CSH: begin
                    if (clk_cnt != 32'd0) begin
                        clk_cnt <= clk_cnt - 32'd1;
                    end else begin
                        adar_csb    <= 8'hFF;
                        adar_sdio_t <= 1'b1;
                        clk_cnt     <= (CLK_DIV > 1) ? (CLK_DIV - 1) : 32'd0;
                        state       <= ST_SPI_CONT;
                    end
                end

                ST_SPI_CONT: begin
                    if (clk_cnt != 32'd0) begin
                        clk_cnt <= clk_cnt - 32'd1;
                    end else begin
                        if (host_spi_active) begin
                            host_spi_active <= 1'b0;
                            spi_resp_valid  <= 1'b1;
                            spi_resp_rdata  <= spi_shift_rx;
                            state           <= ST_IDLE;
                        end else if (ret_state == ST_INIT_STEP) begin
                            if ((init_reg_step == 3'd2) && (spi_shift_rx != 8'hA5))
                                init_err <= 1'b1;
                            if (init_reg_step == 3'd6) begin
                                init_reg_step <= 3'd0;
                                if (init_chip == (NUM_CHIPS - 1)) begin
                                    init_done <= 1'b1;
                                    load_busy <= 1'b0;
                                    state     <= ST_IDLE;
                                end else begin
                                    init_chip <= init_chip + 3'd1;
                                    state     <= ST_INIT_STEP;
                                end
                            end else begin
                                init_reg_step <= init_reg_step + 3'd1;
                                state         <= ST_INIT_STEP;
                            end
                        end else begin
                            state <= ret_state;
                        end
                    end
                end

                default: state <= ST_IDLE;
            endcase
        end
    end
endmodule
