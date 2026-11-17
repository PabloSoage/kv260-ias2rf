// SPDX-License-Identifier: Apache-2.0
// DDC Wrapper & Link Packetizer for the XC7A50T Front-End
// Connects adc_capture (400 MSPS AD9484) -> AERIS ddc_400m_enhanced (400->100 MSPS)
// -> ddc_input_interface (18b->16b I/Q) -> optional post-decimation -> async dual-clock
// FIFO -> link_pcs_tx packet interface on link_clk.

`timescale 1ns/1ps

module ddc_wrapper #(
    parameter integer POST_DECIM = 1,          // 1 = 100 MSPS, 4 = 25 MSPS (0.8 Gb/s)
    parameter integer PKT_WORDS  = 8,          // 64-bit words per packet (2 I/Q samples each)
    parameter integer FIFO_AW    = 5,          // log2 of the CDC FIFO depth in 64-bit words (> PKT_WORDS)
    parameter [7:0]   STREAM_ID  = 8'h01,      // Radar baseband CPI stream
    parameter integer CPI_CHIRPS = 16          // chirps per CPI (kria_radar_proc DOPPLER_M)
) (
    input  wire        clk_400m,
    input  wire        clk_100m,
    input  wire        rst,
    input  wire        ddc_en,
    input  wire        reset_monitors,
    input  wire [31:0] nco_ftw_ovrd,

    // Rev08 G-8 radar framing: chirp_tog toggles (dac_radar's domain) at each chirp start; with cpi_mark_en, the
    // first sample of every CPI_CHIRPS-th chirp carries I[0] = 1 and every other sample I[0] = 0, cpi_mark_dly
    // post-decimation samples after the chirp start (the DDC's latency, so the mark lands on the sample the ADC
    // took when the chirp left)
    input  wire        chirp_tog,
    input  wire        cpi_mark_en,
    input  wire [3:0]  cpi_mark_dly,

    // AD9484 400 MSPS stream (clk_400m domain)
    input  wire [7:0]  adc_data,
    input  wire        adc_valid,

    // Baseband outputs (clk_100m domain, for debug / Pmod fallback)
    output wire signed [15:0] bb_i,
    output wire signed [15:0] bb_q,
    output wire               bb_valid,
    output wire [1:0]         ddc_status,
    output wire               mixer_saturation,
    output wire               filter_overflow,
    output wire               sync_error,

    // Packet interface toward link_pcs_tx (link_clk domain)
    input  wire        link_clk,
    input  wire        link_rst,
    input  wire [63:0] timestamp_cnt,
    output wire        pkt_valid,
    input  wire        pkt_ready,
    output wire        pkt_sop,
    output wire        pkt_eop,
    output wire [7:0]  pkt_stream_id,
    output wire [15:0] pkt_len,
    output reg  [31:0] pkt_seq,
    output reg  [63:0] pkt_timestamp,
    output wire [63:0] pkt_data,
    output reg  [23:0] dropped_cnt
);

    wire reset_n = ~rst;

    wire signed [17:0] raw_bb_i, raw_bb_q;
    wire               raw_valid_i, raw_valid_q;

    ddc_400m_enhanced u_ddc (
        .clk_400m            (clk_400m),
        .clk_100m            (clk_100m),
        .reset_n             (reset_n),
        .mixers_enable       (ddc_en),
        .adc_data            (adc_data),
        .adc_data_valid_i    (adc_valid),
        .adc_data_valid_q    (adc_valid),
        .baseband_i          (raw_bb_i),
        .baseband_q          (raw_bb_q),
        .baseband_valid_i    (raw_valid_i),
        .baseband_valid_q    (raw_valid_q),
        .ddc_status          (ddc_status),
        .ddc_diagnostics     (),
        .mixer_saturation    (mixer_saturation),
        .filter_overflow     (filter_overflow),
        .test_mode           (2'b00),
        .test_phase_inc      (16'd0),
        .force_saturation    (1'b0),
        .reset_monitors      (reset_monitors),
        .ftw_override        (nco_ftw_ovrd),
        .debug_sample_count  (),
        .debug_internal_i    (),
        .debug_internal_q    ()
    );

    wire signed [15:0] scaled_i, scaled_q;
    wire               scaled_valid;

    ddc_input_interface u_scale (
        .clk             (clk_100m),
        .reset_n         (reset_n),
        .ddc_i           (raw_bb_i),
        .ddc_q           (raw_bb_q),
        .valid_i         (raw_valid_i),
        .valid_q         (raw_valid_q),
        .adc_i           (scaled_i),
        .adc_q           (scaled_q),
        .adc_valid       (scaled_valid),
        .data_sync_error (sync_error)
    );

    wire signed [15:0] sw_i, sw_q;
`ifdef MUTATE_SWAP_IQ
    assign sw_i = scaled_q;
    assign sw_q = scaled_i;
