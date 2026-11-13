// SPDX-License-Identifier: BSD-2-Clause
// SGMII 1.25 Gb/s Over LVDS Feasibility Proof on XC7A50T-FTG256-2
//
// Implements:
//   1) sgmii_lvds_rx  - XAPP523-style receiver on M16/N16 (Bank 14 LVDS_25,
//      DIFF_TERM=FALSE): IBUFDS_DIFF_OUT -> 2x IDELAYE2 (VAR_LOAD, 200 MHz
//      IODELAY_GROUP="bank14_idelay_grp") -> 2x ISERDESE2 (DDR 4:1 at 625 MHz
//      with 0 deg and 90 deg clocks) -> dynamic shadow-channel guardband probe,
//      phase handover with +1/-1 bit slip compensation, 10b K28.5 aligner,
//      elastic async FIFO (312.5 MHz -> 125 MHz), and PRBS-7 checker.
//   2) sgmii_lvds_test - Top-level implementation wrapper targeting
//      xc7a50t-ftg256-2 with Bank 14 IDELAYCTRL (200 MHz) and Bank 34 L4/M4
//      OSERDESE2 1.25 Gb/s transmitter.

`timescale 1ns/1ps
`default_nettype none

module sgmii_lvds_rx #(
    parameter [0:0] DIFF_TERM_EN = 1'b0  // FALSE on Bank 14 (3.3 V VCCO, ext 100 ohm R1209)
) (
    input  wire        sgmii_rx_p,
    input  wire        sgmii_rx_n,
    input  wire        clk_625_0,
    input  wire        clk_625_90,
    input  wire        clk_312p5,
    input  wire        clk_312p5_45,
    input  wire        clk_125,
    input  wire        rst_312p5,
    input  wire        rst_125,
    output reg  [9:0]  rx_code_125,
    output reg         rx_valid_125,
    output reg         rx_comma_aligned,
    output reg         rx_prbs_locked,
    output reg  [31:0] rx_prbs_err_cnt,
    output wire        phase_sel_mon,
    output reg  [31:0] phase_switch_cnt
);

    // K28.5 commas in LSB-first 10b serial order (a..j -> bit[0]..bit[9])
    localparam [9:0] K28_5_RD_NEG = 10'h17C; // 10'b0101_1111_00 (a..j = 0011111010)
    localparam [9:0] K28_5_RD_POS = 10'h283; // 10'b1010_0000_11 (a..j = 1100000101)

    // Guardband monitor taps at 200 MHz REFCLK (~78.125 ps/tap):
    //   tap 3 = ~234 ps (400 - 234 = 166 ps guardband after active edge)
    //   tap 7 = ~546 ps (400 - 546 = -146 ps guardband before active edge)
    localparam [4:0] TAP_CENTER = 5'd0;
    localparam [4:0] TAP_RIGHT  = 5'd3;
    localparam [4:0] TAP_LEFT   = 5'd7;
    localparam [4:0] SETTLE_CYC = 5'd6;
    localparam [4:0] PROBE_CYC  = 5'd15;

    // -------------------------------------------------------------------------
    // 1. Differential Input + Dual IDELAYE2 + Dual 625 MHz DDR ISERDESE2
    // -------------------------------------------------------------------------
    wire rx_p_ibuf, rx_n_ibuf;
    wire rx_p_dly,  rx_n_dly;

    IBUFDS_DIFF_OUT #(
        .DIFF_TERM  (DIFF_TERM_EN ? "TRUE" : "FALSE"),
        .IOSTANDARD ("LVDS_25")
    ) u_ibuf_diff (
        .I  (sgmii_rx_p),
        .IB (sgmii_rx_n),
        .O  (rx_p_ibuf),
        .OB (rx_n_ibuf)
    );

    reg  [4:0] tap_p_r = TAP_CENTER;
    reg  [4:0] tap_n_r = TAP_CENTER;
    reg        ld_p_r  = 1'b0;
    reg        ld_n_r  = 1'b0;

    (* IODELAY_GROUP = "bank14_idelay_grp" *)
    IDELAYE2 #(
        .CINVCTRL_SEL          ("FALSE"),
        .DELAY_SRC             ("IDATAIN"),
        .HIGH_PERFORMANCE_MODE ("TRUE"),
        .IDELAY_TYPE           ("VAR_LOAD"),
        .IDELAY_VALUE          (0),
        .PIPE_SEL              ("FALSE"),
        .REFCLK_FREQUENCY      (200.0),
        .SIGNAL_PATTERN        ("DATA")
    ) u_idelay_p (
        .CNTVALUEOUT (),
        .DATAOUT     (rx_p_dly),
        .C           (clk_312p5),
        .CE          (1'b0),
        .CINVCTRL    (1'b0),
        .CNTVALUEIN  (tap_p_r),
        .DATAIN      (1'b0),
        .IDATAIN     (rx_p_ibuf),
        .INC         (1'b0),
        .LD          (ld_p_r),
        .LDPIPEEN    (1'b0),
        .REGRST      (rst_312p5)
    );

    (* IODELAY_GROUP = "bank14_idelay_grp" *)
    IDELAYE2 #(
        .CINVCTRL_SEL          ("FALSE"),
        .DELAY_SRC             ("IDATAIN"),
        .HIGH_PERFORMANCE_MODE ("TRUE"),
        .IDELAY_TYPE           ("VAR_LOAD"),
        .IDELAY_VALUE          (0),
        .PIPE_SEL              ("FALSE"),
        .REFCLK_FREQUENCY      (200.0),
        .SIGNAL_PATTERN        ("DATA")
    ) u_idelay_n (
        .CNTVALUEOUT (),
        .DATAOUT     (rx_n_dly),
        .C           (clk_312p5),
        .CE          (1'b0),
        .CINVCTRL    (1'b0),
        .CNTVALUEIN  (tap_n_r),
        .DATAIN      (1'b0),
        .IDATAIN     (rx_n_ibuf),
        .INC         (1'b0),
        .LD          (ld_n_r),
        .LDPIPEEN    (1'b0),
        .REGRST      (rst_312p5)
    );

    wire qp1, qp2, qp3, qp4;
    wire qn1, qn2, qn3, qn4;

    // Master ISERDESE2 on P leg: 0 deg 625 MHz DDR (0, 800, 1600, 2400 ps)
    ISERDESE2 #(
        .DATA_RATE          ("DDR"),
        .DATA_WIDTH         (4),
        .DYN_CLKDIV_INV_EN  ("FALSE"),
        .DYN_CLK_INV_EN     ("FALSE"),
        .INIT_Q1            (1'b0),
        .INIT_Q2            (1'b0),
        .INIT_Q3            (1'b0),
        .INIT_Q4            (1'b0),
        .INTERFACE_TYPE     ("NETWORKING"),
        .IOBDELAY           ("IFD"),
        .IS_CLKB_INVERTED   (1'b1),
        .IS_CLKDIVP_INVERTED(1'b0),
        .IS_CLKDIV_INVERTED (1'b0),
        .IS_CLK_INVERTED    (1'b0),
        .IS_D_INVERTED      (1'b0),
        .IS_OCLKB_INVERTED  (1'b0),
        .IS_OCLK_INVERTED   (1'b0),
        .NUM_CE             (1),
        .OFB_USED           ("FALSE"),
        .SERDES_MODE        ("MASTER"),
        .SRVAL_Q1           (1'b0),
        .SRVAL_Q2           (1'b0),
        .SRVAL_Q3           (1'b0),
        .SRVAL_Q4           (1'b0)
    ) u_iserdes_p (
        .O            (),
        .Q1           (qp1),
        .Q2           (qp2),
        .Q3           (qp3),
        .Q4           (qp4),
        .Q5           (),
        .Q6           (),
        .Q7           (),
        .Q8           (),
        .SHIFTOUT1    (),
        .SHIFTOUT2    (),
        .BITSLIP      (1'b0),
        .CE1          (1'b1),
        .CE2          (1'b1),
        .CLK          (clk_625_0),
        .CLKB         (clk_625_0),
        .CLKDIV       (clk_312p5),
        .CLKDIVP      (1'b0),
        .D            (1'b0),
        .DDLY         (rx_p_dly),
        .DYNCLKDIVSEL (1'b0),
        .DYNCLKSEL    (1'b0),
        .OCLK         (1'b0),
        .OCLKB        (1'b0),
        .OFB          (1'b0),
        .RST          (rst_312p5),
        .SHIFTIN1     (1'b0),
        .SHIFTIN2     (1'b0)
    );

    // Slave ISERDESE2 on N leg: 90 deg 625 MHz DDR (+400, +1200, +2000, +2800 ps)
    // CLKDIV uses phase-aligned clk_312p5_45 (+400 ps) for clean internal retiming.
    (* ASYNC_REG = "TRUE" *) reg [1:0] rst_312p5_45_sync = 2'b11;
    always @(posedge clk_312p5_45 or posedge rst_312p5) begin
        if (rst_312p5) begin
            rst_312p5_45_sync <= 2'b11;
        end else begin
            rst_312p5_45_sync <= {rst_312p5_45_sync[0], 1'b0};
        end
    end

    ISERDESE2 #(
        .DATA_RATE          ("DDR"),
        .DATA_WIDTH         (4),
        .DYN_CLKDIV_INV_EN  ("FALSE"),
        .DYN_CLK_INV_EN     ("FALSE"),
        .INIT_Q1            (1'b0),
        .INIT_Q2            (1'b0),
        .INIT_Q3            (1'b0),
        .INIT_Q4            (1'b0),
        .INTERFACE_TYPE     ("NETWORKING"),
        .IOBDELAY           ("IFD"),
        .IS_CLKB_INVERTED   (1'b1),
        .IS_CLKDIVP_INVERTED(1'b0),
        .IS_CLKDIV_INVERTED (1'b0),
        .IS_CLK_INVERTED    (1'b0),
        .IS_D_INVERTED      (1'b0),
        .IS_OCLKB_INVERTED  (1'b0),
        .IS_OCLK_INVERTED   (1'b0),
        .NUM_CE             (1),
        .OFB_USED           ("FALSE"),
        .SERDES_MODE        ("MASTER"),
        .SRVAL_Q1           (1'b0),
        .SRVAL_Q2           (1'b0),
        .SRVAL_Q3           (1'b0),
        .SRVAL_Q4           (1'b0)
    ) u_iserdes_n (
        .O            (),
        .Q1           (qn1),
        .Q2           (qn2),
        .Q3           (qn3),
        .Q4           (qn4),
        .Q5           (),
        .Q6           (),
        .Q7           (),
        .Q8           (),
        .SHIFTOUT1    (),
        .SHIFTOUT2    (),
        .BITSLIP      (1'b0),
        .CE1          (1'b1),
        .CE2          (1'b1),
        .CLK          (clk_625_90),
        .CLKB         (clk_625_90),
        .CLKDIV       (clk_312p5_45),
        .CLKDIVP      (1'b0),
        .D            (1'b0),
        .DDLY         (rx_n_dly),
        .DYNCLKDIVSEL (1'b0),
        .DYNCLKSEL    (1'b0),
        .OCLK         (1'b0),
        .OCLKB        (1'b0),
        .OFB          (1'b0),
        .RST          (rst_312p5_45_sync[1]),
        .SHIFTIN1     (1'b0),
        .SHIFTIN2     (1'b0)
    );

    // Register P and N nibbles into clk_312p5 (0 deg) domain; index [0] = oldest bit.
    // N leg from IBUFDS_DIFF_OUT.OB is inverted back to positive polarity.
    reg [3:0] p_vec;
    reg [3:0] n_vec;
    reg       prev_n3;

    always @(posedge clk_312p5) begin
        if (rst_312p5) begin
            p_vec   <= 4'd0;
            n_vec   <= 4'd0;
            prev_n3 <= 1'b0;
        end else begin
            p_vec   <= {qp1, qp2, qp3, qp4};
            n_vec   <= {~qn1, ~qn2, ~qn3, ~qn4};
            prev_n3 <= n_vec[3];
        end
    end

    // -------------------------------------------------------------------------
    // 2. Shadow-Channel Guardband Eye Monitor & Slip-Compensated Phase Selector
    // -------------------------------------------------------------------------
    localparam [2:0] ST_INIT_LOAD   = 3'd0;
    localparam [2:0] ST_MON_RIGHT   = 3'd1;
    localparam [2:0] ST_MON_LEFT    = 3'd2;
    localparam [2:0] ST_SW_SETTLE   = 3'd3;
    localparam [2:0] ST_SW_DO       = 3'd4;

    reg [2:0] mon_state;
    reg [4:0] mon_timer;
    reg [4:0] hit_cnt;
    reg       init_done;
    reg       probe_is_right; // 1 => TAP_RIGHT (234 ps, +ppm guard), 0 => TAP_LEFT (546 ps, -ppm guard)
    reg       handover_plus_ppm;
    reg       phase_sel;      // 0 => active P (0 deg), 1 => active N (90 deg)

    // Mismatch detectors between active sampler and idle guardband sampler:
    //   When phase_sel == 0 (P active):
    //     probe_is_right (N tap=3, +166 ps after P): compare P[3:0] vs N[3:0]
    //     probe_is_left  (N tap=7, -146 ps before P): compare P[3:1] vs N[3:1]
    //   When phase_sel == 1 (N active):
    //     probe_is_right (P tap=3, +166 ps after N): compare N[2:0] vs P[3:1]
    //     probe_is_left  (P tap=7, -146 ps before N): compare N[2:0] vs P[3:1]
    wire edge_on_p_right = |(p_vec ^ n_vec);
    wire edge_on_p_left  = |(p_vec[3:1] ^ n_vec[3:1]);
    wire edge_on_n_right = |(n_vec[2:0] ^ p_vec[3:1]);
    wire edge_on_n_left  = |(n_vec[2:0] ^ p_vec[3:1]);

    wire probe_edge_hit = (phase_sel == 1'b0)
                          ? (probe_is_right ? edge_on_p_right : edge_on_p_left)
                          : (probe_is_right ? edge_on_n_right : edge_on_n_left);

    reg [4:0] out_bits;
    reg [2:0] out_nbits;

    assign phase_sel_mon = phase_sel;

    always @(posedge clk_312p5) begin
        if (rst_312p5) begin
            mon_state         <= ST_INIT_LOAD;
            mon_timer         <= 5'd0;
            hit_cnt           <= 5'd0;
            init_done         <= 1'b0;
            probe_is_right    <= 1'b1;
            handover_plus_ppm <= 1'b0;
            phase_sel         <= 1'b0;
            tap_p_r           <= TAP_CENTER;
            tap_n_r           <= TAP_CENTER;
            ld_p_r            <= 1'b1;
            ld_n_r            <= 1'b1;
            out_bits          <= 5'd0;
            out_nbits         <= 3'd0;
            phase_switch_cnt  <= 32'd0;
        end else begin
            ld_p_r <= 1'b0;
            ld_n_r <= 1'b0;

`ifdef MUTATE_NO_PHASE_SELECT
            // Mutation: freeze phase_sel at 0 without oversampling tracking
            phase_sel <= 1'b0;
            tap_p_r   <= TAP_CENTER;
            tap_n_r   <= TAP_CENTER;
            out_bits  <= {1'b0, p_vec};
            out_nbits <= 3'd4;
`else
            case (mon_state)
                ST_INIT_LOAD: begin
                    // Always emit current active bits after initial reset settles
                    if (!init_done) begin
                        out_bits  <= 5'd0;
                        out_nbits <= 3'd0;
                    end else begin
                        out_bits  <= phase_sel ? {1'b0, n_vec} : {1'b0, p_vec};
                        out_nbits <= 3'd4;
                    end

                    if (mon_timer < SETTLE_CYC) begin
                        mon_timer <= mon_timer + 5'd1;
                    end else begin
                        // Start monitoring right guardband on idle channel
                        probe_is_right <= 1'b1;
                        hit_cnt        <= 5'd0;
                        mon_timer      <= 5'd0;
                        if (phase_sel == 1'b0) begin
                            tap_n_r <= TAP_RIGHT;
                            ld_n_r  <= 1'b1;
                        end else begin
                            tap_p_r <= TAP_RIGHT;
                            ld_p_r  <= 1'b1;
                        end
                        mon_state <= ST_MON_RIGHT;
                    end
                end

                ST_MON_RIGHT: begin
                    out_bits  <= phase_sel ? {1'b0, n_vec} : {1'b0, p_vec};
                    out_nbits <= 3'd4;

                    if (mon_timer < SETTLE_CYC) begin
                        mon_timer <= mon_timer + 5'd1;
                    end else if (mon_timer < (SETTLE_CYC + PROBE_CYC)) begin
                        mon_timer <= mon_timer + 5'd1;
                        if (probe_edge_hit && hit_cnt != 5'h1F)
                            hit_cnt <= hit_cnt + 5'd1;
                    end else begin
                        if (hit_cnt >= 5'd2) begin
                            // Active phase edge approached from right (+ppm): prepare clean handover
                            handover_plus_ppm <= 1'b1;
                            if (phase_sel == 1'b0) begin
                                tap_n_r <= TAP_CENTER;
                                ld_n_r  <= 1'b1;
                            end else begin
                                tap_p_r <= TAP_CENTER;
                                ld_p_r  <= 1'b1;
                            end
                            mon_timer <= 5'd0;
                            mon_state <= ST_SW_SETTLE;
                        end else begin
                            // Switch idle channel to check left guardband (-ppm)
                            probe_is_right <= 1'b0;
                            hit_cnt        <= 5'd0;
                            mon_timer      <= 5'd0;
                            if (phase_sel == 1'b0) begin
                                tap_n_r <= TAP_LEFT;
                                ld_n_r  <= 1'b1;
                            end else begin
                                tap_p_r <= TAP_LEFT;
                                ld_p_r  <= 1'b1;
                            end
                            mon_state <= ST_MON_LEFT;
                        end
                    end
                end

                ST_MON_LEFT: begin
                    out_bits  <= phase_sel ? {1'b0, n_vec} : {1'b0, p_vec};
                    out_nbits <= 3'd4;

                    if (mon_timer < SETTLE_CYC) begin
                        mon_timer <= mon_timer + 5'd1;
                    end else if (mon_timer < (SETTLE_CYC + PROBE_CYC)) begin
                        mon_timer <= mon_timer + 5'd1;
                        if (probe_edge_hit && hit_cnt != 5'h1F)
                            hit_cnt <= hit_cnt + 5'd1;
                    end else begin
                        init_done <= 1'b1;
                        if (hit_cnt >= 5'd2) begin
                            // Active phase edge approached from left (-ppm): prepare clean handover
                            handover_plus_ppm <= 1'b0;
                            if (phase_sel == 1'b0) begin
                                tap_n_r <= TAP_CENTER;
                                ld_n_r  <= 1'b1;
                            end else begin
                                tap_p_r <= TAP_CENTER;
                                ld_p_r  <= 1'b1;
                            end
                            mon_timer <= 5'd0;
                            mon_state <= ST_SW_SETTLE;
                        end else begin
                            // Neither guardband reached: alternate back to right guardband
                            probe_is_right <= 1'b1;
                            hit_cnt        <= 5'd0;
                            mon_timer      <= 5'd0;
                            if (phase_sel == 1'b0) begin
                                tap_n_r <= TAP_RIGHT;
                                ld_n_r  <= 1'b1;
                            end else begin
                                tap_p_r <= TAP_RIGHT;
                                ld_p_r  <= 1'b1;
                            end
                            mon_state <= ST_MON_RIGHT;
                        end
                    end
                end

                ST_SW_SETTLE: begin
                    // Continue emitting from active phase while newly centered idle channel flushes
                    out_bits  <= phase_sel ? {1'b0, n_vec} : {1'b0, p_vec};
                    out_nbits <= 3'd4;
                    if (mon_timer < SETTLE_CYC) begin
                        mon_timer <= mon_timer + 5'd1;
                    end else begin
                        mon_state <= ST_SW_DO;
                    end
                end

                ST_SW_DO: begin
                    init_done        <= 1'b1;
                    phase_sel        <= ~phase_sel;
                    phase_switch_cnt <= phase_switch_cnt + 32'd1;

                    // Handover bit count preserves continuity without loss or duplication:
                    //   P -> N (+ppm): {n3, n2, n1, n0, prev_n3} = 5 bits (oldest in LSB)
                    //   P -> N (-ppm): {1'b0, n3, n2, n1, n0}   = 4 bits
                    //   N -> P (+ppm): {1'b0, p3, p2, p1, p0}   = 4 bits
                    //   N -> P (-ppm): {2'b0, p3, p2, p1}       = 3 bits
                    if (phase_sel == 1'b0) begin
                        if (handover_plus_ppm) begin
                            out_bits  <= {n_vec, prev_n3};
                            out_nbits <= 3'd5;
                        end else begin
                            out_bits  <= {1'b0, n_vec};
                            out_nbits <= 3'd4;
                        end
                    end else begin
                        if (handover_plus_ppm) begin
                            out_bits  <= {1'b0, p_vec};
                            out_nbits <= 3'd4;
                        end else begin
                            out_bits  <= {2'b0, p_vec[3:1]};
                            out_nbits <= 3'd3;
                        end
                    end

                    mon_timer <= 5'd0;
                    mon_state <= ST_INIT_LOAD;
                end

                default: mon_state <= ST_INIT_LOAD;
            endcase
`endif
        end
    end

    // -------------------------------------------------------------------------
    // 3. Pure 3/4/5-to-10-bit Gearbox (312.5 MHz, no comma hunt on 3.2 ns path)
    // -------------------------------------------------------------------------
    reg [15:0] bit_buf;
    reg [4:0]  bit_cnt;

    reg [9:0]  word_wr_data;
    reg        word_wr_en;

    reg [15:0] comb_buf;
    reg [4:0]  comb_cnt;

    always @(posedge clk_312p5) begin
        if (rst_312p5) begin
            bit_buf      <= 16'd0;
            bit_cnt      <= 5'd0;
            word_wr_data <= 10'd0;
            word_wr_en   <= 1'b0;
        end else begin
            word_wr_en <= 1'b0;

            comb_buf = bit_buf;
            comb_cnt = bit_cnt;
            if (comb_cnt >= 5'd10) begin
                word_wr_data <= comb_buf[9:0];
                word_wr_en   <= 1'b1;
                comb_buf     = {10'd0, comb_buf[15:10]};
                comb_cnt     = comb_cnt - 5'd10;
            end

            // Append out_bits[out_nbits-1:0] at bit position comb_cnt (0..9)
            bit_buf <= comb_buf | ({11'd0, out_bits} << comb_cnt[3:0]);
            bit_cnt <= comb_cnt + {2'b00, out_nbits};
        end
    end

    // -------------------------------------------------------------------------
    // 4. Elastic Async FIFO (312.5 MHz -> 125 MHz, 32-entry Gray-coded)
    // -------------------------------------------------------------------------
    (* ram_style = "distributed" *) reg [9:0] fifo_mem [0:31];
    reg [5:0] wr_ptr_bin = 6'd0;
    reg [5:0] wr_ptr_gray = 6'd0;
    reg [5:0] rd_ptr_bin = 6'd0;
    reg [5:0] rd_ptr_gray = 6'd0;

    (* ASYNC_REG = "TRUE" *) reg [5:0] wr_gray_sync1 = 6'd0;
    (* ASYNC_REG = "TRUE" *) reg [5:0] wr_gray_sync2 = 6'd0;
    (* ASYNC_REG = "TRUE" *) reg [5:0] rd_gray_sync1 = 6'd0;
    (* ASYNC_REG = "TRUE" *) reg [5:0] rd_gray_sync2 = 6'd0;

    function [5:0] bin2gray(input [5:0] b);
        bin2gray = b ^ (b >> 1);
    endfunction

    wire [5:0] wr_next_bin  = wr_ptr_bin + 6'd1;
    wire [5:0] wr_next_gray = bin2gray(wr_next_bin);
    wire       fifo_full    = (wr_next_gray == {~rd_gray_sync2[5:4], rd_gray_sync2[3:0]});

    always @(posedge clk_312p5) begin
        if (rst_312p5) begin
            wr_ptr_bin    <= 6'd0;
            wr_ptr_gray   <= 6'd0;
            rd_gray_sync1 <= 6'd0;
            rd_gray_sync2 <= 6'd0;
        end else begin
            rd_gray_sync1 <= rd_ptr_gray;
            rd_gray_sync2 <= rd_gray_sync1;
            if (word_wr_en && !fifo_full) begin
                fifo_mem[wr_ptr_bin[4:0]] <= word_wr_data;
                wr_ptr_bin                <= wr_next_bin;
                wr_ptr_gray               <= wr_next_gray;
            end
        end
    end

    wire       fifo_empty   = (rd_ptr_gray == wr_gray_sync2);
    wire [5:0] rd_next_bin  = rd_ptr_bin + 6'd1;
    wire [5:0] rd_next_gray = bin2gray(rd_next_bin);

    // 10-bit Barrel-Shifter K28.5 Comma Aligner in 125 MHz (8.0 ns) domain
    reg [9:0]  fifo_word_q;
    reg        fifo_word_vld;
    reg [9:0]  prev_word_10b;
    reg        has_prev_word;
    reg [19:0] win20_r;
    reg        win20_vld;
    reg [3:0]  slip_sel;
    reg [2:0]  comma_streak;

    reg [9:0] k28_5_match;
    integer   k_idx;
    always @(*) begin
        for (k_idx = 0; k_idx < 10; k_idx = k_idx + 1) begin
            k28_5_match[k_idx] = (win20_r[k_idx +: 10] == K28_5_RD_NEG) ||
                                 (win20_r[k_idx +: 10] == K28_5_RD_POS);
        end
    end

    wire [9:0] aligned_word = win20_r[slip_sel +: 10];

    always @(posedge clk_125) begin
        if (rst_125) begin
            rd_ptr_bin       <= 6'd0;
            rd_ptr_gray      <= 6'd0;
            wr_gray_sync1    <= 6'd0;
            wr_gray_sync2    <= 6'd0;
            fifo_word_q      <= 10'd0;
            fifo_word_vld    <= 1'b0;
            prev_word_10b    <= 10'd0;
            has_prev_word    <= 1'b0;
            win20_r          <= 20'd0;
            win20_vld        <= 1'b0;
            slip_sel         <= 4'd0;
            comma_streak     <= 3'd0;
            rx_comma_aligned <= 1'b0;
            rx_code_125      <= 10'd0;
            rx_valid_125     <= 1'b0;
        end else begin
            wr_gray_sync1 <= wr_ptr_gray;
            wr_gray_sync2 <= wr_gray_sync1;

            if (!fifo_empty) begin
                fifo_word_q   <= fifo_mem[rd_ptr_bin[4:0]];
                fifo_word_vld <= 1'b1;
                rd_ptr_bin    <= rd_next_bin;
                rd_ptr_gray   <= rd_next_gray;
            end else begin
                fifo_word_vld <= 1'b0;
            end

            win20_vld <= 1'b0;
            if (fifo_word_vld) begin
                prev_word_10b <= fifo_word_q;
                if (!has_prev_word) begin
                    has_prev_word <= 1'b1;
                end else begin
                    win20_r   <= {fifo_word_q, prev_word_10b};
                    win20_vld <= 1'b1;
                end
            end

            rx_valid_125 <= 1'b0;
            if (win20_vld) begin
                if (!rx_comma_aligned) begin
                    if (k28_5_match[slip_sel]) begin
                        if (comma_streak == 3'd3) begin
                            rx_comma_aligned <= 1'b1;
                            rx_code_125      <= aligned_word;
                            rx_valid_125     <= 1'b1;
                        end else begin
                            comma_streak <= comma_streak + 3'd1;
                        end
                    end else if (k28_5_match != 10'd0) begin
                        comma_streak <= 3'd1;
                        if      (k28_5_match[0]) slip_sel <= 4'd0;
                        else if (k28_5_match[1]) slip_sel <= 4'd1;
                        else if (k28_5_match[2]) slip_sel <= 4'd2;
                        else if (k28_5_match[3]) slip_sel <= 4'd3;
                        else if (k28_5_match[4]) slip_sel <= 4'd4;
                        else if (k28_5_match[5]) slip_sel <= 4'd5;
                        else if (k28_5_match[6]) slip_sel <= 4'd6;
                        else if (k28_5_match[7]) slip_sel <= 4'd7;
                        else if (k28_5_match[8]) slip_sel <= 4'd8;
                        else                     slip_sel <= 4'd9;
                    end else begin
                        comma_streak <= 3'd0;
                    end
                end else begin
                    rx_code_125  <= aligned_word;
                    rx_valid_125 <= 1'b1;
                end
            end
        end
    end

    // -------------------------------------------------------------------------
    // 5. 10-bit PRBS-7 Checker in 125 MHz Domain (x^7 + x^6 + 1), Pipelined
    // -------------------------------------------------------------------------
    function [16:0] prbs7_step10(input [6:0] st);
        reg [6:0] s;
        reg [9:0] bits;
        reg       fb;
        integer   k;
        begin
            s = st;
            for (k = 0; k < 10; k = k + 1) begin
                fb      = s[6] ^ s[5];
                bits[k] = fb;
                s       = {s[5:0], fb};
            end
            prbs7_step10 = {bits, s};
        end
    endfunction

    reg [6:0] prbs_lfsr;
    reg [3:0] prbs_match_streak;
    reg       prbs_seeded;
    reg [9:0] prbs_diff_q;
    reg       prbs_err_vld_q;

    wire        rx_is_comma = (rx_code_125 == K28_5_RD_NEG) || (rx_code_125 == K28_5_RD_POS);
    wire [16:0] prbs_pred   = prbs7_step10(prbs_lfsr);
    wire [9:0]  prbs_diff   = rx_code_125 ^ prbs_pred[16:7];

    wire [3:0] diff_pop_q = {3'd0, prbs_diff_q[0]} + {3'd0, prbs_diff_q[1]} +
                            {3'd0, prbs_diff_q[2]} + {3'd0, prbs_diff_q[3]} +
                            {3'd0, prbs_diff_q[4]} + {3'd0, prbs_diff_q[5]} +
                            {3'd0, prbs_diff_q[6]} + {3'd0, prbs_diff_q[7]} +
                            {3'd0, prbs_diff_q[8]} + {3'd0, prbs_diff_q[9]};

    always @(posedge clk_125) begin
        if (rst_125) begin
            prbs_lfsr         <= 7'h7F;
            prbs_seeded       <= 1'b0;
            prbs_match_streak <= 4'd0;
            prbs_diff_q       <= 10'd0;
            prbs_err_vld_q    <= 1'b0;
            rx_prbs_locked    <= 1'b0;
            rx_prbs_err_cnt   <= 32'd0;
        end else begin
            prbs_err_vld_q <= 1'b0;
            if (prbs_err_vld_q)
                rx_prbs_err_cnt <= rx_prbs_err_cnt + {28'd0, diff_pop_q};

            if (rx_valid_125 && rx_comma_aligned) begin
                if (!prbs_seeded) begin
                    if (!rx_is_comma) begin
                        // Seed state from the last 7 bits of the first PRBS word (bit[9:3], newest in bit[9])
                        prbs_lfsr         <= {rx_code_125[3], rx_code_125[4], rx_code_125[5],
                                              rx_code_125[6], rx_code_125[7], rx_code_125[8], rx_code_125[9]};
                        prbs_seeded       <= 1'b1;
                        prbs_match_streak <= 4'd0;
                    end
                end else begin
                    prbs_lfsr <= prbs_pred[6:0];
                    if (prbs_diff == 10'd0) begin
                        if (prbs_match_streak == 4'd7)
                            rx_prbs_locked <= 1'b1;
                        else
                            prbs_match_streak <= prbs_match_streak + 4'd1;
                    end else begin
                        prbs_match_streak <= 4'd0;
                        prbs_diff_q       <= prbs_diff;
                        prbs_err_vld_q    <= 1'b1;
                    end
                end
            end
        end
    end

endmodule

// =============================================================================
// Top-Level Implementation Proof Wrapper for xc7a50t-ftg256-2
// Pins match PINMAP.md ETH assembly option:
//   fpga_clk_p/n : N11/N12 (Bank 14 MRCC, LVDS_25, DIFF_TERM=FALSE)
//   sgmii_rx_p/n : M16/N16 (Bank 14, LVDS_25, DIFF_TERM=FALSE)
//   sgmii_tx_p/n : L4/M4   (Bank 34, VCCO=2.5V, LVDS_25)
//   rst_n / LEDs : K13 / K12, L13, M15 (unused Bank 14 balls, LVCMOS33)
// =============================================================================
module sgmii_lvds_test (
    input  wire fpga_clk_p,
    input  wire fpga_clk_n,
    input  wire rst_n,
    input  wire sgmii_rx_p,
    input  wire sgmii_rx_n,
    output wire sgmii_tx_p,
    output wire sgmii_tx_n,
    output wire status_locked,
    output wire status_aligned,
    output wire status_err
);

    // -------------------------------------------------------------------------
    // 1. 100 MHz Reference Clock -> MMCM (1250 MHz VCO) -> 200 / 625(0/90) / 312.5(0/45) / 125 MHz
    // -------------------------------------------------------------------------
    wire fpga_clk_ibuf, fpga_clk_bufg;
    IBUFDS #(
        .DIFF_TERM  ("FALSE"),
        .IOSTANDARD ("LVDS_25")
    ) u_ibuf_clk (
        .I  (fpga_clk_p),
        .IB (fpga_clk_n),
        .O  (fpga_clk_ibuf)
    );
    BUFG u_bufg_in (.I(fpga_clk_ibuf), .O(fpga_clk_bufg));

    wire mmcm_fb, mmcm_locked;
    wire clk_200m_u, clk_625_0_u, clk_625_90_u, clk_312p5_u, clk_312p5_45_u, clk_125_u;
    wire clk_200m,   clk_625_0,   clk_625_90,   clk_312p5,   clk_312p5_45,   clk_125;

    MMCME2_ADV #(
        .BANDWIDTH         ("OPTIMIZED"),
        .CLKIN1_PERIOD     (10.000),
        .DIVCLK_DIVIDE     (1),
        .CLKFBOUT_MULT_F   (12.500),  // 100 MHz * 12.5 = 1250 MHz VCO (legal up to 1440 MHz on -2)
        .CLKFBOUT_PHASE    (0.0),
        .CLKOUT0_DIVIDE_F  (6.250),   // 200.00 MHz IDELAYCTRL REFCLK (exact Bank 14 sharing)
        .CLKOUT0_PHASE     (0.0),
        .CLKOUT1_DIVIDE    (2),       // 625.00 MHz DDR (0 deg)
        .CLKOUT1_PHASE     (0.0),
        .CLKOUT2_DIVIDE    (2),       // 625.00 MHz DDR (90 deg = +400 ps)
        .CLKOUT2_PHASE     (90.0),
        .CLKOUT3_DIVIDE    (4),       // 312.50 MHz CLKDIV (0 deg)
        .CLKOUT3_PHASE     (0.0),
        .CLKOUT4_DIVIDE    (4),       // 312.50 MHz CLKDIV (45 deg = +400 ps, aligned to clk_625_90)
        .CLKOUT4_PHASE     (45.0),
        .CLKOUT5_DIVIDE    (10),      // 125.00 MHz SGMII byte/word fabric clock
        .CLKOUT5_PHASE     (0.0),
        .COMPENSATION      ("INTERNAL"),
        .STARTUP_WAIT      ("FALSE")
    ) u_mmcm_sgmii (
        .CLKIN1       (fpga_clk_bufg),
        .CLKIN2       (1'b0),
        .CLKINSEL     (1'b1),
        .CLKFBIN      (mmcm_fb),
        .CLKFBOUT     (mmcm_fb),
        .CLKFBOUTB    (),
        .CLKOUT0      (clk_200m_u),
        .CLKOUT0B     (),
        .CLKOUT1      (clk_625_0_u),
        .CLKOUT1B     (),
        .CLKOUT2      (clk_625_90_u),
        .CLKOUT2B     (),
        .CLKOUT3      (clk_312p5_u),
        .CLKOUT3B     (),
        .CLKOUT4      (clk_312p5_45_u),
        .CLKOUT5      (clk_125_u),
        .CLKOUT6      (),
        .LOCKED       (mmcm_locked),
        .PWRDWN       (1'b0),
        .RST          (~rst_n),
        .DADDR        (7'd0),
        .DCLK         (1'b0),
        .DEN          (1'b0),
        .DI           (16'd0),
        .DWE          (1'b0),
        .DO           (),
        .DRDY         (),
        .PSCLK        (1'b0),
        .PSEN         (1'b0),
        .PSINCDEC     (1'b0),
        .PSDONE       (),
        .CLKFBSTOPPED (),
        .CLKINSTOPPED ()
    );

    BUFG u_bufg_200      (.I(clk_200m_u),     .O(clk_200m));
    BUFG u_bufg_625_0    (.I(clk_625_0_u),    .O(clk_625_0));
    BUFG u_bufg_625_90   (.I(clk_625_90_u),   .O(clk_625_90));
    BUFG u_bufg_312p5    (.I(clk_312p5_u),    .O(clk_312p5));
    BUFG u_bufg_312p5_45 (.I(clk_312p5_45_u), .O(clk_312p5_45));
    BUFG u_bufg_125      (.I(clk_125_u),      .O(clk_125));

    // Bank 14 IDELAYCTRL (REFCLK = 200 MHz)
    (* ASYNC_REG = "TRUE" *) reg [2:0] rst_200_sync = 3'b111;
    always @(posedge clk_200m or negedge mmcm_locked) begin
        if (!mmcm_locked)
            rst_200_sync <= 3'b111;
        else
            rst_200_sync <= {rst_200_sync[1:0], 1'b0};
    end

    wire idelayctrl_rdy;
    (* IODELAY_GROUP = "bank14_idelay_grp" *)
    IDELAYCTRL u_idelayctrl_b14 (
        .RDY    (idelayctrl_rdy),
        .REFCLK (clk_200m),
        .RST    (rst_200_sync[2])
    );

    wire rst_src = ~mmcm_locked | ~idelayctrl_rdy;
    (* ASYNC_REG = "TRUE" *) reg [2:0] rst_312_sync = 3'b111;
    (* ASYNC_REG = "TRUE" *) reg [2:0] rst_125_sync = 3'b111;
    always @(posedge clk_312p5 or posedge rst_src) begin
        if (rst_src) rst_312_sync <= 3'b111;
        else         rst_312_sync <= {rst_312_sync[1:0], 1'b0};
    end
    always @(posedge clk_125 or posedge rst_src) begin
        if (rst_src) rst_125_sync <= 3'b111;
        else         rst_125_sync <= {rst_125_sync[1:0], 1'b0};
    end
    wire rst_312p5 = rst_312_sync[2];
    wire rst_125   = rst_125_sync[2];

    // -------------------------------------------------------------------------
    // 2. XAPP523-Style SGMII RX (M16/N16 Bank 14)
    // -------------------------------------------------------------------------
    wire [9:0]  rx_code_125;
    wire        rx_valid_125;
    wire        rx_comma_aligned;
    wire        rx_prbs_locked;
    wire [31:0] rx_prbs_err_cnt;
    wire        phase_sel_mon;
    wire [31:0] phase_switch_cnt;

    sgmii_lvds_rx #(
        .DIFF_TERM_EN (1'b0)
    ) u_sgmii_rx (
        .sgmii_rx_p       (sgmii_rx_p),
        .sgmii_rx_n       (sgmii_rx_n),
        .clk_625_0        (clk_625_0),
        .clk_625_90       (clk_625_90),
        .clk_312p5        (clk_312p5),
        .clk_312p5_45     (clk_312p5_45),
        .clk_125          (clk_125),
        .rst_312p5        (rst_312p5),
        .rst_125          (rst_125),
        .rx_code_125      (rx_code_125),
        .rx_valid_125     (rx_valid_125),
        .rx_comma_aligned (rx_comma_aligned),
        .rx_prbs_locked   (rx_prbs_locked),
        .rx_prbs_err_cnt  (rx_prbs_err_cnt),
        .phase_sel_mon    (phase_sel_mon),
        .phase_switch_cnt (phase_switch_cnt)
    );

    // -------------------------------------------------------------------------
    // 3. 1.25 Gb/s SGMII TX (L4/M4 Bank 34): 10b @ 125 MHz -> 4b @ 312.5 MHz -> OSERDESE2
    // -------------------------------------------------------------------------
    reg [6:0]  tx_prbs;
    reg [9:0]  tx_word_125;
    reg [5:0]  tx_init_cnt;
    reg        tx_tog_125;
    reg [19:0] tx_pair_125;
    reg [9:0]  tx_prev_word;

    function [16:0] prbs7_step10_tx(input [6:0] st);
        reg [6:0] s;
        reg [9:0] bits;
        reg       fb;
        integer   k;
        begin
            s = st;
            for (k = 0; k < 10; k = k + 1) begin
                fb      = s[6] ^ s[5];
                bits[k] = fb;
                s       = {s[5:0], fb};
            end
            prbs7_step10_tx = {bits, s};
        end
    endfunction

    wire [16:0] tx_prbs_next = prbs7_step10_tx(tx_prbs);

    always @(posedge clk_125) begin
        if (rst_125) begin
            tx_prbs      <= 7'h7F;
            tx_word_125  <= 10'h17C;
            tx_init_cnt  <= 6'd0;
            tx_tog_125   <= 1'b0;
            tx_pair_125  <= 20'd0;
            tx_prev_word <= 10'h17C;
        end else begin
            if (tx_init_cnt != 6'h3F) begin
                tx_init_cnt <= tx_init_cnt + 6'd1;
                tx_word_125 <= tx_init_cnt[0] ? 10'h283 : 10'h17C;
            end else begin
                tx_prbs     <= tx_prbs_next[6:0];
                // Keep RX observable to prevent trimming
                tx_word_125 <= rx_valid_125 ? (tx_prbs_next[16:7] ^ rx_code_125) : tx_prbs_next[16:7];
            end

            tx_prev_word <= tx_word_125;
            if (!tx_tog_125) begin
                tx_pair_125 <= {tx_word_125, tx_prev_word};
                tx_tog_125  <= 1'b1;
            end else begin
                tx_tog_125  <= 1'b0;
            end
        end
    end

    // CDC 20-bit pair (2 words @ 62.5 MHz = 5 nibbles @ 312.5 MHz)
    (* ASYNC_REG = "TRUE" *) reg [2:0] tx_tog_sync = 3'd0;
    reg [19:0] tx_pair_312;
    reg [2:0]  tx_nib_idx;
    reg [3:0]  tx_nib;

    always @(posedge clk_312p5) begin
        if (rst_312p5) begin
            tx_tog_sync <= 3'd0;
            tx_pair_312 <= 20'd0;
            tx_nib_idx  <= 3'd0;
            tx_nib      <= 4'd0;
        end else begin
            tx_tog_sync <= {tx_tog_sync[1:0], tx_tog_125};
            if (tx_tog_sync[2] != tx_tog_sync[1]) begin
                tx_pair_312 <= tx_pair_125;
                tx_nib_idx  <= 3'd0;
                tx_nib      <= tx_pair_125[3:0];
            end else begin
                tx_nib_idx <= (tx_nib_idx == 3'd4) ? 3'd0 : (tx_nib_idx + 3'd1);
                case (tx_nib_idx)
                    3'd0:    tx_nib <= tx_pair_312[7:4];
                    3'd1:    tx_nib <= tx_pair_312[11:8];
                    3'd2:    tx_nib <= tx_pair_312[15:12];
                    3'd3:    tx_nib <= tx_pair_312[19:16];
                    default: tx_nib <= tx_pair_312[3:0];
                endcase
            end
        end
    end

    wire ser_tx_oq;
    OSERDESE2 #(
        .DATA_RATE_OQ  ("DDR"),
        .DATA_RATE_TQ  ("BUF"),
        .DATA_WIDTH    (4),
        .INIT_OQ       (1'b0),
        .INIT_TQ       (1'b0),
        .SERDES_MODE   ("MASTER"),
        .SRVAL_OQ      (1'b0),
        .SRVAL_TQ      (1'b0),
        .TBYTE_CTL     ("FALSE"),
        .TBYTE_SRC     ("FALSE"),
        .TRISTATE_WIDTH(1)
    ) u_oserdes_tx (
        .OFB       (),
        .OQ        (ser_tx_oq),
        .SHIFTOUT1 (),
        .SHIFTOUT2 (),
        .TBYTEOUT  (),
        .TFB       (),
        .TQ        (),
        .CLK       (clk_625_0),
        .CLKDIV    (clk_312p5),
        .D1        (tx_nib[0]),
        .D2        (tx_nib[1]),
        .D3        (tx_nib[2]),
        .D4        (tx_nib[3]),
        .D5        (1'b0),
        .D6        (1'b0),
        .D7        (1'b0),
        .D8        (1'b0),
        .OCE       (1'b1),
        .RST       (rst_312p5),
        .SHIFTIN1  (1'b0),
        .SHIFTIN2  (1'b0),
        .T1        (1'b0),
        .T2        (1'b0),
        .T3        (1'b0),
        .T4        (1'b0),
        .TBYTEIN   (1'b0),
        .TCE       (1'b0)
    );

    OBUFDS #(
        .IOSTANDARD ("LVDS_25")
    ) u_obuf_tx (
        .I  (ser_tx_oq),
        .O  (sgmii_tx_p),
        .OB (sgmii_tx_n)
    );

    assign status_locked  = mmcm_locked & idelayctrl_rdy & rx_prbs_locked;
    assign status_aligned = rx_comma_aligned ^ phase_sel_mon;
    assign status_err     = (rx_prbs_err_cnt != 32'd0) | (phase_switch_cnt[31]);

endmodule
`default_nettype wire
