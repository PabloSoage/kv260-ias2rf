// SPDX-License-Identifier: Apache-2.0
// tb_kria_ps_framer: kria_dsp_out feeding input B of kria_ps_framer, random link packets on input A, random
// backpressure on the DMA side.
//
// Checks, on the framer's output: every packet accepted at either input comes out in the order accepted, behind
// its two header words (magic, tid, flags, length, sequence; a non-decreasing time stamp), word for word; tlast
// only on a packet's last word, exactly when the block reaches BLOCK_WORDS, or on a flush packet after the idle
// time, and never on an empty block.
// Checks, on kria_dsp_out's output: audio words in order with no gap, 64 a packet, the RDS flags where the bits
// were sent, the last partial packet flushed; only the ADS-B frames with a good CRC, in order; per CPI the
// detections (at most 64, the rest counted in the summary) and the summary; a map every second CPI with every
// cell's det, bins, exponent and mantissa.
// Mutations: framer_last_every_packet (block rule), map_no_normalise (map cells).

`timescale 1ns/1ps

module tb_kria_ps_framer;
    localparam BLOCK = 1024;
    localparam FLUSH = 3000;
    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;

    integer errors = 0;
    integer seed = 12345;

    // ---------------------------------------------------------------- kria_dsp_out and its stimulus
    reg               aud_valid = 0; reg signed [15:0] aud_l = 0, aud_r = 0, aud_mono = 0;
    reg               rds_valid = 0, rds_bit = 0;
    reg               adsb_valid = 0, adsb_crc_ok = 0; reg [111:0] adsb_data = 0; reg [15:0] adsb_snr = 0;
    reg               rd_valid = 0, rd_det = 0; reg [5:0] rd_rbin = 0; reg [3:0] rd_dbin = 0; reg [31:0] rd_pwr = 0;
    reg               cpi_done = 0; reg [15:0] cpi_det_cnt = 0;
    wire [63:0] b_tdata; wire b_tvalid, b_tready, b_tlast; wire [7:0] b_tid; wire [15:0] drop_cnt;

    kria_dsp_out #(.AUD_FLUSH(32'd5000)) dut_out (
        .clk(clk), .rst(!rstn), .en(1'b1), .map_log2(4'd1),
        .aud_valid(aud_valid), .aud_l(aud_l), .aud_r(aud_r), .aud_mono(aud_mono), .pilot_locked(1'b1),
        .ctcss_det(1'b0), .rds_valid(rds_valid), .rds_bit(rds_bit),
        .adsb_valid(adsb_valid), .adsb_crc_ok(adsb_crc_ok), .adsb_data(adsb_data), .adsb_snr(adsb_snr),
        .rd_valid(rd_valid), .rd_rbin(rd_rbin), .rd_dbin(rd_dbin), .rd_pwr(rd_pwr), .rd_det(rd_det),
        .cpi_done(cpi_done), .cpi_det_cnt(cpi_det_cnt),
        .m_tdata(b_tdata), .m_tvalid(b_tvalid), .m_tready(b_tready), .m_tlast(b_tlast), .m_tid(b_tid),
        .drop_cnt(drop_cnt));

    // ---------------------------------------------------------------- input A: random link packets
    reg  [63:0] a_tdata = 0; reg a_tvalid = 0, a_tlast = 0; reg [7:0] a_tid = 0; reg a_tuser = 0;
    wire        a_tready;
    wire [63:0] m_tdata; wire [7:0] m_tkeep; wire m_tvalid, m_tlast; reg m_tready = 0;

    kria_ps_framer #(.BLOCK_WORDS(BLOCK), .FIFO_AW(12), .IDLE_FLUSH(FLUSH)) dut (
        .clk(clk), .resetn(rstn),
        .s_axis_a_tdata(a_tdata), .s_axis_a_tkeep(8'hFF), .s_axis_a_tvalid(a_tvalid), .s_axis_a_tready(a_tready),
        .s_axis_a_tlast(a_tlast), .s_axis_a_tid(a_tid), .s_axis_a_tuser(a_tuser),
        .s_axis_b_tdata(b_tdata), .s_axis_b_tvalid(b_tvalid), .s_axis_b_tready(b_tready), .s_axis_b_tlast(b_tlast),
        .s_axis_b_tid(b_tid),
        .m_axis_tdata(m_tdata), .m_axis_tkeep(m_tkeep), .m_axis_tvalid(m_tvalid), .m_axis_tready(m_tready),
        .m_axis_tlast(m_tlast));

    // ---------------------------------------------------------------- the expected packets, as accepted
    localparam NP = 4096, ND = 1 << 20;
    reg [7:0]  e_tid   [0:NP-1];
    reg [7:0]  e_flags [0:NP-1];
    reg [15:0] e_len   [0:NP-1];
    reg [19:0] e_start [0:NP-1];
    reg [63:0] e_data  [0:ND-1];
    integer n_pk = 0, n_dw = 0, cur_len = 0, cur_start = 0;
    reg     cur_open = 0, cur_err = 0;

    always @(posedge clk) if (rstn) begin
        if (a_tvalid && a_tready) begin
            if (!cur_open) begin cur_open = 1; cur_start = n_dw; cur_len = 0; cur_err = 0; end
            e_data[n_dw] = a_tdata; n_dw = n_dw + 1; cur_len = cur_len + 1; cur_err = cur_err | a_tuser;
            if (a_tlast) begin
                e_tid[n_pk] = a_tid; e_flags[n_pk] = {6'd0, 1'b0, cur_err}; e_len[n_pk] = cur_len;
                e_start[n_pk] = cur_start; n_pk = n_pk + 1; cur_open = 0;
            end
        end
        if (b_tvalid && b_tready) begin
            if (!cur_open) begin cur_open = 1; cur_start = n_dw; cur_len = 0; end
            e_data[n_dw] = b_tdata; n_dw = n_dw + 1; cur_len = cur_len + 1;
            if (b_tlast) begin
                e_tid[n_pk] = b_tid; e_flags[n_pk] = 8'h02; e_len[n_pk] = cur_len;
                e_start[n_pk] = cur_start; n_pk = n_pk + 1; cur_open = 0;
            end
        end
    end

    // ---------------------------------------------------------------- output parser
    integer o_pk = 0, o_st = 0, o_left = 0, o_idx = 0, blk = 0, n_blocks = 0, n_flush = 0, o_seq = 0;
    integer max_blk = 0;
    reg [63:0] last_time = 0;
    reg        o_isflush = 0;
    always @(posedge clk) if (rstn && m_tvalid && m_tready) begin
        blk = blk + 1;
        case (o_st)
            0: begin
                if (m_tdata[63:56] != 8'hA5) begin errors = errors + 1; $display("FAIL magic %h", m_tdata); end
                if (m_tdata[15:0] != o_seq[15:0]) begin errors = errors + 1; $display("FAIL seq %0d want %0d", m_tdata[15:0], o_seq); end
                o_seq = o_seq + 1;
                if (m_tdata[55:48] == 8'h00 && m_tdata[31:16] == 16'd0) begin
                    o_isflush = 1; n_flush = n_flush + 1;
                    if (blk == 1) begin errors = errors + 1; $display("FAIL flush of an empty block"); end
                end else begin
                    o_isflush = 0;
                    if (o_pk >= n_pk) begin errors = errors + 1; $display("FAIL packet out that never went in"); end
                    else if (m_tdata[55:48] != e_tid[o_pk] || m_tdata[47:40] != e_flags[o_pk] || m_tdata[31:16] != e_len[o_pk]) begin
                        errors = errors + 1;
                        $display("FAIL header %h, want tid %h flags %h len %0d", m_tdata, e_tid[o_pk], e_flags[o_pk], e_len[o_pk]);
                    end
                    o_left = m_tdata[31:16]; o_idx = e_start[o_pk];
                end
                if (m_tlast) begin errors = errors + 1; $display("FAIL tlast on a header"); end
                o_st = 1;
            end
            1: begin
                if (m_tdata < last_time) begin errors = errors + 1; $display("FAIL time went back"); end
                last_time = m_tdata;
                if (o_isflush) begin
                    if (!m_tlast) begin errors = errors + 1; $display("FAIL flush without tlast"); end
                    n_blocks = n_blocks + 1; if (blk > max_blk) max_blk = blk; blk = 0; o_st = 0;
                end else begin
                    if (m_tlast) begin errors = errors + 1; $display("FAIL tlast on the time word"); end
                    o_st = 2;
                end
            end
            2: begin
                if (m_tdata !== e_data[o_idx]) begin
                    errors = errors + 1;
                    if (errors < 10) $display("FAIL data pkt %0d word %0d: %h want %h", o_pk, o_idx - e_start[o_pk], m_tdata, e_data[o_idx]);
                end
                o_idx = o_idx + 1; o_left = o_left - 1;
                if (o_left == 0) begin
                    if (m_tlast != (blk >= BLOCK)) begin
                        errors = errors + 1;
                        if (errors < 10) $display("FAIL tlast %0d with the block at %0d words", m_tlast, blk);
                    end
                    if (m_tlast) begin n_blocks = n_blocks + 1; if (blk > max_blk) max_blk = blk; blk = 0; end
                    o_pk = o_pk + 1; o_st = 0;
                end else if (m_tlast) begin
                    errors = errors + 1; $display("FAIL tlast inside a packet");
                end
            end
        endcase
    end

    // ---------------------------------------------------------------- kria_dsp_out semantic checks (input B)
    integer b_word = 0, aud_next = 0, aud_pk_len = 0, n_aud_pk = 0, ads_next = 0, ads_w = 0, n_ads_out = 0;
    integer cpi_seen = 0, det_i = 0, n_det_pk = 0, n_map = 0, map_w = 0;
    reg [111:0] ads_sent [0:255]; integer n_ads_sent = 0;
    reg [63:0]  ads_w0;
    // radar truth, per CPI
    reg [31:0] r_pwr [0:7][0:1023];
    reg        r_det [0:7][0:1023];
    integer    r_ndet [0:7];
    integer    map_cpi = 0;

    function [31:0] want_cell;
        input integer c, idx;
        integer k; reg [4:0] e; reg [31:0] p, sh;
        begin
            p = r_pwr[c][idx]; e = 0;
            for (k = 0; k < 32; k = k + 1) if (p[k]) e = k;
            sh = p << (31 - e);
            want_cell = {r_det[c][idx], idx[9:6], idx[5:0], e, sh[30:15]};
        end
    endfunction

    integer kk;
    reg [31:0] cl;
    always @(posedge clk) if (rstn && b_tvalid && b_tready) begin
        case (b_tid)
            8'h20: begin
                if (b_tdata[15:0] != aud_next[15:0] || b_tdata[31:16] != (-aud_next & 16'hFFFF)) begin
                    errors = errors + 1; if (errors < 10) $display("FAIL audio word %h, want sample %0d", b_tdata, aud_next);
                end
                if (b_tdata[50] != (aud_next % 7 == 0) || ((aud_next % 7 == 0) && b_tdata[51] != aud_next[3])) begin
                    errors = errors + 1; if (errors < 10) $display("FAIL RDS flags on sample %0d: %h", aud_next, b_tdata[63:48]);
                end
                aud_next = aud_next + 1; aud_pk_len = aud_pk_len + 1;
                if (b_tlast) begin
                    n_aud_pk = n_aud_pk + 1;
                    if (aud_pk_len != 64 && aud_next != 3000) begin errors = errors + 1; $display("FAIL audio packet of %0d words", aud_pk_len); end
                    aud_pk_len = 0;
                end
            end
            8'h21: begin
                if (ads_w == 0) begin ads_w0 = b_tdata; ads_w = 1; if (b_tlast) begin errors = errors + 1; $display("FAIL ADS-B packet of 1 word"); end end
                else begin
                    ads_w = 0; n_ads_out = n_ads_out + 1;
                    if (!b_tlast || {ads_w0, b_tdata[63:16]} != ads_sent[ads_next] || b_tdata[15:0] != ads_next[15:0]) begin
                        errors = errors + 1; $display("FAIL ADS-B frame %0d", ads_next);
                    end
                    ads_next = ads_next + 1;
                end
            end
            8'h22: begin
                if (b_tlast) begin
                    n_det_pk = n_det_pk + 1;
                    if (b_tdata[63:56] != 8'hFF || b_tdata[55:40] != cpi_seen[15:0] || b_tdata[39:24] != r_ndet[cpi_seen % 8][15:0]
                        || b_tdata[23:16] != ((r_ndet[cpi_seen % 8] > 64) ? r_ndet[cpi_seen % 8] - 64 : 0) || det_i != ((r_ndet[cpi_seen % 8] > 64) ? 64 : r_ndet[cpi_seen % 8])) begin
                        errors = errors + 1; $display("FAIL radar summary CPI %0d: %h, %0d detections out", cpi_seen, b_tdata, det_i);
                    end
                    cpi_seen = cpi_seen + 1; det_i = 0;
                end else begin
                    // the det_i-th detection of this CPI
                    begin : find
                        integer c, n;
                        c = cpi_seen % 8; n = 0;
                        for (kk = 0; kk < 1024; kk = kk + 1)
                            if (r_det[c][kk]) begin
                                if (n == det_i && (b_tdata[63:32] != r_pwr[c][kk] || b_tdata[5:0] != kk[5:0] || b_tdata[11:8] != kk[9:6]
                                                  || b_tdata[31:16] != cpi_seen[15:0])) begin
                                    errors = errors + 1; $display("FAIL detection %0d of CPI %0d: %h", det_i, cpi_seen, b_tdata);
                                end
                                n = n + 1;
                            end
                    end
                    det_i = det_i + 1;
                end
            end
            8'h23: begin
                cl = want_cell(map_cpi % 8, 2 * map_w);
                if (b_tdata[31:0] != cl) begin errors = errors + 1; if (errors < 10) $display("FAIL map cell %0d: %h want %h", 2 * map_w, b_tdata[31:0], cl); end
                cl = want_cell(map_cpi % 8, 2 * map_w + 1);
                if (b_tdata[63:32] != cl) begin errors = errors + 1; if (errors < 10) $display("FAIL map cell %0d: %h want %h", 2 * map_w + 1, b_tdata[63:32], cl); end
                map_w = map_w + 1;
                if (b_tlast) begin
                    if (map_w != 512) begin errors = errors + 1; $display("FAIL map of %0d words", map_w); end
                    n_map = n_map + 1; map_w = 0; map_cpi = map_cpi + 2;
                end
            end
            default: begin errors = errors + 1; $display("FAIL unknown tid %h from kria_dsp_out", b_tid); end
        endcase
    end

    // ---------------------------------------------------------------- stimulus
    integer i, k, len, cyc;
    initial begin
        repeat (20) @(posedge clk);
        rstn = 1;
    end
    // DMA side: random readiness
    always @(posedge clk) m_tready <= ($random(seed) % 4) != 0;

    // input A: 600 packets of random length with random gaps
    initial begin : drive_a
        integer p, w;
        @(posedge rstn);
        for (p = 0; p < 600; p = p + 1) begin
            len = 1 + ({$random(seed)} % 512);
            for (w = 0; w < len; w = w + 1) begin
                a_tvalid <= 1; a_tdata <= {$random(seed), $random(seed)}; a_tlast <= (w == len - 1);
                a_tid <= (p % 3 == 0) ? 8'h01 : (p % 3 == 1) ? 8'h05 : 8'h11; a_tuser <= (p % 17 == 3) && (w == len - 1);
                @(posedge clk);
                while (!a_tready) @(posedge clk);
                if ({$random(seed)} % 8 == 0) begin a_tvalid <= 0; repeat ({$random(seed)} % 20) @(posedge clk); end
            end
            a_tvalid <= 0;
            if (p == 300) repeat (20000) @(posedge clk);       // a quiet spell: the flush
            else repeat ({$random(seed)} % 200) @(posedge clk);
        end
        a_tvalid <= 0;
    end

    // audio: 3000 samples, one every 60 clocks, an RDS bit with every 7th
    initial begin : drive_aud
        integer s;
        @(posedge rstn);
        for (s = 0; s < 3000; s = s + 1) begin
            repeat (59) @(posedge clk);
            aud_valid <= 1; aud_l <= s; aud_r <= -s; aud_mono <= s ^ 16'h5555;
            rds_valid <= (s % 7 == 0); rds_bit <= s[3];
            @(posedge clk);
            aud_valid <= 0; rds_valid <= 0;
        end
    end

    // ADS-B: 200 frames, every 1500 clocks, a third with a bad CRC
    initial begin : drive_ads
        integer f;
        @(posedge rstn);
        for (f = 0; f < 200; f = f + 1) begin
            repeat (1500) @(posedge clk);
            adsb_valid <= 1; adsb_crc_ok <= (f % 3 != 1);
            adsb_data <= {$random(seed), $random(seed), $random(seed), $random(seed)};
            adsb_snr <= n_ads_sent;
            @(posedge clk);
            if (adsb_crc_ok) begin ads_sent[n_ads_sent] = adsb_data; n_ads_sent = n_ads_sent + 1; end
            adsb_valid <= 0;
        end
    end

    // radar: 12 CPIs of 1024 cells, every 15000 clocks; CPI 5 has 70 detections
    initial begin : drive_radar
        integer c, x, nd;
        @(posedge rstn);
        for (c = 0; c < 12; c = c + 1) begin
            repeat (15000) @(posedge clk);
            nd = 0;
            for (x = 0; x < 1024; x = x + 1) begin
                r_pwr[c % 8][x] = (x == 7) ? 32'd0 : ({$random(seed)} >> ({$random(seed)} % 31));
                r_det[c % 8][x] = (c == 5) ? (x < 70) : ({$random(seed)} % 40 == 0);
                if (r_det[c % 8][x]) nd = nd + 1;
            end
            r_ndet[c % 8] = nd;
            for (x = 0; x < 1024; x = x + 1) begin
                rd_valid <= 1; rd_rbin <= x[5:0]; rd_dbin <= x[9:6]; rd_pwr <= r_pwr[c % 8][x]; rd_det <= r_det[c % 8][x];
                cpi_done <= (x == 1023); cpi_det_cnt <= nd;
                @(posedge clk);
            end
            rd_valid <= 0; cpi_done <= 0;
        end
    end

    initial begin
        #(6000000);
        $display("framer: %0d packets in, %0d out, %0d blocks (largest %0d words), %0d flushes", n_pk, o_pk, n_blocks, max_blk, n_flush);
        $display("dsp_out: %0d audio samples in %0d packets, %0d ADS-B frames of %0d sent, %0d CPI summaries, %0d maps, drop_cnt %0d",
                 aud_next, n_aud_pk, n_ads_out, n_ads_sent, n_det_pk, n_map, drop_cnt);
        if (o_pk != n_pk || n_pk < 600) begin errors = errors + 1; $display("FAIL %0d packets in, %0d out", n_pk, o_pk); end
        if (n_flush == 0) begin errors = errors + 1; $display("FAIL no flush packet"); end
        if (aud_next != 3000 || n_ads_out != n_ads_sent || n_det_pk != 12 || n_map != 6) begin
            errors = errors + 1; $display("FAIL kria_dsp_out counts");
        end
        if (max_blk > BLOCK + 514) begin errors = errors + 1; $display("FAIL a block of %0d words", max_blk); end
        if (errors == 0) $display("PASS tb_kria_ps_framer");
        else $display("FAIL tb_kria_ps_framer: %0d errors", errors);
        $finish;
    end
endmodule
