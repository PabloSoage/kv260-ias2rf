// SPDX-License-Identifier: BSD-2-Clause
// Si549 I2C Programmable Oscillator + CLK_SEL Open-Drain Multiplexer Controller
//
// Physical pins (Bank 15, LVCMOS33):
//   - xo_scl  (D9)  : Open-drain I2C clock to Si549 (U12 / 7'h55 default)
//   - xo_sda  (C14) : Open-drain I2C data to Si549
//   - clk_sel (D8)  : Open-drain clock mux select (High/Z = CLK1 Si549 default, Low = CLK0 SMA)
//
// Si549 Datasheet Register Map Procedure (f_XTAL = 152.6 MHz, Fvco in [10.8, 12.206718160] GHz):
//   1. Reg 255 = 0x00 (Page 0)
//   2. Reg 69  = 0x00 (Normal FCAL mode)
//   3. Reg 17  = 0x00 (Disable output)
//   4. Reg 23  = HSDIV[7:0]
//   5. Reg 24  = {1'b0, LSDIV[2:0], 1'b0, HSDIV[10:8]}
//   6. Reg 26..31 = FBDIV[42:0] (LSB first: Reg 26 = FBDIV[7:0] .. Reg 31 = {5'b0, FBDIV[42:40]})
//   7. Reg 7   = 0x08 (Start FCAL)
//   8. Wait >= 30 ms (parameterized FCAL_WAIT_CYC)
//   9. Reg 17  = 0x01 (Enable output)
// Fine +/-950 ppm trim via ADPLL_DELTA_M[23:0] -> Reg 231, 232, 233 (latched on Reg 233 write).
//
// Verified integer+fractional constants for f_XTAL = 152.6 MHz:
//   - 400.0 MHz: LSDIV=0 (/1), HSDIV=28 (0x01C), Fvco=11.200 GHz, FBDIV=43'h049_64FDA6C1
//   - 500.0 MHz: LSDIV=0 (/1), HSDIV=22 (0x016), Fvco=11.000 GHz, FBDIV=43'h048_15791F34