`else
    assign sw_i = scaled_i;
    assign sw_q = scaled_q;
`endif

    // Post-decimation (clk_100m domain). By 4: two anti-alias half-bands (ddc_hb4, G-8); otherwise one sample in
    // POST_DECIM, as before.
    reg [7:0]  decim_cnt;
    reg        post_valid;
    reg signed [15:0] post_i, post_q;
    generate
        if (POST_DECIM == 4) begin : g_hb4
            wire               hb_valid;
            wire signed [15:0] hb_i, hb_q;
            ddc_hb4 u_hb4 (.clk(clk_100m), .rst(rst || !ddc_en), .in_valid(scaled_valid), .in_i(sw_i), .in_q(sw_q),
                .out_valid(hb_valid), .out_i(hb_i), .out_q(hb_q));
            always @(posedge clk_100m) begin
                decim_cnt  <= 8'd0;
                post_valid <= hb_valid && ddc_en;
                post_i     <= hb_i;
                post_q     <= hb_q;
            end
        end else begin : g_drop
            always @(posedge clk_100m) begin
                post_i <= sw_i;
                post_q <= sw_q;
                if (rst || !ddc_en) begin
                    decim_cnt  <= 8'd0;
                    post_valid <= 1'b0;
                end else if (scaled_valid) begin
                    if (decim_cnt == POST_DECIM - 1) begin
                        decim_cnt  <= 8'd0;
                        post_valid <= 1'b1;
                    end else begin
                        decim_cnt  <= decim_cnt + 8'd1;
                        post_valid <= 1'b0;
                    end
                end else begin
                    post_valid <= 1'b0;
                end
            end
        end
    endgenerate

    assign bb_i     = post_i;
    assign bb_q     = post_q;
    assign bb_valid = post_valid;

    // CPI mark (clk_100m): count chirp starts; cpi_mark_dly output samples after every CPI_CHIRPS-th one, that
    // sample's I[0] is 1
    (* ASYNC_REG = "TRUE" *) reg [2:0] chirp_s;
    reg [7:0]  chirp_n;
    reg        mark_arm;
    reg [3:0]  mark_wait;
    wire       mark_now = mark_arm && (mark_wait == 4'd0);
    always @(posedge clk_100m) begin
        if (rst || !cpi_mark_en) begin
            chirp_s   <= {3{chirp_tog}};
            chirp_n   <= 8'd0;
            mark_arm  <= 1'b0;
            mark_wait <= 4'd0;
        end else begin
            chirp_s <= {chirp_s[1:0], chirp_tog};
            if (post_valid && mark_arm) begin
                if (mark_wait == 4'd0) mark_arm  <= 1'b0;
                else                   mark_wait <= mark_wait - 4'd1;
            end
            if (chirp_s[2] ^ chirp_s[1]) begin
                chirp_n <= (chirp_n == CPI_CHIRPS - 1) ? 8'd0 : chirp_n + 8'd1;
                if (chirp_n == 8'd0) begin
                    mark_arm  <= 1'b1;
                    mark_wait <= cpi_mark_dly;
                end
            end
        end
    end
    wire [15:0] bb_i_m = cpi_mark_en ? {bb_i[15:1], mark_now} : bb_i;

    // -------------------------------------------------------------------------
    // Pack two 32-bit complex samples {Q, I} into 64-bit word -> Async FIFO
    // -------------------------------------------------------------------------
    reg        half_phase;
    reg [31:0] half_word;
    reg        wr_en_100;
    reg [63:0] wr_data_100;

    // dual-clock Gray-coded async FIFO, 2^FIFO_AW words (distributed RAM)
    localparam ADDR_W = FIFO_AW;
    localparam DEPTH  = (1 << ADDR_W);

    reg [63:0] fifo_mem [0:DEPTH-1];
    reg [ADDR_W:0] wr_ptr_bin, wr_ptr_gray;
    reg [ADDR_W:0] rd_ptr_bin, rd_ptr_gray;

    (* ASYNC_REG = "TRUE" *) reg [ADDR_W:0] rd_gray_sync1, rd_gray_sync2;
    (* ASYNC_REG = "TRUE" *) reg [ADDR_W:0] wr_gray_sync1, wr_gray_sync2;

    function [ADDR_W:0] bin2gray;
        input [ADDR_W:0] b;
        bin2gray = b ^ (b >> 1);
    endfunction

    wire [ADDR_W:0] wr_next_bin  = wr_ptr_bin + 1'b1;
    wire [ADDR_W:0] wr_next_gray = bin2gray(wr_next_bin);
    wire fifo_full = (wr_ptr_gray == {~rd_gray_sync2[ADDR_W:ADDR_W-1],
                                      rd_gray_sync2[ADDR_W-2:0]});

    reg [23:0] drop_100;
    always @(posedge clk_100m) begin
        if (rst) begin
            half_phase    <= 1'b0;
            half_word     <= 32'd0;
            wr_en_100     <= 1'b0;
            wr_data_100   <= 64'd0;
            wr_ptr_bin    <= {(ADDR_W+1){1'b0}};
            wr_ptr_gray   <= {(ADDR_W+1){1'b0}};
            rd_gray_sync1 <= {(ADDR_W+1){1'b0}};
            rd_gray_sync2 <= {(ADDR_W+1){1'b0}};
            drop_100      <= 24'd0;
        end else begin
            rd_gray_sync1 <= rd_ptr_gray;
            rd_gray_sync2 <= rd_gray_sync1;
            wr_en_100     <= 1'b0;

            if (post_valid) begin
                if (!half_phase) begin
                    half_word  <= {bb_q, bb_i_m};
                    half_phase <= 1'b1;
                end else begin
                    half_phase <= 1'b0;
                    if (!fifo_full) begin
                        fifo_mem[wr_ptr_bin[ADDR_W-1:0]] <= {bb_q, bb_i_m, half_word};
                        wr_ptr_bin  <= wr_next_bin;
                        wr_ptr_gray <= wr_next_gray;
                    end else begin
                        drop_100 <= drop_100 + 24'd1;
                    end
                end
            end
        end
    end

    // Read side in link_clk domain + store-and-forward packet framing toward link_pcs_tx
    reg  [ADDR_W:0] wr_ptr_bin_sync;
    reg  [ADDR_W:0] wr_ptr_bin_sync_r;
    integer g;
    always @* begin
        wr_ptr_bin_sync[ADDR_W] = wr_gray_sync2[ADDR_W];
        for (g = ADDR_W - 1; g >= 0; g = g - 1)
            wr_ptr_bin_sync[g] = wr_ptr_bin_sync[g + 1] ^ wr_gray_sync2[g];
    end
    wire [ADDR_W:0] fifo_fill  = wr_ptr_bin_sync_r - rd_ptr_bin;
    wire            fifo_empty = (rd_ptr_bin == wr_ptr_bin_sync_r);
    // Rev08 G-7: pkt_valid from registers. A packet starts with PKT_WORDS in the FIFO (store and forward), so it
    // cannot run empty during one: pkt_valid = pkt_active or a registered "a packet is ready" (one cycle later
    // than before), and the pointer arithmetic is out of the uplink arbiter's path to the SDR FIFOs.
    reg             pkt_avail_r;
    wire            pkt_avail  = pkt_avail_r;

    (* ASYNC_REG = "TRUE" *) reg [23:0] drop_sync1, drop_sync2;

    reg [15:0] word_idx;
    reg        pkt_active;

    assign pkt_stream_id = STREAM_ID;
    assign pkt_len       = PKT_WORDS * 16'd8;
    assign pkt_valid     = pkt_active | pkt_avail_r;
    assign pkt_sop       = (word_idx == 16'd0);
    assign pkt_eop       = pkt_valid && (word_idx == PKT_WORDS - 1);
    assign pkt_data      = fifo_mem[rd_ptr_bin[ADDR_W-1:0]];

    wire [ADDR_W:0] rd_next_bin  = rd_ptr_bin + 1'b1;
    wire [ADDR_W:0] rd_next_gray = bin2gray(rd_next_bin);

    always @(posedge link_clk) begin
        if (link_rst) begin
            rd_ptr_bin        <= {(ADDR_W+1){1'b0}};
            rd_ptr_gray       <= {(ADDR_W+1){1'b0}};
            wr_gray_sync1     <= {(ADDR_W+1){1'b0}};
            wr_gray_sync2     <= {(ADDR_W+1){1'b0}};
            wr_ptr_bin_sync_r <= {(ADDR_W+1){1'b0}};
            drop_sync1        <= 24'd0;
            drop_sync2        <= 24'd0;
            dropped_cnt       <= 24'd0;
            word_idx          <= 16'd0;
            pkt_active        <= 1'b0;
            pkt_avail_r       <= 1'b0;
            pkt_seq           <= 32'd0;
            pkt_timestamp     <= 64'd0;
        end else begin
            pkt_avail_r <= !pkt_active && !pkt_avail_r && (fifo_fill >= PKT_WORDS);
            wr_gray_sync1     <= wr_ptr_gray;
            wr_gray_sync2     <= wr_gray_sync1;
            wr_ptr_bin_sync_r <= wr_ptr_bin_sync;
            drop_sync1    <= drop_100;
            drop_sync2    <= drop_sync1;
            dropped_cnt   <= drop_sync2;

            if (!pkt_active && pkt_avail) begin
                pkt_timestamp <= timestamp_cnt;
                pkt_active    <= 1'b1;
            end

            if (pkt_valid && pkt_ready) begin
                rd_ptr_bin  <= rd_next_bin;
                rd_ptr_gray <= rd_next_gray;
                if (word_idx == PKT_WORDS - 1) begin
                    word_idx   <= 16'd0;
                    pkt_active <= 1'b0;
                    pkt_seq    <= pkt_seq + 32'd1;
                end else begin
                    word_idx <= word_idx + 16'd1;
                end
            end
        end
    end

endmodule
