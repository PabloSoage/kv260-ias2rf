// ---------------------------------------------------------------------------
// tb_serdes_us.v - UltraScale+ (Kria K26) OSERDESE3 -> ISERDESE3 8:1 DDR loopback.
//
// Models one IAS1 link lane at 1.0 Gb/s (500 MHz DDR serial clock, 125 MHz
// parallel word clock) using native UltraScale+ component-mode primitives,
// a forwarded 500 MHz clock, a 3-UI channel bit offset, fabric barrel-shifter
// bitslip alignment (ISERDESE3 has no hardware BITSLIP pin), and >= 10,000-bit
// PRBS7 verification.
//
// Mutations (via xvlog -d):
//   MUTATE_FLIP_BIT   : corrupts transmitted bit 0 every 64th word
//   MUTATE_NO_BITSLIP : suppresses bitslip steps so word alignment fails
// ---------------------------------------------------------------------------

`timescale 1ns/1ps
`default_nettype none

module tb_serdes_us;

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

    // Reset held past glbl.GSR (100 ns)
    reg rst = 1'b1;

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
        if (rst) begin
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
    // UltraScale+ TX: OSERDESE3 (8:1 DDR) for data and forwarded clock
    // -----------------------------------------------------------------------
    wire tx_serial_data;
    wire tx_serial_clk;

    OSERDESE3 #(
        .DATA_WIDTH         (8),
        .INIT               (1'b0),
        .IS_CLKDIV_INVERTED (1'b0),
        .IS_CLK_INVERTED    (1'b0),
        .IS_RST_INVERTED    (1'b0),
        .ODDR_MODE          ("FALSE"),
        .OSERDES_D_BYPASS   ("FALSE"),
        .OSERDES_T_BYPASS   ("FALSE"),
        .SIM_DEVICE         ("ULTRASCALE_PLUS"),
        .SIM_VERSION        (2.0)
    ) u_oserdes3_data (
        .OQ     (tx_serial_data),
        .T_OUT  (),
        .CLK    (clk_500m),
        .CLKDIV (clk_125m),
        .D      (tx_serdes_word),
        .RST    (rst),
        .T      (1'b0)
    );

    OSERDESE3 #(
        .DATA_WIDTH         (8),
        .INIT               (1'b0),
        .IS_CLKDIV_INVERTED (1'b0),
        .IS_CLK_INVERTED    (1'b0),
        .IS_RST_INVERTED    (1'b0),
        .ODDR_MODE          ("FALSE"),
        .OSERDES_D_BYPASS   ("FALSE"),
        .OSERDES_T_BYPASS   ("FALSE"),
        .SIM_DEVICE         ("ULTRASCALE_PLUS"),
        .SIM_VERSION        (2.0)
    ) u_oserdes3_clk (
        .OQ     (tx_serial_clk),
        .T_OUT  (),
        .CLK    (clk_500m),
        .CLKDIV (clk_125m),
        .D      (8'b10101010),
        .RST    (rst),
        .T      (1'b0)
    );

    // -----------------------------------------------------------------------
    // Channel model: fixed 3-UI offset so bitslip alignment is required, plus
    // 0.5 ns (90-degree) eye centering on the forwarded clock.
    // -----------------------------------------------------------------------
    reg [2:0] chan_sr = 3'b000;
    always @(posedge clk_500m or negedge clk_500m) begin
        chan_sr <= {chan_sr[1:0], tx_serial_data};
    end
    wire rx_serial_data = chan_sr[2];

    wire #0.5 rx_clk_p = tx_serial_clk;
    wire      rx_clk_n = ~rx_clk_p;

    // BUFGCE_DIV divide-by-4 model in phase with rx_clk_p
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
    // UltraScale+ RX: ISERDESE3 (1:8 DDR component mode, FIFO_ENABLE=FALSE)
    // -----------------------------------------------------------------------
    wire [7:0] q_raw;

    ISERDESE3 #(
        .DATA_WIDTH        (8),
        .DDR_CLK_EDGE      ("OPPOSITE_EDGE"),
        .FIFO_ENABLE       ("FALSE"),
        .FIFO_SYNC_MODE    ("FALSE"),
        .IDDR_MODE         ("FALSE"),
        .IS_CLK_B_INVERTED (1'b0),
        .IS_CLK_INVERTED   (1'b0),
        .IS_RST_INVERTED   (1'b0),
        .SIM_DEVICE        ("ULTRASCALE_PLUS"),
        .SIM_VERSION       (2.0)
    ) u_iserdes3 (
        .FIFO_EMPTY      (),
        .INTERNAL_DIVCLK (),
        .Q               (q_raw),
        .CLK             (rx_clk_p),
        .CLKDIV          (rx_clkdiv),
        .CLK_B           (rx_clk_n),
        .D               (rx_serial_data),
        .FIFO_RD_CLK     (1'b0),
        .FIFO_RD_EN      (1'b0),
        .RST             (rst)
    );

    // -----------------------------------------------------------------------
    // Fabric bitslip gearbox (UG571: ISERDESE3 has no hardware BITSLIP pin)
    // -----------------------------------------------------------------------
    reg [7:0] q_prev   = 8'h00;
    reg [2:0] slip_sel = 3'd0;
    reg       bitslip_pulse = 1'b0;

    always @(posedge rx_clkdiv) begin
        if (rst) begin
            q_prev   <= 8'h00;
            slip_sel <= 3'd0;
        end else begin
            q_prev <= q_raw;
            if (bitslip_pulse)
                slip_sel <= slip_sel + 3'd1;
        end
    end

    wire [15:0] q_window = {q_raw, q_prev};
    wire [7:0]  rx_word  = q_window[slip_sel +: 8];

    // -----------------------------------------------------------------------
    // TX history FIFO
    // -----------------------------------------------------------------------
    reg [7:0] tx_hist [0:15];
    reg [3:0] tx_wr_ptr = 4'd0;
    always @(posedge clk_125m) begin
        if (rst) begin
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

        // Hold reset across glbl.GSR (100 ns) and wait for clocks to stabilize
        rst = 1'b1;
        repeat (20) @(posedge clk_125m);
        @(negedge clk_125m);
        rst = 1'b0;

        // Let pipeline fill
        repeat (16) @(posedge rx_clkdiv);

        // Search alignment using fabric bitslip (max 16 attempts)
        for (i = 0; i < MAX_SLIP_ATTEMPTS && !aligned; i = i + 1) begin
            found_lat = -1;
            for (lat_idx = 1; lat_idx <= 8; lat_idx = lat_idx + 1) begin
                rd_ptr = tx_wr_ptr - lat_idx[3:0];
                if (rx_word === tx_hist[rd_ptr]) begin
                    found_lat = lat_idx;
                end
            end

            if (found_lat != -1) begin
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
                @(posedge rx_clkdiv);
                bitslip_pulse <= 1'b0;
                repeat (2) @(posedge rx_clkdiv);
`else
                @(negedge rx_clkdiv);
                bitslip_pulse = 1'b1;
                @(posedge rx_clkdiv);
                #1;
                bitslip_pulse = 1'b0;
                slip_count = slip_count + 1;
                repeat (2) @(posedge rx_clkdiv);
`endif
            end
        end

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

        $display("tb_serdes_us: aligned=%0d slips=%0d slip_sel=%0d lat=%0d bits=%0d bit_errors=%0d ones=%0d",
                 aligned, slip_count, slip_sel, lat_idx, bits_checked, bit_errors, ones_count);

        if (checks_passed == 4) begin
            $display("PASS 4/4 (tb_serdes_us: bits=%0d, bit_errors=%0d, slips=%0d)",
                     bits_checked, bit_errors, slip_count);
        end else begin
            $display("FAIL %0d/4 (tb_serdes_us: bits=%0d, bit_errors=%0d, aligned=%0d, slips=%0d)",
                     checks_passed, bits_checked, bit_errors, aligned, slip_count);
        end
        $finish;
    end

    initial begin
        #500000;
        $display("FAIL 0/4 (tb_serdes_us: TIMEOUT)");
        $finish;
    end

endmodule

`default_nettype wire
