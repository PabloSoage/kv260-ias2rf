// ---------------------------------------------------------------------------
// tb_serdes7.v - 7-series (Artix-7) OSERDESE2 -> ISERDESE2 8:1 DDR loopback.
//
// Models one IAS1 link lane at 1.0 Gb/s (500 MHz DDR serial clock, 125 MHz
// parallel word clock), including a forwarded 500 MHz clock, a 3-UI channel
// bit offset, BITSLIP word alignment, and >= 10,000-bit PRBS7 verification.
//
// Mutations (via xvlog -d):
//   MUTATE_FLIP_BIT   : corrupts transmitted bit 0 every 64th word
//   MUTATE_NO_BITSLIP : suppresses BITSLIP pulses so word alignment fails
// ---------------------------------------------------------------------------

`timescale 1ns/1ps
`default_nettype none

module tb_serdes7;

    localparam integer ALIGN_CONSEC_WORDS = 16;
    localparam integer MAX_SLIP_ATTEMPTS  = 16;
    localparam integer CHECK_WORDS        = 2000; // 2000 * 8 = 16,000 bits (>= 10,000)

    // -----------------------------------------------------------------------
    // Clocks: 500 MHz DDR serial clock (2.0 ns period) and 125 MHz CLKDIV
    // -----------------------------------------------------------------------
    reg clk_500m = 1'b0;
    always #1.0 clk_500m = ~clk_500m;

    reg [1:0] div_cnt = 2'b00;
    reg       clk_125m = 1'b0;
    always @(posedge clk_500m) begin
        div_cnt <= div_cnt + 2'd1;
        if (div_cnt == 2'd1)
            clk_125m <= 1'b1;
        else if (div_cnt == 2'd3)
            clk_125m <= 1'b0;
    end

    // Reset held past glbl.GSR (100 ns); RX reset is released after TX clock runs
    reg tx_rst = 1'b1;
    reg rx_rst = 1'b1;

    // -----------------------------------------------------------------------
    // PRBS7 generator: x^7 + x^6 + 1, advancing 8 bits per clk_125m cycle
    // -----------------------------------------------------------------------
    reg [6:0] tx_lfsr = 7'h7F;
    reg [7:0] tx_word = 8'h00;
    reg [31:0] tx_word_cnt = 32'd0;

    function [14:0] prbs7_step8(input [6:0] state);
        reg [6:0] s;
        reg [7:0] bits;
        reg       fb;
        integer   k;
        begin
            s = state;
            for (k = 0; k < 8; k = k + 1) begin
                fb      = s[6] ^ s[5];
                bits[k] = fb;
                s       = {s[5:0], fb};
            end
            prbs7_step8 = {bits, s};
        end
    endfunction

    wire [14:0] tx_next = prbs7_step8(tx_lfsr);

    always @(posedge clk_125m) begin
        if (tx_rst) begin
            tx_lfsr     <= 7'h7F;
            tx_word     <= 8'h00;
            tx_word_cnt <= 32'd0;
        end else begin
            tx_lfsr     <= tx_next[6:0];
            tx_word     <= tx_next[14:7];
            tx_word_cnt <= tx_word_cnt + 32'd1;
        end
    end

`ifdef MUTATE_FLIP_BIT
    wire [7:0] tx_serdes_word = ((tx_word_cnt & 32'h3F) == 32'h3F) ? (tx_word ^ 8'h01) : tx_word;
`else
    wire [7:0] tx_serdes_word = tx_word;
`endif

    // -----------------------------------------------------------------------
    // 7-series TX: OSERDESE2 (8:1 DDR) for data and forwarded clock
    // -----------------------------------------------------------------------
    wire tx_serial_data;
    wire tx_serial_clk;

    OSERDESE2 #(
        .DATA_RATE_OQ ("DDR"),
        .DATA_RATE_TQ ("DDR"),
        .DATA_WIDTH   (8),
        .INIT_OQ      (1'b0),
        .INIT_TQ      (1'b0),
        .SERDES_MODE  ("MASTER"),
        .SRVAL_OQ     (1'b0),
        .SRVAL_TQ     (1'b0),
        .TBYTE_CTL    ("FALSE"),
        .TBYTE_SRC    ("FALSE"),
        .TRISTATE_WIDTH(1)
    ) u_oserdes_data (
        .OFB       (),
        .OQ        (tx_serial_data),
        .SHIFTOUT1 (),
        .SHIFTOUT2 (),
        .TBYTEOUT  (),
        .TFB       (),
        .TQ        (),
        .CLK       (clk_500m),
        .CLKDIV    (clk_125m),
        .D1        (tx_serdes_word[0]),
        .D2        (tx_serdes_word[1]),
        .D3        (tx_serdes_word[2]),
        .D4        (tx_serdes_word[3]),
        .D5        (tx_serdes_word[4]),
        .D6        (tx_serdes_word[5]),
        .D7        (tx_serdes_word[6]),
        .D8        (tx_serdes_word[7]),
        .OCE       (1'b1),
        .RST       (tx_rst),
        .SHIFTIN1  (1'b0),
        .SHIFTIN2  (1'b0),
        .T1        (1'b0),
        .T2        (1'b0),
        .T3        (1'b0),
        .T4        (1'b0),
        .TBYTEIN   (1'b0),
        .TCE       (1'b0)
    );

    OSERDESE2 #(
        .DATA_RATE_OQ ("DDR"),
        .DATA_RATE_TQ ("DDR"),
        .DATA_WIDTH   (8),
        .INIT_OQ      (1'b0),
        .INIT_TQ      (1'b0),
        .SERDES_MODE  ("MASTER"),
        .SRVAL_OQ     (1'b0),
        .SRVAL_TQ     (1'b0),
        .TBYTE_CTL    ("FALSE"),
        .TBYTE_SRC    ("FALSE"),
        .TRISTATE_WIDTH(1)
    ) u_oserdes_clk (
        .OFB       (),
        .OQ        (tx_serial_clk),
        .SHIFTOUT1 (),
        .SHIFTOUT2 (),
        .TBYTEOUT  (),
        .TFB       (),
        .TQ        (),
        .CLK       (clk_500m),
        .CLKDIV    (clk_125m),
        .D1        (1'b1),
        .D2        (1'b0),
        .D3        (1'b1),
        .D4        (1'b0),
        .D5        (1'b1),
        .D6        (1'b0),
        .D7        (1'b1),
        .D8        (1'b0),
        .OCE       (1'b1),
        .RST       (tx_rst),
        .SHIFTIN1  (1'b0),
        .SHIFTIN2  (1'b0),
        .T1        (1'b0),
        .T2        (1'b0),
        .T3        (1'b0),
        .T4        (1'b0),
        .TBYTEIN   (1'b0),
        .TCE       (1'b0)
    );

    // -----------------------------------------------------------------------
    // Channel model: fixed 3-UI offset so BITSLIP alignment is required, plus
    // 0.5 ns (90-degree) eye centering on the forwarded clock.
    // -----------------------------------------------------------------------
    reg [2:0] chan_sr = 3'b000;
    always @(posedge clk_500m or negedge clk_500m) begin
        chan_sr <= {chan_sr[1:0], tx_serial_data};
    end
    wire rx_serial_data = chan_sr[2];

    wire #0.5 rx_clk_p = tx_serial_clk;
    wire      rx_clk_n = ~rx_clk_p;

    // BUFR divide-by-4 model in phase with rx_clk_p
    reg [1:0] rx_div_cnt = 2'b00;
    reg       rx_clkdiv  = 1'b0;
    always @(posedge rx_clk_p) begin
        rx_div_cnt <= rx_div_cnt + 2'd1;
        if (rx_div_cnt == 2'd1)
            rx_clkdiv <= 1'b1;
        else if (rx_div_cnt == 2'd3)
            rx_clkdiv <= 1'b0;
    end

    // -----------------------------------------------------------------------
    // 7-series RX: ISERDESE2 (1:8 DDR NETWORKING)
    // -----------------------------------------------------------------------
    wire q1, q2, q3, q4, q5, q6, q7, q8;
    reg  bitslip_pulse = 1'b0;

    ISERDESE2 #(
        .DATA_RATE         ("DDR"),
        .DATA_WIDTH        (8),
        .DYN_CLKDIV_INV_EN ("FALSE"),
        .DYN_CLK_INV_EN    ("FALSE"),
        .INIT_Q1           (1'b0),
        .INIT_Q2           (1'b0),
        .INIT_Q3           (1'b0),
        .INIT_Q4           (1'b0),
        .INTERFACE_TYPE    ("NETWORKING"),
        .IOBDELAY          ("NONE"),
        .IS_CLKB_INVERTED  (1'b0),
        .IS_CLKDIVP_INVERTED(1'b0),
        .IS_CLKDIV_INVERTED(1'b0),
        .IS_CLK_INVERTED   (1'b0),
        .IS_D_INVERTED     (1'b0),
        .IS_OCLKB_INVERTED (1'b0),
        .IS_OCLK_INVERTED  (1'b0),
        .NUM_CE            (2),
        .OFB_USED          ("FALSE"),
        .SERDES_MODE       ("MASTER"),
        .SRVAL_Q1          (1'b0),
        .SRVAL_Q2          (1'b0),
        .SRVAL_Q3          (1'b0),
        .SRVAL_Q4          (1'b0)
    ) u_iserdes (
        .O            (),
        .Q1           (q1),
        .Q2           (q2),
        .Q3           (q3),
        .Q4           (q4),
        .Q5           (q5),
        .Q6           (q6),
        .Q7           (q7),
        .Q8           (q8),
        .SHIFTOUT1    (),
        .SHIFTOUT2    (),
        .BITSLIP      (bitslip_pulse),
        .CE1          (1'b1),
        .CE2          (1'b1),
        .CLK          (rx_clk_p),
        .CLKB         (rx_clk_n),
        .CLKDIV       (rx_clkdiv),
        .CLKDIVP      (1'b0),
        .D            (rx_serial_data),
        .DDLY         (1'b0),
        .DYNCLKDIVSEL (1'b0),
        .DYNCLKSEL    (1'b0),
        .OCLK         (1'b0),
        .OCLKB        (1'b0),
        .OFB          (1'b0),
        .RST          (rx_rst),
        .SHIFTIN1     (1'b0),
        .SHIFTIN2     (1'b0)
    );

    wire [7:0] rx_word = {q1, q2, q3, q4, q5, q6, q7, q8};

    // -----------------------------------------------------------------------
    // TX history FIFO in rx_clkdiv domain (sampled via clk_125m history)
    // Because rx_clkdiv is frequency-locked to clk_125m with fixed offset,
    // keep a 16-entry circular buffer written on clk_125m.
    // -----------------------------------------------------------------------
    reg [7:0] tx_hist [0:15];
    reg [3:0] tx_wr_ptr = 4'd0;
    always @(posedge clk_125m) begin
        if (tx_rst) begin
            tx_wr_ptr <= 4'd0;
        end else begin
            tx_hist[tx_wr_ptr] <= tx_word;
            tx_wr_ptr          <= tx_wr_ptr + 4'd1;
        end
    end

    function integer popcount8(input [7:0] v);
        integer k;
        begin
            popcount8 = 0;
            for (k = 0; k < 8; k = k + 1)
                popcount8 = popcount8 + v[k];
        end
    endfunction

    // -----------------------------------------------------------------------
    // Alignment & PRBS7 Verification Control
    // -----------------------------------------------------------------------
    integer i;
    integer slip_count;
    integer aligned;
    integer lat_idx;
    integer match_streak;
    integer bits_checked;
    integer bit_errors;
    integer ones_count;
    integer checks_passed;
    reg [3:0] rd_ptr;
    reg [7:0] exp_word;
    reg [7:0] diff_word;
    integer found_lat;

    initial begin
        bitslip_pulse = 1'b0;
        slip_count    = 0;
        aligned       = 0;
        lat_idx       = -1;
        bits_checked  = 0;
        bit_errors    = 0;
        ones_count    = 0;
        checks_passed = 0;
        for (i = 0; i < 16; i = i + 1)
            tx_hist[i] = 8'h00;

        // Hold reset across glbl.GSR (100 ns), release TX first so forwarded clock runs
        tx_rst = 1'b1;
        rx_rst = 1'b1;
        repeat (20) @(posedge clk_125m);
        @(negedge clk_125m);
        tx_rst = 1'b0;

        // Clock ISERDESE2 with rx_rst asserted for several CLKDIV cycles
        repeat (16) @(posedge rx_clkdiv);
        @(negedge rx_clkdiv);
        rx_rst = 1'b0;

        // Let pipeline fill
        repeat (16) @(posedge rx_clkdiv);

        // Search alignment using BITSLIP (max 16 attempts)
        for (i = 0; i < MAX_SLIP_ATTEMPTS && !aligned; i = i + 1) begin
            // Check if current rx_word matches any recent tx_hist slot
            found_lat = -1;
            for (lat_idx = 1; lat_idx <= 8; lat_idx = lat_idx + 1) begin
                rd_ptr = tx_wr_ptr - lat_idx[3:0];
                if (rx_word === tx_hist[rd_ptr]) begin
                    found_lat = lat_idx;
                end
            end

            if (found_lat != -1) begin
                // Verify consecutive matches for ALIGN_CONSEC_WORDS
                match_streak = 1;
                repeat (ALIGN_CONSEC_WORDS - 1) begin
                    @(posedge rx_clkdiv);
                    rd_ptr = tx_wr_ptr - found_lat[3:0];
                    if (rx_word === tx_hist[rd_ptr])
                        match_streak = match_streak + 1;
                end
                if (match_streak == ALIGN_CONSEC_WORDS) begin
                    aligned = 1;
                    lat_idx = found_lat;
                end
            end

            if (!aligned) begin
`ifdef MUTATE_NO_BITSLIP
                // Mutation: suppress BITSLIP pulse
                @(posedge rx_clkdiv);
                bitslip_pulse <= 1'b0;
                repeat (4) @(posedge rx_clkdiv);
`else
                @(negedge rx_clkdiv);
                bitslip_pulse = 1'b1;
                @(negedge rx_clkdiv);
                bitslip_pulse = 1'b0;
                slip_count = slip_count + 1;
                // Wait >= 3 CLKDIV cycles per UG471
                repeat (4) @(posedge rx_clkdiv);
`endif
            end
        end

        // Fallback latency index if unaligned (for mutation error counting)
        if (!aligned) begin
            lat_idx = 3;
        end

        // Run PRBS7 verification for CHECK_WORDS * 8 = 16,000 bits
        for (i = 0; i < CHECK_WORDS; i = i + 1) begin
            @(posedge rx_clkdiv);
            rd_ptr       = tx_wr_ptr - lat_idx[3:0];
            exp_word     = tx_hist[rd_ptr];
            diff_word    = rx_word ^ exp_word;
            bits_checked = bits_checked + 8;
            ones_count   = ones_count + popcount8(rx_word);
            if (diff_word !== 8'h00) begin
                bit_errors = bit_errors + popcount8(diff_word);
                if (bit_errors <= 32)
                    $display("  [ERR] word=%0d rx=0x%02x exp=0x%02x (slips=%0d)",
                             i, rx_word, exp_word, slip_count);
            end
        end

        // Self-checks
        if (aligned == 1 && slip_count > 0) checks_passed = checks_passed + 1;
        if (bits_checked >= 10000)          checks_passed = checks_passed + 1;
        if (bit_errors == 0)                checks_passed = checks_passed + 1;
        if (ones_count > 7000 && ones_count < 9000) checks_passed = checks_passed + 1;

        $display("tb_serdes7: aligned=%0d slips=%0d lat=%0d bits=%0d bit_errors=%0d ones=%0d",
                 aligned, slip_count, lat_idx, bits_checked, bit_errors, ones_count);

        if (checks_passed == 4) begin
            $display("PASS 4/4 (tb_serdes7: bits=%0d, bit_errors=%0d, slips=%0d)",
                     bits_checked, bit_errors, slip_count);
        end else begin
            $display("FAIL %0d/4 (tb_serdes7: bits=%0d, bit_errors=%0d, aligned=%0d, slips=%0d)",
                     checks_passed, bits_checked, bit_errors, aligned, slip_count);
        end
        $finish;
    end

    initial begin
        #500000;
        $display("FAIL 0/4 (tb_serdes7: TIMEOUT)");
        $finish;
    end

endmodule

`default_nettype wire
