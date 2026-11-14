// SPDX-License-Identifier: BSD-2-Clause
// Generic Open-Drain I2C Master Core + HK Bus Controller (TMP1075 + M24C02 EEPROM)
//
// Target Devices on HK_SCL (K5) / HK_SDA (J5) / HK_ALERT_N (K2), Bank 35 LVCMOS18 (shared with KV260 PS):
//   - TMP1075DR Temperature Sensor (7'h48): Reg 0x00 (12-bit Temp MSB..LSB in [15:4] * 0.0625 C),
//     Reg 0x01 (Configuration). Open-drain ALERT# monitored actively on hk_alert_n.
//   - M24C02-FMN6TP 256B EEPROM (7'h50): 1-byte word address + 1..2 byte read/write.
//
// Master releases SCL/SDA to high-Z (scl_t=1, sda_t=1) whenever idle or between transactions
// so the carrier PS can share the bus cleanly without contention.

`timescale 1ns/1ps

module hk_i2c_core #(
    parameter integer CLK_DIV = 250 // Quarter-bit divider: f_I2C = f_clk / (4 * CLK_DIV)
) (
    input  wire        clk,
    input  wire        rst,

    // Generic transaction interface (up to 4 write bytes + optional repeated-start 1..2 byte read)
    input  wire        cmd_valid,
    output wire        cmd_ready,
    input  wire [6:0]  cmd_dev_addr,
    input  wire [2:0]  cmd_wr_len,    // 0..4 bytes in cmd_wdata[31:0] (byte0 = MSB [31:24], or [7:0]?)
                                      // Packing: byte0 = cmd_wdata[7:0], byte1 = [15:8], byte2 = [23:16], byte3 = [31:24]
    input  wire [31:0] cmd_wdata,
    input  wire [1:0]  cmd_rd_len,    // 0..2 bytes read into resp_rdata ([7:0] = byte0 / MSB, [15:8] = byte1 / LSB)

    output reg         resp_valid,
    output reg         resp_ack_err,
    output reg  [15:0] resp_rdata,

    // Open-drain I2C physical pins (active-low drive via T=~drv_low, O=0)
    output reg         scl_t,
    input  wire        scl_in,
    output reg         sda_t,
    input  wire        sda_in
);

    localparam [3:0]
        ST_IDLE     = 4'd0,
        ST_START    = 4'd1,
        ST_TX_BIT   = 4'd2,
        ST_TX_ACK   = 4'd3,
        ST_REP_PREP = 4'd4,
        ST_REP_STRT = 4'd5,
        ST_RX_BIT   = 4'd6,
        ST_RX_ACK   = 4'd7,
        ST_STOP     = 4'd8,
        ST_DONE     = 4'd9;

    reg [3:0]  state;
    reg [15:0] div_cnt;
    reg [1:0]  phase;       // 0..3 quarter-bit phase
    reg [2:0]  bit_idx;     // 7 down to 0
    reg [2:0]  byte_idx;
    reg [7:0]  shreg;

    reg [6:0]  lat_addr;
    reg [2:0]  lat_wr_len;
    reg [31:0] lat_wdata;
    reg [1:0]  lat_rd_len;
    reg [15:0] rd_accum;
    reg        in_addr_phase;
    reg        in_rd_phase;
    reg        ack_err;

    assign cmd_ready = (state == ST_IDLE);

    // Helper: select write byte 0..3
    function [7:0] get_wr_byte;
        input [31:0] w;
        input [2:0]  idx;
        begin
            case (idx)
                3'd0: get_wr_byte = w[7:0];
                3'd1: get_wr_byte = w[15:8];
                3'd2: get_wr_byte = w[23:16];
                default: get_wr_byte = w[31:24];
            endcase
        end
    endfunction

    wire [15:0] eff_div = (CLK_DIV < 1) ? 16'd1 : CLK_DIV[15:0];
    wire tick = (div_cnt == 16'd0);
    // Support slave clock stretching while SCL is released high
    wire clk_stretch = (scl_t == 1'b1) && (scl_in == 1'b0) &&
                       (state == ST_TX_BIT || state == ST_TX_ACK ||
                        state == ST_RX_BIT || state == ST_RX_ACK) &&
                       (phase == 2'd2);

    always @(posedge clk) begin
        if (rst) begin
            state         <= ST_IDLE;
            div_cnt       <= 16'd0;
            phase         <= 2'd0;
            bit_idx       <= 3'd7;
            byte_idx      <= 3'd0;
            shreg         <= 8'd0;
            lat_addr      <= 7'd0;
            lat_wr_len    <= 3'd0;
            lat_wdata     <= 32'd0;
            lat_rd_len    <= 2'd0;
            rd_accum      <= 16'd0;
            in_addr_phase <= 1'b0;
            in_rd_phase   <= 1'b0;
            ack_err       <= 1'b0;
            scl_t         <= 1'b1; // High-Z (idle)
            sda_t         <= 1'b1; // High-Z (idle)
            resp_valid    <= 1'b0;
            resp_ack_err  <= 1'b0;
            resp_rdata    <= 16'd0;
        end else begin
            resp_valid <= 1'b0;

            if (state == ST_IDLE) begin
                scl_t   <= 1'b1;
                sda_t   <= 1'b1;
                phase   <= 2'd0;
                div_cnt <= eff_div - 16'd1;
                if (cmd_valid) begin
                    lat_addr      <= cmd_dev_addr;
                    lat_wr_len    <= (cmd_wr_len > 3'd4) ? 3'd4 : cmd_wr_len;
                    lat_wdata     <= cmd_wdata;
                    lat_rd_len    <= (cmd_rd_len > 2'd2) ? 2'd2 : cmd_rd_len;
                    rd_accum      <= 16'd0;
                    ack_err       <= 1'b0;
                    byte_idx      <= 3'd0;
                    in_addr_phase <= 1'b1;
                    // If wr_len == 0 and rd_len > 0, go straight to read address
                    in_rd_phase   <= (cmd_wr_len == 3'd0) && (cmd_rd_len != 2'd0);
                    shreg         <= {cmd_dev_addr, ((cmd_wr_len == 3'd0) && (cmd_rd_len != 2'd0))};
                    state         <= ST_START;
                end
            end else if (!clk_stretch) begin
                if (!tick) begin
                    div_cnt <= div_cnt - 16'd1;
                end else begin
                    div_cnt <= eff_div - 16'd1;

                    case (state)
                        ST_START: begin
                            // Phase 0: SDA high, SCL high -> pull SDA low while SCL high
                            case (phase)
                                2'd0: begin scl_t <= 1'b1; sda_t <= 1'b1; phase <= 2'd1; end
                                2'd1: begin scl_t <= 1'b1; sda_t <= 1'b0; phase <= 2'd2; end
                                2'd2: begin scl_t <= 1'b0; sda_t <= 1'b0; phase <= 2'd3; end
                                default: begin
                                    scl_t   <= 1'b0;
                                    bit_idx <= 3'd7;
                                    phase   <= 2'd0;
                                    state   <= ST_TX_BIT;
                                end
                            endcase
                        end

                        ST_TX_BIT: begin
                            case (phase)
                                2'd0: begin
                                    scl_t <= 1'b0;
                                    sda_t <= shreg[bit_idx];
                                    phase <= 2'd1;
                                end
                                2'd1: begin
                                    scl_t <= 1'b1;
                                    phase <= 2'd2;
                                end
                                2'd2: begin
                                    scl_t <= 1'b1;
                                    phase <= 2'd3;
                                end
                                default: begin
                                    scl_t <= 1'b0;
                                    phase <= 2'd0;
                                    if (bit_idx == 3'd0) begin
                                        sda_t <= 1'b1; // Release SDA for slave ACK
                                        state <= ST_TX_ACK;
                                    end else begin
                                        bit_idx <= bit_idx - 3'd1;
                                    end
                                end
                            endcase
                        end

                        ST_TX_ACK: begin
                            case (phase)
                                2'd0: begin scl_t <= 1'b0; sda_t <= 1'b1; phase <= 2'd1; end
                                2'd1: begin scl_t <= 1'b1; sda_t <= 1'b1; phase <= 2'd2; end
                                2'd2: begin
                                    scl_t <= 1'b1;
`ifdef MUTATE_MISSING_ACK
                                    // Fault mutation: ignore slave NACK (sda_in == 1)
