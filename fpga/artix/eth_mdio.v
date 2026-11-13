// SPDX-License-Identifier: BSD-2-Clause
// IEEE 802.3 Clause 22 MDIO/MDC Master + RTL8211FSI Reset/Status Controller (Rev06)
//
// Periodically polls BMSR (Reg 0x01) for copper link status, handles on-demand
// register R/W requests, drives active-low ETH_RST_N reset pulse on startup,
// and samples active-low ETH_INT_N.

`timescale 1ns/1ps
`default_nettype none

module eth_mdio #(
    parameter [4:0]   PHY_ADDR     = 5'd1,       // R1202 pulls LED0/PHYAD0 high -> 1
    parameter integer MDC_DIV      = 64,         // 125 MHz / 64 = 1.953 MHz MDC
    parameter integer RST_CYC      = 1_250_000,  // 10 ms reset pulse @ 125 MHz (override in sim)
    parameter integer POLL_DIV     = 125_000     // 1 ms BMSR poll interval (override in sim)
) (
    input  wire        clk,
    input  wire        rst,

    // On-demand MDIO transaction interface
    input  wire        req_valid,
    input  wire        req_write,
    input  wire [4:0]  req_reg,
    input  wire [15:0] req_wdata,
    output wire        req_ready,
    output reg         resp_valid,
    output reg  [15:0] resp_rdata,

    // Status outputs
    output reg         phy_rst_done,
    output reg         copper_link_up,
    output reg  [15:0] bmsr_val,
    output wire        int_pending,

    // Board PHY pins
    output reg         eth_mdc,
    inout  wire        eth_mdio,
    output reg         eth_rst_n,
    input  wire        eth_int_n
);

    wire mdio_in;
    reg  mdio_out;
    reg  mdio_oe;

    // Open-drain driver for Bank 14 LVCMOS33 M15 pulled up externally to PHY 2.5V DVDDRG via R1213:
    // Drive LOW only (I=0, T=0 when mdio_oe && !mdio_out); Hi-Z (T=1) otherwise.
    IOBUF #(
        .DRIVE      (8),
        .IOSTANDARD ("LVCMOS33"),
        .SLEW       ("SLOW")
    ) u_iobuf_mdio (
        .O  (mdio_in),
        .IO (eth_mdio),
        .I  (1'b0),
        .T  (~(mdio_oe & ~mdio_out))
    );

    (* ASYNC_REG = "TRUE" *) reg [1:0] int_sync_r;
    always @(posedge clk) begin
        if (rst) int_sync_r <= 2'b11;
        else     int_sync_r <= {int_sync_r[0], eth_int_n};
    end
    assign int_pending = ~int_sync_r[1];

    localparam integer HALF_DIV = (MDC_DIV >= 4) ? (MDC_DIV / 2) : 2;
    reg [7:0]  div_cnt;
    wire       mdc_rise_tick = (div_cnt == HALF_DIV - 1);
    wire       mdc_fall_tick = (div_cnt == (2 * HALF_DIV) - 1);

    reg [23:0] rst_cnt;
    reg [23:0] poll_cnt;

    localparam [1:0] ST_IDLE = 2'd0, ST_SHIFT = 2'd1, ST_DONE = 2'd2;
    reg [1:0]  st;
    reg [5:0]  bit_idx;   // 0..63 (32 preamble 1s + 32 frame bits)
    reg [31:0] tx_frame;
    reg [15:0] rx_shift;
    reg        cur_write;
    reg        cur_is_poll;

    assign req_ready = (st == ST_IDLE) && phy_rst_done;

    // 32-bit Clause 22 frame: {ST(01), OP(01=wr,10=rd), PHYAD[4:0], REGAD[4:0], TA(10), DATA[15:0]}
    always @(posedge clk) begin
        if (rst) begin
            div_cnt        <= 8'd0;
            eth_mdc        <= 1'b0;
            rst_cnt        <= RST_CYC;
            phy_rst_done   <= 1'b0;
            eth_rst_n      <= 1'b0;
            poll_cnt       <= 24'd0;
            st             <= ST_IDLE;
            bit_idx        <= 6'd0;
            tx_frame       <= 32'd0;
            rx_shift       <= 16'd0;
            mdio_out       <= 1'b1;
            mdio_oe        <= 1'b0;
            resp_valid     <= 1'b0;
            resp_rdata     <= 16'd0;
            bmsr_val       <= 16'd0;
            copper_link_up <= 1'b0;
            cur_write      <= 1'b0;
            cur_is_poll    <= 1'b0;
        end else begin
            resp_valid <= 1'b0;

            if (rst_cnt != 24'd0) begin
                rst_cnt      <= rst_cnt - 24'd1;
                eth_rst_n    <= 1'b0;
                phy_rst_done <= 1'b0;
            end else begin
                eth_rst_n    <= 1'b1;
                phy_rst_done <= 1'b1;
            end

            // MDC divider
            if (mdc_fall_tick) begin
                div_cnt <= 8'd0;
                eth_mdc <= 1'b0;
            end else begin
                div_cnt <= div_cnt + 8'd1;
                if (mdc_rise_tick)
                    eth_mdc <= 1'b1;
            end

            if (poll_cnt != 24'd0)
                poll_cnt <= poll_cnt - 24'd1;

            case (st)
                ST_IDLE: begin
                    mdio_oe  <= 1'b0;
                    mdio_out <= 1'b1;
                    if (phy_rst_done) begin
                        if (req_valid) begin
                            cur_write   <= req_write;
                            cur_is_poll <= 1'b0;
                            tx_frame    <= {2'b01, (req_write ? 2'b01 : 2'b10), PHY_ADDR, req_reg, 2'b10, req_wdata};
                            bit_idx     <= 6'd0;
                            st          <= ST_SHIFT;
                        end else if (poll_cnt == 24'd0) begin
                            cur_write   <= 1'b0;
                            cur_is_poll <= 1'b1;
                            tx_frame    <= {2'b01, 2'b10, PHY_ADDR, 5'd1, 2'b10, 16'h0000}; // BMSR Reg 1
                            bit_idx     <= 6'd0;
                            poll_cnt    <= POLL_DIV;
                            st          <= ST_SHIFT;
                        end
                    end
                end

                ST_SHIFT: begin
                    // Drive outgoing MDIO on MDC falling edge so PHY samples on rising edge
                    if (mdc_fall_tick) begin
                        if (bit_idx < 6'd32) begin
                            mdio_oe  <= 1'b1;
                            mdio_out <= 1'b1; // 32-bit preamble
                        end else if (bit_idx < 6'd46) begin
                            mdio_oe  <= 1'b1;
                            mdio_out <= tx_frame[31 - (bit_idx - 6'd32)];
                        end else if (!cur_write) begin
                            mdio_oe  <= 1'b0; // TA (bits 46..47) + Read data (48..63)
                        end else begin
                            mdio_oe  <= 1'b1;
                            mdio_out <= tx_frame[31 - (bit_idx - 6'd32)];
                        end
                    end

                    // Sample incoming MDIO & advance bit counter on MDC rising edge
                    if (mdc_rise_tick) begin
                        if (!cur_write && bit_idx >= 6'd48)
                            rx_shift <= {rx_shift[14:0], mdio_in};
                        if (bit_idx == 6'd63)
                            st <= ST_DONE;
                        else
                            bit_idx <= bit_idx + 6'd1;
                    end
                end

                ST_DONE: begin
                    if (mdc_fall_tick) begin
                        mdio_oe <= 1'b0;
                        st      <= ST_IDLE;
                        if (cur_is_poll) begin
                            bmsr_val       <= rx_shift;
                            copper_link_up <= rx_shift[2]; // BMSR bit 2 = Link Status
                        end else begin
                            resp_valid <= 1'b1;
                            resp_rdata <= rx_shift;
                        end
                    end
                end

                default: st <= ST_IDLE;
            endcase
        end
    end

endmodule
`default_nettype wire
