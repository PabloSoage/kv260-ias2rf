// SPDX-License-Identifier: Apache-2.0
// kria_ps_framer: the PS-bound stream as self-describing packets in large DMA blocks (18 Nov 2026)
//
// axi_dma_0 runs in simple (register) mode, and its S2MM channel ends a transfer at tlast. Before this block the
// link's packets went straight to it: a transfer of at most 512 bytes each, so Linux would have had to re-arm the
// channel about 200,000 times a second at the AD9484 stream's rate, and the packet's stream id (tid) was lost,
// since the DMA writes only tdata. This block sits between kria_pl_link and the DMA:
//
//   * two inputs, packet by packet: A, the link's uplink packets (tid = the link's stream id, tuser[0] = CRC
//     error); B, the DSP suite's results (kria_dsp_out, tid 0x20..0x23);
//   * each packet is stored whole (a 4096-word FIFO, 32 KiB, which also covers the DMA's re-arm time: 330 us at
//     100 MB/s) and goes out behind two header words:
//         word 0 = {8'hA5, tid[7:0], flags[7:0], 8'h00, words[15:0], seq[15:0]}  flags[0]: CRC error (input A)
//                                                                              flags[1]: from input B
//         word 1 = the 64-bit pl_clk_100m tick count when the packet's last word arrived (10 ns)
//   * tlast goes on the last word of the first packet that brings the block to BLOCK_WORDS (8192 words, 64 KiB)
//     or more, so a transfer is at most (BLOCK_WORDS + 514) words: Linux arms the channel with 69,648 bytes and
//     reads S2MM_LENGTH for what came. When nothing is pending for IDLE_FLUSH clocks and the block holds data, a
//     two-word flush packet (tid 8'h00, 0 words) ends it, so a slow stream is never held back for long.