`timescale 1ns/1ps

module hk_xo_ctrl #(
    parameter [6:0]   SI549_ADDR    = 7'h55,
    parameter integer CLK_DIV       = 250,       // ~100 kHz I2C @ 100 MHz
    parameter integer FCAL_WAIT_CYC = 3_000_000  // 30 ms @ 100 MHz (override small in sim)
) (
    input  wire        clk,
    input  wire        rst,

    // Clock mux control: 0 = CLK1 (Si549 onboard, Hi-Z), 1 = CLK0 (external SMA, drive 0)
    input  wire        use_ext_clk,
    output wire        clk_sel_t,    // Connect to OBUFT(.I(1'b0), .T(clk_sel_t), .O(clk_sel))

    // High-level Si549 preset programming trigger (0 = 400.0 MHz, 1 = 500.0 MHz)
    input  wire        prog_start,
    input  wire        prog_freq_500m,

    // High-level +/-950 ppm fine delta_M programming trigger (Regs 231..233)
    input  wire        delta_start,
    input  wire [23:0] delta_m,

    // Generic raw Si549 register read/write (when idle)
    input  wire        raw_req_valid,
    output wire        raw_req_ready,
    input  wire        raw_req_rw,    // 0 = Write, 1 = Read
    input  wire [7:0]  raw_req_reg,
    input  wire [7:0]  raw_req_wdata,
    output reg         raw_resp_valid,
    output reg  [7:0]  raw_resp_rdata,
    output reg         raw_resp_err,

    // Status
    output reg         busy,
    output reg         prog_done,
    output reg         active_freq_500m,
    output reg         ack_err,
    output reg  [15:0] ack_err_cnt,

    // Physical pins (Bank 15 LVCMOS33)
    output wire        xo_scl_t,
    input  wire        xo_scl_in,
    output wire        xo_sda_t,
    input  wire        xo_sda_in
);

    // 400.0 MHz & 500.0 MHz Si549 constants (f_XTAL = 152.6 MHz)
    localparam [10:0] HSDIV_400 = 11'd28;              // 0x01C -> Fvco = 11.2 GHz
    localparam [42:0] FBDIV_400 = 43'h049_64FDA6C1;
    localparam [10:0] HSDIV_500 = 11'd22;              // 0x016 -> Fvco = 11.0 GHz
    localparam [42:0] FBDIV_500 = 43'h048_15791F34;

    assign clk_sel_t = ~use_ext_clk; // 1 = Hi-Z (Si549 CLK1), 0 = drive Low (SMA CLK0)

    reg        core_cmd_valid;
    wire       core_cmd_ready;
    reg [2:0]  core_wr_len;
    reg [31:0] core_wdata;
    reg [1:0]  core_rd_len;
    wire       core_resp_valid;
    wire       core_resp_ack_err;
    wire [15:0] core_resp_rdata;

    hk_i2c_core #(
        .CLK_DIV (CLK_DIV)
    ) u_xo_i2c (
        .clk          (clk),
        .rst          (rst),
        .cmd_valid    (core_cmd_valid),
        .cmd_ready    (core_cmd_ready),
        .cmd_dev_addr (SI549_ADDR),
        .cmd_wr_len   (core_wr_len),
        .cmd_wdata    (core_wdata),
        .cmd_rd_len   (core_rd_len),
        .resp_valid   (core_resp_valid),
        .resp_ack_err (core_resp_ack_err),
        .resp_rdata   (core_resp_rdata),
        .scl_t        (xo_scl_t),
        .scl_in       (xo_scl_in),
        .sda_t        (xo_sda_t),
        .sda_in       (xo_sda_in)
    );

    localparam [2:0]
        ST_IDLE       = 3'd0,
        ST_PROG_ISSUE = 3'd1,
        ST_PROG_WAIT  = 3'd2,
        ST_FCAL_WAIT  = 3'd3,
        ST_DELTA_SEND = 3'd4,
        ST_DELTA_WAIT = 3'd5,
        ST_RAW_WAIT   = 3'd6;

    reg [2:0]  state;
    reg [3:0]  step_idx;
    reg [31:0] wait_cnt;
    reg        lat_freq_500m;
    reg [23:0] lat_delta_m;
    reg [1:0]  delta_idx;

    wire [10:0] cur_hsdiv = lat_freq_500m ? HSDIV_500 : HSDIV_400;
    wire [42:0] cur_fbdiv = lat_freq_500m ? FBDIV_500 : FBDIV_400;

    // 13 I2C steps for full Si549 reconfiguration:
    //   0: Reg 255 = 0x00
    //   1: Reg 69  = 0x00
    //   2: Reg 17  = 0x00 (disable output)
    //   3: Reg 23  = HSDIV[7:0]
    //   4: Reg 24  = {1'b0, 3'd0 (LSDIV=/1), 1'b0, HSDIV[10:8]}
    //   5..10: Reg 26..31 = FBDIV[42:0]
    //  11: Reg 7   = 0x08 (start FCAL) -> followed by >=30ms FCAL wait
    //  12: Reg 17  = 0x01 (enable output)
    function [15:0] prog_step_pair;
        input [3:0]  idx;
        input [10:0] hs;
        input [42:0] fb;
        begin
            case (idx)
                4'd0:  prog_step_pair = {8'h00, 8'd255};
                4'd1:  prog_step_pair = {8'h00, 8'd69};
                4'd2:  prog_step_pair = {8'h00, 8'd17};
                4'd3:  prog_step_pair = {hs[7:0], 8'd23};
                4'd4:  prog_step_pair = {{1'b0, 3'd0, 1'b0, hs[10:8]}, 8'd24};
                4'd5:  prog_step_pair = {fb[7:0], 8'd26};
                4'd6:  prog_step_pair = {fb[15:8], 8'd27};
                4'd7:  prog_step_pair = {fb[23:16], 8'd28};
                4'd8:  prog_step_pair = {fb[31:24], 8'd29};
                4'd9:  prog_step_pair = {fb[39:32], 8'd30};
                4'd10: prog_step_pair = {{5'd0, fb[42:40]}, 8'd31};
                4'd11: prog_step_pair = {8'h08, 8'd7};
                default: prog_step_pair = {8'h01, 8'd17};
            endcase
        end
    endfunction

    assign raw_req_ready = (state == ST_IDLE) && core_cmd_ready && !prog_start && !delta_start;

    always @(posedge clk) begin
        if (rst) begin
            state            <= ST_IDLE;
            step_idx         <= 4'd0;
            wait_cnt         <= 32'd0;
            lat_freq_500m    <= 1'b0;
            lat_delta_m      <= 24'd0;
            delta_idx        <= 2'd0;
            core_cmd_valid   <= 1'b0;
            core_wr_len      <= 3'd0;
            core_wdata       <= 32'd0;
            core_rd_len      <= 2'd0;
            busy             <= 1'b0;
            prog_done        <= 1'b0;
            active_freq_500m <= 1'b0;
            ack_err          <= 1'b0;
            ack_err_cnt      <= 16'd0;
            raw_resp_valid   <= 1'b0;
            raw_resp_rdata   <= 8'd0;
            raw_resp_err     <= 1'b0;
        end else begin
            core_cmd_valid <= 1'b0;
            raw_resp_valid <= 1'b0;

            case (state)
                ST_IDLE: begin
                    busy <= 1'b0;
                    if (core_cmd_ready) begin
                        if (prog_start) begin
                            lat_freq_500m <= prog_freq_500m;
                            step_idx      <= 4'd0;
                            busy          <= 1'b1;
                            prog_done     <= 1'b0;
                            ack_err       <= 1'b0;
                            state         <= ST_PROG_ISSUE;
                        end else if (delta_start) begin
                            lat_delta_m <= delta_m;
                            delta_idx   <= 2'd0;
                            busy        <= 1'b1;
                            ack_err     <= 1'b0;
                            state       <= ST_DELTA_SEND;
                        end else if (raw_req_valid) begin
                            core_cmd_valid <= 1'b1;
                            if (raw_req_rw) begin
                                core_wr_len <= 3'd1;
                                core_wdata  <= {24'd0, raw_req_reg};
                                core_rd_len <= 2'd1;
                            end else begin
                                core_wr_len <= 3'd2;
                                core_wdata  <= {16'd0, raw_req_wdata, raw_req_reg};
                                core_rd_len <= 2'd0;
                            end
                            busy  <= 1'b1;
                            state <= ST_RAW_WAIT;
                        end
                    end
                end

                ST_PROG_ISSUE: begin
                    if (core_cmd_ready) begin
                        core_cmd_valid <= 1'b1;
                        core_wr_len    <= 3'd2;
                        core_wdata     <= {16'd0, prog_step_pair(step_idx, cur_hsdiv, cur_fbdiv)};
                        core_rd_len    <= 2'd0;
                        state          <= ST_PROG_WAIT;
                    end
                end

                ST_PROG_WAIT: begin
                    if (core_resp_valid) begin
                        if (core_resp_ack_err) begin
                            ack_err <= 1'b1;
                            if (ack_err_cnt != 16'hFFFF)
                                ack_err_cnt <= ack_err_cnt + 16'd1;
                            state <= ST_IDLE;
                        end else if (step_idx == 4'd11) begin
                            wait_cnt <= (FCAL_WAIT_CYC < 1) ? 32'd1 : FCAL_WAIT_CYC[31:0];
                            state    <= ST_FCAL_WAIT;
                        end else if (step_idx == 4'd12) begin
                            active_freq_500m <= lat_freq_500m;
                            prog_done        <= 1'b1;
                            state            <= ST_IDLE;
                        end else begin
                            step_idx <= step_idx + 4'd1;
                            state    <= ST_PROG_ISSUE;
                        end
                    end
                end

                ST_FCAL_WAIT: begin
                    if (wait_cnt != 32'd0) begin
                        wait_cnt <= wait_cnt - 32'd1;
                    end else begin
                        step_idx <= 4'd12;
                        state    <= ST_PROG_ISSUE;
                    end
                end

                ST_DELTA_SEND: begin
                    if (core_cmd_ready) begin
                        core_cmd_valid <= 1'b1;
                        core_wr_len    <= 3'd2;
                        core_rd_len    <= 2'd0;
                        case (delta_idx)
                            2'd0:    core_wdata <= {16'd0, lat_delta_m[7:0],   8'd231};
                            2'd1:    core_wdata <= {16'd0, lat_delta_m[15:8],  8'd232};
                            default: core_wdata <= {16'd0, lat_delta_m[23:16], 8'd233};
                        endcase
                        state <= ST_DELTA_WAIT;
                    end
                end

                ST_DELTA_WAIT: begin
                    if (core_resp_valid) begin
                        if (core_resp_ack_err) begin
                            ack_err <= 1'b1;
                            if (ack_err_cnt != 16'hFFFF)
                                ack_err_cnt <= ack_err_cnt + 16'd1;
                            state <= ST_IDLE;
                        end else if (delta_idx == 2'd2) begin
                            state <= ST_IDLE;
                        end else begin
                            delta_idx <= delta_idx + 2'd1;
                            state     <= ST_DELTA_SEND;
                        end
                    end
                end

                ST_RAW_WAIT: begin
                    if (core_resp_valid) begin
                        raw_resp_valid <= 1'b1;
                        raw_resp_rdata <= core_resp_rdata[7:0];
                        raw_resp_err   <= core_resp_ack_err;
                        if (core_resp_ack_err) begin
                            ack_err <= 1'b1;
                            if (ack_err_cnt != 16'hFFFF)
                                ack_err_cnt <= ack_err_cnt + 16'd1;
                        end
                        state <= ST_IDLE;
                    end
                end

                default: state <= ST_IDLE;
            endcase
        end
    end

endmodule
`default_nettype wire
