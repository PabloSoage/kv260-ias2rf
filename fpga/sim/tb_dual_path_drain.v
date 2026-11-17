// SPDX-License-Identifier: Apache-2.0
// tb_dual_path_drain: dual_path_sf_fifo's drain input (IAS1 uplink closed after a link loss or a clock switch).
//   1. Queue bulk packets (stream 0x01/0x04) and a 0x11 read-back with the consumer stalled, raise drain:
//      every bulk packet is discarded whole, the 0x11 word comes out first once the consumer is back.
//   2. A packet whose first word the consumer already took is never cut by drain (it finishes intact).
//   3. A discard that started runs to its eop even if drain falls half-way (no headless tail on the link).
//   4. With drain low the FIFO is unchanged: every packet out, in order, with its data.
// Mutations: drain_started_pkt, drain_all_sid, drain_release, drain_no_wskip.
`timescale 1ns/1ps
`default_nettype none

module tb_dual_path_drain;
    reg clk = 1'b0;
    always #4 clk = ~clk;
    reg rst = 1'b1;

    reg         push_valid = 1'b0, push_sop = 1'b0, push_eop = 1'b0;
    reg  [7:0]  push_sid = 8'd0;
    reg  [63:0] push_data = 64'd0;
    wire        push_ready;
    reg         drain = 1'b0;
    reg         out_ready = 1'b0;
    wire        out_valid, out_sop, out_eop;
    wire [7:0]  out_sid;
    wire [15:0] out_len;
    wire [31:0] out_seq;
    wire [63:0] out_ts, out_data;

    dual_path_sf_fifo #(.DATA_ADDR_W(10), .META_ADDR_W(5)) dut (
        .clk(clk), .rst(rst),
        .push_valid(push_valid), .push_sop(push_sop), .push_eop(push_eop), .push_stream_id(push_sid),
        .push_len(16'd8), .push_seq(32'd0), .push_timestamp(64'd0), .push_data(push_data),
        .push_abort(1'b0), .push_ready(push_ready), .drain(drain),
        .out_valid(out_valid), .out_sop(out_sop), .out_eop(out_eop), .out_stream_id(out_sid),
        .out_len(out_len), .out_seq(out_seq), .out_timestamp(out_ts), .out_data(out_data),
        .out_ready(out_ready));

    integer errors = 0;
    task fail(input [8*80-1:0] msg);
        begin
            $display("FAIL: tb_dual_path_drain %0s", msg);
            errors = errors + 1;
        end
    endtask

    // Packet p, word w carries {sid, 0, p, 0, w}; a packet of n words
    task push_pkt(input [7:0] sid, input [15:0] p, input integer n);
        integer w;
        begin
            for (w = 0; w < n; w = w + 1) begin
                push_valid <= 1'b1; push_sop <= (w == 0); push_eop <= (w == n - 1); push_sid <= sid;
                push_data  <= {sid, 8'd0, p, 16'd0, w[15:0]};
                @(posedge clk);
                while (!push_ready) @(posedge clk);
            end
            push_valid <= 1'b0; push_sop <= 1'b0; push_eop <= 1'b0;
        end
    endtask

    // Output monitor: framing (sop first, words in order, eop last) and the list of packets seen
    reg  [15:0] seen_p   [0:255];
    reg  [7:0]  seen_sid [0:255];
    reg  [15:0] seen_n   [0:255];
    integer     nseen = 0;
    reg         in_pkt = 1'b0;
    reg  [15:0] cur_p = 16'd0, cur_w = 16'd0;
    always @(posedge clk) if (!rst && out_valid && out_ready) begin
        if (out_sid != out_data[63:56]) fail("header does not match its packet");
        if (out_sop) begin
            if (in_pkt) fail("sop inside a packet");
            if (out_data[15:0] != 16'd0) fail("packet does not start at its word 0");
            in_pkt <= !out_eop; cur_p <= out_data[47:32]; cur_w <= 16'd1;
            if (out_eop) begin
                seen_p[nseen] = out_data[47:32]; seen_sid[nseen] = out_sid; seen_n[nseen] = 16'd1; nseen = nseen + 1;
            end
        end else begin
            if (!in_pkt) fail("word outside a packet (headless tail)");
            else if (out_data[47:32] != cur_p || out_data[15:0] != cur_w) fail("word out of order");
            cur_w <= cur_w + 16'd1;
            if (out_eop) begin
                in_pkt <= 1'b0;
                seen_p[nseen] = cur_p; seen_sid[nseen] = out_sid; seen_n[nseen] = cur_w + 16'd1; nseen = nseen + 1;
            end
        end
    end

    integer n0;
    initial begin
        repeat (5) @(posedge clk); rst <= 1'b0; repeat (2) @(posedge clk);

        // ---- 4. drain low: plain store-and-forward ----
        out_ready <= 1'b1;
        push_pkt(8'h01, 16'd1, 64); push_pkt(8'h11, 16'd2, 1); push_pkt(8'h04, 16'd3, 5);
        repeat (100) @(posedge clk);
        if (nseen != 3 || seen_p[0] != 1 || seen_p[1] != 2 || seen_p[2] != 3 || seen_n[0] != 64 || seen_n[2] != 5)
            fail("drain low: packets lost or reordered");

        // ---- 1. link closed: bulk queued around a read-back, consumer stalled, drain high ----
        out_ready <= 1'b0; drain <= 1'b1;
        n0 = nseen;
        push_pkt(8'h01, 16'd10, 64); push_pkt(8'h04, 16'd11, 64); push_pkt(8'h11, 16'd12, 1);
        push_pkt(8'h01, 16'd13, 64); push_pkt(8'h01, 16'd14, 1);
        repeat (300) @(posedge clk);
        drain <= 1'b0; out_ready <= 1'b1;
        push_pkt(8'h01, 16'd15, 8);
        repeat (50) @(posedge clk);
        if (nseen != n0 + 2) fail("drain: wrong number of packets out (bulk not dropped, or 0x11 lost)");
        if (seen_p[n0] != 12 || seen_sid[n0] != 8'h11) fail("drain: the 0x11 read-back is not the first packet out");
        if (seen_p[n0 + 1] != 15 || seen_n[n0 + 1] != 8) fail("drain: packet sent after the link came back is lost");

        // ---- 2. packet already started: drain must not cut it ----
        n0 = nseen;
        out_ready <= 1'b0;
        push_pkt(8'h01, 16'd20, 16);
        repeat (5) @(posedge clk);
        out_ready <= 1'b1; @(posedge clk); out_ready <= 1'b0;      // the consumer takes word 0 only
        drain <= 1'b1; repeat (40) @(posedge clk);
        drain <= 1'b0; out_ready <= 1'b1; repeat (40) @(posedge clk);
        if (nseen != n0 + 1 || seen_p[n0] != 20 || seen_n[n0] != 16) fail("started packet cut by drain");

        // ---- 3. a discard that started finishes even if drain falls half-way ----
        n0 = nseen;
        out_ready <= 1'b0;
        push_pkt(8'h01, 16'd30, 200);
        repeat (3) @(posedge clk);
        drain <= 1'b1; repeat (4) @(posedge clk);                    // a few words dropped, then the link is back
        drain <= 1'b0; out_ready <= 1'b1;
        push_pkt(8'h11, 16'd31, 1);
        repeat (300) @(posedge clk);
        if (nseen != n0 + 1 || seen_p[n0] != 31) fail("discard did not run to eop, or the 0x11 behind it is lost");
        if (in_pkt) fail("left inside a packet");

        if (errors == 0) $display("PASS: tb_dual_path_drain packets_out=%0d", nseen);
        $finish;
    end

    initial begin
        #2000000;
        $display("FAIL: tb_dual_path_drain global timeout");
        $finish;
    end
endmodule
`default_nettype wire