`timescale 1ns/1ps

module kria_ps_framer #(
    parameter BLOCK_WORDS = 8192,
    parameter FIFO_AW     = 12,
    parameter IDLE_FLUSH  = 100000          // 1 ms at 100 MHz
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 clk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axis_a:s_axis_b:m_axis, ASSOCIATED_RESET resetn" *)
    input  wire        clk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 resetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire        resetn,

    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_a TDATA" *)
    input  wire [63:0] s_axis_a_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_a TKEEP" *)
    input  wire [7:0]  s_axis_a_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_a TVALID" *)
    input  wire        s_axis_a_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_a TREADY" *)
    output wire        s_axis_a_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_a TLAST" *)
    input  wire        s_axis_a_tlast,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_a TID" *)
    input  wire [7:0]  s_axis_a_tid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_a TUSER" *)
    input  wire [0:0]  s_axis_a_tuser,

    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_b TDATA" *)
    input  wire [63:0] s_axis_b_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_b TVALID" *)
    input  wire        s_axis_b_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_b TREADY" *)
    output wire        s_axis_b_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_b TLAST" *)
    input  wire        s_axis_b_tlast,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_b TID" *)
    input  wire [7:0]  s_axis_b_tid,

    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis TDATA" *)
    output wire [63:0] m_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis TKEEP" *)
    output wire [7:0]  m_axis_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis TVALID" *)
    output wire        m_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis TREADY" *)
    input  wire        m_axis_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis TLAST" *)
    output wire        m_axis_tlast
);
    wire rst = !resetn;
    localparam DEPTH = 1 << FIFO_AW;

    reg [63:0] now;
    always @(posedge clk) now <= rst ? 64'd0 : now + 64'd1;

    // ------------------------------------------------------------------ input side: one whole packet at a time
    reg         in_busy, in_sel;          // in_sel 1: input B
    reg  [15:0] in_words;
    reg         in_err;
    reg  [7:0]  in_tid;
    wire [FIFO_AW:0] d_used;
    wire        room   = (d_used <= DEPTH - 520);     // a whole packet of up to 512 words fits
    reg         prio_b;                   // B goes first after an A packet, so a busy link never starves it
    wire        pick_b = s_axis_b_tvalid && (prio_b || !s_axis_a_tvalid);
    wire        a_go   = !in_busy ? (room && s_axis_a_tvalid && !pick_b) : !in_sel;
    wire        b_go   = !in_busy ? (room && pick_b) : in_sel;
    wire        h_full;
    assign s_axis_a_tready = a_go && !h_full;
    assign s_axis_b_tready = b_go && !h_full;
    wire        a_beat = s_axis_a_tvalid && s_axis_a_tready;
    wire        b_beat = s_axis_b_tvalid && s_axis_b_tready;
    wire        beat   = a_beat || b_beat;
    wire        bsel   = b_beat;
    wire [63:0] bdata  = bsel ? s_axis_b_tdata : s_axis_a_tdata;
    wire        blast  = bsel ? s_axis_b_tlast : s_axis_a_tlast;
    wire [7:0]  btid   = bsel ? s_axis_b_tid   : s_axis_a_tid;
    wire        berr   = bsel ? 1'b0 : s_axis_a_tuser[0];

    reg         h_we;
    reg  [96:0] h_wd;                     // {from_b, err, tid[7:0], words[15:0], time[63:0], spare 7}
    always @(posedge clk) begin
        h_we <= 1'b0;
        if (rst) begin
            in_busy <= 1'b0; in_sel <= 1'b0; in_words <= 16'd0; in_err <= 1'b0; in_tid <= 8'd0; prio_b <= 1'b0;
        end else if (beat) begin
            if (blast) prio_b <= !bsel;
            if (!in_busy) begin
                in_busy <= !blast;
                in_sel  <= bsel;
            end else if (blast) begin
                in_busy <= 1'b0;
            end
            if (blast) begin
                h_we     <= 1'b1;
                h_wd     <= {bsel, (in_busy ? in_err : 1'b0) | berr, btid, in_busy ? in_words + 16'd1 : 16'd1, now,
                             7'd0};
                in_words <= 16'd0;
                in_err   <= 1'b0;
            end else begin
                in_words <= in_busy ? in_words + 16'd1 : 16'd1;
                in_err   <= (in_busy ? in_err : 1'b0) | berr;
                in_tid   <= btid;
            end
        end
    end

    // ------------------------------------------------------------------ the data FIFO and the header FIFO
    wire        d_rd_en;
    wire [63:0] d_rd;
    wire        d_rv;
    wire        d_full;
    kria_dsp_sfifo #(.DW(64), .AW(FIFO_AW)) u_data (
        .clk(clk), .rst(rst), .wr_en(beat), .wr_data(bdata), .full(d_full), .count(),
        .rd_en(d_rd_en), .rd_data(d_rd), .rd_valid(d_rv));
    // words written and not yet read, for the room check (the FIFO's own count lags by its two output stages)
    reg [FIFO_AW:0] d_in, d_out;
    always @(posedge clk) begin
        if (rst) begin d_in <= 0; d_out <= 0; end
        else begin
            if (beat) d_in <= d_in + 1'b1;
            if (d_rd_en && d_rv) d_out <= d_out + 1'b1;
        end
    end
    assign d_used = d_in - d_out;

    wire        h_rd_en;
    wire [96:0] h_rd;
    wire        h_rv;
    kria_dsp_sfifo #(.DW(97), .AW(6)) u_hdr (
        .clk(clk), .rst(rst), .wr_en(h_we), .wr_data(h_wd), .full(h_full), .count(),
        .rd_en(h_rd_en), .rd_data(h_rd), .rd_valid(h_rv));

    // ------------------------------------------------------------------ output side
    localparam O_IDLE = 2'd0, O_H0 = 2'd1, O_H1 = 2'd2, O_DATA = 2'd3;
    reg  [1:0]  ost;
    reg  [15:0] o_left, o_words, o_seq;
    reg  [7:0]  o_tid, o_flags;
    reg  [63:0] o_time;
    reg  [15:0] blk;                      // words sent in the current block
    reg  [31:0] idle;
    reg         flush;                    // the current packet is a flush packet

    wire        o_beat = m_axis_tvalid && m_axis_tready;
    wire        end_blk_after = (blk + 16'd1 >= BLOCK_WORDS);
    reg  [63:0] o_data;
    reg         o_valid, o_last;
    always @* begin
        o_valid = 1'b0; o_data = 64'd0; o_last = 1'b0;
        case (ost)
            O_H0: begin
                o_valid = 1'b1;
                o_data  = {8'hA5, o_tid, o_flags, 8'h00, o_words, o_seq};
            end
            O_H1: begin
                o_valid = 1'b1;
                o_data  = o_time;
                o_last  = flush;
            end
            O_DATA: begin
                o_valid = d_rv;
                o_data  = d_rd;
                o_last  = (o_left == 16'd1) && end_blk_after;
`ifdef MUTATE_FRAMER_LAST_EVERY_PACKET
                o_last  = (o_left == 16'd1);
`endif
            end
            default: ;
        endcase
    end
    assign m_axis_tvalid = o_valid;
    assign m_axis_tdata  = o_data;
    assign m_axis_tlast  = o_last;
    assign m_axis_tkeep  = 8'hFF;
    assign d_rd_en       = (ost == O_DATA) && m_axis_tready;
    assign h_rd_en       = (ost == O_IDLE) && h_rv;

    always @(posedge clk) begin
        if (rst) begin
            ost <= O_IDLE; o_left <= 0; o_words <= 0; o_seq <= 0; o_tid <= 0; o_flags <= 0; o_time <= 0;
            blk <= 0; idle <= 0; flush <= 1'b0;
        end else begin
            case (ost)
                O_IDLE: begin
                    if (h_rv) begin
                        {o_flags[1], o_flags[0], o_tid, o_words, o_time} <= h_rd[96:7];
                        o_flags[7:2] <= 6'd0;
                        o_left <= h_rd[86:71];
                        flush  <= 1'b0;
                        idle   <= 0;
                        ost    <= O_H0;
                    end else if (blk != 16'd0 && idle >= IDLE_FLUSH) begin
                        o_flags <= 8'd0; o_tid <= 8'h00; o_words <= 16'd0; o_left <= 16'd0; o_time <= now;
                        flush   <= 1'b1;
                        idle    <= 0;
                        ost     <= O_H0;
                    end else begin
                        idle <= (blk != 16'd0) ? idle + 1 : 0;
                    end
                end
                O_H0: if (o_beat) begin blk <= blk + 16'd1; ost <= O_H1; end
                O_H1: if (o_beat) begin
                    o_seq <= o_seq + 16'd1;
                    if (flush) begin blk <= 16'd0; ost <= O_IDLE; end
                    else begin blk <= blk + 16'd1; ost <= (o_left == 16'd0) ? O_IDLE : O_DATA; end
                end
                O_DATA: if (o_beat) begin
                    o_left <= o_left - 16'd1;
                    if (o_left == 16'd1) begin
                        blk <= o_last ? 16'd0 : blk + 16'd1;
                        ost <= O_IDLE;
                    end else begin
                        blk <= blk + 16'd1;
                    end
                end
            endcase
        end
    end
endmodule
