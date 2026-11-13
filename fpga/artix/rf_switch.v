// SPDX-License-Identifier: BSD-2-Clause
// Front-End IF RF Switch Matrix Control (SW_CTRL0..3, Bank 35 LVCMOS18)
//   sw_ctrl[0] (SW1: IF_RX_A) : 0 = RF1 (default), 1 = RF2
//   sw_ctrl[1] (SW2: IF_RX_B) : 0 = RF1 (default), 1 = RF2
//   sw_ctrl[2] (SW3: IF_TX_A) : 0 = RF1 (default), 1 = RF2
//   sw_ctrl[3] (SW4: IF_TX_B) : 0 = RF1 (default), 1 = RF2
// Provides glitch-free registered control and a programmable settling guard timer (sw_ready).

`timescale 1ns/1ps

module rf_switch #(
    parameter [3:0]  DEFAULT_STATE   = 4'b0000,
    parameter [15:0] DEFAULT_SETTLE  = 16'd125   // 1 us @ 125 MHz
) (
    input  wire        clk,
    input  wire        rst,

    input  wire [3:0]  sw_req,         // Desired SW_CTRL[3:0] configuration
    input  wire [15:0] settle_cycles,  // Guard cycles after any switch change
    output reg         sw_ready,       // 1 when switches have settled

    output reg  [3:0]  sw_ctrl
);
    reg [15:0] settle_cnt;
    wire [15:0] eff_settle = (settle_cycles == 16'd0) ? DEFAULT_SETTLE : settle_cycles;

    always @(posedge clk) begin
        if (rst) begin
            sw_ctrl    <= DEFAULT_STATE;
            settle_cnt <= eff_settle;
            sw_ready   <= 1'b0;
        end else if (sw_ctrl != sw_req) begin
            sw_ctrl    <= sw_req;
            settle_cnt <= eff_settle;
            sw_ready   <= 1'b0;
        end else if (settle_cnt != 16'd0) begin
            settle_cnt <= settle_cnt - 16'd1;
            sw_ready   <= 1'b0;
        end else begin
            sw_ready   <= 1'b1;
        end
    end
endmodule