`else
                                    if (sda_in == 1'b1)
                                        ack_err <= 1'b1;
`endif
                                    phase <= 2'd3;
                                end
                                default: begin
                                    scl_t <= 1'b0;
                                    phase <= 2'd0;
                                    if (ack_err) begin
                                        sda_t <= 1'b0;
                                        state <= ST_STOP;
                                    end else if (in_addr_phase) begin
                                        in_addr_phase <= 1'b0;
                                        if (in_rd_phase) begin
                                            byte_idx <= 3'd0;
                                            bit_idx  <= 3'd7;
                                            shreg    <= 8'd0;
                                            sda_t    <= 1'b1;
                                            state    <= ST_RX_BIT;
                                        end else if (lat_wr_len == 3'd0) begin
                                            sda_t <= 1'b0;
                                            state <= ST_STOP;
                                        end else begin
                                            byte_idx <= 3'd0;
                                            bit_idx  <= 3'd7;
                                            shreg    <= get_wr_byte(lat_wdata, 3'd0);
                                            state    <= ST_TX_BIT;
                                        end
                                    end else begin
                                        // Finished a write data byte
                                        if ((byte_idx + 3'd1) < lat_wr_len) begin
                                            byte_idx <= byte_idx + 3'd1;
                                            bit_idx  <= 3'd7;
                                            shreg    <= get_wr_byte(lat_wdata, byte_idx + 3'd1);
                                            state    <= ST_TX_BIT;
                                        end else if (lat_rd_len != 2'd0) begin
                                            // Switch to repeated start for read
                                            in_rd_phase   <= 1'b1;
                                            in_addr_phase <= 1'b1;
                                            sda_t         <= 1'b1;
                                            state         <= ST_REP_PREP;
                                        end else begin
                                            sda_t <= 1'b0;
                                            state <= ST_STOP;
                                        end
                                    end
                                end
                            endcase
                        end

                        ST_REP_PREP: begin
                            // Release SDA=1 then SCL=1 cleanly before Repeated START
                            case (phase)
                                2'd0: begin scl_t <= 1'b0; sda_t <= 1'b1; phase <= 2'd1; end
                                2'd1: begin scl_t <= 1'b1; sda_t <= 1'b1; phase <= 2'd2; end
                                default: begin
                                    phase <= 2'd0;
                                    shreg <= {lat_addr, 1'b1};
                                    state <= ST_REP_STRT;
                                end
                            endcase
                        end

                        ST_REP_STRT: begin
                            case (phase)
                                2'd0: begin scl_t <= 1'b1; sda_t <= 1'b1; phase <= 2'd1; end
                                2'd1: begin scl_t <= 1'b1; sda_t <= 1'b0; phase <= 2'd2; end
                                default: begin
                                    scl_t   <= 1'b0;
                                    bit_idx <= 3'd7;
                                    phase   <= 2'd0;
                                    state   <= ST_TX_BIT;
                                end
                            endcase
                        end

                        ST_RX_BIT: begin
                            case (phase)
                                2'd0: begin scl_t <= 1'b0; sda_t <= 1'b1; phase <= 2'd1; end
                                2'd1: begin scl_t <= 1'b1; phase <= 2'd2; end
                                2'd2: begin
                                    scl_t          <= 1'b1;
                                    shreg[bit_idx] <= sda_in;
                                    phase          <= 2'd3;
                                end
                                default: begin
                                    scl_t <= 1'b0;
                                    phase <= 2'd0;
                                    if (bit_idx == 3'd0) begin
                                        if (byte_idx == 3'd0)
                                            rd_accum[7:0] <= shreg;
                                        else
                                            rd_accum[15:8] <= shreg;
                                        state <= ST_RX_ACK;
                                    end else begin
                                        bit_idx <= bit_idx - 3'd1;
                                    end
                                end
                            endcase
                        end

                        ST_RX_ACK: begin
                            // Master sends ACK (0) if more bytes remain, else NACK (1)
                            case (phase)
                                2'd0: begin
                                    scl_t <= 1'b0;
                                    sda_t <= ((byte_idx + 3'd1) >= {1'b0, lat_rd_len});
                                    phase <= 2'd1;
                                end
                                2'd1: begin scl_t <= 1'b1; phase <= 2'd2; end
                                2'd2: begin scl_t <= 1'b1; phase <= 2'd3; end
                                default: begin
                                    scl_t <= 1'b0;
                                    phase <= 2'd0;
                                    if ((byte_idx + 3'd1) < {1'b0, lat_rd_len}) begin
                                        byte_idx <= byte_idx + 3'd1;
                                        bit_idx  <= 3'd7;
                                        sda_t    <= 1'b1;
                                        state    <= ST_RX_BIT;
                                    end else begin
                                        sda_t <= 1'b0;
                                        state <= ST_STOP;
                                    end
                                end
                            endcase
                        end

                        ST_STOP: begin
                            case (phase)
                                2'd0: begin scl_t <= 1'b0; sda_t <= 1'b0; phase <= 2'd1; end
                                2'd1: begin scl_t <= 1'b1; sda_t <= 1'b0; phase <= 2'd2; end
                                2'd2: begin scl_t <= 1'b1; sda_t <= 1'b1; phase <= 2'd3; end
                                default: begin
                                    scl_t <= 1'b1;
                                    sda_t <= 1'b1;
                                    phase <= 2'd0;
                                    state <= ST_DONE;
                                end
                            endcase
                        end

                        ST_DONE: begin
                            resp_valid   <= 1'b1;
                            resp_ack_err <= ack_err;
                            resp_rdata   <= rd_accum;
                            state        <= ST_IDLE;
                        end

                        default: state <= ST_IDLE;
                    endcase
                end
            end
        end
    end

endmodule

module hk_i2c_master #(
    parameter integer CLK_DIV   = 250,      // ~100 kHz @ 100 MHz
    parameter integer POLL_DIV  = 10_000_000 // ~100 ms @ 100 MHz (override small in sim)
) (
    input  wire        clk,
    input  wire        rst,

    // Automatic TMP1075 (7'h48) background temperature polling
    input  wire        poll_en,

    // Host manual transaction request (TMP1075 config, M24C02 EEPROM 7'h50, etc.)
    input  wire        req_valid,
    output wire        req_ready,
    input  wire [6:0]  req_dev_addr,
    input  wire [2:0]  req_wr_len,
    input  wire [31:0] req_wdata,
    input  wire [1:0]  req_rd_len,
    output reg         req_done,
    output reg         req_ack_err,
    output reg  [15:0] req_rdata,

    // Live housekeeping status
    output reg  [15:0] tmp_raw,        // {MSB, LSB}: signed [15:4] = 0.0625 C/LSB
    output reg         tmp_valid,
    output reg         alert_active,   // ~hk_alert_n (synchronized)
    output reg         last_ack_err,
    output reg  [15:0] ack_err_cnt,
    output wire        busy,

    // Physical pins (Bank 35 LVCMOS18)
    output wire        hk_scl_t,
    input  wire        hk_scl_in,
    output wire        hk_sda_t,
    input  wire        hk_sda_in,
    input  wire        hk_alert_n
);

    localparam [6:0] TMP1075_ADDR = 7'h48;

    (* ASYNC_REG = "TRUE" *) reg [1:0] alert_sync;
    always @(posedge clk) begin
        if (rst) begin
            alert_sync   <= 2'b11;
            alert_active <= 1'b0;
        end else begin
            alert_sync   <= {alert_sync[0], hk_alert_n};
            alert_active <= ~alert_sync[1];
        end
    end

    reg        core_cmd_valid;
    wire       core_cmd_ready;
    reg [6:0]  core_dev_addr;
    reg [2:0]  core_wr_len;
    reg [31:0] core_wdata;
    reg [1:0]  core_rd_len;
    wire       core_resp_valid;
    wire       core_resp_ack_err;
    wire [15:0] core_resp_rdata;

    hk_i2c_core #(
        .CLK_DIV (CLK_DIV)
    ) u_core (
        .clk          (clk),
        .rst          (rst),
        .cmd_valid    (core_cmd_valid),
        .cmd_ready    (core_cmd_ready),
        .cmd_dev_addr (core_dev_addr),
        .cmd_wr_len   (core_wr_len),
        .cmd_wdata    (core_wdata),
        .cmd_rd_len   (core_rd_len),
        .resp_valid   (core_resp_valid),
        .resp_ack_err (core_resp_ack_err),
        .resp_rdata   (core_resp_rdata),
        .scl_t        (hk_scl_t),
        .scl_in       (hk_scl_in),
        .sda_t        (hk_sda_t),
        .sda_in       (hk_sda_in)
    );

    localparam [1:0]
        ARB_IDLE = 2'd0,
        ARB_HOST = 2'd1,
        ARB_POLL = 2'd2;

    reg [1:0]  arb_state;
    reg [31:0] poll_cnt;

    assign req_ready = (arb_state == ARB_IDLE) && core_cmd_ready;
    assign busy      = (arb_state != ARB_IDLE);

    always @(posedge clk) begin
        if (rst) begin
            arb_state      <= ARB_IDLE;
            core_cmd_valid <= 1'b0;
            core_dev_addr  <= 7'd0;
            core_wr_len    <= 3'd0;
            core_wdata     <= 32'd0;
            core_rd_len    <= 2'd0;
            poll_cnt       <= 32'd0;
            req_done       <= 1'b0;
            req_ack_err    <= 1'b0;
            req_rdata      <= 16'd0;
            tmp_raw        <= 16'd0;
            tmp_valid      <= 1'b0;
            last_ack_err   <= 1'b0;
            ack_err_cnt    <= 16'd0;
        end else begin
            core_cmd_valid <= 1'b0;
            req_done       <= 1'b0;

            if (poll_en) begin
                if (poll_cnt != 32'd0)
                    poll_cnt <= poll_cnt - 32'd1;
            end else begin
                poll_cnt <= 32'd0;
            end

            case (arb_state)
                ARB_IDLE: begin
                    if (core_cmd_ready) begin
                        if (req_valid) begin
                            core_cmd_valid <= 1'b1;
                            core_dev_addr  <= req_dev_addr;
                            core_wr_len    <= req_wr_len;
                            core_wdata     <= req_wdata;
                            core_rd_len    <= req_rd_len;
                            arb_state      <= ARB_HOST;
                        end else if (poll_en && (poll_cnt == 32'd0)) begin
                            // TMP1075 Reg 0x00 temperature read (2 bytes)
                            core_cmd_valid <= 1'b1;
                            core_dev_addr  <= TMP1075_ADDR;
                            core_wr_len    <= 3'd1;
                            core_wdata     <= 32'h0000_0000; // Pointer = 0x00
                            core_rd_len    <= 2'd2;
                            poll_cnt       <= (POLL_DIV < 1) ? 32'd1 : POLL_DIV[31:0];
                            arb_state      <= ARB_POLL;
                        end
                    end
                end

                ARB_HOST: begin
                    if (core_resp_valid) begin
                        req_done     <= 1'b1;
                        req_ack_err  <= core_resp_ack_err;
                        req_rdata    <= core_resp_rdata;
                        last_ack_err <= core_resp_ack_err;
                        if (core_resp_ack_err && (ack_err_cnt != 16'hFFFF))
                            ack_err_cnt <= ack_err_cnt + 16'd1;
                        arb_state <= ARB_IDLE;
                    end
                end

                ARB_POLL: begin
                    if (core_resp_valid) begin
                        last_ack_err <= core_resp_ack_err;
                        if (core_resp_ack_err) begin
                            if (ack_err_cnt != 16'hFFFF)
                                ack_err_cnt <= ack_err_cnt + 16'd1;
                        end else begin
                            // core resp_rdata[7:0]=MSB, [15:8]=LSB -> pack {MSB, LSB} in [15:0]
                            tmp_raw   <= {core_resp_rdata[7:0], core_resp_rdata[15:8]};
                            tmp_valid <= 1'b1;
                        end
                        arb_state <= ARB_IDLE;
                    end
                end

                default: arb_state <= ARB_IDLE;
            endcase
        end
    end

endmodule
`default_nettype wire
