// SPDX-License-Identifier: BSD-2-Clause
// Stream 1 SDR / Telemetry Packet Generator for Dual-Path Uplinks (Rev06)
//
// Emits 64-bit LINK_PROTOCOL packets (stream_id = 8'h01) with deterministic
// I/Q sequence patterns, timestamp tagging, and selectable inter-packet gap.

`timescale 1ns/1ps
`default_nettype none

module eth_sdr_pkt_gen #(
    parameter [7:0]   STREAM_ID = 8'h01,
    parameter integer PKT_BYTES = 1024,
    parameter integer GAP_CYC   = 64
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        en,
    input  wire [63:0] timestamp_cnt,

    output reg         pkt_valid,
    input  wire        pkt_ready,
    output wire        pkt_sop,
    output wire        pkt_eop,
    output wire [7:0]  pkt_stream_id,
    output wire [15:0] pkt_len,
    output reg  [31:0] pkt_seq,
    output reg  [63:0] pkt_timestamp,
    output wire [63:0] pkt_data
);

    localparam [15:0] WORDS_PER_PKT = PKT_BYTES / 8;

    reg [15:0] word_idx;
    reg [15:0] gap_cnt;
    reg [15:0] iq_phase;

    assign pkt_sop       = pkt_valid && (word_idx == 16'd0);
    assign pkt_eop       = pkt_valid && (word_idx == WORDS_PER_PKT - 16'd1);
    assign pkt_stream_id = STREAM_ID;
    assign pkt_len       = PKT_BYTES[15:0];
    // Pack two 32-bit I/Q pairs per 64-bit word (matches SDR format)
    wire [15:0] i0 = iq_phase;
    wire [15:0] q0 = ~iq_phase;
    wire [15:0] i1 = iq_phase + 16'd1;
    wire [15:0] q1 = ~(iq_phase + 16'd1);
    assign pkt_data = {q1, i1, q0, i0};

    always @(posedge clk) begin
        if (rst) begin
            pkt_valid     <= 1'b0;
            word_idx      <= 16'd0;
            gap_cnt       <= 16'd0;
            pkt_seq       <= 32'd0;
            pkt_timestamp <= 64'd0;
            iq_phase      <= 16'd0;
        end else begin
            if (!pkt_valid) begin
                if (en) begin
                    if (gap_cnt >= GAP_CYC) begin
                        pkt_valid     <= 1'b1;
                        word_idx      <= 16'd0;
                        pkt_timestamp <= timestamp_cnt;
                        gap_cnt       <= 16'd0;
                    end else begin
                        gap_cnt <= gap_cnt + 16'd1;
                    end
                end
            end else if (pkt_ready) begin
                iq_phase <= iq_phase + 16'd2;
                if (pkt_eop) begin
                    pkt_valid <= 1'b0;
                    word_idx  <= 16'd0;
                    pkt_seq   <= pkt_seq + 32'd1;
                end else begin
                    word_idx <= word_idx + 16'd1;
                end
            end
        end
    end

endmodule
`default_nettype wire
